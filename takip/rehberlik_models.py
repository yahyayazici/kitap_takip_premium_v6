"""Rehberlik modelleri — premium görüşme takibi."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class GorusmeTuru(models.Model):
    class Grup(models.TextChoices):
        VELI = "veli", "Veli"
        OGRENCI = "ogrenci", "Öğrenci"
        TELEFON = "telefon", "Telefon"
        WHATSAPP = "whatsapp", "WhatsApp"
        AKADEMIK = "akademik", "Akademik"
        DISIPLIN = "disiplin", "Disiplin"
        DIN = "din", "Din Eğitimi"
        GENEL = "genel", "Genel Not"

    class Alan(models.TextChoices):
        REHBERLIK = "rehberlik", "Rehberlik"
        ILETISIM = "iletisim", "Veli & Talebe İletişim"

    ad = models.CharField(max_length=120, verbose_name="Ad")
    kod = models.SlugField(max_length=40, blank=True, verbose_name="Kod")
    grup = models.CharField(
        max_length=20,
        choices=Grup.choices,
        default=Grup.GENEL,
        verbose_name="Grup",
    )
    alan = models.CharField(
        max_length=20,
        choices=Alan.choices,
        default=Alan.REHBERLIK,
        verbose_name="Bölüm",
    )
    ikon = models.CharField(max_length=8, default="💬", verbose_name="İkon")
    renk = models.CharField(max_length=20, default="#3b82f6", verbose_name="Renk")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Görüşme türü"
        verbose_name_plural = "Görüşme türleri"
        ordering = ["sira", "ad"]

    def __str__(self) -> str:
        return self.ad


class OgrenciGorusmesi(models.Model):
    class GenelDurum(models.TextChoices):
        IYI = "iyi", "İyi Durumda"
        TAKIP = "takip", "Takip Gerekiyor"
        RISK = "risk", "Riskli"
        PASIF = "pasif", "Pasif"

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="rehberlik_gorusmeleri",
        verbose_name="Talebe",
    )
    tur = models.ForeignKey(
        GorusmeTuru,
        on_delete=models.PROTECT,
        related_name="gorusmeler",
        verbose_name="Görüşme türü",
    )
    kaydeden = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rehberlik_gorusmeleri",
        verbose_name="Kaydeden",
    )
    tarih = models.DateField(verbose_name="Tarih")
    saat = models.TimeField(null=True, blank=True, verbose_name="Saat")
    ozet = models.CharField(max_length=200, verbose_name="Özet")
    detay = models.TextField(blank=True, verbose_name="Detay")
    kararlar = models.TextField(blank=True, verbose_name="Alınan kararlar")
    yapilacaklar = models.JSONField(default=list, blank=True, verbose_name="Yapılacaklar")
    etiketler = models.JSONField(default=list, blank=True, verbose_name="Etiketler")
    veli_goster = models.BooleanField(default=False, verbose_name="Veliye göster")
    takip_gerekiyor = models.BooleanField(default=False, verbose_name="Takip gerekiyor")
    genel_durum = models.CharField(
        max_length=12,
        choices=GenelDurum.choices,
        default=GenelDurum.IYI,
        verbose_name="Genel durum",
    )
    sonraki_gorusme = models.DateField(null=True, blank=True, verbose_name="Sonraki görüşme")
    sonraki_gorusme_saat = models.TimeField(null=True, blank=True, verbose_name="Sonraki görüşme saati")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Öğrenci görüşmesi"
        verbose_name_plural = "Öğrenci görüşmeleri"
        ordering = ["-tarih", "-saat", "-id"]

    def __str__(self) -> str:
        return f"{self.talebe.ad_soyad} — {self.tur.ad} ({self.tarih:%d.%m.%Y})"


class GorusmeGorevi(models.Model):
    class Durum(models.TextChoices):
        BEKLIYOR = "bekliyor", "Bekliyor"
        DEVAM = "devam", "Devam Ediyor"
        TAMAM = "tamam", "Tamamlandı"

    gorusme = models.ForeignKey(
        OgrenciGorusmesi,
        on_delete=models.CASCADE,
        related_name="gorevler",
        verbose_name="Görüşme",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="rehberlik_gorevleri",
        verbose_name="Talebe",
    )
    baslik = models.CharField(max_length=200, verbose_name="Görev")
    sorumlu = models.CharField(max_length=120, blank=True, verbose_name="Sorumlu")
    durum = models.CharField(
        max_length=12,
        choices=Durum.choices,
        default=Durum.BEKLIYOR,
        verbose_name="Durum",
    )
    tamamlandi = models.BooleanField(default=False, verbose_name="Tamamlandı")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Görüşme görevi"
        verbose_name_plural = "Görüşme görevleri"
        ordering = ["tamamlandi", "-olusturulma"]


class GorusmeDosyasi(models.Model):
    class DosyaTuru(models.TextChoices):
        PDF = "pdf", "PDF"
        FOTO = "foto", "Fotoğraf"
        SES = "ses", "Ses Kaydı"
        DIGER = "diger", "Diğer"

    gorusme = models.ForeignKey(
        OgrenciGorusmesi,
        on_delete=models.CASCADE,
        related_name="dosyalar",
        verbose_name="Görüşme",
    )
    ad = models.CharField(max_length=160, blank=True, verbose_name="Dosya adı")
    dosya = models.FileField(upload_to="rehberlik/%Y/%m/", verbose_name="Dosya")
    tur = models.CharField(
        max_length=12,
        choices=DosyaTuru.choices,
        default=DosyaTuru.DIGER,
        verbose_name="Tür",
    )
    yukleyen = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rehberlik_dosyalari",
        verbose_name="Yükleyen",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Görüşme dosyası"
        verbose_name_plural = "Görüşme dosyaları"
        ordering = ["-olusturulma"]
