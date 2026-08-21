"""Public veli semineri değerlendirme anketi modeli."""

from __future__ import annotations

from django.db import models


class VeliAnketCevap(models.Model):
    class Sinif(models.TextChoices):
        BES = "5. sınıf", "5. sınıf"
        ALTI = "6. sınıf", "6. sınıf"
        YEDI = "7. sınıf", "7. sınıf"
        SEKIZ = "8. sınıf", "8. sınıf"

    class EvetKismenHayir(models.TextChoices):
        EVET = "Evet", "Evet"
        KISMEN = "Kısmen", "Kısmen"
        HAYIR = "Hayır", "Hayır"

    seminer_adi = models.CharField(
        max_length=200,
        default="Veli Eğitim Semineri",
        verbose_name="Seminer adı",
    )
    sinif = models.CharField(
        max_length=20,
        choices=Sinif.choices,
        blank=True,
        verbose_name="Talebenin sınıfı",
    )
    genel_degerlendirme = models.TextField(
        blank=True,
        verbose_name="Genel değerlendirme",
    )
    konu_ihtiyaci_cevap = models.CharField(
        max_length=10,
        choices=EvetKismenHayir.choices,
        blank=True,
        verbose_name="Konu ihtiyaca cevap verdi mi",
    )
    konusmaci_gorus = models.TextField(
        blank=True,
        verbose_name="Konuşmacı hakkındaki görüş",
    )
    istifade_puani = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="İstifade puanı (1-5)",
    )
    onerilen_konular = models.TextField(
        blank=True,
        verbose_name="Önerilen konular",
    )
    oneriler = models.TextField(
        blank=True,
        verbose_name="Diğer değerlendirme/öneriler",
    )
    olusturulma = models.DateTimeField(auto_now_add=True, verbose_name="Gönderim zamanı")

    class Meta:
        verbose_name = "Veli anket cevabı"
        verbose_name_plural = "Veli anket cevapları"
        ordering = ["-olusturulma"]

    def __str__(self) -> str:
        return f"{self.sinif or self.seminer_adi} — {self.olusturulma:%d.%m.%Y %H:%M}"
