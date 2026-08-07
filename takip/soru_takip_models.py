"""Günlük soru takip modelleri."""

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum


class GunlukSoruKaydi(models.Model):
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="gunluk_soru_kayitlari",
        verbose_name="Talebe",
    )
    tarih = models.DateField(verbose_name="Tarih")
    kitap_okunan_sayfa = models.PositiveIntegerField(
        default=0,
        verbose_name="Kitap okunan sayfa",
    )
    gunluk_not = models.TextField(blank=True, verbose_name="Günlük not")
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_soru_kayitlari",
        verbose_name="Kaydeden",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Günlük soru kaydı"
        verbose_name_plural = "Günlük soru kayıtları"
        ordering = ["-tarih", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["talebe", "tarih"],
                name="talebe_gunluk_soru_tek_kayit",
            )
        ]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.tarih:%d.%m.%Y}"

    @property
    def toplam_soru(self) -> int:
        return int(
            self.ders_satirlari.aggregate(t=Sum("toplam_soru"))["t"] or 0
        )

    @property
    def toplam_net(self) -> Decimal:
        toplam = self.ders_satirlari.aggregate(t=Sum("net"))["t"]
        if toplam is None:
            return Decimal("0.00")
        return Decimal(toplam).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def basari_orani(self) -> Decimal:
        agg = self.ders_satirlari.aggregate(
            dogru=Sum("dogru"),
            toplam=Sum("toplam_soru"),
        )
        toplam = int(agg["toplam"] or 0)
        if toplam <= 0:
            return Decimal("0.00")
        dogru = int(agg["dogru"] or 0)
        return (
            Decimal(dogru) * Decimal("100") / Decimal(toplam)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class GunlukSoruDersSatiri(models.Model):
    kayit = models.ForeignKey(
        GunlukSoruKaydi,
        on_delete=models.CASCADE,
        related_name="ders_satirlari",
        verbose_name="Kayıt",
    )
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.PROTECT,
        related_name="gunluk_soru_satirlari",
        verbose_name="Ders",
    )
    toplam_soru = models.PositiveIntegerField(default=0, verbose_name="Toplam soru")
    dogru = models.PositiveIntegerField(default=0, verbose_name="Doğru")
    yanlis = models.PositiveIntegerField(default=0, verbose_name="Yanlış")
    bos = models.PositiveIntegerField(default=0, verbose_name="Boş")
    net = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
        verbose_name="Net",
    )

    class Meta:
        verbose_name = "Günlük soru ders satırı"
        verbose_name_plural = "Günlük soru ders satırları"
        constraints = [
            models.UniqueConstraint(
                fields=["kayit", "ders"],
                name="gunluk_soru_kayit_ders_benzersiz",
            )
        ]

    @staticmethod
    def net_hesapla(dogru: int, yanlis: int) -> Decimal:
        net = Decimal(int(dogru or 0)) - (
            Decimal(int(yanlis or 0)) / Decimal("4")
        )
        if net < 0:
            net = Decimal("0.00")
        return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def clean(self):
        if self.toplam_soru == 0 and self.dogru == 0 and self.yanlis == 0 and self.bos == 0:
            return

        toplam = int(self.dogru or 0) + int(self.yanlis or 0) + int(self.bos or 0)
        if toplam != int(self.toplam_soru or 0):
            raise ValidationError(
                f"{self.ders.ad}: Doğru + yanlış + boş, toplam soruya eşit olmalı."
            )

    def save(self, *args, **kwargs):
        self.net = self.net_hesapla(int(self.dogru or 0), int(self.yanlis or 0))
        if self.toplam_soru == 0:
            self.dogru = self.yanlis = self.bos = 0
            self.net = Decimal("0.00")
        self.full_clean()
        super().save(*args, **kwargs)
