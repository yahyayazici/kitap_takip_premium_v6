"""Seviye Tespit — sınav salonları ve kelebek yerleşimi."""

from __future__ import annotations

from django.db import models


class SinavSalon(models.Model):
    sinav_adi = models.CharField(max_length=200, verbose_name="Sınav adı")
    ad = models.CharField(max_length=60, verbose_name="Salon adı")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    masa_sayisi = models.PositiveSmallIntegerField(default=0, verbose_name="Masa sayısı")
    masa_kisi = models.PositiveSmallIntegerField(default=1, verbose_name="Masa başına öğrenci")

    class Meta:
        verbose_name = "Sınav salonu"
        verbose_name_plural = "Sınav salonları"
        ordering = ["sinav_adi", "sira", "id"]

    def __str__(self) -> str:
        return self.ad

    @property
    def kapasite(self) -> int:
        return self.masa_sayisi * max(self.masa_kisi, 1)


class SinavYerlesim(models.Model):
    basvuru = models.OneToOneField(
        "SinavBasvuru",
        on_delete=models.CASCADE,
        related_name="yerlesim",
        verbose_name="Başvuru",
    )
    salon = models.ForeignKey(
        SinavSalon,
        on_delete=models.CASCADE,
        related_name="yerlesimler",
        verbose_name="Salon",
    )
    masa_no = models.PositiveSmallIntegerField(verbose_name="Masa")
    koltuk = models.PositiveSmallIntegerField(default=1, verbose_name="Koltuk")

    class Meta:
        verbose_name = "Sınav yerleşimi"
        verbose_name_plural = "Sınav yerleşimleri"
        ordering = ["salon__sira", "masa_no", "koltuk"]
        constraints = [
            models.UniqueConstraint(
                fields=["salon", "masa_no", "koltuk"],
                name="uniq_sinav_yerlesim_koltuk",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.salon.ad} · {self.yer_metni}"

    @property
    def koltuk_metni(self) -> str:
        if self.salon.masa_kisi < 2:
            return ""
        if self.salon.masa_kisi == 2:
            return "Sol" if self.koltuk == 1 else "Sağ"
        return f"{self.koltuk}. koltuk"

    @property
    def yer_metni(self) -> str:
        koltuk = self.koltuk_metni
        return f"Masa {self.masa_no}" + (f" {koltuk}" if koltuk else "")

    @property
    def tam_metin(self) -> str:
        return f"{self.salon.ad}, {self.yer_metni}"
