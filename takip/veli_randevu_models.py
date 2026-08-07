"""Veli randevu sistemi modelleri."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class RandevuPersonelAyar(models.Model):
    personel = models.OneToOneField(
        "PersonelProfili",
        on_delete=models.CASCADE,
        related_name="randevu_ayari",
        verbose_name="Personel",
    )
    aktif = models.BooleanField(default=False, verbose_name="Randevu alabilir")
    sure_dk = models.PositiveSmallIntegerField(default=30, verbose_name="Görüşme süresi (dk)")
    aciklama = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Veliye gösterilen açıklama",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Randevu personel ayarı"
        verbose_name_plural = "Randevu personel ayarları"

    def __str__(self) -> str:
        return f"{self.personel.ad_soyad} — Randevu"


class RandevuMusaitlik(models.Model):
    class HaftaGunu(models.IntegerChoices):
        PZT = 0, "Pazartesi"
        SAL = 1, "Salı"
        CAR = 2, "Çarşamba"
        PER = 3, "Perşembe"
        CUM = 4, "Cuma"
        CMT = 5, "Cumartesi"
        PAZ = 6, "Pazar"

    personel = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.CASCADE,
        related_name="randevu_musaitlikleri",
        verbose_name="Personel",
    )
    hafta_gunu = models.PositiveSmallIntegerField(
        choices=HaftaGunu.choices,
        verbose_name="Gün",
    )
    baslangic = models.TimeField(verbose_name="Başlangıç")
    bitis = models.TimeField(verbose_name="Bitiş")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Randevu müsaitliği"
        verbose_name_plural = "Randevu müsaitlikleri"
        ordering = ["hafta_gunu", "baslangic"]

    def __str__(self) -> str:
        return f"{self.personel.ad_soyad} · {self.get_hafta_gunu_display()} {self.baslangic:%H:%M}-{self.bitis:%H:%M}"


class VeliRandevu(models.Model):
    class Durum(models.TextChoices):
        PLANLANDI = "planlandi", "Planlandı"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"
        IPTAL_VELI = "iptal_veli", "Veli İptal"
        IPTAL_PERSONEL = "iptal_personel", "Personel İptal"

    veli = models.ForeignKey(
        "VeliHesap",
        on_delete=models.CASCADE,
        related_name="randevulari",
        verbose_name="Veli",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="veli_randevulari",
        verbose_name="Talebe",
    )
    personel = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.PROTECT,
        related_name="veli_randevulari",
        verbose_name="Personel",
    )
    tarih = models.DateField(verbose_name="Tarih")
    baslangic = models.TimeField(verbose_name="Başlangıç")
    bitis = models.TimeField(verbose_name="Bitiş")
    konu = models.CharField(max_length=255, blank=True, verbose_name="Konu")
    durum = models.CharField(
        max_length=20,
        choices=Durum.choices,
        default=Durum.PLANLANDI,
    )
    gorusme = models.ForeignKey(
        "OgrenciGorusmesi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="veli_randevulari",
        verbose_name="Görüşme kaydı",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Veli randevusu"
        verbose_name_plural = "Veli randevuları"
        ordering = ["tarih", "baslangic"]
        constraints = [
            models.UniqueConstraint(
                fields=["personel", "tarih", "baslangic"],
                name="benzersiz_personel_randevu_slot",
            )
        ]

    def __str__(self) -> str:
        return f"{self.talebe.ad_soyad} · {self.personel.ad_soyad} · {self.tarih:%d.%m.%Y} {self.baslangic:%H:%M}"
