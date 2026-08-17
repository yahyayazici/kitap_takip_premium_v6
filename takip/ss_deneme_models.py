"""Sözel–sayısal deneme (90 / 75 soru) modelleri."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

SOZEL_BRANSLAR: tuple[str, ...] = ("turkce", "sosyal", "din", "ingilizce")
SAYISAL_BRANSLAR: tuple[str, ...] = ("matematik", "fen")
TUM_BRANSLAR: tuple[str, ...] = SOZEL_BRANSLAR + SAYISAL_BRANSLAR

BRANS_ETIKETLERI: dict[str, str] = {
    "turkce": "Türkçe",
    "sosyal": "Sosyal",
    "din": "Din",
    "ingilizce": "İngilizce",
    "matematik": "Matematik",
    "fen": "Fen",
}

BRANS_DERS_ADLARI: dict[str, str] = {
    "turkce": "Türkçe",
    "sosyal": "Sosyal Bilgiler",
    "din": "Din Kültürü",
    "ingilizce": "İngilizce",
    "matematik": "Matematik",
    "fen": "Fen Bilimleri",
}

SORU_DAGILIMI: dict[int, dict[str, int]] = {
    90: {
        "turkce": 20,
        "matematik": 20,
        "fen": 20,
        "sosyal": 10,
        "din": 10,
        "ingilizce": 10,
    },
    75: {
        "turkce": 15,
        "matematik": 15,
        "fen": 15,
        "sosyal": 10,
        "din": 10,
        "ingilizce": 10,
    },
}


def brans_soru_sayisi(deneme: "SozelSayisalDeneme", brans: str) -> int:
    dagilim = SORU_DAGILIMI.get(int(deneme.soru_formati), SORU_DAGILIMI[90])
    return int(dagilim.get(brans, 0))


def bolum_soru_sayisi(deneme: "SozelSayisalDeneme", bolum: str) -> int:
    kodlar = TUM_BRANSLAR
    if bolum == "sozel":
        kodlar = SOZEL_BRANSLAR
    elif bolum == "sayisal":
        kodlar = SAYISAL_BRANSLAR
    return sum(brans_soru_sayisi(deneme, kod) for kod in kodlar)


class SozelSayisalDeneme(models.Model):
    class Format(models.IntegerChoices):
        SORU_90 = 90, "90 soru"
        SORU_75 = 75, "75 soru"

    ad = models.CharField(max_length=200, verbose_name="Deneme adı")
    sinav_tarihi = models.DateField(verbose_name="Sınav tarihi")
    soru_formati = models.PositiveSmallIntegerField(
        choices=Format.choices,
        default=Format.SORU_90,
        verbose_name="Soru formatı",
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
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.PROTECT,
        related_name="ss_denemeleri",
        verbose_name="Etüt hocası",
    )
    veliye_goster = models.BooleanField(
        default=True,
        verbose_name="Veli panelinde göster",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    haric_talebeler = models.ManyToManyField(
        "Talebe",
        blank=True,
        related_name="ss_deneme_haric",
        verbose_name="Katılmayan / hariç talebeler",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_ss_denemeler",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sözel–sayısal deneme"
        verbose_name_plural = "Sözel–sayısal denemeler"
        ordering = ["-sinav_tarihi", "-id"]

    def __str__(self):
        return self.ad

    @property
    def sinif_goster(self) -> str:
        return self.hedef_siniflar.strip() or self.sinif_seviyesi

    @property
    def soru_sayisi(self) -> int:
        return int(self.soru_formati)


class SozelSayisalSonuc(models.Model):
    deneme = models.ForeignKey(
        SozelSayisalDeneme,
        on_delete=models.CASCADE,
        related_name="sonuclar",
        verbose_name="Deneme",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="ss_deneme_sonuclari",
        verbose_name="Talebe",
    )
    sozel_dogru = models.PositiveIntegerField(default=0)
    sozel_yanlis = models.PositiveIntegerField(default=0)
    sozel_bos = models.PositiveIntegerField(default=0)
    sozel_net = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    sayisal_dogru = models.PositiveIntegerField(default=0)
    sayisal_yanlis = models.PositiveIntegerField(default=0)
    sayisal_bos = models.PositiveIntegerField(default=0)
    sayisal_net = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    toplam_dogru = models.PositiveIntegerField(default=0)
    toplam_yanlis = models.PositiveIntegerField(default=0)
    toplam_bos = models.PositiveIntegerField(default=0)
    toplam_net = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    puan = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_ss_deneme_sonuclari",
        verbose_name="Kaydeden",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sözel–sayısal sonuç"
        verbose_name_plural = "Sözel–sayısal sonuçlar"
        ordering = ["-toplam_net", "talebe__ad_soyad"]
        constraints = [
            models.UniqueConstraint(
                fields=["deneme", "talebe"],
                name="ss_deneme_talebe_tek_sonuc",
            )
        ]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.deneme.ad}"


class SozelSayisalBransSonuc(models.Model):
    class Brans(models.TextChoices):
        TURKCE = "turkce", "Türkçe"
        SOSYAL = "sosyal", "Sosyal"
        DIN = "din", "Din"
        INGILIZCE = "ingilizce", "İngilizce"
        MATEMATIK = "matematik", "Matematik"
        FEN = "fen", "Fen"

    sonuc = models.ForeignKey(
        SozelSayisalSonuc,
        on_delete=models.CASCADE,
        related_name="brans_satirlari",
        verbose_name="Sonuç",
    )
    brans = models.CharField(max_length=20, choices=Brans.choices, verbose_name="Branş")
    dogru = models.PositiveIntegerField(default=0)
    yanlis = models.PositiveIntegerField(default=0)
    bos = models.PositiveIntegerField(default=0)
    net = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = "Sözel–sayısal branş sonucu"
        verbose_name_plural = "Sözel–sayısal branş sonuçları"
        constraints = [
            models.UniqueConstraint(
                fields=["sonuc", "brans"],
                name="ss_deneme_sonuc_brans_benzersiz",
            )
        ]

    @staticmethod
    def net_hesapla(dogru: int, yanlis: int) -> Decimal:
        net = Decimal(int(dogru or 0)) - (Decimal(int(yanlis or 0)) / Decimal("4"))
        if net < 0:
            net = Decimal("0.00")
        return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def clean(self):
        if not self.sonuc_id:
            return
        hedef = brans_soru_sayisi(self.sonuc.deneme, self.brans)
        toplam = int(self.dogru or 0) + int(self.yanlis or 0) + int(self.bos or 0)
        if toplam != hedef:
            raise ValidationError(
                {
                    "dogru": (
                        f"{self.get_brans_display()} için doğru + yanlış + boş "
                        f"{hedef} olmalıdır."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.net = self.net_hesapla(int(self.dogru or 0), int(self.yanlis or 0))
        super().save(*args, **kwargs)
