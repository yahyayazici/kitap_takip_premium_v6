"""Akademik müdahale modelleri."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class MudahaleTuru(models.Model):
    ad = models.CharField(max_length=120, verbose_name="Ad")
    ikon = models.CharField(max_length=8, blank=True, verbose_name="İkon")
    renk = models.CharField(
        max_length=7,
        default="#2563EB",
        verbose_name="Renk",
        help_text="Hex renk kodu (#2563EB)",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    form_semasi = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Ek form alanları",
        help_text='[{"key":"kaynak","label":"Kaynak","type":"text"}]',
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Müdahale türü"
        verbose_name_plural = "Müdahale türleri"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad


class AkademikMudahale(models.Model):
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="akademik_mudahaleler",
        verbose_name="Talebe",
    )
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="akademik_mudahaleler",
        verbose_name="Ders",
    )
    konu = models.CharField(max_length=200, blank=True, verbose_name="Konu")
    mudahale_turu = models.ForeignKey(
        MudahaleTuru,
        on_delete=models.PROTECT,
        related_name="kayitlar",
        verbose_name="Müdahale türü",
    )
    tarih = models.DateField(verbose_name="Tarih")
    sure_dakika = models.PositiveIntegerField(
        default=0,
        verbose_name="Süre (dk)",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_akademik_mudahaleler",
        verbose_name="Kaydı oluşturan",
    )
    degerlendirme_notu = models.TextField(
        blank=True,
        verbose_name="Değerlendirme notu (personel)",
    )
    veliye_goster = models.BooleanField(
        default=True,
        verbose_name="Veliye göster",
    )
    ek_alanlar = models.JSONField(default=dict, blank=True, verbose_name="Ek alanlar")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Akademik müdahale"
        verbose_name_plural = "Akademik müdahaleler"
        ordering = ["-tarih", "-id"]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.mudahale_turu.ad} ({self.tarih:%d.%m.%Y})"

    @property
    def veli_ozet(self) -> str:
        parcalar = [self.mudahale_turu.ad]
        if self.ders_id:
            parcalar.append(self.ders.ad)
        if self.konu:
            parcalar.append(self.konu)
        if self.sure_dakika:
            parcalar.append(f"{self.sure_dakika} dk")
        return " · ".join(parcalar)
