"""Finans yönetim modelleri — ücret, taksit, tahsilat, audit."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from takip.wave0_models import EgitimYili


class FinansUcretPolitikasi(models.Model):
    SINIF_SECENEKLERI = (
        ("5", "5. Sınıf"),
        ("6", "6. Sınıf"),
        ("7", "7. Sınıf"),
        ("8", "8. Sınıf"),
    )

    egitim_yili = models.ForeignKey(
        EgitimYili,
        on_delete=models.CASCADE,
        related_name="finans_ucret_politikalari",
        verbose_name="Eğitim yılı",
    )
    sinif_seviyesi = models.CharField(max_length=2, choices=SINIF_SECENEKLERI, verbose_name="Sınıf")
    tutar = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Yıllık ücret",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ücret politikası"
        verbose_name_plural = "Ücret politikaları"
        ordering = ["egitim_yili__baslangic", "sinif_seviyesi"]
        constraints = [
            models.UniqueConstraint(
                fields=["egitim_yili", "sinif_seviyesi"],
                name="benzersiz_finans_ucret_politikasi",
            )
        ]

    def __str__(self) -> str:
        return f"{self.egitim_yili.ad} · {self.get_sinif_seviyesi_display()} — {self.tutar} ₺"


class FinansIndirim(models.Model):
    class Tur(models.TextChoices):
        YUZDE = "yuzde", "Yüzde"
        TUTAR = "tutar", "Sabit Tutar"

    kod = models.SlugField(max_length=40, unique=True, verbose_name="Kod")
    ad = models.CharField(max_length=80, verbose_name="Ad")
    tur = models.CharField(max_length=10, choices=Tur.choices, default=Tur.YUZDE, verbose_name="Tür")
    deger = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Değer",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    baslangic = models.DateField(null=True, blank=True, verbose_name="Başlangıç")
    bitis = models.DateField(null=True, blank=True, verbose_name="Bitiş")
    aciklama = models.CharField(max_length=255, blank=True, verbose_name="Açıklama")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "İndirim"
        verbose_name_plural = "İndirimler"
        ordering = ["sira", "ad"]

    def __str__(self) -> str:
        return self.ad

    @property
    def gecerli_mi(self) -> bool:
        if not self.aktif:
            return False
        bugun = timezone.localdate()
        if self.baslangic and bugun < self.baslangic:
            return False
        if self.bitis and bugun > self.bitis:
            return False
        return True

    @property
    def deger_goster(self) -> str:
        if self.tur == self.Tur.YUZDE:
            return f"%{self.deger}"
        return f"{self.deger} ₺"


class FinansKampanya(models.Model):
    ad = models.CharField(max_length=120, verbose_name="Kampanya adı")
    indirim = models.ForeignKey(
        FinansIndirim,
        on_delete=models.PROTECT,
        related_name="kampanyalar",
        verbose_name="İndirim",
    )
    baslangic = models.DateField(verbose_name="Başlangıç")
    bitis = models.DateField(verbose_name="Bitiş")
    kosullar = models.TextField(blank=True, verbose_name="Koşullar")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kampanya"
        verbose_name_plural = "Kampanyalar"
        ordering = ["-baslangic"]

    def __str__(self) -> str:
        return self.ad

    @property
    def gecerli_mi(self) -> bool:
        bugun = timezone.localdate()
        return self.aktif and self.baslangic <= bugun <= self.bitis


class TalebeFinansDosyasi(models.Model):
    class Durum(models.TextChoices):
        BEKLIYOR = "bekliyor", "Bekliyor"
        DEVAM = "devam", "Devam Ediyor"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"
        GECIKTI = "gecikti", "Gecikti"

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="finans_dosyalari",
        verbose_name="Talebe",
    )
    egitim_yili = models.ForeignKey(
        EgitimYili,
        on_delete=models.PROTECT,
        related_name="finans_dosyalari",
        verbose_name="Eğitim yılı",
    )
    toplam_ucret = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    indirim_tutari = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    net_ucret = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    pesinat = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    odenen_tutar = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    taksit_sayisi = models.PositiveSmallIntegerField(default=10, verbose_name="Taksit sayısı")
    durum = models.CharField(max_length=12, choices=Durum.choices, default=Durum.BEKLIYOR)
    not_alani = models.TextField(blank=True, verbose_name="Not")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_finans_dosyalari",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Öğrenci finans dosyası"
        verbose_name_plural = "Öğrenci finans dosyaları"
        ordering = ["-egitim_yili__baslangic", "talebe__ad_soyad"]
        constraints = [
            models.UniqueConstraint(
                fields=["talebe", "egitim_yili"],
                name="benzersiz_talebe_finans_yil",
            )
        ]

    def __str__(self) -> str:
        return f"{self.talebe.ad_soyad} · {self.egitim_yili.ad}"

    @property
    def kalan_tutar(self) -> Decimal:
        return max(self.net_ucret - self.odenen_tutar, Decimal("0.00"))

    @property
    def tahsilat_orani(self) -> int:
        if self.net_ucret <= 0:
            return 0
        return int(round(100 * float(self.odenen_tutar) / float(self.net_ucret)))


class FinansTaksit(models.Model):
    class Durum(models.TextChoices):
        BEKLIYOR = "bekliyor", "Bekliyor"
        ODENDI = "odendi", "Ödendi"
        KISMI = "kismi", "Kısmi"
        GECIKTI = "gecikti", "Gecikti"

    dosya = models.ForeignKey(
        TalebeFinansDosyasi,
        on_delete=models.CASCADE,
        related_name="taksitler",
        verbose_name="Finans dosyası",
    )
    sira = models.PositiveSmallIntegerField(verbose_name="Sıra")
    tutar = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    vade = models.DateField(verbose_name="Vade")
    odenen_tutar = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    durum = models.CharField(max_length=10, choices=Durum.choices, default=Durum.BEKLIYOR)
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Taksit"
        verbose_name_plural = "Taksitler"
        ordering = ["dosya", "sira"]
        constraints = [
            models.UniqueConstraint(fields=["dosya", "sira"], name="benzersiz_finans_taksit_sira")
        ]

    def __str__(self) -> str:
        return f"{self.dosya.talebe.ad_soyad} · Taksit {self.sira}"

    @property
    def kalan(self) -> Decimal:
        return max(self.tutar - self.odenen_tutar, Decimal("0.00"))


class FinansTahsilat(models.Model):
    class Yontem(models.TextChoices):
        NAKIT = "nakit", "Nakit"
        EFT = "eft", "EFT"
        KART = "kart", "Kart"
        DIGER = "diger", "Diğer"

    class Tur(models.TextChoices):
        PESINAT = "pesinat", "Peşinat"
        TAKSIT = "taksit", "Taksit"
        DIGER = "diger", "Diğer"

    dosya = models.ForeignKey(
        TalebeFinansDosyasi,
        on_delete=models.PROTECT,
        related_name="tahsilatlar",
        verbose_name="Finans dosyası",
    )
    taksit = models.ForeignKey(
        FinansTaksit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tahsilatlar",
        verbose_name="Taksit",
    )
    tutar = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    tarih = models.DateField(verbose_name="Tarih")
    yontem = models.CharField(max_length=10, choices=Yontem.choices, default=Yontem.NAKIT)
    tur = models.CharField(max_length=10, choices=Tur.choices, default=Tur.TAKSIT)
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_finans_tahsilatlari",
    )
    iptal = models.BooleanField(default=False, verbose_name="İptal")
    iptal_nedeni = models.TextField(blank=True, verbose_name="İptal nedeni")
    iptal_eden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="iptal_ettigi_finans_tahsilatlari",
    )
    iptal_tarihi = models.DateTimeField(null=True, blank=True)
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Finans tahsilat"
        verbose_name_plural = "Finans tahsilatları"
        ordering = ["-tarih", "-id"]

    def __str__(self) -> str:
        return f"{self.tutar} ₺ · {self.tarih:%d.%m.%Y}"


class FinansIslemLog(models.Model):
    dosya = models.ForeignKey(
        TalebeFinansDosyasi,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="islem_loglari",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finans_islem_loglari",
    )
    islem = models.CharField(max_length=80, verbose_name="İşlem")
    detay = models.TextField(blank=True, verbose_name="Detay")
    kullanici = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finans_islem_loglari",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Finans işlem logu"
        verbose_name_plural = "Finans işlem logları"
        ordering = ["-olusturulma"]
