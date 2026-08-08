"""Yıllık Çalışma Takvimi (YÇT) modelleri."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class YctOlay(models.Model):
    class Kategori(models.TextChoices):
        GENEL = "genel", "Genel"
        YAZILI = "yazili", "Yazılı / kamp"
        DENEME = "deneme", "Deneme"
        KTT = "ktt", "KTT"
        ETKINLIK = "etkinlik", "Etkinlik"
        TATIL = "tatil", "Tatil"
        TOPLANTI = "toplanti", "Toplantı"
        PROGRAM = "program", "Program"

    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama / plan")
    baslangic = models.DateField(verbose_name="Başlangıç")
    bitis = models.DateField(
        null=True,
        blank=True,
        verbose_name="Bitiş",
        help_text="Boş bırakılırsa tek günlük olay sayılır.",
    )
    kategori = models.CharField(
        max_length=20,
        choices=Kategori.choices,
        default=Kategori.GENEL,
        verbose_name="Kategori",
    )
    tum_personel = models.BooleanField(
        default=True,
        verbose_name="Tüm personele görünür",
    )
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_yct_olaylari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "YÇT olayı"
        verbose_name_plural = "YÇT olayları"
        ordering = ["baslangic", "id"]

    def __str__(self) -> str:
        return self.baslik

    @property
    def bitis_efektif(self):
        return self.bitis or self.baslangic
