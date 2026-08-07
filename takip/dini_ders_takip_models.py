"""Dini ders takip modelleri — alan, konu, ilerleme kaydı."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class DiniDersTakipAlani(models.Model):
    ad = models.CharField(max_length=120, unique=True, verbose_name="Takip alanı")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dini ders takip alanı"
        verbose_name_plural = "Dini ders takip alanları"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad


class DiniDersKonu(models.Model):
    alan = models.ForeignKey(
        DiniDersTakipAlani,
        on_delete=models.CASCADE,
        related_name="konular",
        verbose_name="Takip alanı",
    )
    seviye = models.ForeignKey(
        "DiniDersSeviyesi",
        on_delete=models.CASCADE,
        related_name="dini_ders_konulari",
        verbose_name="Seviye",
    )
    ad = models.CharField(max_length=200, verbose_name="Konu")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dini ders konusu"
        verbose_name_plural = "Dini ders konuları"
        ordering = ["sira", "ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["alan", "seviye", "ad"],
                name="dini_ders_alan_seviye_konu_benzersiz",
            )
        ]

    def __str__(self):
        return f"{self.alan.ad} · {self.seviye.ad} · {self.ad}"


class DiniDersKonuKaydi(models.Model):
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="dini_ders_konu_kayitlari",
        verbose_name="Talebe",
    )
    konu = models.ForeignKey(
        DiniDersKonu,
        on_delete=models.CASCADE,
        related_name="kayitlar",
        verbose_name="Konu",
    )
    tamamlandi = models.BooleanField(default=False, verbose_name="Tamamlandı")
    personel_notu = models.TextField(blank=True, verbose_name="Not (personel)")
    isaretleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dini_ders_isaretleri",
        verbose_name="İşaretleyen",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dini ders konu kaydı"
        verbose_name_plural = "Dini ders konu kayıtları"
        constraints = [
            models.UniqueConstraint(
                fields=["talebe", "konu"],
                name="dini_ders_talebe_konu_benzersiz",
            )
        ]

    def __str__(self):
        durum = "✅" if self.tamamlandi else "⬜"
        return f"{durum} {self.talebe.ad_soyad} — {self.konu.ad}"
