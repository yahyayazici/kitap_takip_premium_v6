"""Personel vazife atama ve takip modelleri."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class PersonelVazife(models.Model):
    class Durum(models.TextChoices):
        ATANDI = "atandi", "Atandı"
        ONAYLANDI = "onaylandi", "Onaylandı"
        DEVAM = "devam", "Devam ediyor"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"
        IPTAL = "iptal", "İptal"

    class Oncelik(models.TextChoices):
        DUSUK = "dusuk", "Düşük"
        NORMAL = "normal", "Normal"
        YUKSEK = "yuksek", "Yüksek"
        ACIL = "acil", "Acil"

    baslik = models.CharField(max_length=200, verbose_name="Vazife")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    atanan = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.CASCADE,
        related_name="vazifeler",
        verbose_name="Atanan personel",
    )
    atayan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atadigi_vazifeler",
        verbose_name="Atayan",
    )
    sinif_sube = models.ForeignKey(
        "SinifSube",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vazifeler",
        verbose_name="İlgili sınıf",
    )
    baslangic = models.DateField(verbose_name="Başlangıç")
    bitis = models.DateField(null=True, blank=True, verbose_name="Şu güne kadar")
    durum = models.CharField(
        max_length=20,
        choices=Durum.choices,
        default=Durum.ATANDI,
        verbose_name="Durum",
    )
    oncelik = models.CharField(
        max_length=10,
        choices=Oncelik.choices,
        default=Oncelik.NORMAL,
        verbose_name="Öncelik",
    )
    personel_notu = models.TextField(blank=True, verbose_name="Personel notu")
    onay_tarihi = models.DateTimeField(null=True, blank=True, verbose_name="Onay tarihi")
    tamamlanma_tarihi = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Tamamlanma tarihi",
    )
    toplanti_karar = models.ForeignKey(
        "PersonelToplantiKarar",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bagli_vazifeler",
        verbose_name="Toplantı kararı",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Personel vazife"
        verbose_name_plural = "Personel vazifeleri"
        ordering = ["-olusturulma", "-id"]

    def __str__(self) -> str:
        return f"{self.baslik} → {self.atanan}"
