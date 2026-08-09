"""Pazar izin dönüşü yoklama — sorgular ve iş kuralları."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import User
from django.db.models import Count, QuerySet

from takip.filter_utils import qs_filtre_id
from takip.models import SinifSube, Talebe
from takip.pazar_izin_donus_models import (
    PazarIzinDonusDurumu,
    PazarIzinDonusGunAyar,
    PazarIzinDonusKaydi,
    PazarIzinDonusOturum,
)
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user

VARSAYILAN_BEKLENEN_SAAT = time(18, 0)


def pazar_izin_tam_yetki(user: User) -> bool:
    return user.is_superuser or tum_talebe_kapsami_var(user)


def pazar_izin_gorebilir(user: User) -> bool:
    return can(user, "pazar_izin_donus", "view")


def pazar_izin_kaydedebilir(user: User) -> bool:
    return can(user, "pazar_izin_donus", "edit") or can(
        user, "pazar_izin_donus", "create"
    )


def gecikme_hesapla(
    beklenen_tarih: date,
    beklenen_saat: time,
    giris_tarih: date | None,
    giris_saat: time | None,
) -> int:
    if not giris_tarih or not giris_saat:
        return 0
    beklenen = datetime.combine(beklenen_tarih, beklenen_saat)
    gercek = datetime.combine(giris_tarih, giris_saat)
    fark = int((gercek - beklenen).total_seconds() // 60)
    return max(fark, 0)


def gun_ayari_getir(tarih: date) -> PazarIzinDonusGunAyar | None:
    return PazarIzinDonusGunAyar.objects.filter(tarih=tarih).first()


def varsayilan_beklenen(tarih: date) -> tuple[date, time]:
    ayar = gun_ayari_getir(tarih)
    if ayar:
        return ayar.beklenen_giris_tarihi, ayar.beklenen_giris_saati
    return tarih, VARSAYILAN_BEKLENEN_SAAT


def gun_ayari_kaydet(
    user: User,
    tarih: date,
    beklenen_tarih: date,
    beklenen_saat: time,
    *,
    tum_siniflara_uygula: bool = False,
) -> PazarIzinDonusGunAyar:
    ayar, _ = PazarIzinDonusGunAyar.objects.update_or_create(
        tarih=tarih,
        defaults={
            "beklenen_giris_tarihi": beklenen_tarih,
            "beklenen_giris_saati": beklenen_saat,
            "guncelleyen": user,
        },
    )
    if tum_siniflara_uygula:
        PazarIzinDonusOturum.objects.filter(tarih=tarih).update(
            beklenen_giris_tarihi=beklenen_tarih,
            beklenen_giris_saati=beklenen_saat,
        )
    return ayar


def yetkili_sinif_subeler(user: User) -> QuerySet[SinifSube]:
    if not pazar_izin_gorebilir(user):
        return SinifSube.objects.none()

    qs = SinifSube.objects.filter(aktif=True)
    if pazar_izin_tam_yetki(user):
        return qs.order_by("sinif", "sube")

    hoca = etut_hocasi_for_user(user)
    if hoca:
        sinif_ids = (
            Talebe.objects.filter(aktif=True, etut_hocasi=hoca)
            .exclude(sinif_sube_id__isnull=True)
            .values_list("sinif_sube_id", flat=True)
            .distinct()
        )
        return qs.filter(id__in=sinif_ids).order_by("sinif", "sube")

    talebe_ids = yetkili_talebeler(user, aktif_only=True).values_list("id", flat=True)
    sinif_ids = (
        Talebe.objects.filter(id__in=talebe_ids)
        .exclude(sinif_sube_id__isnull=True)
        .values_list("sinif_sube_id", flat=True)
        .distinct()
    )
    return qs.filter(id__in=sinif_ids).order_by("sinif", "sube")


def panel_talebeleri(user: User, sinif_sube_id: int | str | None) -> QuerySet[Talebe]:
    if not pazar_izin_gorebilir(user):
        return Talebe.objects.none()

    tum_kurum = sinif_sube_id == "tum"
    if not sinif_sube_id and not tum_kurum:
        return Talebe.objects.none()

    qs = Talebe.objects.filter(aktif=True).select_related("sinif_sube", "etut_hocasi")
    if not tum_kurum:
        qs = qs.filter(sinif_sube_id=sinif_sube_id)

    if pazar_izin_tam_yetki(user):
        return qs.order_by("sinif_sube__sinif", "sinif_sube__sube", "ad_soyad")

    hoca = etut_hocasi_for_user(user)
    if hoca:
        return qs.filter(etut_hocasi=hoca).order_by(
            "sinif_sube__sinif", "sinif_sube__sube", "ad_soyad"
        )

    talebe_ids = yetkili_talebeler(user, aktif_only=True).values_list("id", flat=True)
    return qs.filter(id__in=talebe_ids).order_by(
        "sinif_sube__sinif", "sinif_sube__sube", "ad_soyad"
    )


def oturum_getir(
    sinif_sube_id: int | str,
    tarih: date,
) -> PazarIzinDonusOturum | None:
    return (
        PazarIzinDonusOturum.objects.filter(sinif_sube_id=sinif_sube_id, tarih=tarih)
        .prefetch_related("kayitlar")
        .first()
    )


def kayit_haritasi_tarih(
    tarih: date,
    talebe_ids: Iterable[int],
) -> dict[int, PazarIzinDonusKaydi]:
    if not talebe_ids:
        return {}
    return {
        k.talebe_id: k
        for k in PazarIzinDonusKaydi.objects.filter(
            oturum__tarih=tarih,
            talebe_id__in=talebe_ids,
        ).select_related("oturum")
    }


def oturum_hazirla(
    user: User,
    sinif_sube_id: int | str,
    tarih: date,
    beklenen_tarih: date | None = None,
    beklenen_saat: time | None = None,
) -> PazarIzinDonusOturum:
    if beklenen_tarih is None or beklenen_saat is None:
        beklenen_tarih, beklenen_saat = varsayilan_beklenen(tarih)

    oturum, _ = PazarIzinDonusOturum.objects.get_or_create(
        sinif_sube_id=sinif_sube_id,
        tarih=tarih,
        defaults={
            "beklenen_giris_tarihi": beklenen_tarih,
            "beklenen_giris_saati": beklenen_saat,
            "kaydeden": user,
        },
    )
    return oturum


def yoklama_kaydet(
    user: User,
    oturum: PazarIzinDonusOturum,
    *,
    beklenen_tarih: date,
    beklenen_saat: time,
    satirlar: dict[int, dict],
    talebe_ids: list[int],
) -> None:
    oturum.beklenen_giris_tarihi = beklenen_tarih
    oturum.beklenen_giris_saati = beklenen_saat
    oturum.kaydeden = user
    oturum.save(
        update_fields=[
            "beklenen_giris_tarihi",
            "beklenen_giris_saati",
            "kaydeden",
            "guncellenme",
        ]
    )

    mevcut = {k.talebe_id: k for k in oturum.kayitlar.all()}
    for talebe_id in talebe_ids:
        veri = satirlar.get(talebe_id, {})
        durum = veri.get("durum") or PazarIzinDonusDurumu.GELMEDI
        giris_tarih = veri.get("giris_tarihi")
        giris_saat = veri.get("giris_saati")
        aciklama = veri.get("aciklama", "")

        if durum == PazarIzinDonusDurumu.GEC_GELDI:
            gecikme = gecikme_hesapla(
                beklenen_tarih, beklenen_saat, giris_tarih, giris_saat
            )
        else:
            gecikme = 0
            if durum != PazarIzinDonusDurumu.GEC_GELDI:
                giris_tarih = None
                giris_saat = None

        kayit = mevcut.get(talebe_id)
        if kayit:
            kayit.durum = durum
            kayit.giris_tarihi = giris_tarih
            kayit.giris_saati = giris_saat
            kayit.gecikme_dk = gecikme
            kayit.aciklama = aciklama
            kayit.save()
        else:
            PazarIzinDonusKaydi.objects.create(
                oturum=oturum,
                talebe_id=talebe_id,
                durum=durum,
                giris_tarihi=giris_tarih,
                giris_saati=giris_saat,
                gecikme_dk=gecikme,
                aciklama=aciklama,
            )


def yoklama_kaydet_siniflara(
    user: User,
    tarih: date,
    *,
    beklenen_tarih: date,
    beklenen_saat: time,
    satirlar: dict[int, dict],
    talebeler: list[Talebe],
) -> None:
    """Tüm kurum görünümünde talebeleri sınıf oturumlarına böler."""
    from collections import defaultdict

    gruplar: dict[int, list[int]] = defaultdict(list)
    for talebe in talebeler:
        if talebe.sinif_sube_id:
            gruplar[talebe.sinif_sube_id].append(talebe.id)

    for sinif_id, talebe_ids in gruplar.items():
        oturum = oturum_hazirla(
            user, sinif_id, tarih, beklenen_tarih, beklenen_saat
        )
        yoklama_kaydet(
            user,
            oturum,
            beklenen_tarih=beklenen_tarih,
            beklenen_saat=beklenen_saat,
            satirlar=satirlar,
            talebe_ids=talebe_ids,
        )


def satir_verisi(
    talebe: Talebe,
    kayit: PazarIzinDonusKaydi | None,
) -> dict:
    if kayit:
        return {
            "talebe": talebe,
            "durum": kayit.durum,
            "giris_tarihi": kayit.giris_tarihi,
            "giris_saati": kayit.giris_saati,
            "gecikme_dk": kayit.gecikme_dk,
            "aciklama": kayit.aciklama,
            "kayitli": True,
        }
    return {
        "talebe": talebe,
        "durum": PazarIzinDonusDurumu.GELMEDI,
        "giris_tarihi": None,
        "giris_saati": None,
        "gecikme_dk": 0,
        "aciklama": "",
        "kayitli": False,
    }


def rapor_kayitlari(user: User) -> QuerySet[PazarIzinDonusKaydi]:
    if not pazar_izin_gorebilir(user):
        return PazarIzinDonusKaydi.objects.none()

    qs = PazarIzinDonusKaydi.objects.select_related(
        "talebe",
        "talebe__sinif_sube",
        "talebe__etut_hocasi",
        "oturum",
        "oturum__sinif_sube",
    )

    if pazar_izin_tam_yetki(user):
        return qs

    hoca = etut_hocasi_for_user(user)
    if hoca:
        return qs.filter(talebe__etut_hocasi=hoca)

    talebe_ids = yetkili_talebeler(user, aktif_only=True).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def rapor_filtrele(
    qs: QuerySet[PazarIzinDonusKaydi],
    *,
    baslangic: str | date | None = None,
    bitis: str | date | None = None,
    sinif_sube_ids: list[int] | None = None,
    etut_hocasi_ids: list[int] | None = None,
    talebe_ids: list[int] | None = None,
    durumlar: list[str] | None = None,
    donem: str | None = None,
) -> QuerySet[PazarIzinDonusKaydi]:
    if donem == "haftalik":
        bitis_d = date.today()
        baslangic_d = bitis_d - timedelta(days=7)
        qs = qs.filter(oturum__tarih__gte=baslangic_d, oturum__tarih__lte=bitis_d)
    elif donem == "aylik":
        bitis_d = date.today()
        baslangic_d = bitis_d - timedelta(days=30)
        qs = qs.filter(oturum__tarih__gte=baslangic_d, oturum__tarih__lte=bitis_d)
    elif donem == "donemlik":
        bitis_d = date.today()
        baslangic_d = bitis_d - timedelta(days=120)
        qs = qs.filter(oturum__tarih__gte=baslangic_d, oturum__tarih__lte=bitis_d)

    if baslangic:
        qs = qs.filter(oturum__tarih__gte=baslangic)
    if bitis:
        qs = qs.filter(oturum__tarih__lte=bitis)
    if sinif_sube_ids:
        qs = qs.filter(oturum__sinif_sube_id__in=sinif_sube_ids)
    if etut_hocasi_ids:
        qs = qs.filter(talebe__etut_hocasi_id__in=etut_hocasi_ids)
    if talebe_ids:
        qs = qs.filter(talebe_id__in=talebe_ids)
    if durumlar:
        qs = qs.filter(durum__in=durumlar)
    return qs.order_by("-oturum__tarih", "talebe__ad_soyad")


def rapor_istatistik(qs: QuerySet[PazarIzinDonusKaydi]) -> dict:
    qs = qs.distinct()
    toplam = qs.count()
    ozet = qs.values("durum").annotate(sayi=Count("id", distinct=True))
    sayilar = {o["durum"]: o["sayi"] for o in ozet}
    gec_ort = 0
    gec_kayitlar = qs.filter(durum=PazarIzinDonusDurumu.GEC_GELDI)
    if gec_kayitlar.exists():
        gec_ort = (
            sum(k.gecikme_dk for k in gec_kayitlar[:500]) / gec_kayitlar.count()
        )
    return {
        "toplam": toplam,
        "geldi": sayilar.get(PazarIzinDonusDurumu.GELDI, 0),
        "izinli": sayilar.get(PazarIzinDonusDurumu.IZINLI, 0),
        "gec_geldi": sayilar.get(PazarIzinDonusDurumu.GEC_GELDI, 0),
        "gelmedi": sayilar.get(PazarIzinDonusDurumu.GELMEDI, 0),
        "gec_ort_dk": round(gec_ort, 1),
    }
