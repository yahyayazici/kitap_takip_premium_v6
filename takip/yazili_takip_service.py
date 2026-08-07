"""Yazılı takip sorguları ve yardımcılar."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, QuerySet

from takip.models import Talebe, YaziliKamp, YaziliSinav, YaziliSonuc
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can


def yazili_duzenleyebilir(user: User) -> bool:
    return can(user, "yazili_takip", "edit") or can(user, "yazili_takip", "create")


def yetkili_kamplar(user: User) -> QuerySet[YaziliKamp]:
    if not can(user, "yazili_takip", "view"):
        return YaziliKamp.objects.none()

    qs = YaziliKamp.objects.filter(aktif=True).annotate(
        sinav_sayisi=Count("sinavlar"),
        sonuc_sayisi=Count("sinavlar__sonuclar"),
    ).order_by("-baslangic", "-id")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(
        sinavlar__durum=YaziliSinav.Durum.AKTIF,
        sinavlar__sonuclar__talebe_id__in=talebe_ids,
    ).distinct()


def yetkili_sinavlar(user: User, kamp: YaziliKamp | None = None) -> QuerySet[YaziliSinav]:
    if not can(user, "yazili_takip", "view"):
        return YaziliSinav.objects.none()

    qs = YaziliSinav.objects.select_related("kamp").annotate(
        sonuc_sayisi=Count("sonuclar"),
    )

    if kamp:
        qs = qs.filter(kamp=kamp)

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs.order_by("sinav_tarihi", "id")

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(
        durum=YaziliSinav.Durum.AKTIF,
        sonuclar__talebe_id__in=talebe_ids,
    ).distinct().order_by("sinav_tarihi", "id")


def yetkili_yazili_sonuclari(user: User) -> QuerySet[YaziliSonuc]:
    if not can(user, "yazili_takip", "view"):
        return YaziliSonuc.objects.none()

    qs = YaziliSonuc.objects.select_related(
        "sinav",
        "sinav__kamp",
        "talebe",
        "talebe__sinif_sube",
    )

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def sinav_sonuclari(user: User, sinav: YaziliSinav) -> QuerySet[YaziliSonuc]:
    return (
        yetkili_yazili_sonuclari(user)
        .filter(sinav=sinav)
        .order_by("-net", "-puan", "talebe__ad_soyad")
    )


def sinav_sonuclari_sirali(user: User, sinav: YaziliSinav) -> list[dict]:
    sonuclar = list(sinav_sonuclari(user, sinav))
    satirlar = []
    for sira, sonuc in enumerate(sonuclar, start=1):
        satirlar.append({"sira": sira, "sonuc": sonuc})
    return satirlar


def kamp_talebeleri(kamp: YaziliKamp) -> QuerySet[Talebe]:
    from django.db.models import Q

    qs = Talebe.objects.filter(aktif=True).select_related("sinif_sube")
    if kamp.sinif_seviyesi:
        qs = qs.filter(
            Q(sinif=kamp.sinif_seviyesi) | Q(sinif_sube__sinif=kamp.sinif_seviyesi)
        )
    return qs.order_by("ad_soyad")


def sinav_sonuc_talebeleri(user: User, sinav: YaziliSinav) -> QuerySet[Talebe]:
    qs = kamp_talebeleri(sinav.kamp)

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(id__in=talebe_ids)


def sonuc_giris_satirlari(user: User, sinav: YaziliSinav) -> list[dict]:
    talebeler = list(sinav_sonuc_talebeleri(user, sinav))
    mevcut = {
        s.talebe_id: s
        for s in YaziliSonuc.objects.filter(sinav=sinav, talebe__in=talebeler)
    }
    toplam_soru = int(sinav.soru_sayisi or 0)
    satirlar = []
    for talebe in talebeler:
        sonuc = mevcut.get(talebe.id)
        satirlar.append(
            {
                "talebe": talebe,
                "sonuc": sonuc,
                "dogru": sonuc.dogru if sonuc else 0,
                "yanlis": sonuc.yanlis if sonuc else 0,
                "bos": sonuc.bos if sonuc else toplam_soru,
                "net": sonuc.net if sonuc else 0,
                "puan": sonuc.puan if sonuc else 0,
            }
        )
    return satirlar


def sonuclari_toplu_kaydet(
    user: User,
    sinav: YaziliSinav,
    talebeler: list[Talebe],
    post_data,
) -> tuple[int, list[str]]:
    toplam_soru = int(sinav.soru_sayisi or 0)
    if toplam_soru <= 0:
        return 0, ["Sınav soru sayısı geçersiz."]

    hatalar: list[str] = []
    kaydedilen = 0

    with transaction.atomic():
        for talebe in talebeler:
            try:
                dogru = int(post_data.get(f"dogru_{talebe.id}", 0) or 0)
                yanlis = int(post_data.get(f"yanlis_{talebe.id}", 0) or 0)
                bos = int(post_data.get(f"bos_{talebe.id}", 0) or 0)
            except (TypeError, ValueError):
                hatalar.append(f"{talebe.ad_soyad}: Geçerli sayılar girin.")
                continue

            if dogru + yanlis + bos != toplam_soru:
                hatalar.append(
                    f"{talebe.ad_soyad}: Toplam {toplam_soru} olmalı."
                )
                continue

            if dogru == 0 and yanlis == 0 and bos == toplam_soru:
                YaziliSonuc.objects.filter(sinav=sinav, talebe=talebe).delete()
                continue

            YaziliSonuc.objects.update_or_create(
                sinav=sinav,
                talebe=talebe,
                defaults={
                    "dogru": dogru,
                    "yanlis": yanlis,
                    "bos": bos,
                    "kaydeden": user,
                },
            )
            kaydedilen += 1

        if hatalar:
            transaction.set_rollback(True)

    return kaydedilen, hatalar


def talebe_yazili_sonuclari(talebe: Talebe) -> QuerySet[YaziliSonuc]:
    return (
        YaziliSonuc.objects.filter(
            talebe=talebe,
            sinav__durum=YaziliSinav.Durum.AKTIF,
            sinav__kamp__aktif=True,
            sinav__kamp__veli_goster=True,
        )
        .select_related("sinav", "sinav__kamp")
        .order_by("-sinav__sinav_tarihi", "-id")
    )


def kamp_ozet_istatistik(user: User, kamp: YaziliKamp) -> dict:
    sinavlar = list(yetkili_sinavlar(user, kamp))
    toplam_sonuc = sum(s.sonuc_sayisi for s in sinavlar)
    return {
        "sinav_sayisi": len(sinavlar),
        "toplam_sonuc": toplam_sonuc,
    }


def seed_yazili_takip_demo() -> None:
    """Örnek yazılı kamp + sınav sonuçları."""
    from django.utils import timezone

    bugun = timezone.localdate()
    kamp, _ = YaziliKamp.objects.update_or_create(
        ad="Yazılı Kamp Demo",
        defaults={
            "baslangic": bugun - timedelta(days=14),
            "bitis": bugun + timedelta(days=7),
            "sinif_seviyesi": "7",
            "aktif": True,
            "veli_goster": True,
        },
    )
    sinav, _ = YaziliSinav.objects.update_or_create(
        kamp=kamp,
        ad="Matematik Deneme 1",
        defaults={
            "sinav_tarihi": bugun - timedelta(days=3),
            "ders_ad": "Matematik",
            "brans": "Matematik",
            "soru_sayisi": 20,
            "durum": YaziliSinav.Durum.AKTIF,
        },
    )
    for i, talebe in enumerate(Talebe.objects.filter(aktif=True)[:5]):
        dogru = min(17, 12 + i)
        yanlis = 2
        bos = 20 - dogru - yanlis
        YaziliSonuc.objects.update_or_create(
            sinav=sinav,
            talebe=talebe,
            defaults={
                "dogru": dogru,
                "yanlis": yanlis,
                "bos": bos,
            },
        )
