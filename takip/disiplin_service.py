"""Disiplin sorguları ve işlemler."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet

from takip.models import DisiplinKaydi, DisiplinOlayTuru
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can


DEFAULT_DISIPLIN_TURLERI: tuple[str, ...] = (
    "Geç Kalma",
    "Devamsızlık",
    "Kural İhlali",
    "Davranış Sorunu",
    "Tekrarlayan Uyarı",
)


def seed_disiplin_turleri() -> None:
    for sira, ad in enumerate(DEFAULT_DISIPLIN_TURLERI, start=1):
        DisiplinOlayTuru.objects.update_or_create(
            ad=ad,
            defaults={"sira": sira, "aktif": True},
        )


def aktif_disiplin_turleri() -> QuerySet[DisiplinOlayTuru]:
    return DisiplinOlayTuru.objects.filter(aktif=True).order_by("sira", "ad")


def disiplin_gorebilir(user: User) -> bool:
    return can(user, "disiplin", "view")


def disiplin_duzenleyebilir(user: User) -> bool:
    return can(user, "disiplin", "edit") or can(user, "disiplin", "create")


def yetkili_disiplin_kayitlari(user: User) -> QuerySet[DisiplinKaydi]:
    if not disiplin_gorebilir(user):
        return DisiplinKaydi.objects.none()

    qs = DisiplinKaydi.objects.select_related(
        "talebe",
        "talebe__sinif_sube",
        "tur",
    )

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user, aktif_only=False).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def disiplin_kayitlari_filtrele(
    qs: QuerySet[DisiplinKaydi],
    *,
    q: str | None = None,
    tur_id: str | None = None,
    talebe_id: str | None = None,
) -> QuerySet[DisiplinKaydi]:
    if q:
        qs = qs.filter(
            Q(talebe__ad_soyad__icontains=q)
            | Q(aciklama__icontains=q)
            | Q(sonuc__icontains=q)
        )
    if tur_id:
        qs = qs.filter(tur_id=tur_id)
    if talebe_id:
        qs = qs.filter(talebe_id=talebe_id)
    return qs
