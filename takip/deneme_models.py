"""Deneme sınavı modelleri — kitap sınavı ve KTT'den ayrı."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.db import models


class DenemeSinavi(models.Model):
    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        AKTIF = "aktif", "Aktif"

    ad = models.CharField(max_length=200, verbose_name="Deneme adı")
    sinav_tarihi = models.DateField(verbose_name="Sınav tarihi")
    sinif_seviyesi = models.CharField(
        max_length=30,
        verbose_name="Sınıf seviyesi",
        help_text="Örn. 6, 7, 8",
    )
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    durum = models.CharField(
        max_length=10,
        choices=Durum.choices,
        default=Durum.TASLAK,
        verbose_name="Durum",
    )
    yukleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="yukledigi_denemeler",
        verbose_name="Excel yükleyen",
    )
    yuklenme_zamani = models.DateTimeField(null=True, blank=True)
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_denemeler",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Deneme sınavı"
        verbose_name_plural = "Deneme sınavları"
        ordering = ["-sinav_tarihi", "-id"]

    def __str__(self):
        return self.ad


class DenemeSonucu(models.Model):
    deneme = models.ForeignKey(
        DenemeSinavi,
        on_delete=models.CASCADE,
        related_name="sonuclar",
        verbose_name="Deneme",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="deneme_sonuclari",
        verbose_name="Talebe",
    )
    toplam_dogru = models.PositiveIntegerField(default=0)
    toplam_yanlis = models.PositiveIntegerField(default=0)
    toplam_bos = models.PositiveIntegerField(default=0)
    toplam_net = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    puan = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Deneme sonucu"
        verbose_name_plural = "Deneme sonuçları"
        constraints = [
            models.UniqueConstraint(
                fields=["deneme", "talebe"],
                name="deneme_talebe_tek_sonuc",
            )
        ]
        ordering = ["-toplam_net", "talebe__ad_soyad"]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.deneme.ad}"


class DenemeBransSonucu(models.Model):
    class Brans(models.TextChoices):
        TURKCE = "turkce", "Türkçe"
        MATEMATIK = "matematik", "Matematik"
        FEN = "fen", "Fen Bilimleri"
        SOSYAL = "sosyal", "Sosyal Bilgiler"
        DIN = "din", "Din Kültürü"
        INGILIZCE = "ingilizce", "İngilizce"

    sonuc = models.ForeignKey(
        DenemeSonucu,
        on_delete=models.CASCADE,
        related_name="brans_satirlari",
        verbose_name="Sonuç",
    )
    brans = models.CharField(max_length=20, choices=Brans.choices, verbose_name="Branş")
    dogru = models.PositiveIntegerField(default=0)
    yanlis = models.PositiveIntegerField(default=0)
    bos = models.PositiveIntegerField(default=0)
    net = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        verbose_name = "Deneme branş sonucu"
        verbose_name_plural = "Deneme branş sonuçları"
        constraints = [
            models.UniqueConstraint(
                fields=["sonuc", "brans"],
                name="deneme_sonuc_brans_benzersiz",
            )
        ]

    @staticmethod
    def net_hesapla(dogru: int, yanlis: int) -> Decimal:
        net = Decimal(int(dogru or 0)) - (Decimal(int(yanlis or 0)) / Decimal("4"))
        if net < 0:
            net = Decimal("0.00")
        return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class DenemeEslestirmeAlias(models.Model):
    excel_adi = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Excel ad soyad (normalize)",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="deneme_eslestirme_aliaslari",
        verbose_name="Talebe",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Deneme eşleştirme alias"
        verbose_name_plural = "Deneme eşleştirme aliasları"

    def __str__(self):
        return f"{self.excel_adi} → {self.talebe.ad_soyad}"
