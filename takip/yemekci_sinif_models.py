"""Yemekçilik — sınıf bazlı kalıcı havuz ve günlük döngü."""

from __future__ import annotations

from django.conf import settings
from django.db import models


SINIF_SEVIYELERI = ("5", "6", "7", "8")

SINIF_RENKLERI = {
    "5": "#0071e3",
    "6": "#15803d",
    "7": "#ea580c",
    "8": "#dc2626",
}

SINIF_ETIKET = {
    "5": "5. Sınıf",
    "6": "6. Sınıf",
    "7": "7. Sınıf",
    "8": "8. Sınıf",
}


class YemekciAyar(models.Model):
    """Tek satırlık sistem ayarı."""

    hafta_sonu_cikar = models.BooleanField(
        default=True,
        verbose_name="Hafta sonlarını çıkar",
        help_text="Cumartesi/Pazar görev yazılmaz.",
    )
    dongu_baslangic = models.DateField(
        verbose_name="Döngü başlangıç tarihi",
        help_text="Gün indeksi bu tarihten itibaren sayılır.",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yemekçilik ayarı"
        verbose_name_plural = "Yemekçilik ayarları"

    def __str__(self) -> str:
        return f"Yemekçilik ayarı · {self.dongu_baslangic}"


class YemekciSinifHavuzu(models.Model):
    sinif = models.CharField(max_length=4, unique=True, verbose_name="Sınıf")
    renk = models.CharField(max_length=20, blank=True, verbose_name="Renk")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Yemekçi sınıf havuzu"
        verbose_name_plural = "Yemekçi sınıf havuzları"
        ordering = ["sinif"]

    def __str__(self) -> str:
        return SINIF_ETIKET.get(self.sinif, self.sinif)

    @property
    def etiket(self) -> str:
        return SINIF_ETIKET.get(self.sinif, f"{self.sinif}. Sınıf")

    @property
    def renk_kod(self) -> str:
        return self.renk or SINIF_RENKLERI.get(self.sinif, "#64748b")


class YemekciHavuzKaydi(models.Model):
    havuz = models.ForeignKey(
        YemekciSinifHavuzu,
        on_delete=models.CASCADE,
        related_name="kayitlar",
        verbose_name="Havuz",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="yemekci_havuz_kayitlari",
        verbose_name="Talebe",
    )
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Yemekçi havuz kaydı"
        verbose_name_plural = "Yemekçi havuz kayıtları"
        ordering = ["havuz__sinif", "sira", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["havuz", "talebe"],
                name="yemekci_havuz_talebe_tek",
            )
        ]

    def __str__(self) -> str:
        return f"{self.havuz.sinif} · {self.talebe} (#{self.sira})"


class YemekciGunAtama(models.Model):
    """Günlük görev — manuel override veya toplu kaydedilmiş atama."""

    tarih = models.DateField(db_index=True, verbose_name="Tarih")
    sinif = models.CharField(max_length=4, verbose_name="Sınıf")
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.PROTECT,
        related_name="yemekci_gun_gorevleri",
        verbose_name="Talebe",
    )
    manuel = models.BooleanField(
        default=False,
        verbose_name="Manuel",
        help_text="True ise döngü hesabını ezer.",
    )
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_yemekci_gun_atamalari",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yemekçi gün ataması"
        verbose_name_plural = "Yemekçi gün atamaları"
        ordering = ["tarih", "sinif"]
        constraints = [
            models.UniqueConstraint(
                fields=["tarih", "sinif"],
                name="yemekci_gun_sinif_tek",
            )
        ]

    def __str__(self) -> str:
        return f"{self.tarih} · {self.sinif} · {self.talebe}"
