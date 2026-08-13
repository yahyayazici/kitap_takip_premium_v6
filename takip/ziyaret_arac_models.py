"""Ziyaret Araç Planlama — modeller."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models


class ZiyaretPlani(models.Model):
    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        ARAC_TOPLANIYOR = "arac_toplaniyor", "Araç Toplanıyor"
        DAGITIM = "dagitim", "Dağıtım Yapılıyor"
        HAZIR = "hazir", "Hazır"
        ARSIV = "arsiv", "Arşiv"

    ad = models.CharField(max_length=200, verbose_name="Plan adı")
    tarih = models.DateField(verbose_name="Ziyaret tarihi")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    durum = models.CharField(
        max_length=20,
        choices=Durum.choices,
        default=Durum.TASLAK,
        verbose_name="Durum",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_ziyaret_planlari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ziyaret planı"
        verbose_name_plural = "Ziyaret planları"
        ordering = ["-tarih", "-id"]

    def __str__(self) -> str:
        return f"{self.ad} · {self.tarih:%d.%m.%Y}"


class ZiyaretProgramAdimi(models.Model):
    plan = models.ForeignKey(
        ZiyaretPlani,
        on_delete=models.CASCADE,
        related_name="program_adimlari",
        verbose_name="Ziyaret planı",
    )
    saat = models.TimeField(verbose_name="Saat")
    aciklama = models.CharField(max_length=300, verbose_name="Açıklama")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Program adımı"
        verbose_name_plural = "Program adımları"
        ordering = ["sira", "saat", "id"]

    def __str__(self) -> str:
        return f"{self.saat:%H:%M} — {self.aciklama}"


class ZiyaretAraci(models.Model):
    plan = models.ForeignKey(
        ZiyaretPlani,
        on_delete=models.CASCADE,
        related_name="araclar",
        verbose_name="Ziyaret planı",
    )
    surucu_ad = models.CharField(max_length=120, verbose_name="Araç sahibi / sürücü")
    surucu_personel = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ziyaret_araclari",
        verbose_name="Personel kaydı (varsa)",
    )
    kapasite = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Talebe kapasitesi",
    )
    ekleyen = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buldugu_ziyaret_araclari",
        verbose_name="Aracı bulan etüt hocası",
    )
    notlar = models.CharField(max_length=300, blank=True, verbose_name="Not")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ziyaret aracı"
        verbose_name_plural = "Ziyaret araçları"
        ordering = ["surucu_ad", "id"]

    def __str__(self) -> str:
        return f"{self.surucu_ad} ({self.kapasite})"


class ZiyaretPlaniTalebe(models.Model):
    plan = models.ForeignKey(
        ZiyaretPlani,
        on_delete=models.CASCADE,
        related_name="plan_talebeleri",
        verbose_name="Ziyaret planı",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="ziyaret_plan_kayitlari",
        verbose_name="Talebe",
    )
    aktif = models.BooleanField(default=True, verbose_name="Listede aktif")
    sabit = models.BooleanField(default=False, verbose_name="Sabitle")
    sabit_arac = models.ForeignKey(
        ZiyaretAraci,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sabit_talebeler",
        verbose_name="Sabit araç",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ziyaret planı talebesi"
        verbose_name_plural = "Ziyaret planı talebeleri"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "talebe"],
                name="ziyaret_plan_talebe_tek",
            )
        ]
        ordering = ["talebe__ad_soyad"]

    def __str__(self) -> str:
        return str(self.talebe)


class ZiyaretAracAtama(models.Model):
    class Tur(models.TextChoices):
        TALEBE = "talebe", "Talebe"
        ETUT_HOCASI = "etut_hocasi", "Etüt Hocası"

    arac = models.ForeignKey(
        ZiyaretAraci,
        on_delete=models.CASCADE,
        related_name="atamalar",
        verbose_name="Araç",
    )
    tur = models.CharField(max_length=16, choices=Tur.choices, verbose_name="Tür")
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ziyaret_arac_atamalari",
        verbose_name="Talebe",
    )
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ziyaret_arac_atamalari",
        verbose_name="Etüt hocası",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ziyaret araç ataması"
        verbose_name_plural = "Ziyaret araç atamaları"
        ordering = ["sira", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["arac", "talebe"],
                condition=models.Q(talebe__isnull=False),
                name="ziyaret_arac_talebe_tek",
            ),
            models.UniqueConstraint(
                fields=["arac", "etut_hocasi"],
                condition=models.Q(etut_hocasi__isnull=False),
                name="ziyaret_arac_etut_tek",
            ),
        ]

    def __str__(self) -> str:
        if self.tur == self.Tur.TALEBE and self.talebe_id:
            return str(self.talebe)
        if self.tur == self.Tur.ETUT_HOCASI and self.etut_hocasi_id:
            return str(self.etut_hocasi)
        return f"Atama #{self.pk}"
