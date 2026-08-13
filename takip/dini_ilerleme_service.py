"""Dinî eğitim ilerleme motoru — talebe, grup, plan ve durum analizi."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from takip.dini_ilerleme_models import DiniAlanPlani, DiniIlerlemeEsik, DiniKonuHedefTarihi
from takip.models import (
    DiniDersKonu,
    DiniDersKonuKaydi,
    DiniDersSeviyesi,
    DiniDersTakipAlani,
    Donem,
    EgitimYili,
    Talebe,
)

DEFAULT_ESIKLER = {
    "plan_onunde_puan": 8,
    "geride_puan": -8,
    "grupla_uyumlu_puan": 5,
    "hiz_artis_esik_puan": 5,
}

DURUM_ETIKETLERI = {
    "plan_onunde": ("Planın Önünde", "success"),
    "duzenli": ("Düzenli İlerliyor", "success"),
    "grupla_uyumlu": ("Grupla Uyumlu", "info"),
    "takip": ("Takip Edilmeli", "warn"),
    "geride": ("Planın Gerisinde", "danger"),
    "veri_yok": ("Veri Bekleniyor", "muted"),
}


@dataclass(frozen=True)
class AlanIlerlemeOzet:
    alan_id: int
    alan_ad: str
    talebe_yuzde: int
    tamamlanan: int
    toplam: int
    grup_ortalama: int
    grup_medyan: int
    beklenen_yuzde: int
    grup_fark_puan: int
    plan_fark_puan: int
    durum_kodu: str
    durum_etiket: str
    durum_sinif: str
    karsilastirma_metni: str
    durum_aciklama: str
    son_30_gun: dict
    siradaki_konu: str | None
    son_hareket: dict | None


def aktif_egitim_yili() -> EgitimYili | None:
    return EgitimYili.objects.filter(aktif=True).order_by("-baslangic").first()


def _esikler(yil: EgitimYili | None) -> dict:
    if not yil:
        return dict(DEFAULT_ESIKLER)
    kayit = DiniIlerlemeEsik.objects.filter(egitim_yili=yil).first()
    if not kayit:
        return dict(DEFAULT_ESIKLER)
    return {
        "plan_onunde_puan": kayit.plan_onunde_puan,
        "geride_puan": kayit.geride_puan,
        "grupla_uyumlu_puan": kayit.grupla_uyumlu_puan,
        "hiz_artis_esik_puan": kayit.hiz_artis_esik_puan,
    }


def toplam_konu_sayisi(seviye: DiniDersSeviyesi, alan: DiniDersTakipAlani) -> int:
    return DiniDersKonu.objects.filter(seviye=seviye, alan=alan, aktif=True).count()


def tamamlanan_konu_sayisi(talebe: Talebe, alan: DiniDersTakipAlani) -> int:
    if not talebe.dini_ders_seviyesi_id:
        return 0
    return DiniDersKonuKaydi.objects.filter(
        talebe=talebe,
        tamamlandi=True,
        konu__alan=alan,
        konu__seviye=talebe.dini_ders_seviyesi,
        konu__aktif=True,
    ).count()


def talebe_alan_yuzde(talebe: Talebe, alan: DiniDersTakipAlani) -> tuple[int, int, int]:
    if not talebe.dini_ders_seviyesi_id:
        return 0, 0, 0
    toplam = toplam_konu_sayisi(talebe.dini_ders_seviyesi, alan)
    if not toplam:
        return 0, 0, 0
    tamamlanan = tamamlanan_konu_sayisi(talebe, alan)
    return round(100 * tamamlanan / toplam), tamamlanan, toplam


def dini_grup_talebeleri(talebe: Talebe) -> QuerySet[Talebe]:
    """Aynı dinî eğitim hocası + seviye cohort."""
    if not talebe.dini_ders_hocasi_id or not talebe.dini_ders_seviyesi_id:
        return Talebe.objects.none()
    return Talebe.objects.filter(
        durum=Talebe.Durum.AKTIF,
        dini_ders_hocasi_id=talebe.dini_ders_hocasi_id,
        dini_ders_seviyesi_id=talebe.dini_ders_seviyesi_id,
    )


def _grup_yuzdeleri(talebe: Talebe, alan: DiniDersTakipAlani) -> list[int]:
    return [
        talebe_alan_yuzde(t, alan)[0]
        for t in dini_grup_talebeleri(talebe).only("id", "dini_ders_seviyesi_id")
    ]


def _linear_konu_hedef(
    baslangic: date,
    bitis: date,
    hedef_bas: float,
    hedef_bit: float,
    bugun: date,
) -> float:
    if bitis <= baslangic:
        return hedef_bit
    if bugun <= baslangic:
        return hedef_bas
    if bugun >= bitis:
        return hedef_bit
    oran = (bugun - baslangic).days / (bitis - baslangic).days
    return hedef_bas + (hedef_bit - hedef_bas) * oran


def _manuel_hedef_konu_sayisi(
    seviye: DiniDersSeviyesi,
    alan: DiniDersTakipAlani,
    bugun: date,
) -> int:
    """Hedef tarihi geçmiş konular — otomatik plandan yüksekse kullanılır."""
    return DiniKonuHedefTarihi.objects.filter(
        konu__seviye=seviye,
        konu__alan=alan,
        konu__aktif=True,
        hedef_tarih__lte=bugun,
    ).count()


def beklenen_konu_sayisi(
    seviye: DiniDersSeviyesi,
    alan: DiniDersTakipAlani,
    bugun: date | None = None,
    yil: EgitimYili | None = None,
) -> float:
    bugun = bugun or timezone.localdate()
    yil = yil or aktif_egitim_yili()
    toplam = toplam_konu_sayisi(seviye, alan)
    if not toplam or not yil:
        return 0.0

    plan = DiniAlanPlani.objects.filter(
        egitim_yili=yil,
        seviye=seviye,
        alan=alan,
        aktif=True,
    ).first()

    yil_sonu = plan.yil_sonu_hedef if plan and plan.yil_sonu_hedef else toplam
    yil_sonu = min(yil_sonu, toplam)

    donemler = list(
        Donem.objects.filter(egitim_yili=yil, aktif=True).order_by("baslangic")[:2]
    )
    if plan and plan.birinci_donem_hedef and len(donemler) >= 1:
        d1 = donemler[0]
        d1_hedef = min(plan.birinci_donem_hedef, yil_sonu)
        if bugun <= d1.bitis:
            linear = _linear_konu_hedef(yil.baslangic, d1.bitis, 0, d1_hedef, bugun)
        else:
            bitis = donemler[1].bitis if len(donemler) > 1 else yil.bitis
            linear = _linear_konu_hedef(d1.bitis, bitis, d1_hedef, yil_sonu, bugun)
        manuel = _manuel_hedef_konu_sayisi(seviye, alan, bugun)
        return max(linear, manuel)

    linear = _linear_konu_hedef(yil.baslangic, yil.bitis, 0, yil_sonu, bugun)
    manuel = _manuel_hedef_konu_sayisi(seviye, alan, bugun)
    return max(linear, manuel)


def beklenen_yuzde(
    seviye: DiniDersSeviyesi,
    alan: DiniDersTakipAlani,
    bugun: date | None = None,
) -> int:
    toplam = toplam_konu_sayisi(seviye, alan)
    if not toplam:
        return 0
    beklenen = beklenen_konu_sayisi(seviye, alan, bugun)
    return round(100 * beklenen / toplam)


def son_donem_hizi(
    talebe: Talebe,
    alan: DiniDersTakipAlani,
    gun: int = 30,
) -> dict:
    if not talebe.dini_ders_seviyesi_id:
        return {"yeni_tamamlanan": 0, "ilerleme_puan": 0, "artis": False}

    toplam = toplam_konu_sayisi(talebe.dini_ders_seviyesi, alan)
    if not toplam:
        return {"yeni_tamamlanan": 0, "ilerleme_puan": 0, "artis": False}

    bugun = timezone.localdate()
    bas = bugun - timedelta(days=gun - 1)
    onceki_bas = bas - timedelta(days=gun)

    yeni = DiniDersKonuKaydi.objects.filter(
        talebe=talebe,
        tamamlandi=True,
        konu__alan=alan,
        konu__seviye=talebe.dini_ders_seviyesi,
        konu__aktif=True,
        tamamlanma_tarihi__gte=bas,
        tamamlanma_tarihi__lte=bugun,
    ).count()

    onceki = DiniDersKonuKaydi.objects.filter(
        talebe=talebe,
        tamamlandi=True,
        konu__alan=alan,
        konu__seviye=talebe.dini_ders_seviyesi,
        konu__aktif=True,
        tamamlanma_tarihi__gte=onceki_bas,
        tamamlanma_tarihi__lt=bas,
    ).count()

    ilerleme_puan = round(100 * yeni / toplam) if toplam else 0
    onceki_puan = round(100 * onceki / toplam) if toplam else 0

    return {
        "yeni_tamamlanan": yeni,
        "ilerleme_puan": ilerleme_puan,
        "onceki_puan": onceki_puan,
        "artis": ilerleme_puan - onceki_puan >= DEFAULT_ESIKLER["hiz_artis_esik_puan"],
        "gun": gun,
    }


def _karsilastirma_metni(fark: int, hedef: str) -> str:
    if fark > 0:
        return f"{hedef} {abs(fark)} puan önünde"
    if fark < 0:
        return f"{hedef} {abs(fark)} puan gerisinde"
    return f"{hedef} ile aynı seviyede"


def _durum_kodu(
    talebe_yuzde: int,
    grup_yuzde: int,
    beklenen: int,
    hiz: dict,
    esikler: dict,
) -> str:
    plan_fark = talebe_yuzde - beklenen
    grup_fark = talebe_yuzde - grup_yuzde

    if plan_fark >= esikler["plan_onunde_puan"]:
        return "plan_onunde"
    if plan_fark <= esikler["geride_puan"]:
        return "geride"
    if hiz.get("artis") and plan_fark >= esikler["geride_puan"]:
        return "duzenli"
    if abs(grup_fark) <= esikler["grupla_uyumlu_puan"]:
        return "grupla_uyumlu"
    if plan_fark < 0:
        return "takip"
    return "duzenli"


def _durum_aciklama(kod: str, plan_fark: int, grup_fark: int) -> str:
    if kod == "plan_onunde":
        return "Yıllık plana göre ileri seviyede ve grubunun önünde olabilir."
    if kod == "duzenli":
        if plan_fark >= 0:
            return "Yıllık plana uygun ilerliyor."
        return "Plana göre hafif geride olsa da son dönemde hızlanma var."
    if kod == "grupla_uyumlu":
        return "Dinî eğitim grubu ile uyumlu seviyede."
    if kod == "takip":
        return "Grubunun ve yıllık planın gerisinde kalma riski var; takip önerilir."
    if kod == "geride":
        return "Grubunun ve yıllık planın belirgin şekilde gerisinde."
    return "Henüz yeterli veri yok."


def siradaki_konu_ad(talebe: Talebe, alan: DiniDersTakipAlani) -> str | None:
    if not talebe.dini_ders_seviyesi_id:
        return None
    tamamlanan_ids = set(
        DiniDersKonuKaydi.objects.filter(
            talebe=talebe,
            tamamlandi=True,
            konu__alan=alan,
            konu__seviye=talebe.dini_ders_seviyesi,
        ).values_list("konu_id", flat=True)
    )
    konu = (
        DiniDersKonu.objects.filter(
            alan=alan,
            seviye=talebe.dini_ders_seviyesi,
            aktif=True,
        )
        .exclude(id__in=tamamlanan_ids)
        .order_by("sira", "ad")
        .first()
    )
    return konu.ad if konu else None


def son_hareket(talebe: Talebe, alan: DiniDersTakipAlani) -> dict | None:
    kayit = (
        DiniDersKonuKaydi.objects.filter(
            talebe=talebe,
            tamamlandi=True,
            konu__alan=alan,
            konu__seviye=talebe.dini_ders_seviyesi,
            konu__aktif=True,
        )
        .select_related("konu")
        .order_by("-tamamlanma_tarihi", "-guncellenme")
        .first()
    )
    if not kayit:
        return None
    tarih = kayit.tamamlanma_tarihi or kayit.guncellenme.date()
    gun_once = (timezone.localdate() - tarih).days
    if gun_once == 0:
        zaman = "bugün"
    elif gun_once == 1:
        zaman = "dün"
    else:
        zaman = f"{gun_once} gün önce"
    return {"konu_ad": kayit.konu.ad, "zaman": zaman, "tarih": tarih}


def alan_ilerleme_ozeti(talebe: Talebe, alan: DiniDersTakipAlani) -> AlanIlerlemeOzet:
    yuzde, tamamlanan, toplam = talebe_alan_yuzde(talebe, alan)
    yil = aktif_egitim_yili()
    esikler = _esikler(yil)

    if not talebe.dini_ders_seviyesi_id or not toplam:
        etiket, sinif = DURUM_ETIKETLERI["veri_yok"]
        return AlanIlerlemeOzet(
            alan_id=alan.id,
            alan_ad=alan.ad,
            talebe_yuzde=0,
            tamamlanan=0,
            toplam=0,
            grup_ortalama=0,
            grup_medyan=0,
            beklenen_yuzde=0,
            grup_fark_puan=0,
            plan_fark_puan=0,
            durum_kodu="veri_yok",
            durum_etiket=etiket,
            durum_sinif=sinif,
            karsilastirma_metni="",
            durum_aciklama="Henüz müfredat veya ilerleme kaydı yok.",
            son_30_gun={"yeni_tamamlanan": 0, "ilerleme_puan": 0, "artis": False, "gun": 30},
            siradaki_konu=None,
            son_hareket=None,
        )

    grup_yuzdeleri = _grup_yuzdeleri(talebe, alan)
    grup_ort = round(statistics.mean(grup_yuzdeleri)) if grup_yuzdeleri else yuzde
    grup_med = round(statistics.median(grup_yuzdeleri)) if grup_yuzdeleri else yuzde
    beklenen = beklenen_yuzde(talebe.dini_ders_seviyesi, alan)
    hiz = son_donem_hizi(talebe, alan)

    grup_fark = yuzde - grup_ort
    plan_fark = yuzde - beklenen
    kod = _durum_kodu(yuzde, grup_ort, beklenen, hiz, esikler)
    etiket, sinif = DURUM_ETIKETLERI.get(kod, DURUM_ETIKETLERI["veri_yok"])

    if abs(grup_fark) <= esikler["grupla_uyumlu_puan"]:
        karsilastirma = _karsilastirma_metni(grup_fark, "Grubunun")
    else:
        karsilastirma = _karsilastirma_metni(grup_fark, "Grubunun")

    return AlanIlerlemeOzet(
        alan_id=alan.id,
        alan_ad=alan.ad,
        talebe_yuzde=yuzde,
        tamamlanan=tamamlanan,
        toplam=toplam,
        grup_ortalama=grup_ort,
        grup_medyan=grup_med,
        beklenen_yuzde=beklenen,
        grup_fark_puan=grup_fark,
        plan_fark_puan=plan_fark,
        durum_kodu=kod,
        durum_etiket=etiket,
        durum_sinif=sinif,
        karsilastirma_metni=karsilastirma,
        durum_aciklama=_durum_aciklama(kod, plan_fark, grup_fark),
        son_30_gun=hiz,
        siradaki_konu=siradaki_konu_ad(talebe, alan),
        son_hareket=son_hareket(talebe, alan),
    )


def talebe_alan_analizleri(talebe: Talebe) -> list[AlanIlerlemeOzet]:
    if not talebe.dini_ders_seviyesi_id:
        return []
    alanlar = DiniDersTakipAlani.objects.filter(aktif=True).order_by("sira", "ad")
    return [alan_ilerleme_ozeti(talebe, alan) for alan in alanlar if toplam_konu_sayisi(talebe.dini_ders_seviyesi, alan)]


def grup_saglik_ozeti(hoca_id: int, seviye_id: int) -> dict:
    """Personel/yönetim: grubun alan bazlı sağlık dağılımı."""
    talebeler = Talebe.objects.filter(
        durum=Talebe.Durum.AKTIF,
        dini_ders_hocasi_id=hoca_id,
        dini_ders_seviyesi_id=seviye_id,
    )
    if not talebeler.exists():
        return {"talebe_sayisi": 0, "alanlar": []}

    ornek = talebeler.first()
    assert ornek is not None
    alanlar = []
    for alan in DiniDersTakipAlani.objects.filter(aktif=True).order_by("sira", "ad"):
        if not toplam_konu_sayisi(ornek.dini_ders_seviyesi, alan):
            continue
        beklenen = beklenen_yuzde(ornek.dini_ders_seviyesi, alan)
        yuzdeler = [talebe_alan_yuzde(t, alan)[0] for t in talebeler]
        grup_yuzde = round(statistics.mean(yuzdeler)) if yuzdeler else 0

        durum_dagilimi: dict[str, int] = {}
        for t in talebeler:
            ozet = alan_ilerleme_ozeti(t, alan)
            durum_dagilimi[ozet.durum_kodu] = durum_dagilimi.get(ozet.durum_kodu, 0) + 1

        alanlar.append(
            {
                "alan": alan.ad,
                "grup_yuzde": grup_yuzde,
                "beklenen_yuzde": beklenen,
                "plan_fark": grup_yuzde - beklenen,
                "durum_dagilimi": durum_dagilimi,
                "talebe_sayisi": talebeler.count(),
            }
        )

    return {"talebe_sayisi": talebeler.count(), "alanlar": alanlar}


def gruplar_karsilastirma(seviye_id: int) -> list[dict]:
    """Yönetim: aynı seviyede farklı hocaların grup ortalamaları."""
    beklenen_cache: dict[int, int] = {}
    satirlar = []
    hoca_ids = (
        Talebe.objects.filter(
            durum=Talebe.Durum.AKTIF,
            dini_ders_seviyesi_id=seviye_id,
            dini_ders_hocasi_id__isnull=False,
        )
        .values_list("dini_ders_hocasi_id", flat=True)
        .distinct()
    )
    for hoca_id in hoca_ids:
        talebeler = Talebe.objects.filter(
            durum=Talebe.Durum.AKTIF,
            dini_ders_seviyesi_id=seviye_id,
            dini_ders_hocasi_id=hoca_id,
        ).select_related("dini_ders_hocasi", "sinif_sube")
        if not talebeler.exists():
            continue
        t0 = talebeler.first()
        if not t0 or not t0.dini_ders_hocasi_id:
            continue
        hoca_obj = t0.dini_ders_hocasi
        if not hoca_obj:
            continue
        alan_yuzdeleri = []
        for alan in DiniDersTakipAlani.objects.filter(aktif=True):
            toplam = toplam_konu_sayisi(t0.dini_ders_seviyesi, alan)
            if not toplam:
                continue
            yuzdeler = [talebe_alan_yuzde(t, alan)[0] for t in talebeler]
            alan_yuzdeleri.append(statistics.mean(yuzdeler))
            if alan.id not in beklenen_cache:
                beklenen_cache[alan.id] = beklenen_yuzde(t0.dini_ders_seviyesi, alan)
        if not alan_yuzdeleri:
            continue
        genel = round(statistics.mean(alan_yuzdeleri))
        beklenen = round(statistics.mean(beklenen_cache.values())) if beklenen_cache else 0
        sinif = str(t0.sinif_sube) if t0.sinif_sube_id else t0.sinif or "—"
        satirlar.append(
            {
                "hoca": hoca_obj.ad_soyad,
                "sinif_etiket": sinif,
                "talebe_sayisi": talebeler.count(),
                "grup_yuzde": genel,
                "beklenen_yuzde": beklenen,
                "plan_fark": genel - beklenen,
            }
        )
    return sorted(satirlar, key=lambda x: (-x["grup_yuzde"], x["hoca"]))
