"""KTT (Kazanım Tarama Testi) modelleri."""

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class KttSinav(models.Model):
    ad = models.CharField(max_length=200, verbose_name="KTT adı")
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.PROTECT,
        related_name="ktt_sinavlari",
        verbose_name="Ders",
    )
    sinif_seviyesi = models.CharField(
        max_length=30,
        verbose_name="Sınıf seviyesi",
        help_text="Örn. 6, 7, 8",
    )
    hedef_siniflar = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Hedef sınıflar",
        help_text="Örn. 7-A, 7-B",
    )
    sinav_tarihi = models.DateField(verbose_name="Sınav tarihi")
    soru_sayisi = models.PositiveIntegerField(verbose_name="Soru sayısı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.PROTECT,
        related_name="ktt_sinavlari",
        verbose_name="Etüt hocası",
    )
    veliye_goster = models.BooleanField(
        default=True,
        verbose_name="Veli panelinde göster",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_ktt_sinavlari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "KTT"
        verbose_name_plural = "KTT'ler"
        ordering = ["-sinav_tarihi", "-id"]

    def __str__(self):
        return self.ad

    @property
    def sinif_goster(self) -> str:
        return self.hedef_siniflar.strip() or self.sinif_seviyesi

    def clean(self):
        super().clean()
        if self.soru_sayisi <= 0:
            raise ValidationError({"soru_sayisi": "Soru sayısı en az 1 olmalıdır."})


class KttSonucu(models.Model):
    ktt = models.ForeignKey(
        KttSinav,
        on_delete=models.CASCADE,
        related_name="sonuclar",
        verbose_name="KTT",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="ktt_sonuclari",
        verbose_name="Talebe",
    )
    dogru = models.PositiveIntegerField(default=0, verbose_name="Doğru")
    yanlis = models.PositiveIntegerField(default=0, verbose_name="Yanlış")
    bos = models.PositiveIntegerField(default=0, verbose_name="Boş")
    net = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
        verbose_name="Net",
    )
    puan = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
        verbose_name="100'lük puan",
    )
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_ktt_sonuclari",
        verbose_name="Kaydeden",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "KTT sonucu"
        verbose_name_plural = "KTT sonuçları"
        ordering = ["-puan", "-net", "talebe__ad_soyad"]
        constraints = [
            models.UniqueConstraint(
                fields=["ktt", "talebe"],
                name="ktt_talebe_tek_sonuc",
            )
        ]

    def clean(self):
        if not self.ktt_id:
            return

        toplam = int(self.dogru or 0) + int(self.yanlis or 0) + int(self.bos or 0)
        if toplam != self.ktt.soru_sayisi:
            raise ValidationError(
                {
                    "dogru": (
                        f"Doğru + yanlış + boş toplamı "
                        f"{self.ktt.soru_sayisi} olmalıdır."
                    )
                }
            )

    @staticmethod
    def net_hesapla(dogru: int, yanlis: int) -> Decimal:
        net = Decimal(int(dogru or 0)) - (
            Decimal(int(yanlis or 0)) / Decimal("4")
        )
        return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def puan_hesapla(self) -> Decimal:
        if not self.ktt_id or not self.ktt.soru_sayisi:
            return Decimal("0.00")

        net = self.net_hesapla(int(self.dogru or 0), int(self.yanlis or 0))
        if net < 0:
            net = Decimal("0.00")

        puan = net * Decimal("100") / Decimal(int(self.ktt.soru_sayisi))
        return puan.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        self.net = self.net_hesapla(int(self.dogru or 0), int(self.yanlis or 0))
        if self.net < 0:
            self.net = Decimal("0.00")
        self.puan = self.puan_hesapla()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.ktt.ad}"
