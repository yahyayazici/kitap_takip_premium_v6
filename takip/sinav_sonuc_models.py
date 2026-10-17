"""Seviye Tespit — sınav sonuçları ve veliye gönderilen karne dosyası."""

from __future__ import annotations

import os
from decimal import Decimal

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models


class SinavSonucDepolama(FileSystemStorage):
    """Karneler herkese açık URL'den servis edilmez; imzalı bağlantıdaki görünümden verilir."""

    @property
    def base_location(self):
        return self._value_or_setting(self._location, str(settings.SINAV_SONUC_MEDIA_ROOT))

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None


def sinav_sonuc_depolama() -> SinavSonucDepolama:
    return SinavSonucDepolama()


def karne_yolu(sonuc: "SinavSonuc", dosya_adi: str) -> str:
    uzanti = os.path.splitext(dosya_adi)[1].lower()[:6]
    return f"karne/{sonuc.basvuru_id}-{sonuc.karne_surum}{uzanti}"


class SinavSonuc(models.Model):
    basvuru = models.OneToOneField(
        "SinavBasvuru",
        on_delete=models.CASCADE,
        related_name="sonuc",
        verbose_name="Başvuru",
    )
    veri_var = models.BooleanField(default=False, verbose_name="Excel sonucu var")
    excel_ad = models.CharField(max_length=150, blank=True, verbose_name="Excel'deki ad")
    toplam_dogru = models.PositiveSmallIntegerField(default=0)
    toplam_yanlis = models.PositiveSmallIntegerField(default=0)
    toplam_bos = models.PositiveSmallIntegerField(default=0)
    toplam_net = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    puan = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    branslar = models.JSONField(default=dict, blank=True, verbose_name="Ders sonuçları")
    genel_sira = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Genel sıra")
    sinif_sira = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Sınıf sırası")
    karne = models.FileField(
        storage=sinav_sonuc_depolama,
        upload_to=karne_yolu,
        blank=True,
        verbose_name="Karne dosyası",
    )
    karne_adi = models.CharField(max_length=200, blank=True, verbose_name="Yüklenen dosya adı")
    karne_surum = models.PositiveSmallIntegerField(default=0)
    karne_yuklenme = models.DateTimeField(null=True, blank=True)
    gonderilen_surum = models.PositiveSmallIntegerField(default=0)
    gonderim_zamani = models.DateTimeField(null=True, blank=True, verbose_name="Veliye gönderildi")
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Seviye tespit sonucu"
        verbose_name_plural = "Seviye tespit sonuçları"
        ordering = ["genel_sira", "basvuru__ad_soyad"]

    def __str__(self) -> str:
        return f"{self.basvuru.ad_soyad} — {self.toplam_net} net"

    @property
    def karne_gorsel_mi(self) -> bool:
        return os.path.splitext(self.karne.name or "")[1].lower() in {".png", ".jpg", ".jpeg", ".webp"}

    @property
    def gonderildi(self) -> bool:
        return bool(self.gonderim_zamani)

    @property
    def guncel_gonderildi(self) -> bool:
        return bool(self.karne_surum) and self.gonderilen_surum == self.karne_surum
