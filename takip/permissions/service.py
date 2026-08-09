"""Merkezi yetki kontrol servisi."""

from __future__ import annotations

from functools import lru_cache

from django.contrib.auth.models import User

from takip.models import KullaniciRol, KullaniciYetkiOverride, PersonelProfili, Rol

from .registry import (
    ADMIN_ONLY_EDIT_MODULES,
    DEFAULT_VIEW_ONLY_MODULES,
    LEGACY_IDARE_ROLLER,
    LEGACY_ROL_MODULLER,
    LEGACY_TUM_TALEBE_ROLLER,
)


def _personel_profili(user: User) -> PersonelProfili | None:
    if not user.is_authenticated:
        return None

    try:
        profil = user.personel_profili
    except PersonelProfili.DoesNotExist:
        return None

    if profil.aktif:
        return profil

    return None


def kullanici_birincil_rol_slug(user: User) -> str | None:
    if not user.is_authenticated:
        return None

    if user.is_superuser:
        return "idareci"

    birincil = (
        KullaniciRol.objects.filter(user=user, birincil=True)
        .select_related("rol")
        .first()
    )
    if birincil and birincil.rol.aktif:
        return birincil.rol.slug

    profil = _personel_profili(user)
    if profil:
        if profil.rol_id and profil.rol.aktif:
            return profil.rol.slug
        return profil.ana_rol

    if hasattr(user, "etut_profili"):
        hoca = user.etut_profili
        if hoca and getattr(hoca, "aktif", True):
            return "etut_mesul"

    return None


def kullanici_rol_slugleri(user: User) -> frozenset[str]:
    if not user.is_authenticated:
        return frozenset()

    slugler: set[str] = set()

    for kr in KullaniciRol.objects.filter(user=user).select_related("rol"):
        if kr.rol.aktif:
            slugler.add(kr.rol.slug)

    birincil = kullanici_birincil_rol_slug(user)
    if birincil:
        slugler.add(birincil)

    return frozenset(slugler)


@lru_cache(maxsize=256)
def _rol_modul_erisim_cached(rol_slug: str, modul_kod: str) -> bool | None:
    try:
        rol = Rol.objects.get(slug=rol_slug, aktif=True)
    except Rol.DoesNotExist:
        return None

    kayit = rol.modul_erisimleri.filter(modul__kod=modul_kod).first()
    if kayit is None:
        return None
    return kayit.erisim


def _legacy_modul_erisim(rol_slug: str | None, modul_kod: str) -> bool:
    if not rol_slug:
        return False

    moduller = LEGACY_ROL_MODULLER.get(rol_slug, frozenset())
    return modul_kod in moduller


def _legacy_islem_izin(rol_slug: str | None, modul_kod: str, islem_kod: str) -> bool:
    if not _legacy_modul_erisim(rol_slug, modul_kod):
        return False

    if islem_kod == "view":
        return True

    if modul_kod in ADMIN_ONLY_EDIT_MODULES and islem_kod in {
        "create",
        "edit",
        "delete",
    }:
        return rol_slug in LEGACY_IDARE_ROLLER

    if modul_kod in DEFAULT_VIEW_ONLY_MODULES:
        return islem_kod == "view"

    if islem_kod in {"export_pdf", "export_excel"}:
        if modul_kod == "egitim_kitap" and rol_slug in {"etut_mesul", "sinif_mesul"}:
            return True
        if modul_kod in {
            "ktt",
            "deneme",
            "yazili_takip",
            "soru_takip",
            "akademik_mudahale",
        } and rol_slug in {"etut_mesul", "sinif_mesul", "egitim_mesul"}:
            return _legacy_modul_erisim(rol_slug, modul_kod)
        # Yoklama modülleri — modül erişimi olan herkes filtreli rapor indirebilir
        if modul_kod in {"pazar_izin_donus", "namaz_yoklama", "gunluk_takip"}:
            return _legacy_modul_erisim(rol_slug, modul_kod)
        return rol_slug in LEGACY_TUM_TALEBE_ROLLER or rol_slug in LEGACY_IDARE_ROLLER or rol_slug == "muhasebeci"

    if islem_kod == "view_financial":
        return rol_slug in LEGACY_IDARE_ROLLER or rol_slug == "muhasebeci"

    if islem_kod == "delete":
        return rol_slug in LEGACY_IDARE_ROLLER

    if islem_kod in {"create", "edit"}:
        return rol_slug not in {"muhasebeci"}

    return True


def _override_etki(user: User, modul_kod: str, islem_kod: str) -> str | None:
    override = (
        KullaniciYetkiOverride.objects.filter(
            user=user,
            modul__kod=modul_kod,
            islem_kod=islem_kod,
        )
        .values_list("etki", flat=True)
        .first()
    )
    return override


def _rbac_islem_izin(user: User, modul_kod: str, islem_kod: str) -> bool | None:
    slugler = kullanici_rol_slugleri(user)
    if not slugler:
        return None

    deny = _override_etki(user, modul_kod, islem_kod)
    if deny == KullaniciYetkiOverride.Etki.DENY:
        return False

    grant_override = (
        KullaniciYetkiOverride.objects.filter(
            user=user,
            modul__kod=modul_kod,
            islem_kod=islem_kod,
            etki=KullaniciYetkiOverride.Etki.GRANT,
        ).exists()
    )

    for slug in slugler:
        cached = _rol_modul_erisim_cached(slug, modul_kod)
        if cached is False:
            continue
        if cached is None and not _legacy_modul_erisim(slug, modul_kod):
            continue

        try:
            rol = Rol.objects.get(slug=slug, aktif=True)
        except Rol.DoesNotExist:
            if _legacy_islem_izin(slug, modul_kod, islem_kod):
                return True
            continue

        izin = rol.islem_yetkileri.filter(
            islem__modul__kod=modul_kod,
            islem__kod=islem_kod,
            izin=True,
        ).exists()
        if izin:
            return True

        if _legacy_islem_izin(slug, modul_kod, islem_kod):
            return True

    if grant_override:
        return True

    return None


def can(user: User, modul_kod: str, islem_kod: str = "view") -> bool:
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    rbac = _rbac_islem_izin(user, modul_kod, islem_kod)
    if rbac is not None:
        return rbac

    slug = kullanici_birincil_rol_slug(user)
    return _legacy_islem_izin(slug, modul_kod, islem_kod)


def modul_erisimi_var(user: User, modul_kod: str) -> bool:
    return can(user, modul_kod, "view")


def clear_permission_cache() -> None:
    _rol_modul_erisim_cached.cache_clear()
