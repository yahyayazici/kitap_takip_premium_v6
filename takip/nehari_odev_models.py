"""Nehari hoca günlük ödevi — gün bazında metin ve talebe işareti."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class NehariGunlukOdev(models.Model):
    """O gün bütün nehari listesinde görünen tek ödev metni."""

    tarih = models.DateField(unique=True, verbose_name="Tarih")
    metin = models.CharField(max_length=300, verbose_name="Günün ödevi")
    guncelleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nehari_odev_metinleri",
        verbose_name="Güncelleyen",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Nehari günlük ödev"
        verbose_name_plural = "Nehari günlük ödevler"
        ordering = ["-tarih"]

    def __str__(self) -> str:
        return f"{self.tarih:%d.%m.%Y} — {self.metin}"


class NehariOdevIsaret(models.Model):
    """Talebenin o günkü ödevi. Kayıt yoksa yapılmadı sayılır."""

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="nehari_odev_isaretleri",
        verbose_name="Talebe",
    )
    tarih = models.DateField(verbose_name="Tarih")
    yapildi = models.BooleanField(default=False, verbose_name="Yapıldı")
    isaretleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nehari_odev_isaretleri",
        verbose_name="İşaretleyen",
    )
    isaretlenme = models.DateTimeField(auto_now=True, verbose_name="İşaretlenme")

    class Meta:
        verbose_name = "Nehari ödev işareti"
        verbose_name_plural = "Nehari ödev işaretleri"
        ordering = ["-tarih", "talebe__ad_soyad"]
        constraints = [
            models.UniqueConstraint(
                fields=["talebe", "tarih"],
                name="benzersiz_nehari_odev_talebe_tarih",
            )
        ]

    def __str__(self) -> str:
        durum = "yapıldı" if self.yapildi else "yapılmadı"
        return f"{self.talebe.ad_soyad} — {self.tarih:%d.%m.%Y} ({durum})"
