"""Public sınav başvuru formu modeli."""

from __future__ import annotations

from django.db import models


class SinavBasvuru(models.Model):
    class Durum(models.TextChoices):
        YENI = "yeni", "Yeni"
        INCELENIYOR = "inceleniyor", "İnceleniyor"
        KABUL = "kabul", "Kabul"
        RED = "red", "Red"

    ad_soyad = models.CharField(max_length=150, verbose_name="Ad soyad")
    baba_adi = models.CharField(max_length=100, verbose_name="Baba adı")
    baba_telefon = models.CharField(max_length=20, verbose_name="Baba telefon")
    anne_adi = models.CharField(max_length=100, verbose_name="Anne adı")
    anne_telefon = models.CharField(max_length=20, verbose_name="Anne telefon")
    il = models.CharField(max_length=80, default="İstanbul", verbose_name="İl")
    ilce = models.CharField(max_length=80, verbose_name="İlçe")
    dogum_tarihi = models.DateField(verbose_name="Doğum tarihi")
    sinav_adi = models.CharField(
        max_length=200,
        verbose_name="Sınav adı",
        help_text="Başvuru anındaki sınav başlığı",
    )
    durum = models.CharField(
        max_length=20,
        choices=Durum.choices,
        default=Durum.YENI,
        verbose_name="Durum",
    )
    notlar = models.TextField(blank=True, verbose_name="Yönetim notu")
    olusturulma = models.DateTimeField(auto_now_add=True, verbose_name="Başvuru zamanı")
    guncellenme = models.DateTimeField(auto_now=True, verbose_name="Güncellenme")

    class Meta:
        verbose_name = "Sınav başvurusu"
        verbose_name_plural = "Sınav başvuruları"
        ordering = ["-olusturulma"]

    def __str__(self) -> str:
        return f"{self.ad_soyad} — {self.sinav_adi}"
