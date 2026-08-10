"""Yapay zeka üretim kayıtları — önbellek ve denetim."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AiUretimKaydi(models.Model):
    class Tur(models.TextChoices):
        GELISIM_ZEKASI = "gelisim_zekasi", "Gelişim Zekası"
        MUDAHALE_ONERI = "mudahale_oneri", "Müdahale Önerisi"
        VELI_HAFTALIK = "veli_haftalik", "Veli Haftalık Özet"
        DENEME_ANALIZ = "deneme_analiz", "Deneme Analizi"
        REHBERLIK_OZET = "rehberlik_ozet", "Rehberlik Özeti"
        KURUM_ZEKASI = "kurum_zekasi", "Kurum Zekası"
        SORU_TAKIP = "soru_takip", "Soru Takip İçgörüsü"
        VELI_TAKIP = "veli_takip", "Veli Takip Raporu"

    tur = models.CharField(max_length=32, choices=Tur.choices, verbose_name="Tür")
    anahtar = models.CharField(max_length=160, db_index=True, verbose_name="Anahtar")
    icerik = models.JSONField(default=dict, verbose_name="İçerik")
    yapay_zeka = models.BooleanField(default=False, verbose_name="Yapay zeka ile üretildi")
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_uretimleri",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI üretim kaydı"
        verbose_name_plural = "AI üretim kayıtları"
        constraints = [
            models.UniqueConstraint(
                fields=["tur", "anahtar"],
                name="benzersiz_ai_uretim",
            )
        ]
        ordering = ["-guncellenme"]

    def __str__(self) -> str:
        return f"{self.get_tur_display()} · {self.anahtar}"
