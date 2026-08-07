"""Öğretmen sınav notu modelleri."""

from django.db import models


class OgretmenSinavNotu(models.Model):
    class Tur(models.TextChoices):
        YAZILI = "yazili", "Yazılı"
        SOZLU = "sozlu", "Sözlü"

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="ogretmen_sinav_notlari",
        verbose_name="Talebe",
    )
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.CASCADE,
        related_name="girdigi_sinav_notlari",
        verbose_name="Etüt hocası",
    )
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.PROTECT,
        related_name="ogretmen_sinav_notlari",
        verbose_name="Ders",
    )
    tur = models.CharField(
        max_length=10,
        choices=Tur.choices,
        default=Tur.YAZILI,
        verbose_name="Tür",
    )
    puan = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Puan",
    )
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    tarih = models.DateField(verbose_name="Tarih")
    veliye_goster = models.BooleanField(default=True, verbose_name="Veliye göster")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Öğretmen sınav notu"
        verbose_name_plural = "Öğretmen sınav notları"
        ordering = ["-tarih", "-id"]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.ders.ad} ({self.get_tur_display()}): {self.puan}"
