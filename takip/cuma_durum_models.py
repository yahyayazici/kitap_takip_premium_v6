"""Cuma WhatsApp durumu — hadis/söz havuzu (yönetim) + personel stüdyo."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class CumaDurumMetni(models.Model):
    class Sablon(models.TextChoices):
        GECE = "gece", "Gece mavisi"
        ZUMRUT = "zumrut", "Zümrüt yeşili"
        MOR = "mor", "Mor ışık"
        ALTIN = "altin", "Altın şafak"
        LACIVERT = "lacivert", "Lacivert"

    metin = models.TextField(verbose_name="Hadis / söz")
    kaynak = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Kaynak",
        help_text="Örn. Buhari, Müslim, Mevlana",
    )
    sablon = models.CharField(
        max_length=16,
        choices=Sablon.choices,
        default=Sablon.GECE,
        verbose_name="Görsel tema",
    )
    cuma_tarihi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Atanan Cuma",
        help_text="Belirli bir Cuma günü için sabit metin. Boş bırakılırsa otomatik sıradan seçilir.",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_cuma_durum_metinleri",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cuma durum metni"
        verbose_name_plural = "Cuma durum metinleri"
        ordering = ["sira", "-id"]

    def __str__(self) -> str:
        ozet = (self.metin[:60] + "…") if len(self.metin) > 60 else self.metin
        if self.cuma_tarihi:
            return f"{self.cuma_tarihi:%d.%m.%Y} · {ozet}"
        return ozet
