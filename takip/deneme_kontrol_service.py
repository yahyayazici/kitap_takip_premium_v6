"""Etüt Hocası — Deneme Kontrol Merkezi.

Etüt hocasının sorumlu olduğu sınıfın deneme durumunu tek ekranda,
birkaç saniyede anlaşılır şekilde özetler. Var olan deneme/deneme
gelişim verilerinin üstüne kurulur; yeni bir deneme modeli veya soru
çözüm sistemi açmaz. LLM kullanılmaz — tüm sinyaller deterministiktir,
nihai pedagojik değerlendirme etüt hocasına bırakılır.

Üç ayrı kavram birbirine karıştırılmaz:
- Başarı sıralaması: son grup denemesindeki puana göre.
- Gelişim sıralaması: ilk→son grup deneme puan farkına göre.
- Öncelikli takip: çok sinyalli, deterministik uyarı listesi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count

from takip.deneme_gelisim_service import (
    talebe_calisma_karsilik_analizi,
    talebe_gelisim_metrikleri,
    talebe_grup_deneme_gelisimi,
    talebe_trend_sinifla,
)
from takip.deneme_service import BRANS_ETIKETLERI, DENEME_BRANS_DERS_MAP
from takip.models import (
    DenemeBransSonucu,
    DenemeSinavi,
    DenemeSonucu,
    EtutHocasi,
    SinifSube,
    Talebe,
)
from takip.ogretmen_not_service import ogretmen_sinif_ogrencileri
from takip.ogretmen_service import _demo_siniflar as _hoca_sinif_kartlari

_VARSAYILAN_ONCELIK_ESIK: dict[str, float] = {
    "puan_dususu": 15.0,
    "net_dususu": 3.0,
    "bos_orani_artis_esik": 0.10,
    "soru_yuksek_esik": 80,
    "ardisik_negatif": 2,
}

_GRUP_DERS_OK_ESIK = 0.5  # net — bunun altı "→ sabit" sayılır


def hoca_sinif_secenekleri(hoca: EtutHocasi):
    """Hocanın sorumlu olduğu gerçek sınıflar (kart listesi: id/etiket/ogrenci_sayisi)."""
    return _hoca_sinif_kartlari(hoca)


def _oncelik_esik() -> dict:
    esik = dict(_VARSAYILAN_ONCELIK_ESIK)
    esik.update(getattr(settings, "DENEME_ONCELIKLI_TAKIP", {}) or {})
    return esik


def _durum_ok(degisim: float | None) -> str:
    if degisim is None:
        return "yeni"
    if degisim > 0.5:
        return "yukseliyor"
    if degisim < -0.5:
        return "dusuyor"
    return "sabit"


def _talebe_dususe_sinyalleri(grup_seri: list[dict], esik: dict) -> tuple[list[str], bool]:
    """Puan/net düşüşü ve art arda negatif trend sinyalleri (madde 18)."""
    sinyaller: list[str] = []
    kritik = False
    if len(grup_seri) < 2:
        return sinyaller, kritik

    son2 = grup_seri[-2:]
    puan_degisim = son2[-1]["puan"] - son2[0]["puan"]
    if puan_degisim <= -esik["puan_dususu"]:
        sinyaller.append(f"Puan düşüşü: {puan_degisim:.2f}")
        kritik = True

    net_degisim = son2[-1]["net"] - son2[0]["net"]
    if net_degisim <= -esik["net_dususu"]:
        sinyaller.append(f"Net düşüşü: {net_degisim:.2f}")

    ardisik = int(esik["ardisik_negatif"])
    if len(grup_seri) >= ardisik + 1:
        son_n = grup_seri[-(ardisik + 1):]
        farklar = [son_n[i + 1]["puan"] - son_n[i]["puan"] for i in range(len(son_n) - 1)]
        if farklar and all(f < 0 for f in farklar):
            sinyaller.append(f"Art arda {ardisik} denemede düşüş")
            kritik = True

    return sinyaller, kritik


def _talebe_bos_yanlis_sinyalleri(grup_seri: list[dict], esik: dict) -> list[str]:
    """Ders bazında boş bırakma oranı artışı — yanlıştan ayrı bir sinyal (madde 21)."""
    if len(grup_seri) < 2:
        return []
    mesajlar = []
    for kod, ders_ad in DENEME_BRANS_DERS_MAP.items():
        oranlar = []
        for nokta in grup_seri[-3:]:
            sonuc: DenemeSonucu = nokta["sonuc"]
            brans = next((b for b in sonuc.brans_satirlari.all() if b.brans == kod), None)
            if not brans:
                continue
            toplam = int(brans.dogru or 0) + int(brans.yanlis or 0) + int(brans.bos or 0)
            if toplam <= 0:
                continue
            oranlar.append(int(brans.bos or 0) / toplam)
        if len(oranlar) >= 2 and (oranlar[-1] - oranlar[0]) >= esik["bos_orani_artis_esik"]:
            mesajlar.append(
                f"{BRANS_ETIKETLERI[kod]}te boş bırakma oranı son denemelerde artıyor."
            )
    return mesajlar


def _talebe_calisma_sinyalleri(calisma_karsilik: list[dict], esik: dict) -> list[str]:
    mesajlar = []
    for c in calisma_karsilik:
        if c["durum"] == "uyari" and c["son_30_gun_soru"] >= esik["soru_yuksek_esik"]:
            mesajlar.append(
                f"{c['etiket']}: yüksek çalışmaya rağmen ({c['son_30_gun_soru']} soru) "
                "net artmıyor."
            )
    return mesajlar


@dataclass
class OgrenciDenemeSatiri:
    talebe: Talebe
    grup_seri: list = field(default_factory=list)
    son_puan: float | None = None
    son_net: float | None = None
    onceki_puan: float | None = None
    degisim: float | None = None
    durum_ok: str = "yeni"
    trend: dict | None = None
    metrikler: dict | None = None
    calisma_karsilik: list = field(default_factory=list)
    sinyaller: list = field(default_factory=list)
    kritik: bool = False

    @property
    def takip_gerekli(self) -> bool:
        return bool(self.sinyaller)


def _ogrenci_satiri(talebe: Talebe, esik: dict) -> OgrenciDenemeSatiri:
    grup_seri = talebe_grup_deneme_gelisimi(talebe)
    metrikler = talebe_gelisim_metrikleri(grup_seri)
    trend = talebe_trend_sinifla(grup_seri)
    calisma = talebe_calisma_karsilik_analizi(talebe, grup_seri)

    son_puan = grup_seri[-1]["puan"] if grup_seri else None
    son_net = grup_seri[-1]["net"] if grup_seri else None
    onceki_puan = grup_seri[-2]["puan"] if len(grup_seri) >= 2 else None
    degisim = (
        round(son_puan - onceki_puan, 2)
        if son_puan is not None and onceki_puan is not None
        else None
    )

    sinyaller, kritik = _talebe_dususe_sinyalleri(grup_seri, esik)
    sinyaller += _talebe_bos_yanlis_sinyalleri(grup_seri, esik)
    sinyaller += _talebe_calisma_sinyalleri(calisma, esik)

    return OgrenciDenemeSatiri(
        talebe=talebe,
        grup_seri=grup_seri,
        son_puan=son_puan,
        son_net=son_net,
        onceki_puan=onceki_puan,
        degisim=degisim,
        durum_ok=_durum_ok(degisim),
        trend=trend,
        metrikler=metrikler,
        calisma_karsilik=calisma,
        sinyaller=sinyaller,
        kritik=kritik,
    )


def _sinif_denemeleri(sinif: SinifSube) -> list[DenemeSinavi]:
    """Bu sınıfı kapsayan grup denemeleri (hedefli veya seviye geneli), kronolojik."""
    hedefli = DenemeSinavi.objects.filter(
        tur=DenemeSinavi.Tur.GRUP,
        durum=DenemeSinavi.Durum.AKTIF,
        hedef_sinif_subeler=sinif,
    )
    genel = DenemeSinavi.objects.filter(
        tur=DenemeSinavi.Tur.GRUP,
        durum=DenemeSinavi.Durum.AKTIF,
        sinif_seviyesi=sinif.sinif,
        hedef_sinif_subeler__isnull=True,
    )
    denemeler = {d.pk: d for d in hedefli}
    denemeler.update({d.pk: d for d in genel})
    return sorted(denemeler.values(), key=lambda d: (d.sinav_tarihi, d.id))


def _sinif_deneme_ortalamasi(deneme: DenemeSinavi, sinif: SinifSube) -> tuple[Decimal | None, int]:
    agg = DenemeSonucu.objects.filter(deneme=deneme, talebe__sinif_sube=sinif).aggregate(
        ort=Avg("puan"), n=Count("id")
    )
    ort = agg["ort"]
    return (round(Decimal(ort), 2) if ort is not None else None), int(agg["n"] or 0)


def sinif_grup_analizi(sinif: SinifSube) -> dict:
    """Madde 20: deneme bazlı sınıf ortalaması + ders bazlı grup gelişim oku."""
    denemeler = _sinif_denemeleri(sinif)
    seri = []
    for deneme in denemeler:
        ort, n = _sinif_deneme_ortalamasi(deneme, sinif)
        if ort is None:
            continue
        seri.append(
            {
                "deneme_id": deneme.pk,
                "sira_no": deneme.sira_no,
                "ad": deneme.ad,
                "tarih": deneme.sinav_tarihi,
                "ortalama": float(ort),
                "ogrenci_sayisi": n,
            }
        )
    if seri:
        max_ort = max(nokta["ortalama"] for nokta in seri) or 1
        for nokta in seri:
            nokta["ortalama_yuzde"] = round(nokta["ortalama"] / max_ort * 100, 1)

    genel_degisim = None
    if len(seri) >= 2:
        genel_degisim = round(seri[-1]["ortalama"] - seri[0]["ortalama"], 2)

    ders_okları = []
    if len(denemeler) >= 2:
        son_iki = denemeler[-2:]
        ort_onceki = {
            r["brans"]: r["ort_net"]
            for r in DenemeBransSonucu.objects.filter(
                sonuc__deneme=son_iki[0], sonuc__talebe__sinif_sube=sinif
            )
            .values("brans")
            .annotate(ort_net=Avg("net"))
        }
        ort_son = {
            r["brans"]: r["ort_net"]
            for r in DenemeBransSonucu.objects.filter(
                sonuc__deneme=son_iki[1], sonuc__talebe__sinif_sube=sinif
            )
            .values("brans")
            .annotate(ort_net=Avg("net"))
        }
        for kod, etiket in BRANS_ETIKETLERI.items():
            onceki = ort_onceki.get(kod)
            son = ort_son.get(kod)
            if onceki is None or son is None:
                continue
            fark = float(son) - float(onceki)
            if fark > _GRUP_DERS_OK_ESIK:
                ok = "yukseliyor"
            elif fark < -_GRUP_DERS_OK_ESIK:
                ok = "dusuyor"
            else:
                ok = "sabit"
            ders_okları.append({"kod": kod, "etiket": etiket, "fark": round(fark, 2), "ok": ok})

    return {
        "seri": seri,
        "genel_degisim": genel_degisim,
        "ders_okları": ders_okları,
    }


def sinif_kontrol_verisi_hesapla(ogrenciler: list[Talebe], sinif: SinifSube) -> dict:
    """Üst özet + üç sıralama + grup analizi — verilen öğrenci listesi üzerinden.

    Etüt hocası ekranı (hoca'ya sorumlu öğrenciler) ve yönetici özeti
    (sınıftaki tüm öğrenciler) aynı hesaplamayı kullanır; kapsam
    (hangi öğrenciler) çağıran tarafından belirlenir.
    """
    esik = _oncelik_esik()
    satirlar = [_ogrenci_satiri(t, esik) for t in ogrenciler]

    yukselen = sum(1 for s in satirlar if s.durum_ok == "yukseliyor")
    dusen = sum(1 for s in satirlar if s.durum_ok == "dusuyor")
    sabit = sum(1 for s in satirlar if s.durum_ok == "sabit")
    takip_gereken = sum(1 for s in satirlar if s.takip_gerekli)

    denemeler = _sinif_denemeleri(sinif)
    son_deneme = denemeler[-1] if denemeler else None
    onceki_deneme = denemeler[-2] if len(denemeler) >= 2 else None
    son_ortalama, _ = _sinif_deneme_ortalamasi(son_deneme, sinif) if son_deneme else (None, 0)
    onceki_ortalama, _ = (
        _sinif_deneme_ortalamasi(onceki_deneme, sinif) if onceki_deneme else (None, 0)
    )
    ort_degisim = (
        round(son_ortalama - onceki_ortalama, 2)
        if son_ortalama is not None and onceki_ortalama is not None
        else None
    )

    basari_siralamasi = sorted(
        (s for s in satirlar if s.son_puan is not None),
        key=lambda s: (-s.son_puan, s.talebe.ad_soyad or ""),
    )
    gelisim_siralamasi = sorted(
        (s for s in satirlar if s.metrikler),
        key=lambda s: (-s.metrikler["genel_degisim"], s.talebe.ad_soyad or ""),
    )
    oncelikli_takip = sorted(
        (s for s in satirlar if s.takip_gerekli),
        key=lambda s: (not s.kritik, s.talebe.ad_soyad or ""),
    )

    return {
        "sinif": sinif,
        "ogrenci_sayisi": len(ogrenciler),
        "satirlar": satirlar,
        "son_deneme": son_deneme,
        "sinif_ortalamasi": son_ortalama,
        "onceki_ortalama": onceki_ortalama,
        "ortalama_degisim": ort_degisim,
        "yukselen": yukselen,
        "dusen": dusen,
        "sabit": sabit,
        "takip_gereken": takip_gereken,
        "basari_siralamasi": basari_siralamasi,
        "gelisim_siralamasi": gelisim_siralamasi,
        "oncelikli_takip": oncelikli_takip,
        "grup_analizi": sinif_grup_analizi(sinif),
    }


def sinif_deneme_kontrol_verisi(hoca: EtutHocasi, sinif: SinifSube) -> dict:
    """Etüt hocası ekranı — hocanın sorumlu olduğu öğrencilerle sınırlı."""
    ogrenciler = ogretmen_sinif_ogrencileri(hoca, sinif)
    return sinif_kontrol_verisi_hesapla(ogrenciler, sinif)


def satirlari_sirala(satirlar: list[OgrenciDenemeSatiri], sirala: str) -> list[OgrenciDenemeSatiri]:
    if sirala == "gelisim":
        return sorted(
            satirlar,
            key=lambda s: (
                s.metrikler["genel_degisim"] if s.metrikler else float("-inf")
            ),
            reverse=True,
        )
    if sirala == "isim":
        return sorted(satirlar, key=lambda s: s.talebe.ad_soyad or "")
    return sorted(
        satirlar,
        key=lambda s: (s.son_puan if s.son_puan is not None else -1),
        reverse=True,
    )
