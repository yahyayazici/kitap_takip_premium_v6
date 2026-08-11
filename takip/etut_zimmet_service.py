"""Etüt / sınıf mesulü — sorumlu sınıf zimmeti ↔ talebe.etut_hocasi senkronu."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q

from takip.models import EtutHocasi, Talebe
from takip.panel_permissions import ROL_ETUT_MESUL, ROL_SINIF_MESUL

_MESUL_ROLLER = frozenset({ROL_ETUT_MESUL, ROL_SINIF_MESUL})


def etut_mesul_mu(hoca: EtutHocasi | None) -> bool:
    if not hoca or not hoca.pk:
        return False
    personel = getattr(hoca, "personel_kaydi", None)
    if personel is None:
        return False
    return bool(
        personel.aktif and personel.ana_rol in _MESUL_ROLLER
    )


def mesul_zimmet_sinif_ids(hoca: EtutHocasi) -> list[int]:
    return list(
        hoca.sorumlu_sinif_subeler.filter(aktif=True).values_list("pk", flat=True)
    )


def hoca_talebe_q(hoca: EtutHocasi) -> Q:
    """Etüt/sınıf mesulünde kaynak = sorumlu sınıf zimmeti (dini ders FK sızmaz)."""
    zimmet_ids = mesul_zimmet_sinif_ids(hoca)
    if zimmet_ids and etut_mesul_mu(hoca):
        return Q(sinif_sube_id__in=zimmet_ids)
    return Q(etut_hocasi=hoca) | Q(dini_ders_hocasi=hoca)


def _sinifin_etut_mesulu(
    sinif_sube_id: int | None, *, haric: EtutHocasi | None = None
) -> EtutHocasi | None:
    if not sinif_sube_id:
        return None
    qs = EtutHocasi.objects.filter(
        aktif=True,
        sorumlu_sinif_subeler__pk=sinif_sube_id,
        personel_kaydi__aktif=True,
        personel_kaydi__ana_rol__in=_MESUL_ROLLER,
    ).distinct()
    if haric is not None:
        qs = qs.exclude(pk=haric.pk)
    return qs.order_by("pk").first()


@transaction.atomic
def etut_mesul_sinif_zimmet_senkronize(hoca: EtutHocasi) -> dict[str, int]:
    """Zimmetli sınıflardaki talebeleri bu mesule bağlar; zimmet dışındakileri koparır."""
    if not etut_mesul_mu(hoca):
        return {"atanan": 0, "cikarilan": 0}

    sinif_ids = mesul_zimmet_sinif_ids(hoca)
    if not sinif_ids:
        return {"atanan": 0, "cikarilan": 0}

    atanan = (
        Talebe.objects.filter(aktif=True, sinif_sube_id__in=sinif_ids)
        .exclude(etut_hocasi=hoca)
        .update(etut_hocasi=hoca)
    )

    cikarilan = 0
    for talebe in Talebe.objects.filter(etut_hocasi=hoca, aktif=True).exclude(
        sinif_sube_id__in=sinif_ids
    ):
        yeni = _sinifin_etut_mesulu(talebe.sinif_sube_id, haric=hoca)
        Talebe.objects.filter(pk=talebe.pk).update(
            etut_hocasi_id=yeni.pk if yeni else None
        )
        cikarilan += 1

    return {"atanan": atanan, "cikarilan": cikarilan}


@transaction.atomic
def tum_etut_mesul_zimmet_senkronize() -> dict[str, int]:
    """Tüm aktif etüt/sınıf mesullerinin zimmetlerini senkronize eder."""
    toplam = {"atanan": 0, "cikarilan": 0}
    hocalar = (
        EtutHocasi.objects.filter(
            aktif=True,
            personel_kaydi__aktif=True,
            personel_kaydi__ana_rol__in=_MESUL_ROLLER,
        )
        .select_related("personel_kaydi")
        .prefetch_related("sorumlu_sinif_subeler")
    )
    for hoca in hocalar:
        sonuc = etut_mesul_sinif_zimmet_senkronize(hoca)
        toplam["atanan"] += sonuc["atanan"]
        toplam["cikarilan"] += sonuc["cikarilan"]
    return toplam
