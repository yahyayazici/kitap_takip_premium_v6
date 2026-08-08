"""Temizlik listesi dağıtım ve sorgular."""

from __future__ import annotations

from django.utils.timezone import localdate

from .imam_muezzin_service import calisma_gunleri, parse_haric_tarih_metni
from .models import Talebe, TemizlikAlani, TemizlikAtama, TemizlikListesi

__all__ = ["parse_haric_tarih_metni", "calisma_gunleri"]


def alanlari_al(liste: TemizlikListesi) -> list[TemizlikAlani]:
    alanlar = list(
        liste.alanlar.filter(aktif=True).order_by("sira", "ad")
    )

    if alanlar:
        return alanlar

    return list(TemizlikAlani.objects.filter(aktif=True).order_by("sira", "ad"))


def talebe_havuzunu_al(liste: TemizlikListesi) -> list[Talebe]:
    havuz = list(
        liste.talebe_havuzu.filter(aktif=True).order_by("sinif", "sube", "ad_soyad")
    )

    if havuz:
        return havuz

    return list(
        Talebe.objects.filter(aktif=True).order_by("sinif", "sube", "ad_soyad")
    )


def otomatik_dagit(liste: TemizlikListesi) -> int:
    havuz = talebe_havuzunu_al(liste)
    alanlar = alanlari_al(liste)

    if not havuz or not alanlar:
        return 0

    gunler = calisma_gunleri(liste)
    liste.atamalar.all().delete()

    talebe_indeks = 0
    olusturulan = 0

    for gun in gunler:
        for alan in alanlar:
            talebe = havuz[talebe_indeks % len(havuz)]
            TemizlikAtama.objects.create(
                liste=liste,
                tarih=gun,
                alan=alan,
                talebe=talebe,
                manuel_duzenlendi=False,
            )
            olusturulan += 1
            talebe_indeks += 1

    return olusturulan


def bugunun_listesi() -> TemizlikListesi | None:
    bugun = localdate()

    return (
        TemizlikListesi.objects.filter(
            aktif=True,
            baslangic_tarihi__lte=bugun,
            bitis_tarihi__gte=bugun,
        )
        .order_by("-baslangic_tarihi", "id")
        .first()
    )


def aktif_temizlik_listesi() -> TemizlikListesi | None:
    """Yönetim ve personel için varsayılan liste (yayındaki veya en güncel)."""
    liste = bugunun_listesi()
    if liste:
        return liste
    return (
        TemizlikListesi.objects.filter(aktif=True)
        .order_by("-baslangic_tarihi", "-id")
        .first()
    )


def temizlik_listesi_olustur_veya_al(user=None) -> TemizlikListesi:
    """Liste yoksa tek bir aktif yönetim listesi oluşturur."""
    liste = aktif_temizlik_listesi()
    if liste:
        return liste

    from datetime import timedelta

    bugun = localdate()
    liste = TemizlikListesi.objects.create(
        ad="Temizlik Yönetimi",
        baslangic_tarihi=bugun - timedelta(days=bugun.weekday()),
        bitis_tarihi=bugun + timedelta(days=120),
        aktif=True,
        olusturan=user if getattr(user, "is_authenticated", False) else None,
    )
    try:
        from takip.temizlik_yonetim_service import katlari_hazirla

        katlari_hazirla(liste)
    except Exception:
        pass
    return liste


def bugunun_atamalari() -> list[TemizlikAtama]:
    liste = bugunun_listesi()

    if not liste:
        return []

    return list(
        liste.atamalar.select_related("alan", "alan__kat", "talebe")
        .filter(tarih=localdate())
        .order_by("alan__kat__sira", "alan__sira", "alan__ad")
    )


def kullanici_kat_sorumluluklari(user) -> list:
    """Etüt hocasının sorumlu olduğu temizlik katları."""
    from django.contrib.auth.models import User

    from .models import TemizlikKatSorumlusu

    if not isinstance(user, User) or not user.is_authenticated:
        return []

    return list(
        TemizlikKatSorumlusu.objects.filter(personel=user)
        .select_related("kat", "kat__liste")
        .order_by("kat__sira", "kat__ad")
    )


def temizlik_kat_sorumlusu_mu(user) -> bool:
    return bool(kullanici_kat_sorumluluklari(user))


def bugunun_atamalari_kullanici(user) -> list[TemizlikAtama]:
    """Kat sorumlusu yalnızca kendi katındaki mahalleri görür; zimmet yoksa boş."""
    atamalar = bugunun_atamalari()
    if not atamalar:
        return []

    from takip.permissions.service import kullanici_birincil_rol_slug
    from takip.permissions.registry import LEGACY_IDARE_ROLLER

    if user.is_superuser:
        return atamalar

    rol = kullanici_birincil_rol_slug(user)
    if rol in LEGACY_IDARE_ROLLER or rol in {"egitim_mesul", "sinif_mesul"}:
        return atamalar

    kat_ids = {s.kat_id for s in kullanici_kat_sorumluluklari(user)}
    if not kat_ids:
        return []

    return [
        a
        for a in atamalar
        if a.alan_id and a.alan.kat_id in kat_ids
    ]
