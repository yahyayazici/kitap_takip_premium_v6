"""Yemekçilik listesi dağıtım ve sorgular."""

from __future__ import annotations

from django.utils.timezone import localdate

from .imam_muezzin_service import calisma_gunleri
from .models import Talebe, YemekciAtama, YemekciListesi, YemekOgun


def ogunleri_al(liste: YemekciListesi) -> list[YemekOgun]:
    ogunler = list(liste.ogunler.filter(aktif=True).order_by("sira", "ad"))

    if ogunler:
        return ogunler

    return list(YemekOgun.objects.filter(aktif=True).order_by("sira", "ad"))


def talebe_havuzunu_al(liste: YemekciListesi) -> list[Talebe]:
    havuz = list(
        liste.talebe_havuzu.filter(aktif=True).order_by("sinif", "sube", "ad_soyad")
    )

    if havuz:
        return havuz

    return list(
        Talebe.objects.filter(aktif=True).order_by("sinif", "sube", "ad_soyad")
    )


def otomatik_dagit(liste: YemekciListesi) -> int:
    havuz = talebe_havuzunu_al(liste)
    ogunler = ogunleri_al(liste)

    if not havuz or not ogunler:
        return 0

    gunler = calisma_gunleri(liste)
    liste.atamalar.all().delete()

    talebe_indeks = 0
    yardimci_indeks = 1 if len(havuz) > 1 else 0
    olusturulan = 0

    for gun in gunler:
        for ogun in ogunler:
            talebe = havuz[talebe_indeks % len(havuz)]
            yardimci = havuz[yardimci_indeks % len(havuz)]

            if len(havuz) > 1 and talebe.pk == yardimci.pk:
                yardimci_indeks += 1
                yardimci = havuz[yardimci_indeks % len(havuz)]

            YemekciAtama.objects.create(
                liste=liste,
                tarih=gun,
                ogun=ogun,
                talebe=talebe,
                yardimci=yardimci,
                manuel_duzenlendi=False,
            )
            olusturulan += 1
            talebe_indeks += 1
            yardimci_indeks += 1

    return olusturulan


def bugunun_listesi() -> YemekciListesi | None:
    bugun = localdate()

    return (
        YemekciListesi.objects.filter(
            aktif=True,
            baslangic_tarihi__lte=bugun,
            bitis_tarihi__gte=bugun,
        )
        .order_by("-baslangic_tarihi", "id")
        .first()
    )


def bugunun_atamalari() -> list[YemekciAtama]:
    liste = bugunun_listesi()

    if not liste:
        return []

    return list(
        liste.atamalar.select_related("ogun", "talebe", "yardimci")
        .filter(tarih=localdate())
        .order_by("ogun__sira", "ogun__ad")
    )
