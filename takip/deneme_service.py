"""Deneme sorguları ve yardımcılar."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Count, QuerySet

from takip.models import DenemeSinavi, DenemeSonucu, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can

BRANS_ETIKETLERI = {
    "turkce": "Türkçe",
    "matematik": "Matematik",
    "fen": "Fen Bilimleri",
    "sosyal": "Sosyal Bilgiler",
    "din": "Din Kültürü",
    "ingilizce": "İngilizce",
}


def deneme_yukleyebilir(user: User) -> bool:
    from takip.permissions.registry import LEGACY_IDARE_ROLLER
    from takip.permissions.service import kullanici_birincil_rol_slug

    if user.is_superuser:
        return True
    if kullanici_birincil_rol_slug(user) not in LEGACY_IDARE_ROLLER:
        return False
    return can(user, "deneme", "create")


def yetkili_denemeler(user: User) -> QuerySet[DenemeSinavi]:
    if not can(user, "deneme", "view"):
        return DenemeSinavi.objects.none()

    qs = DenemeSinavi.objects.annotate(
        sonuc_sayisi=Count("sonuclar")
    ).order_by("-sinav_tarihi", "-id")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(
        durum=DenemeSinavi.Durum.AKTIF,
        sonuclar__talebe_id__in=talebe_ids,
    ).distinct()


def yetkili_deneme_sonuclari(user: User) -> QuerySet[DenemeSonucu]:
    if not can(user, "deneme", "view"):
        return DenemeSonucu.objects.none()

    qs = DenemeSonucu.objects.select_related(
        "deneme", "talebe", "talebe__sinif_sube"
    ).prefetch_related("brans_satirlari")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def deneme_sonuclari(user: User, deneme: DenemeSinavi) -> QuerySet[DenemeSonucu]:
    qs = yetkili_deneme_sonuclari(user).filter(deneme=deneme)
    return qs.order_by("-toplam_net", "talebe__ad_soyad")


def talebe_deneme_sonuclari(talebe: Talebe) -> QuerySet[DenemeSonucu]:
    return (
        DenemeSonucu.objects.filter(talebe=talebe, deneme__durum=DenemeSinavi.Durum.AKTIF)
        .select_related("deneme")
        .prefetch_related("brans_satirlari")
        .order_by("-deneme__sinav_tarihi", "-id")
    )
