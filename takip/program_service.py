"""Program planı sorguları ve yardımcılar."""

from __future__ import annotations

from datetime import date

from django.db.models import QuerySet
from django.utils.timezone import localdate

from .models import ProgramPlan


def tarihe_uygun_programlar(tarih: date | None = None) -> QuerySet[ProgramPlan]:
    tarih = tarih or localdate()

    return (
        ProgramPlan.objects.filter(
            aktif=True,
            baslangic_tarihi__lte=tarih,
            bitis_tarihi__gte=tarih,
        )
        .prefetch_related("satirlar")
        .order_by("-baslangic_tarihi", "ad")
    )


def bugunun_programi() -> ProgramPlan | None:
    return tarihe_uygun_programlar().first()


def program_arsivi() -> QuerySet[ProgramPlan]:
    return (
        ProgramPlan.objects.filter(aktif=True)
        .prefetch_related("satirlar")
        .order_by("-baslangic_tarihi", "ad")
    )
