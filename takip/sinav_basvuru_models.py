"""Public sınav başvuru formu modeli."""

from __future__ import annotations

from django.db import models


class SinavBasvuruDurum(models.Model):
    kod = models.SlugField(max_length=40, unique=True, verbose_name="Kod")
    ad = models.CharField(max_length=80, verbose_name="Durum adı")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    mesaj_an_kodu = models.CharField(
        max_length=40,
        blank=True,
        verbose_name="WhatsApp mesaj anı",
        help_text="Bu duruma geçince tetiklenecek mesaj anı kodu (örn. kabul, red).",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sınav başvuru durumu"
        verbose_name_plural = "Sınav başvuru durumları"
        ordering = ["sira", "ad"]

    def __str__(self) -> str:
        return self.ad


def varsayilan_basvuru_durumu():
    durum, _ = SinavBasvuruDurum.objects.get_or_create(
        kod="yeni",
        defaults={"ad": "Yeni", "sira": 1, "aktif": True},
    )
    return durum.pk


class SinavBasvuru(models.Model):
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
    durum = models.ForeignKey(
        SinavBasvuruDurum,
        on_delete=models.PROTECT,
        related_name="basvurular",
        verbose_name="Durum",
        default=varsayilan_basvuru_durumu,
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
