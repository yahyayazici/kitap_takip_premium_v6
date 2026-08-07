"""Talebe erişim kapsamı."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet

from takip.models import Talebe

from .registry import LEGACY_TUM_TALEBE_ROLLER
from .service import can, kullanici_birincil_rol_slug, kullanici_rol_slugleri
from takip.user_helpers import etut_hocasi_for_user


def tum_talebe_kapsami_var(user: User) -> bool:
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    slugler = kullanici_rol_slugleri(user)
    if slugler:
        from takip.models import Rol, RolKapsam

        for rol in Rol.objects.filter(slug__in=slugler, aktif=True).prefetch_related(
            "kapsamlar"
        ):
            for kapsam in rol.kapsamlar.all():
                if kapsam.tip == RolKapsam.KapsamTipi.TUM:
                    return True
        if any(s in LEGACY_TUM_TALEBE_ROLLER for s in slugler):
            return True
        return False

    slug = kullanici_birincil_rol_slug(user)
    return slug in LEGACY_TUM_TALEBE_ROLLER if slug else False


def yetkili_talebeler(user: User, *, aktif_only: bool = True) -> QuerySet[Talebe]:
    talebeler = Talebe.objects.all()

    if aktif_only:
        talebeler = talebeler.filter(durum=Talebe.Durum.AKTIF)

    if not user.is_authenticated:
        return Talebe.objects.none()

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return talebeler

    slugler = kullanici_rol_slugleri(user)
    if slugler:
        from takip.models import Rol, RolKapsam

        sinif_ids: set[int] = set()
        seviye_ids: set[int] = set()
        etut_grubu = False

        for rol in Rol.objects.filter(slug__in=slugler, aktif=True).prefetch_related(
            "kapsamlar"
        ):
            for kapsam in rol.kapsamlar.all():
                if kapsam.tip == RolKapsam.KapsamTipi.TUM:
                    return talebeler
                if kapsam.tip == RolKapsam.KapsamTipi.ETUT_GRUBU:
                    etut_grubu = True
                if kapsam.tip == RolKapsam.KapsamTipi.SINIF_LISTESI:
                    sinif_ids.update(kapsam.deger.get("sinif_sube_ids", []))
                if kapsam.tip == RolKapsam.KapsamTipi.DINI_SEVIYE:
                    seviye_ids.update(kapsam.deger.get("dini_ders_seviyesi_ids", []))

        kosullar = Q()
        if etut_grubu:
            hoca = etut_hocasi_for_user(user)
            if hoca:
                kosullar |= Q(etut_hocasi=hoca) | Q(dini_ders_hocasi=hoca)
        if sinif_ids:
            kosullar |= Q(sinif_sube_id__in=sinif_ids)
        if seviye_ids:
            kosullar |= Q(dini_ders_seviyesi_id__in=seviye_ids)

        if kosullar:
            return talebeler.filter(kosullar).distinct()

    hoca = etut_hocasi_for_user(user)
    if hoca:
        return talebeler.filter(
            Q(etut_hocasi=hoca) | Q(dini_ders_hocasi=hoca)
        )

    return Talebe.objects.none()


def yonetim_kapsami_var(user: User) -> bool:
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if can(user, "yonetim", "view") or can(user, "rbac", "view"):
        return True

    slug = kullanici_birincil_rol_slug(user)
    from .registry import LEGACY_IDARE_ROLLER

    return slug in LEGACY_IDARE_ROLLER if slug else False
