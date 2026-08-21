"""Public veli değerlendirme anketi modeli."""

from __future__ import annotations

from django.db import models


class VeliAnketCevap(models.Model):
    class Istifade(models.TextChoices):
        HIC = "Hiç", "Hiç"
        AZ = "Az", "Az"
        ORTA = "Orta", "Orta"
        COK = "Çok", "Çok"
        COK_FAZLA = "Çok Fazla", "Çok Fazla"

    seminer_adi = models.CharField(
        max_length=200,
        default="Veli Eğitim Semineri",
        verbose_name="Seminer adı",
    )
    genel_degerlendirme = models.PositiveSmallIntegerField(
        verbose_name="Genel değerlendirme (1-5)",
    )
    konu_secimi_gorus = models.TextField(
        blank=True,
        verbose_name="Konu seçimi hakkındaki görüş",
    )
    konusmaci_gorus = models.TextField(
        blank=True,
        verbose_name="Konuşmacı hakkındaki görüş",
    )
    istifade_duzeyi = models.CharField(
        max_length=20,
        choices=Istifade.choices,
        blank=True,
        verbose_name="İstifade düzeyi",
    )
    oneriler = models.TextField(
        blank=True,
        verbose_name="Görüş ve öneriler",
    )
    olusturulma = models.DateTimeField(auto_now_add=True, verbose_name="Gönderim zamanı")

    class Meta:
        verbose_name = "Veli anket cevabı"
        verbose_name_plural = "Veli anket cevapları"
        ordering = ["-olusturulma"]

    def __str__(self) -> str:
        return f"{self.seminer_adi} — {self.genel_degerlendirme}/5 ({self.olusturulma:%d.%m.%Y %H:%M})"
