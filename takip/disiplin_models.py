"""Disiplin modelleri."""

from __future__ import annotations

from django.db import models


class DisiplinOlayTuru(models.Model):
    ad = models.CharField(max_length=120, verbose_name="Ad")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Disiplin olay türü"
        verbose_name_plural = "Disiplin olay türleri"
        ordering = ["sira", "ad"]

    def __str__(self) -> str:
        return self.ad


class DisiplinKaydi(models.Model):
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="disiplin_kayitlari",
        verbose_name="Talebe",
    )
    tur = models.ForeignKey(
        DisiplinOlayTuru,
        on_delete=models.PROTECT,
        related_name="kayitlar",
        verbose_name="Olay türü",
    )
    tarih = models.DateField(verbose_name="Tarih")
    aciklama = models.TextField(verbose_name="Açıklama")
    sonuc = models.TextField(blank=True, verbose_name="Sonuç")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Disiplin kaydı"
        verbose_name_plural = "Disiplin kayıtları"
        ordering = ["-tarih", "-id"]

    def __str__(self) -> str:
        return f"{self.talebe.ad_soyad} — {self.tur.ad} ({self.tarih:%d.%m.%Y})"
