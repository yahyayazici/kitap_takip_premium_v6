"""Etüt Hocası — Deneme Kontrol Merkezi.

Etüt hocasının sorumlu olduğu sınıfın deneme durumunu tek ekranda,
birkaç saniyede anlaşılır şekilde özetler. Var olan deneme sonuçlarının
üstüne kurulur. Soru karnesi (2. sayfa) ayrıca tutulur; sınıfta aynı
soruyu yüzde 33 ve üzeri yanlış yapanlar burada listelenir. LLM
kullanılmaz — tüm sinyaller deterministiktir, nihai pedagojik
değerlendirme etüt hocasına bırakılır.

Üç ayrı kavram birbirine karıştırılmaz:
- Başarı sıralaması: son grup denemesindeki puana göre.
- Gelişim sıralaması: ilk→son grup deneme puan farkına göre.
- Öncelikli takip: çok sinyalli, deterministik uyarı listesi.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Avg, Count

from takip.deneme_gelisim_service import (
    talebe_calisma_karsilik_analizi,
    talebe_gelisim_metrikleri,
    talebe_grup_deneme_gelisimi,
    talebe_trend_sinifla,
)
from takip.deneme_models import DenemeSoruSonucu
from takip.deneme_service import (
    BRANS_ETIKETLERI,
    DENEME_BRANS_DERS_MAP,
    deneme_sira_haritasi_talebeler,
)
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


def _sinifi_var(hoca: EtutHocasi) -> bool:
    return hoca.sorumlu_sinif_subeler.filter(aktif=True).exists()


def deneme_kontrol_hocalari(user) -> list[EtutHocasi]:
    """Sorumlu sınıfı olan etüt mesulü, yoksa personel panelindeki etüt hocaları.

    Branş öğretmeni girmez. Etüt mesulü yalnız kendi sınıfını görür.
    Eğitim mesulü ve idare, etüt kontrolde baktığı hocaların sınıflarını görür.
    """
    if not getattr(user, "is_authenticated", False):
        return []

    from takip.ogretmen_service import ogretmen_paneli_kullanicisi_mi

    if ogretmen_paneli_kullanicisi_mi(user):
        return []

    from takip.user_helpers import etut_mesul_for_user

    kendi = etut_mesul_for_user(user)
    if kendi:
        return [kendi] if _sinifi_var(kendi) else []

    from takip.panel_permissions import deneme_modulu_erisimi_var

    if not deneme_modulu_erisimi_var(user) and not user.is_staff:
        return []

    from takip.etut_kontrol_service import kullanici_etut_hocalari
    from takip.etut_zimmet_service import etut_mesul_queryset

    adaylar = [h for h in kullanici_etut_hocalari(user) if h.aktif and _sinifi_var(h)]
    if not adaylar:
        adaylar = [h for h in etut_mesul_queryset() if _sinifi_var(h)]

    gorulen: set[int] = set()
    sonuc: list[EtutHocasi] = []
    for hoca in adaylar:
        if hoca.pk in gorulen:
            continue
        gorulen.add(hoca.pk)
        sonuc.append(hoca)
    return sonuc


def deneme_kontrol_erisimi_var(user) -> bool:
    """Sorumlu sınıfı olan etüt / sınıf mesulü, ya da o sınıfları gören personel."""
    return bool(deneme_kontrol_hocalari(user))


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


def _talebe_idleri(ogrenciler: list[Talebe]) -> list[int]:
    return [talebe.id for talebe in ogrenciler if getattr(talebe, "id", None)]


def _goster_sira_bagla(denemeler: list[DenemeSinavi], talebe_ids: list[int]) -> None:
    """Kurum sıra numarasını ezmeden, bu talebelerin kendi sırasını yazar."""
    if not denemeler:
        return
    harita = deneme_sira_haritasi_talebeler(talebe_ids)
    for deneme in denemeler:
        deneme.goster_sira = harita.get(deneme.pk, deneme.sira_no)


def _her_subenin_girdigi(
    denemeler: list[DenemeSinavi],
    ogrenciler: list[Talebe],
    siniflar: list[SinifSube],
) -> list[DenemeSinavi]:
    """Tümü özetinde yalnız her şubeden en az bir sonucu olan denemeler kalır.

    5-A'nın tek başına girdiği sonraki deneme, 5-B ile ortak olan son
    denemenin yerine geçmez. Hiç ortak deneme yoksa kart boş kalmasın diye
    sonucu olan listeye dönülür.
    """
    if len(siniflar) <= 1 or not denemeler:
        return denemeler
    sinif_ids = {sinif.id for sinif in siniflar}
    beklenen = {
        talebe.sinif_sube_id
        for talebe in ogrenciler
        if getattr(talebe, "sinif_sube_id", None) in sinif_ids
    }
    if len(beklenen) <= 1:
        return denemeler
    kapsanan: dict[int, set[int]] = {}
    ciftler = (
        DenemeSonucu.objects.filter(
            deneme_id__in=[deneme.pk for deneme in denemeler],
            talebe_id__in=_talebe_idleri(ogrenciler),
        )
        .values_list("deneme_id", "talebe__sinif_sube_id")
        .distinct()
    )
    for deneme_id, sinif_id in ciftler:
        if sinif_id in beklenen:
            kapsanan.setdefault(deneme_id, set()).add(sinif_id)
    ortak = [deneme for deneme in denemeler if beklenen <= kapsanan.get(deneme.pk, set())]
    return ortak or denemeler


def _ogrencilerin_denemeleri(
    ogrenciler: list[Talebe], siniflar: list[SinifSube]
) -> list[DenemeSinavi]:
    """Aktif talebelerin sonucu olan grup denemeleri, tarihe göre.

    Hedefi bu seviyeye yazılmış ama bu talebelerin girmediği deneme
    son deneme sayılmaz. ``sira_no`` değişmez.
    """
    ids = _talebe_idleri(ogrenciler)
    if not ids:
        return []
    denemeler = list(
        DenemeSinavi.objects.filter(
            tur=DenemeSinavi.Tur.GRUP,
            durum=DenemeSinavi.Durum.AKTIF,
            sonuclar__talebe_id__in=ids,
        )
        .distinct()
        .order_by("sinav_tarihi", "id")
    )
    denemeler = _her_subenin_girdigi(denemeler, ogrenciler, siniflar)
    _goster_sira_bagla(denemeler, ids)
    return denemeler


def _siniflar_deneme_ortalamasi(
    deneme: DenemeSinavi,
    siniflar: list[SinifSube],
    talebe_ids: list[int] | None = None,
) -> tuple[Decimal | None, int]:
    qs = DenemeSonucu.objects.filter(deneme=deneme)
    if talebe_ids is not None:
        if not talebe_ids:
            return None, 0
        qs = qs.filter(talebe_id__in=talebe_ids)
    else:
        qs = qs.filter(talebe__sinif_sube__in=siniflar)
    agg = qs.aggregate(ort=Avg("puan"), n=Count("id"))
    ort = agg["ort"]
    return (round(Decimal(ort), 2) if ort is not None else None), int(agg["n"] or 0)


def siniflar_grup_analizi(
    siniflar: list[SinifSube],
    ogrenciler: list[Talebe] | None = None,
    denemeler: list[DenemeSinavi] | None = None,
) -> dict:
    """Deneme bazlı ortak ortalama. Birden fazla şube varsa hepsinin sonucu birlikte sayılır."""
    if ogrenciler is None:
        ogrenciler = list(
            Talebe.objects.filter(
                sinif_sube__in=siniflar, durum=Talebe.Durum.AKTIF
            ).order_by("ad_soyad")
        )
    talebe_ids = _talebe_idleri(ogrenciler)
    if denemeler is None:
        denemeler = _ogrencilerin_denemeleri(ogrenciler, siniflar)
    seri = []
    for deneme in denemeler:
        ort, n = _siniflar_deneme_ortalamasi(deneme, siniflar, talebe_ids)
        if ort is None:
            continue
        seri.append(
            {
                "deneme_id": deneme.pk,
                "sira_no": deneme.sira_no,
                "goster_sira": getattr(deneme, "goster_sira", None) or deneme.sira_no,
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
    if len(denemeler) >= 2 and talebe_ids:
        son_iki = denemeler[-2:]
        ort_onceki = {
            r["brans"]: r["ort_net"]
            for r in DenemeBransSonucu.objects.filter(
                sonuc__deneme=son_iki[0], sonuc__talebe_id__in=talebe_ids
            )
            .values("brans")
            .annotate(ort_net=Avg("net"))
        }
        ort_son = {
            r["brans"]: r["ort_net"]
            for r in DenemeBransSonucu.objects.filter(
                sonuc__deneme=son_iki[1], sonuc__talebe_id__in=talebe_ids
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


def sinif_grup_analizi(sinif: SinifSube) -> dict:
    return siniflar_grup_analizi([sinif])


def sinif_kontrol_verisi_hesapla(
    ogrenciler: list[Talebe],
    sinif: SinifSube,
    siniflar: list[SinifSube] | None = None,
) -> dict:
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

    kapsam = siniflar or [sinif]
    talebe_ids = _talebe_idleri(ogrenciler)
    denemeler = _ogrencilerin_denemeleri(ogrenciler, kapsam)
    son_deneme = denemeler[-1] if denemeler else None
    onceki_deneme = denemeler[-2] if len(denemeler) >= 2 else None
    son_ortalama, _ = (
        _siniflar_deneme_ortalamasi(son_deneme, kapsam, talebe_ids) if son_deneme else (None, 0)
    )
    onceki_ortalama, _ = (
        _siniflar_deneme_ortalamasi(onceki_deneme, kapsam, talebe_ids)
        if onceki_deneme
        else (None, 0)
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
        "grup_analizi": siniflar_grup_analizi(kapsam, ogrenciler, denemeler),
    }


def _yukselis_sirala(satirlar: list[OgrenciDenemeSatiri]) -> list[OgrenciDenemeSatiri]:
    """İlk denemeden son denemeye puan artışı. Artışı olmayanlar listenin sonunda."""

    def anahtar(satir: OgrenciDenemeSatiri):
        degisim = None
        if satir.metrikler:
            degisim = satir.metrikler.get("genel_degisim")
        return (
            degisim is None,
            -(degisim if degisim is not None else 0),
            satir.talebe.ad_soyad or "",
        )

    return sorted(satirlar, key=anahtar)


def kazanim_ortalamalari(talebe_ids: list[int]) -> list[dict]:
    """Yüklenen denemelerden biriken kazanımlar.

    Konu bir kez görününce listede kalır. Aynı konu sonraki denemede
    tekrar gelirse, deneme deneme sınıf (veya talebe) ortalaması alınır.
    Sayı ve ortalama yalnız listede duran grup denemelerinden gelir;
    silinip arşive alınan deneme sayıya katılmaz.
    """
    if not talebe_ids:
        return []

    from takip.deneme_models import DenemeKazanimSonucu

    kayitlar = (
        DenemeKazanimSonucu.objects.filter(
            talebe_id__in=talebe_ids,
            deneme__tur=DenemeSinavi.Tur.GRUP,
            deneme__durum=DenemeSinavi.Durum.AKTIF,
        )
        .select_related("deneme")
        .order_by("deneme__sinav_tarihi", "deneme_id", "id")
    )

    kovalar: dict[tuple[str, str], dict] = {}
    for kayit in kayitlar:
        anahtar = (kayit.ders_key, kayit.konu_key)
        kova = kovalar.get(anahtar)
        if kova is None:
            kova = {
                "ders_ad": kayit.ders_ad,
                "konu_ad": kayit.konu_ad,
                "ders_key": kayit.ders_key,
                "konu_key": kayit.konu_key,
                "ilk": (kayit.deneme.sinav_tarihi, kayit.deneme_id),
                "sira": len(kovalar),
                "sinavlar": {},
            }
            kovalar[anahtar] = kova
        sinav = kova["sinavlar"].setdefault(
            kayit.deneme_id,
            {"tarih": kayit.deneme.sinav_tarihi, "yuzdeler": []},
        )
        if kayit.yuzde is not None:
            sinav["yuzdeler"].append(Decimal(kayit.yuzde))

    ozetler = []
    for kova in kovalar.values():
        sinav_ortalamalari = []
        son = None
        for sinav in kova["sinavlar"].values():
            if not sinav["yuzdeler"]:
                continue
            ort = sum(sinav["yuzdeler"], Decimal("0")) / Decimal(len(sinav["yuzdeler"]))
            sinav_ortalamalari.append(ort)
            if son is None or sinav["tarih"] >= son[0]:
                son = (sinav["tarih"], ort)
        ortalama = None
        if sinav_ortalamalari:
            ortalama = (
                sum(sinav_ortalamalari, Decimal("0")) / Decimal(len(sinav_ortalamalari))
            ).quantize(Decimal("0.01"))
        ozetler.append(
            {
                "ders_ad": kova["ders_ad"],
                "konu_ad": kova["konu_ad"],
                "ders_key": kova["ders_key"],
                "konu_key": kova["konu_key"],
                "ortalama": ortalama,
                "deneme_sayisi": len(sinav_ortalamalari),
                "son_yuzde": son[1].quantize(Decimal("0.01")) if son else None,
                "ilk": kova["ilk"],
                "sira": kova["sira"],
            }
        )

    ozetler.sort(key=lambda o: o["sira"])
    return ozetler


def kazanimlari_derse_gore(ozetler: list[dict]) -> list[dict]:
    gruplar: list[dict] = []
    indeks: dict[str, dict] = {}
    for ozet in ozetler:
        grup = indeks.get(ozet["ders_key"])
        if grup is None:
            grup = {"ders_ad": ozet["ders_ad"], "ders_key": ozet["ders_key"], "konular": []}
            indeks[ozet["ders_key"]] = grup
            gruplar.append(grup)
        grup["konular"].append(ozet)
    return gruplar


def _bos_nokta() -> dict:
    return {"deneme": None, "satirlar": [], "dersler": [], "karne_sayisi": 0}


_NOKTA_DERS_SIRASI = (
    "turkce",
    "paragraf",
    "matematik",
    "fen",
    "sosyal",
    "din",
    "ingiliz",
)


def _nokta_ders_sirasi(ad: str) -> tuple[int, str]:
    ham = (ad or "").casefold()
    for eski, yeni in (
        ("ı", "i"),
        ("i̇", "i"),
        ("ş", "s"),
        ("ğ", "g"),
        ("ü", "u"),
        ("ö", "o"),
        ("ç", "c"),
    ):
        ham = ham.replace(eski, yeni)
    for sira, kok in enumerate(_NOKTA_DERS_SIRASI):
        if kok in ham:
            return (sira, ad or "")
    return (len(_NOKTA_DERS_SIRASI), ad or "")


def _nokta_dersleri(satirlar: list[dict]) -> list[dict]:
    gruplar: list[dict] = []
    indeks: dict[str, dict] = {}
    for satir in satirlar:
        ad = satir.get("ders_ad") or "Diğer"
        grup = indeks.get(ad)
        if grup is None:
            grup = {"ad": ad, "satirlar": []}
            indeks[ad] = grup
            gruplar.append(grup)
        grup["satirlar"].append(satir)
    gruplar.sort(key=lambda grup: _nokta_ders_sirasi(grup["ad"]))
    return gruplar


def _nokta_yuzde(yanlis: int, katilim: int) -> int | None:
    """Ham oran 33'ün altındaysa gizle; görünen yüzde yuvarlanır."""
    if katilim <= 0:
        return None
    oran = (Decimal(yanlis) * Decimal(100)) / Decimal(katilim)
    if oran < 33:
        return None
    return int(oran.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def sinif_nokta_atisi(talebe_ids: list[int]) -> dict:
    """Son aktif grup denemesinde sınıfın yüzde 33+ yanlış yaptığı sorular."""
    if not talebe_ids:
        return _bos_nokta()
    deneme = (
        DenemeSinavi.objects.filter(
            tur=DenemeSinavi.Tur.GRUP,
            durum=DenemeSinavi.Durum.AKTIF,
            soru_sonuclari__talebe_id__in=talebe_ids,
        )
        .distinct()
        .order_by("-sinav_tarihi", "-id")
        .first()
    )
    if deneme is None:
        return _bos_nokta()

    kayitlar = DenemeSoruSonucu.objects.filter(
        deneme=deneme,
        talebe_id__in=talebe_ids,
    ).only("talebe_id", "ders_ad", "ders_key", "soru_no", "konu_ad", "sonuc", "sira")
    karne_sayisi = kayitlar.values("talebe_id").distinct().count()
    kovalar: dict[tuple, dict] = {}
    for kayit in kayitlar:
        anahtar = (kayit.ders_key, kayit.soru_no)
        kova = kovalar.get(anahtar)
        if kova is None:
            kova = {
                "ders_ad": kayit.ders_ad,
                "soru_no": kayit.soru_no,
                "sira": kayit.sira,
                "yanlis": 0,
                "katilim": 0,
                "konular": Counter(),
            }
            kovalar[anahtar] = kova
        kova["katilim"] += 1
        kova["sira"] = min(kova["sira"], kayit.sira)
        if kayit.sonuc == DenemeSoruSonucu.Sonuc.YANLIS:
            kova["yanlis"] += 1
        if kayit.konu_ad:
            kova["konular"][kayit.konu_ad] += 1

    satirlar = []
    for kova in kovalar.values():
        yuzde = _nokta_yuzde(kova["yanlis"], kova["katilim"])
        if yuzde is None:
            continue
        konu = kova["konular"].most_common(1)[0][0] if kova["konular"] else ""
        satirlar.append(
            {
                "cumle": f"{kova['ders_ad']} {kova['soru_no']}. soru %{yuzde} yanlış yapmış",
                "konu": konu,
                "yuzde": yuzde,
                "yanlis": kova["yanlis"],
                "katilim": kova["katilim"],
                "sira": kova["sira"],
                "soru_no": kova["soru_no"],
                "ders_ad": kova["ders_ad"],
            }
        )
    satirlar.sort(key=lambda s: (-s["yuzde"], s["sira"], s["soru_no"], s["ders_ad"]))
    return {
        "deneme": deneme,
        "satirlar": satirlar,
        "dersler": _nokta_dersleri(satirlar),
        "karne_sayisi": karne_sayisi,
    }


def _kontrol_verisini_tamamla(veri: dict, ogrenciler: list[Talebe]) -> dict:
    veri["yukselis_satirlari"] = _yukselis_sirala(veri["satirlar"])
    kazanimlar = kazanim_ortalamalari([t.id for t in ogrenciler])
    veri["kazanimlar"] = kazanimlar
    veri["kazanim_gruplari"] = kazanimlari_derse_gore(kazanimlar)
    veri["nokta"] = sinif_nokta_atisi([t.id for t in ogrenciler])
    return veri


def sinif_deneme_kontrol_verisi(hoca: EtutHocasi, sinif: SinifSube) -> dict:
    """Etüt hocası ekranı — hocanın sorumlu olduğu öğrencilerle sınırlı."""
    ogrenciler = ogretmen_sinif_ogrencileri(hoca, sinif)
    veri = sinif_kontrol_verisi_hesapla(ogrenciler, sinif)
    return _kontrol_verisini_tamamla(veri, ogrenciler)


def siniflar_deneme_kontrol_verisi(ogrenciler: list[Talebe], siniflar: list[SinifSube]) -> dict:
    """Aynı seviyedeki şubelerin ortak deneme özeti."""
    veri = sinif_kontrol_verisi_hesapla(ogrenciler, siniflar[0], siniflar)
    return _kontrol_verisini_tamamla(veri, ogrenciler)


def seviye_etiketi(seviye: str) -> str:
    ham = (seviye or "").strip()
    if ham.isdigit():
        return f"{ham}. Sınıf"
    return ham


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
