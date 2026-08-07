"""Aidat takip modelleri."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models

from takip.wave0_models import EgitimYili


class AidatTanim(models.Model):
    egitim_yili = models.ForeignKey(
        EgitimYili,
        on_delete=models.CASCADE,
        related_name="aidat_tanimlari",
        verbose_name="Eğitim yılı",
    )
    ad = models.CharField(max_length=120, verbose_name="Ad")
    tutar = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Tutar",
    )
    vade = models.DateField(verbose_name="Vade")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Aidat tanımı"
        verbose_name_plural = "Aidat tanımları"
        ordering = ["-vade", "ad"]

    def __str__(self) -> str:
        return f"{self.ad} — {self.tutar} ₺"


class TalebeAidatKaydi(models.Model):
    class Durum(models.TextChoices):
        BEKLIYOR = "bekliyor", "Bekliyor"
        ODENDI = "odendi", "Ödendi"
        KISMI = "kismi", "Kısmi"
        GECIKMIS = "gecikmis", "Gecikmiş"
        MUAF = "muaf", "Muaf"

    tanim = models.ForeignKey(
        AidatTanim,
        on_delete=models.PROTECT,
        related_name="kayitlar",
        verbose_name="Aidat tanımı",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="aidat_kayitlari",
        verbose_name="Talebe",
    )
    durum = models.CharField(
        max_length=10,
        choices=Durum.choices,
        default=Durum.BEKLIYOR,
        verbose_name="Durum",
    )
    odenen_tutar = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Ödenen tutar",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Talebe aidat kaydı"
        verbose_name_plural = "Talebe aidat kayıtları"
        ordering = ["-tanim__vade", "talebe__ad_soyad"]
        constraints = [
            models.UniqueConstraint(
                fields=["tanim", "talebe"],
                name="benzersiz_talebe_aidat_tanim",
            )
        ]

    def __str__(self) -> str:
        return f"{self.talebe.ad_soyad} — {self.tanim.ad}"

    @property
    def borc_tutari(self) -> Decimal:
        if self.durum == self.Durum.MUAF:
            return Decimal("0.00")
        kalan = self.tanim.tutar - self.odenen_tutar
        return max(kalan, Decimal("0.00"))


class AidatTahsilat(models.Model):
    kayit = models.ForeignKey(
        TalebeAidatKaydi,
        on_delete=models.PROTECT,
        related_name="tahsilatlar",
        verbose_name="Aidat kaydı",
    )
    tutar = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Tutar",
    )
    tarih = models.DateField(verbose_name="Tarih")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_aidat_tahsilatlari",
        verbose_name="Kaydeden",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Aidat tahsilat"
        verbose_name_plural = "Aidat tahsilatları"
        ordering = ["-tarih", "-id"]

    def __str__(self) -> str:
        return f"{self.kayit} — {self.tutar} ₺ ({self.tarih:%d.%m.%Y})"
