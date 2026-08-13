"""KTT akıllı takip — hâkimiyet, trend, müdahale ve eksik kapatma motoru."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db.models import Avg
from django.utils.timezone import localdate

from takip.konu_destek_models import KonuKatalogu, TalebeKonuEksigi
from takip.konu_destek_service import ders_adindan_brans, talebe_sinif_seviyesi
from takip.ktt_akilli_models import KttEtutMudahale, KttEslestirmeEsik, KonuEslestirmeInceleme
from takip.ktt_konu_normalize_service import esikler, ktt_konu_eslestir
from takip.models import EtutHocasi, KttSinav, KttSonucu, Talebe

SEVIYE_ESIKLERI = {
    "guclu": 85,
    "iyi": 70,
    "gelistirilmeli": 55,
}

SEVIYE_ETIKET = {
    "guclu": ("Güçlü", "success"),
    "iyi": ("İyi", "info"),
    "gelistirilmeli": ("Geliştirilmeli", "warn"),
    "oncelikli": ("Öncelikli Eksik", "danger"),
}

ONCELIK_ETIKET = {
    "oncelikli": ("Öncelikli", "danger"),
    "takip": ("Takip", "warn"),
    "iyi": ("İyi", "success"),
}

TREND_ETIKET = {
    "yukseliyor": ("↗ Belirgin gelişim gösteriyor", "success"),
    "dengeli": ("→ Dengeli seyrediyor", "info"),
    "dusuyor": ("↘ Son dönemde düşüş var", "warn"),
}


@dataclass(frozen=True)
class KonuHakimiyet:
    konu_id: int
    konu_ad: str
    brans: str
    brans_etiket: str
    ortalama_puan: int
    seviye_kodu: str
    seviye_etiket: str
    seviye_sinif: str
    trend_kodu: str
    trend_etiket: str
    trend_sinif: str
    ktt_sayisi: int
    puan_gecmisi: list[int]
    grup_ortalama: int | None
    grup_fark: int | None


def _zayif_esik() -> Decimal:
    e = esikler()
    return Decimal(str(e.get("zayif_ktt_puan", 70)))


def _kapanma_esik() -> int:
    return esikler().get("kapanma_gelisim_puan", 15)


def _seviye_kodu(puan: float) -> str:
    if puan >= SEVIYE_ESIKLERI["guclu"]:
        return "guclu"
    if puan >= SEVIYE_ESIKLERI["iyi"]:
        return "iyi"
    if puan >= SEVIYE_ESIKLERI["gelistirilmeli"]:
        return "gelistirilmeli"
    return "oncelikli"


def _trend_kodu(puanlar: list[float]) -> str:
    if len(puanlar) < 2:
        return "dengeli"
    if len(puanlar) >= 3:
        eski = statistics.mean(puanlar[:-1])
        yeni = puanlar[-1]
        fark = yeni - eski
    else:
        fark = puanlar[-1] - puanlar[-2]
    if fark >= 8:
        return "yukseliyor"
    if fark <= -8:
        return "dusuyor"
    return "dengeli"


def _agirlikli_ortalama(puanlar: list[float]) -> float:
    if not puanlar:
        return 0.0
    if len(puanlar) == 1:
        return puanlar[0]
    agirliklar = [1.4 ** i for i in range(len(puanlar))]
    toplam = sum(p * w for p, w in zip(puanlar, agirliklar))
    return toplam / sum(agirliklar)


def _talebe_konu_sonuclari(talebe: Talebe, konu: KonuKatalogu) -> list[KttSonucu]:
    return list(
        KttSonucu.objects.filter(
            talebe=talebe,
            ktt__aktif=True,
            ktt__konu_katalog=konu,
        )
        .select_related("ktt")
        .order_by("ktt__sinav_tarihi", "id")
    )


def _grup_konu_ortalama(ktt: KttSinav, konu: KonuKatalogu) -> int | None:
    ort = (
        KttSonucu.objects.filter(ktt=ktt, ktt__konu_katalog=konu)
        .aggregate(v=Avg("puan"))
        .get("v")
    )
    return int(round(float(ort))) if ort is not None else None


def konu_hakimiyeti(talebe: Talebe, konu: KonuKatalogu) -> KonuHakimiyet:
    sonuclar = _talebe_konu_sonuclari(talebe, konu)
    puanlar = [float(s.puan or 0) for s in sonuclar]
    ort = _agirlikli_ortalama(puanlar)
    seviye = _seviye_kodu(ort)
    trend = _trend_kodu(puanlar)
    sev_etiket, sev_sinif = SEVIYE_ETIKET[seviye]
    tr_etiket, tr_sinif = TREND_ETIKET[trend]

    grup_ort = None
    grup_fark = None
    if sonuclar:
        son_ktt = sonuclar[-1].ktt
        grup_ort = _grup_konu_ortalama(son_ktt, konu)
        if grup_ort is not None:
            grup_fark = int(round(puanlar[-1])) - grup_ort

    return KonuHakimiyet(
        konu_id=konu.id,
        konu_ad=konu.konu_ad,
        brans=konu.brans,
        brans_etiket=konu.brans_etiket,
        ortalama_puan=int(round(ort)),
        seviye_kodu=seviye,
        seviye_etiket=sev_etiket,
        seviye_sinif=sev_sinif,
        trend_kodu=trend,
        trend_etiket=tr_etiket,
        trend_sinif=tr_sinif,
        ktt_sayisi=len(puanlar),
        puan_gecmisi=[int(round(p)) for p in puanlar],
        grup_ortalama=grup_ort,
        grup_fark=grup_fark,
    )


def talebe_konu_hakimiyetleri(talebe: Talebe) -> list[KonuHakimiyet]:
    konu_ids = (
        KttSonucu.objects.filter(talebe=talebe, ktt__aktif=True, ktt__konu_katalog__isnull=False)
        .values_list("ktt__konu_katalog_id", flat=True)
        .distinct()
    )
    konular = KonuKatalogu.objects.filter(id__in=konu_ids, aktif=True).order_by("brans", "konu_ad")
    return [konu_hakimiyeti(talebe, k) for k in konular]


def _oncelik_skoru(h: KonuHakimiyet) -> tuple[int, int]:
    oncelik_map = {"oncelikli": 0, "gelistirilmeli": 1, "iyi": 2, "guclu": 3}
    trend_map = {"dusuyor": 0, "dengeli": 1, "yukseliyor": 2}
    return (oncelik_map.get(h.seviye_kodu, 9), trend_map.get(h.trend_kodu, 1))


def etut_bugun_dikkat(hoca: EtutHocasi, limit: int = 8) -> list[dict]:
    """Etüt hocası ana ekranı — bugün dikkat gerektiren talebe×konu."""
    talebeler = Talebe.objects.filter(
        durum=Talebe.Durum.AKTIF,
        etut_hocasi=hoca,
    )
    satirlar: list[dict] = []
    for talebe in talebeler:
        for h in talebe_konu_hakimiyetleri(talebe):
            if h.seviye_kodu in {"guclu"} and h.trend_kodu != "dusuyor":
                continue
            oncelik = "oncelikli" if h.seviye_kodu == "oncelikli" else (
                "takip" if h.seviye_kodu in {"gelistirilmeli"} or h.trend_kodu == "dusuyor" else "iyi"
            )
            if oncelik == "iyi" and h.trend_kodu == "yukseliyor":
                oncelik = "iyi"
            elif oncelik == "iyi":
                continue
            o_etiket, o_sinif = ONCELIK_ETIKET[oncelik]
            oneri = f"{h.konu_ad} konu tekrarı"
            if h.trend_kodu == "dusuyor":
                oneri = f"{h.konu_ad} kısa tekrar"
            satirlar.append(
                {
                    "talebe": talebe,
                    "konu": h,
                    "oncelik": oncelik,
                    "oncelik_etiket": o_etiket,
                    "oncelik_sinif": o_sinif,
                    "oneri": oneri,
                }
            )
    satirlar.sort(key=lambda x: (_oncelik_skoru(x["konu"]), x["talebe"].ad_soyad))
    return satirlar[:limit]


def grup_ortak_eksikler(hoca: EtutHocasi, min_oran: float = 0.5) -> list[dict]:
    talebeler = list(
        Talebe.objects.filter(durum=Talebe.Durum.AKTIF, etut_hocasi=hoca)
    )
    if not talebeler:
        return []
    toplam = len(talebeler)
    konu_zayif: dict[int, dict] = {}

    for talebe in talebeler:
        for h in talebe_konu_hakimiyetleri(talebe):
            if h.seviye_kodu not in {"oncelikli", "gelistirilmeli"}:
                continue
            kayit = konu_zayif.setdefault(
                h.konu_id,
                {
                    "konu_ad": h.konu_ad,
                    "brans_etiket": h.brans_etiket,
                    "sayac": 0,
                },
            )
            kayit["sayac"] += 1

    sonuc = []
    for kid, veri in konu_zayif.items():
        oran = veri["sayac"] / toplam
        if oran >= min_oran:
            sonuc.append(
                {
                    "konu_id": kid,
                    "konu_ad": veri["konu_ad"],
                    "brans_etiket": veri["brans_etiket"],
                    "eksik_sayisi": veri["sayac"],
                    "talebe_sayisi": toplam,
                    "oran_yuzde": int(round(100 * oran)),
                }
            )
    return sorted(sonuc, key=lambda x: (-x["oran_yuzde"], x["konu_ad"]))


def ktt_sonuc_sonrasi_isle(sonuc: KttSonucu) -> None:
    """Sonuç kaydı sonrası eksik tespiti ve kapatma döngüsü."""
    ktt = sonuc.ktt
    if not ktt.konu_katalog_id:
        ktt_konu_eslestir(ktt)
        ktt.refresh_from_db()

    konu = ktt.konu_katalog
    if not konu:
        return

    puan = Decimal(str(sonuc.puan or 0))
    zayif = _zayif_esik()
    talebe = sonuc.talebe

    eksik = TalebeKonuEksigi.objects.filter(
        talebe=talebe,
        konu=konu,
        kaynak=TalebeKonuEksigi.Kaynak.KTT,
    ).first()

    if puan < zayif:
        oncelik = max(10, 100 - int(puan))
        if eksik:
            eksik.skor = puan
            eksik.oncelik = oncelik
            eksik.tespit_tarihi = ktt.sinav_tarihi
            eksik.son_ktt_sonuc = sonuc
            eksik.cozuldu = False
            if eksik.mudahale_durumu == "kapandi":
                eksik.mudahale_durumu = "takip"
            elif eksik.mudahale_durumu not in {"calisildi"}:
                eksik.mudahale_durumu = "bekliyor"
            eksik.save()
        else:
            TalebeKonuEksigi.objects.create(
                talebe=talebe,
                konu=konu,
                kaynak=TalebeKonuEksigi.Kaynak.KTT,
                skor=puan,
                oncelik=oncelik,
                tespit_tarihi=ktt.sinav_tarihi,
                son_ktt_sonuc=sonuc,
                mudahale_durumu="bekliyor",
            )
        return

    if not eksik or eksik.cozuldu:
        return

    onceki = float(eksik.skor or 0)
    yeni = float(puan)
    gelisim = int(round(yeni - onceki))
    kapanma = _kapanma_esik()

    if eksik.mudahale_durumu == "calisildi" and gelisim >= kapanma and yeni >= float(zayif):
        eksik.cozuldu = True
        eksik.mudahale_durumu = "kapandi"
        eksik.kapanma_skor = puan
        eksik.gelisim_puan = gelisim
        eksik.save()
    elif gelisim >= kapanma // 2:
        eksik.mudahale_durumu = "takip"
        eksik.gelisim_puan = gelisim
        eksik.save()


def etut_mudahale_kaydet(
    eksik: TalebeKonuEksigi,
    hoca: EtutHocasi,
    kullanici,
) -> KttEtutMudahale:
    mudahale = KttEtutMudahale.objects.create(
        talebe=eksik.talebe,
        konu=eksik.konu,
        eksik=eksik,
        etut_hocasi=hoca,
        mudahale_tarihi=localdate(),
        tetikleyen_sonuc=eksik.son_ktt_sonuc,
        olusturan=kullanici,
    )
    eksik.mudahale_durumu = "calisildi"
    eksik.cozuldu = False
    eksik.save(update_fields=["mudahale_durumu", "cozuldu"])
    return mudahale


def veli_akademik_gelisim(talebe: Talebe) -> dict:
    """Veli paneli — sade akademik özet."""
    hakimiyetler = talebe_konu_hakimiyetleri(talebe)
    brans_gruplari: dict[str, list[KonuHakimiyet]] = {}
    for h in hakimiyetler:
        brans_gruplari.setdefault(h.brans_etiket, []).append(h)

    dersler = []
    for brans, konular in brans_gruplari.items():
        ort = int(round(statistics.mean(k.ortalama_puan for k in konular))) if konular else 0
        seviye = _seviye_kodu(ort)
        sev_etiket, sev_sinif = SEVIYE_ETIKET[seviye]
        guclu = [k for k in konular if k.seviye_kodu in {"guclu", "iyi"}]
        zayif = [k for k in konular if k.seviye_kodu in {"oncelikli", "gelistirilmeli"}]
        son_konu = max(konular, key=lambda k: k.ktt_sayisi) if konular else None
        trend = son_konu.trend_etiket if son_konu else TREND_ETIKET["dengeli"][0]

        mudahale_metinleri = []
        for eksik in TalebeKonuEksigi.objects.filter(
            talebe=talebe,
            kaynak=TalebeKonuEksigi.Kaynak.KTT,
            konu__brans=konular[0].brans if konular else "",
        ).select_related("konu"):
            if eksik.mudahale_durumu == "calisildi":
                mudahale_metinleri.append(
                    f"{eksik.konu.konu_ad} konusu etüt programında takip edilmektedir."
                )
            elif eksik.mudahale_durumu == "kapandi":
                mudahale_metinleri.append(
                    f"{eksik.konu.konu_ad} konusunda tespit edilen eksik için etüt çalışması "
                    f"yapılmış ve sonraki KTT'de gelişim görülmüştür."
                )

        grup_fark_metni = ""
        if son_konu and son_konu.grup_fark is not None:
            if son_konu.grup_fark > 0:
                grup_fark_metni = f"+{son_konu.grup_fark} puan — grup ortalamasının üzerinde."
            elif son_konu.grup_fark < 0:
                grup_fark_metni = f"{abs(son_konu.grup_fark)} puan — grup ortalamasının altında."

        dersler.append(
            {
                "brans": brans,
                "genel_durum": sev_etiket,
                "genel_sinif": sev_sinif,
                "son_ktt_puan": son_konu.puan_gecmisi[-1] if son_konu and son_konu.puan_gecmisi else ort,
                "gelisim_cizgisi": son_konu.puan_gecmisi if son_konu else [],
                "trend": trend,
                "guclu_konular": guclu[:4],
                "zayif_konular": zayif[:4],
                "mudahale_metinleri": mudahale_metinleri[:3],
                "grup_karsilastirma": grup_fark_metni,
            }
        )

    return {"dersler": dersler, "konu_sayisi": len(hakimiyetler)}


def yonetim_ktt_ozet() -> dict:
    """Yönetim — aksiyon alınabilir KTT KPI'ları."""
    bugun = localdate()
    ay_basi = bugun.replace(day=1)
    eksikler = TalebeKonuEksigi.objects.filter(
        kaynak=TalebeKonuEksigi.Kaynak.KTT,
        tespit_tarihi__gte=ay_basi,
    )
    tespit = eksikler.count()
    mudahale = eksikler.filter(mudahale_durumu__in=["calisildi", "kapandi"]).count()
    kapandi = eksikler.filter(mudahale_durumu="kapandi", cozuldu=True).count()
    bekleyen = eksikler.filter(mudahale_durumu="bekliyor").count()
    inceleme = KonuEslestirmeInceleme.objects.filter(durum="bekliyor").count()

    return {
        "ay": bugun.strftime("%B %Y"),
        "tespit": tespit,
        "mudahale": mudahale,
        "kapandi": kapandi,
        "bekleyen": bekleyen,
        "inceleme_bekleyen": inceleme,
        "mudahale_orani": int(round(100 * mudahale / tespit)) if tespit else 0,
        "kapanma_orani": int(round(100 * kapandi / tespit)) if tespit else 0,
    }


def bekleyen_eslestirmeler(limit: int = 30):
    from takip.ktt_akilli_models import KonuEslestirmeInceleme

    return (
        KonuEslestirmeInceleme.objects.filter(
            durum=KonuEslestirmeInceleme.Durum.BEKLIYOR
        )
        .select_related("onerilen_konu", "ktt")
        .order_by("-guven_yuzde", "-olusturulma")[:limit]
    )
