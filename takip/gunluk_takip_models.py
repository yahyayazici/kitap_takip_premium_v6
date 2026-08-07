"""Günlük takip modelleri."""

from __future__ import annotations

from django.db import models


class GunlukTakipKaydi(models.Model):
    class DevamDurumu(models.TextChoices):
        GELDI = "geldi", "Geldi"
        GEC = "gec", "Geç"
        GELMEDI = "gelmedi", "Gelmedi"

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="gunluk_takip_kayitlari",
        verbose_name="Talebe",
    )
    tarih = models.DateField(verbose_name="Tarih")
    devam = models.CharField(
        max_length=10,
        choices=DevamDurumu.choices,
        default=DevamDurumu.GELDI,
        verbose_name="Devam",
    )
    etut_katilim = models.BooleanField(default=True, verbose_name="Etüt katılım")
    not_alani = models.TextField(blank=True, verbose_name="Not")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Günlük takip kaydı"
        verbose_name_plural = "Günlük takip kayıtları"
        ordering = ["-tarih", "talebe__ad_soyad"]
        constraints = [
            models.UniqueConstraint(
                fields=["talebe", "tarih"],
                name="benzersiz_gunluk_takip_talebe_tarih",
            )
        ]

    def __str__(self) -> str:
        return f"{self.talebe.ad_soyad} — {self.tarih:%d.%m.%Y} ({self.get_devam_display()})"
