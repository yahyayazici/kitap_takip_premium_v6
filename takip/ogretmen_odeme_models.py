"""Öğretmen ödeme modülü — dönem, günlük ders saati ve ödeme kayıtları."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models

from takip.models import EtutHocasi, SinifSube, TimeStampedModel
from takip.wave0_models import Brans


class OgretmenOdemeProfili(models.Model):
    etut_hocasi = models.OneToOneField(
        EtutHocasi,
        on_delete=models.CASCADE,
        related_name="odeme_profili",
        verbose_name="Etüt hocası",
    )
    brans = models.ForeignKey(
        Brans,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ogretmen_odeme_profilleri",
        verbose_name="Branş",
    )
    saatlik_ucret = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Saatlik ücret",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Öğretmen ödeme profili"
        verbose_name_plural = "Öğretmen ödeme profilleri"

    def __str__(self) -> str:
        return f"{self.etut_hocasi.ad_soyad} · {self.saatlik_ucret} ₺/saat"


class OgretmenOdemeDonemi(TimeStampedModel):
    etut_hocasi = models.ForeignKey(
        EtutHocasi,
        on_delete=models.PROTECT,
        related_name="odeme_donemleri",
        verbose_name="Öğretmen",
    )
    baslangic = models.DateField(verbose_name="Başlangıç")
    bitis = models.DateField(verbose_name="Bitiş")
    saatlik_ucret = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Saatlik ücret (dönem)",
    )
    toplam_saat = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Toplam ders saati",
    )
    odenecek_tutar = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Ödenecek tutar",
    )
    notlar = models.TextField(blank=True, verbose_name="Notlar")

    class Meta:
        verbose_name = "Öğretmen ödeme dönemi"
        verbose_name_plural = "Öğretmen ödeme dönemleri"
        ordering = ["-baslangic", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(bitis__gte=models.F("baslangic")),
                name="ogretmen_odeme_donem_tarih_sirasi",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.etut_hocasi.ad_soyad} · "
            f"{self.baslangic:%d.%m.%Y} – {self.bitis:%d.%m.%Y}"
        )


class OgretmenOdemeGunKaydi(models.Model):
    donem = models.ForeignKey(
        OgretmenOdemeDonemi,
        on_delete=models.CASCADE,
        related_name="gunler",
        verbose_name="Dönem",
    )
    tarih = models.DateField(verbose_name="Tarih")
    toplam_saat = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Günlük toplam saat",
    )

    class Meta:
        verbose_name = "Ödeme gün kaydı"
        verbose_name_plural = "Ödeme gün kayıtları"
        ordering = ["tarih"]
        constraints = [
            models.UniqueConstraint(
                fields=["donem", "tarih"],
                name="ogretmen_odeme_gun_benzersiz",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tarih:%d.%m.%Y} · {self.toplam_saat} saat"


class OgretmenOdemeDersKaydi(models.Model):
    gun = models.ForeignKey(
        OgretmenOdemeGunKaydi,
        on_delete=models.CASCADE,
        related_name="dersler",
        verbose_name="Gün",
    )
    sinif_sube = models.ForeignKey(
        SinifSube,
        on_delete=models.PROTECT,
        related_name="ogretmen_odeme_dersleri",
        verbose_name="Sınıf",
    )
    brans = models.ForeignKey(
        Brans,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ogretmen_odeme_dersleri",
        verbose_name="Branş",
    )
    saat = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Ders saati",
    )

    class Meta:
        verbose_name = "Ödeme ders kaydı"
        verbose_name_plural = "Ödeme ders kayıtları"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.sinif_sube} · {self.saat} saat"
