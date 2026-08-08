"""Yazılı takip modelleri — kamp, sınav ve sonuç (puan odaklı)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class YaziliKamp(models.Model):
    ad = models.CharField(max_length=200, verbose_name="Kamp adı")
    baslangic = models.DateField(verbose_name="Başlangıç tarihi")
    bitis = models.DateField(verbose_name="Bitiş tarihi")
    sinif_seviyesi = models.CharField(
        max_length=30,
        verbose_name="Sınıf seviyesi",
        help_text="Örn. 6, 7, 8",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    veli_goster = models.BooleanField(
        default=True,
        verbose_name="Veli panelinde göster",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_yazili_kamplar",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yazılı kamp"
        verbose_name_plural = "Yazılı kamplar"
        ordering = ["-baslangic", "-id"]

    def __str__(self):
        return self.ad


class YaziliSinav(models.Model):
    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        AKTIF = "aktif", "Aktif"

    class Tur(models.TextChoices):
        ORNEK = "ornek", "Örnek yazılı"
        GERCEK = "gercek", "Gerçek yazılı"

    kamp = models.ForeignKey(
        YaziliKamp,
        on_delete=models.CASCADE,
        related_name="sinavlar",
        verbose_name="Kamp",
    )
    ad = models.CharField(max_length=200, verbose_name="Sınav adı")
    sinav_tarihi = models.DateField(verbose_name="Sınav tarihi")
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="yazili_sinavlar",
        verbose_name="Ders",
    )
    ders_ad = models.CharField(max_length=120, verbose_name="Ders")
    brans = models.CharField(max_length=80, blank=True, verbose_name="Branş")
    yazili_no = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Yazılı no",
        help_text="Örn. 1. yazılı, 2. yazılı",
    )
    tur = models.CharField(
        max_length=10,
        choices=Tur.choices,
        default=Tur.ORNEK,
        verbose_name="Tür",
        help_text="Kamp sürecindeki örnek veya okul gerçek yazılısı",
    )
    hedef_siniflar = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Hedef sınıflar",
        help_text="Virgülle: 7-A, 7-B",
    )
    soru_sayisi = models.PositiveIntegerField(
        default=0,
        blank=True,
        verbose_name="Soru sayısı",
        help_text="Puan girişinde kullanılmaz; isteğe bağlı.",
    )
    durum = models.CharField(
        max_length=10,
        choices=Durum.choices,
        default=Durum.TASLAK,
        verbose_name="Durum",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_yazili_sinavlar",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yazılı sınav"
        verbose_name_plural = "Yazılı sınavlar"
        ordering = ["sinav_tarihi", "yazili_no", "id"]

    def __str__(self):
        return self.ad

    @property
    def sinif_goster(self) -> str:
        if self.hedef_siniflar.strip():
            return self.hedef_siniflar.strip()
        return f"{self.kamp.sinif_seviyesi}. sınıf" if self.kamp_id else "—"

    @property
    def ders_goster(self) -> str:
        if self.ders_id:
            return str(self.ders)
        if self.brans:
            return f"{self.ders_ad} ({self.brans})"
        return self.ders_ad

    @property
    def etiket(self) -> str:
        tur = self.get_tur_display()
        return f"{self.ders_ad} · {self.yazili_no}. yazılı ({tur})"

    def clean(self):
        super().clean()
        if self.yazili_no < 1:
            raise ValidationError({"yazili_no": "Yazılı no en az 1 olmalıdır."})
        if self.soru_sayisi is not None and self.soru_sayisi < 0:
            raise ValidationError({"soru_sayisi": "Soru sayısı negatif olamaz."})

    def save(self, *args, **kwargs):
        if self.ders_id and not self.ders_ad:
            self.ders_ad = self.ders.ad
            if self.ders.brans_id and not self.brans:
                self.brans = self.ders.brans.ad
        super().save(*args, **kwargs)


class YaziliSonuc(models.Model):
    sinav = models.ForeignKey(
        YaziliSinav,
        on_delete=models.CASCADE,
        related_name="sonuclar",
        verbose_name="Sınav",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="yazili_sonuclari",
        verbose_name="Talebe",
    )
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
    puan = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Puan (100)",
    )
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_yazili_sonuclar",
        verbose_name="Kaydeden",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yazılı sonuç"
        verbose_name_plural = "Yazılı sonuçlar"
        ordering = ["-puan", "-net", "talebe__ad_soyad"]
        constraints = [
            models.UniqueConstraint(
                fields=["sinav", "talebe"],
                name="yazili_sinav_talebe_tek_sonuc",
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
        puan = Decimal(str(self.puan or 0))
        if puan < 0 or puan > 100:
            raise ValidationError({"puan": "Puan 0–100 arasında olmalıdır."})

        # Eski D/Y/B kayıtları için opsiyonel doğrulama (puan girişi asıl yol)
        toplam = int(self.dogru or 0) + int(self.yanlis or 0) + int(self.bos or 0)
        if (
            self.sinav_id
            and self.sinav.soru_sayisi
            and toplam > 0
            and toplam != self.sinav.soru_sayisi
        ):
            raise ValidationError(
                {
                    "dogru": (
                        f"Doğru + yanlış + boş toplamı "
                        f"{self.sinav.soru_sayisi} olmalıdır."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.puan = Decimal(str(self.puan or 0)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if int(self.dogru or 0) or int(self.yanlis or 0):
            self.net = self.net_hesapla(int(self.dogru or 0), int(self.yanlis or 0))
        else:
            self.net = Decimal("0.00")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.sinav.ad}"
