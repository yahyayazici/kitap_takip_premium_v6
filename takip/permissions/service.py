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


def _req_cache(user: User) -> dict:
    """İstek (request) ömrüne bağlı, ``user`` nesnesi üzerinde tutulan hafif
    bir önbellek. ``request.user`` her istekte yeniden oluşturulan tek bir
    nesne olduğundan (Django AuthenticationMiddleware), buraya eklenen
    değerler istekler arası SIZMAZ — istek bitip nesne çöpe gidince kaybolur.

    Bu, tek bir sayfa render'ında (özellikle nav menüsü oluştururken)
    ``can()``/rol sorgularının onlarca kez tekrar tekrar DB'ye gitmesini
    önlemek için var; performans kritik bir noktadır, dokunurken dikkatli
    olun.
    """
    cache = getattr(user, "_yetki_req_cache", None)
    if cache is None:
        cache = {}
        try:
            user._yetki_req_cache = cache
        except AttributeError:
            return {}
    return cache


def kullanici_birincil_rol_slug(user: User) -> str | None:
    if not user.is_authenticated:
        return None

    if user.is_superuser:
        return "idareci"

    cache = _req_cache(user)
    if "birincil_rol" in cache:
        return cache["birincil_rol"]

    sonuc = _kullanici_birincil_rol_slug_hesapla(user)
    cache["birincil_rol"] = sonuc
    return sonuc


def _kullanici_birincil_rol_slug_hesapla(user: User) -> str | None:
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

    cache = _req_cache(user)
    if "rol_slugleri" in cache:
        return cache["rol_slugleri"]

    slugler: set[str] = set()

    for kr in KullaniciRol.objects.filter(user=user).select_related("rol"):
        if kr.rol.aktif:
            slugler.add(kr.rol.slug)

    birincil = kullanici_birincil_rol_slug(user)
    if birincil:
        slugler.add(birincil)

    sonuc = frozenset(slugler)
    cache["rol_slugleri"] = sonuc
    return sonuc


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


@lru_cache(maxsize=1024)
def _rol_islem_izni_cached(rol_slug: str, modul_kod: str, islem_kod: str) -> bool | None:
    """Bir rolün bir modül+işlem için AÇIK izin kaydı olup olmadığı.

    Rol tanımları (RolIslemYetki) nadiren değişir — süreç ömrü boyunca
    process-wide cache'lenir (``_rol_modul_erisim_cached`` ile aynı desen).
    Rol bulunamazsa None döner ki çağıran taraf legacy fallback'e düşebilsin.
    """
    try:
        rol = Rol.objects.get(slug=rol_slug, aktif=True)
    except Rol.DoesNotExist:
        return None

    return rol.islem_yetkileri.filter(
        islem__modul__kod=modul_kod,
        islem__kod=islem_kod,
        izin=True,
    ).exists()


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
            "olcme",
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
    """(user, modul, işlem) için tanımlı override etkisi (DENY/GRANT), varsa.

    Tek sorguda hem DENY hem GRANT kontrolü için kullanılır (önceden ayrı
    ayrı iki sorguydu).
    """
    return (
        KullaniciYetkiOverride.objects.filter(
            user=user,
            modul__kod=modul_kod,
            islem_kod=islem_kod,
        )
        .values_list("etki", flat=True)
        .first()
    )


def _rbac_islem_izin(user: User, modul_kod: str, islem_kod: str) -> bool | None:
    slugler = kullanici_rol_slugleri(user)
    if not slugler:
        return None

    etki = _override_etki(user, modul_kod, islem_kod)
    if etki == KullaniciYetkiOverride.Etki.DENY:
        return False
    grant_override = etki == KullaniciYetkiOverride.Etki.GRANT

    for slug in slugler:
        cached = _rol_modul_erisim_cached(slug, modul_kod)
        if cached is False:
            continue
        if cached is None and not _legacy_modul_erisim(slug, modul_kod):
            continue

        izin = _rol_islem_izni_cached(slug, modul_kod, islem_kod)
        if izin is None:
            if _legacy_islem_izin(slug, modul_kod, islem_kod):
                return True
            continue
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

    cache = _req_cache(user)
    key = (modul_kod, islem_kod)
    can_cache = cache.setdefault("can", {})
    if key in can_cache:
        return can_cache[key]

    sonuc = _can_hesapla(user, modul_kod, islem_kod)
    can_cache[key] = sonuc
    return sonuc


def _can_hesapla(user: User, modul_kod: str, islem_kod: str) -> bool:
    rbac = _rbac_islem_izin(user, modul_kod, islem_kod)
    if rbac is not None:
        return rbac

    slug = kullanici_birincil_rol_slug(user)
    return _legacy_islem_izin(slug, modul_kod, islem_kod)


def modul_erisimi_var(user: User, modul_kod: str) -> bool:
    return can(user, modul_kod, "view")


def clear_permission_cache() -> None:
    _rol_modul_erisim_cached.cache_clear()
    _rol_islem_izni_cached.cache_clear()
