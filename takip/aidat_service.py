"""Aidat takip sorguları ve işlemler."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.utils.timezone import localdate

from takip.aidat_models import AidatTahsilat, AidatTanim, TalebeAidatKaydi
from takip.models import Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can
from takip.wave0_models import EgitimYili


def aidat_gorebilir(user: User) -> bool:
    return can(user, "aidat", "view")


def aidat_tahsilat_girebilir(user: User) -> bool:
    return can(user, "aidat", "edit") or can(user, "aidat", "create")


def yetkili_aidat_kayitlari(user: User) -> QuerySet[TalebeAidatKaydi]:
    if not aidat_gorebilir(user):
        return TalebeAidatKaydi.objects.none()

    qs = TalebeAidatKaydi.objects.select_related(
        "talebe",
        "talebe__sinif_sube",
        "tanim",
        "tanim__egitim_yili",
    )

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user, aktif_only=False).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def aktif_aidat_tanimlari() -> QuerySet[AidatTanim]:
    return AidatTanim.objects.filter(aktif=True).select_related("egitim_yili")


def aidat_kayitlari_filtrele(
    qs: QuerySet[TalebeAidatKaydi],
    *,
    q: str | None = None,
    durum: str | None = None,
    egitim_yili_id: str | None = None,
) -> QuerySet[TalebeAidatKaydi]:
    if q:
        qs = qs.filter(
            Q(talebe__ad_soyad__icontains=q)
            | Q(talebe__talebe_no__icontains=q)
            | Q(tanim__ad__icontains=q)
        )
    if durum:
        qs = qs.filter(durum=durum)
    if egitim_yili_id:
        qs = qs.filter(tanim__egitim_yili_id=egitim_yili_id)
    return qs


def _durum_guncelle(kayit: TalebeAidatKaydi) -> None:
    if kayit.durum == TalebeAidatKaydi.Durum.MUAF:
        return

    bugun = localdate()
    toplam = kayit.tanim.tutar
    odenen = kayit.odenen_tutar

    if odenen >= toplam:
        kayit.durum = TalebeAidatKaydi.Durum.ODENDI
    elif odenen > Decimal("0"):
        kayit.durum = TalebeAidatKaydi.Durum.KISMI
    elif kayit.tanim.vade < bugun:
        kayit.durum = TalebeAidatKaydi.Durum.GECIKMIS
    else:
        kayit.durum = TalebeAidatKaydi.Durum.BEKLIYOR


@transaction.atomic
def aidat_tahsilat_ekle(
    kayit: TalebeAidatKaydi,
    *,
    tutar: Decimal,
    tarih: date,
    aciklama: str = "",
    kaydeden: User | None = None,
) -> AidatTahsilat:
    tahsilat = AidatTahsilat.objects.create(
        kayit=kayit,
        tutar=tutar,
        tarih=tarih,
        aciklama=aciklama,
        kaydeden=kaydeden,
    )
    kayit.odenen_tutar = (
        kayit.tahsilatlar.aggregate(toplam=Sum("tutar"))["toplam"] or Decimal("0.00")
    )
    _durum_guncelle(kayit)
    kayit.save(update_fields=["odenen_tutar", "durum", "guncellenme"])
    return tahsilat


def talebe_aidat_ozeti(talebe: Talebe) -> dict:
    kayitlar = (
        TalebeAidatKaydi.objects.filter(talebe=talebe)
        .select_related("tanim", "tanim__egitim_yili")
        .order_by("-tanim__vade")
    )
    toplam_borc = sum(k.borc_tutari for k in kayitlar)
    toplam_odenen = kayitlar.aggregate(t=Sum("odenen_tutar"))["t"] or Decimal("0.00")
    gecikmis = kayitlar.filter(durum=TalebeAidatKaydi.Durum.GECIKMIS).count()
    return {
        "kayitlar": list(kayitlar),
        "toplam_borc": toplam_borc,
        "toplam_odenen": toplam_odenen,
        "gecikmis_sayisi": gecikmis,
    }


def aidat_kaydi_olustur_veya_getir(tanim: AidatTanim, talebe: Talebe) -> TalebeAidatKaydi:
    kayit, created = TalebeAidatKaydi.objects.get_or_create(
        tanim=tanim,
        talebe=talebe,
        defaults={"durum": TalebeAidatKaydi.Durum.BEKLIYOR},
    )
    if created:
        _durum_guncelle(kayit)
        kayit.save(update_fields=["durum"])
    return kayit


def aktif_egitim_yillari() -> QuerySet[EgitimYili]:
    return EgitimYili.objects.filter(aktif=True).order_by("-baslangic")
