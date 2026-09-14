"""Sabah Beslenmesi — günlük menü, sipariş, teslim ve borç kaydı."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


KURUS = Decimal("0.01")


def para(tutar: Decimal | int | str) -> Decimal:
    return Decimal(str(tutar)).quantize(KURUS, rounding=ROUND_HALF_UP)


class SabahBeslenmeGunlukMenu(models.Model):
    class Durum(models.TextChoices):
        ACIK = "acik", "Açık"
        KAPALI = "kapali", "Kapalı"

    tarih = models.DateField(unique=True, verbose_name="Tarih")
    urun = models.CharField(max_length=80, verbose_name="Beslenme ürünü")
    birim_fiyat = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Birim fiyat",
    )
    siparis_son_saati = models.TimeField(verbose_name="Sipariş son saati")
    durum = models.CharField(
        max_length=12,
        choices=Durum.choices,
        default=Durum.ACIK,
        verbose_name="Sipariş durumu",
    )
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_sabah_beslenme_menuleri",
    )
    guncelleyen = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guncelledigi_sabah_beslenme_menuleri",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sabah beslenmesi günlük menü"
        verbose_name_plural = "Sabah beslenmesi günlük menüler"
        ordering = ["-tarih"]

    def __str__(self) -> str:
        return f"{self.tarih:%d.%m.%Y} · {self.urun}"

    def clean(self):
        if self.birim_fiyat is None or self.birim_fiyat < 0:
            raise ValidationError({"birim_fiyat": "Birim fiyat negatif olamaz."})


class SabahBeslenmeSiparis(models.Model):
    class OdemeTuru(models.TextChoices):
        PESIN = "pesin", "Peşin"
        BORC = "borc", "Borç"

    menu = models.ForeignKey(
        SabahBeslenmeGunlukMenu,
        on_delete=models.CASCADE,
        related_name="siparisler",
        verbose_name="Günlük menü",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.PROTECT,
        related_name="sabah_beslenme_siparisleri",
        verbose_name="Talebe",
    )
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sabah_beslenme_siparisleri",
        verbose_name="Etüt hocası",
    )
    adet = models.PositiveIntegerField(default=0, verbose_name="Adet")
    kaydeden = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_sabah_beslenme_siparisleri",
        verbose_name="Siparişi kaydeden",
    )
    odeme_turu = models.CharField(
        max_length=8,
        choices=OdemeTuru.choices,
        default=OdemeTuru.PESIN,
        verbose_name="Ödeme durumu",
    )
    teslim_edildi = models.BooleanField(default=False, verbose_name="Satış / teslim")
    teslim_saati = models.DateTimeField(null=True, blank=True, verbose_name="Satış saati")
    teslim_eden = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teslim_ettigi_sabah_beslenme_siparisleri",
        verbose_name="Satışı yapan",
    )
    borc_kaydi_olustu = models.BooleanField(
        default=False,
        verbose_name="Borç kaydı oluştu",
    )
    borc_tutari = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Borç tutarı",
    )
    borc_kapatildi = models.BooleanField(default=False, verbose_name="Borç kapatıldı")
    borc_kapatan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kapattigi_sabah_beslenme_borclari",
        verbose_name="Borcu kapatan",
    )
    borc_kapatma_saati = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Borç kapatma saati",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sabah beslenmesi siparişi"
        verbose_name_plural = "Sabah beslenmesi siparişleri"
        ordering = ["talebe__ad_soyad", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["menu", "talebe"],
                name="sb_siparis_menu_talebe_tek",
            ),
            models.CheckConstraint(
                condition=Q(borc_kaydi_olustu=False) | Q(teslim_edildi=True),
                name="sb_borc_sadece_teslim",
            ),
            models.CheckConstraint(
                condition=Q(teslim_edildi=False) | Q(adet__gt=0),
                name="sb_teslim_adet_pozitif",
            ),
        ]
        indexes = [
            models.Index(
                fields=["teslim_edildi", "borc_kaydi_olustu", "borc_kapatildi"],
                name="sb_siparis_borc_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.talebe} · {self.menu.tarih:%d.%m.%Y} · {self.adet}"

    @property
    def tutar(self) -> Decimal:
        if self.adet <= 0:
            return Decimal("0.00")
        return para(Decimal(self.adet) * self.menu.birim_fiyat)

    @property
    def borc_acik(self) -> bool:
        return bool(
            self.teslim_edildi
            and self.borc_kaydi_olustu
            and not self.borc_kapatildi
        )


class SabahBeslenmeIslemLog(models.Model):
    class Islem(models.TextChoices):
        SIPARIS = "siparis", "Sipariş"
        ODEME = "odeme", "Ödeme tercihi"
        TESLIM = "teslim", "Teslim / satış"
        TESLIM_GERI = "teslim_geri", "Teslim geri alındı"
        BORC_KAPAT = "borc_kapat", "Borç kapatıldı"

    siparis = models.ForeignKey(
        SabahBeslenmeSiparis,
        on_delete=models.CASCADE,
        related_name="islem_loglari",
    )
    islem = models.CharField(max_length=16, choices=Islem.choices)
    yapan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sabah_beslenme_islem_loglari",
    )
    detay = models.CharField(max_length=240, blank=True)
    zaman = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sabah beslenmesi işlem kaydı"
        verbose_name_plural = "Sabah beslenmesi işlem kayıtları"
        ordering = ["-zaman", "-id"]
