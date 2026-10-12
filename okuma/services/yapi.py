"""Deneme türünden (ör. 7. sınıf · 75 soru) denemenin ders yapısını kurar."""

from django.db import transaction

from okuma.models import Deneme, Test


@transaction.atomic
def yapiyi_kur(deneme: Deneme) -> None:
    tur = deneme.tur
    if tur is None:
        return
    deneme.sonuclar.all().delete()
    deneme.testler.all().delete()
    for d in tur.dersler.all():
        Test.objects.create(
            deneme=deneme,
            ad=f"{d.oturum} · {d.ders}" if d.oturum else d.ders,
            ders=d.ders,
            oturum=d.oturum,
            sira=d.sira,
            soru_sayisi=d.soru_sayisi,
            optik_blok=d.optik_blok,
            katsayi=d.katsayi,
            lgs_ders=d.lgs_ders,
        )
    deneme.sinif_seviyesi = tur.sinif_seviyesi
    deneme.sablon = tur.sablon
    deneme.kitapciklar = "A,B"
    deneme.save(update_fields=["sinif_seviyesi", "sablon", "kitapciklar"])
