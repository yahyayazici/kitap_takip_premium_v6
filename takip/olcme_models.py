"""Ölçme ve Değerlendirme Merkezi — sınav soruları, zimmet, şablon modelleri."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class OlcumUnite(models.Model):
    sinif_seviyesi = models.CharField(max_length=30, verbose_name="Sınıf seviyesi")
    brans = models.CharField(max_length=20, verbose_name="Branş")
    unite_ad = models.CharField(max_length=200, verbose_name="Ünite adı")
    sira = models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ünite"
        verbose_name_plural = "Üniteler"
        ordering = ["sinif_seviyesi", "brans", "sira", "unite_ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["sinif_seviyesi", "brans", "unite_ad"],
                name="olcum_unite_benzersiz",
            )
        ]

    def __str__(self):
        return f"{self.sinif_seviyesi} · {self.unite_ad}"


class OlcumKazanim(models.Model):
    konu = models.ForeignKey(
        "KonuKatalogu",
        on_delete=models.CASCADE,
        related_name="kazanimlar",
        verbose_name="Konu",
    )
    kazanim_ad = models.CharField(max_length=300, verbose_name="Kazanım")
    kod = models.CharField(max_length=40, blank=True, verbose_name="Kod")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kazanım"
        verbose_name_plural = "Kazanımlar"
        ordering = ["konu_id", "kazanim_ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["konu", "kazanim_ad"],
                name="olcum_kazanim_benzersiz",
            )
        ]

    def __str__(self):
        return self.kazanim_ad


class OlcumSinavDers(models.Model):
    class Bolum(models.TextChoices):
        SOZEL = "sozel", "Sözel"
        SAYISAL = "sayisal", "Sayısal"
        GENEL = "genel", "Genel"

    sinav = models.ForeignKey(
        "KttSinav",
        on_delete=models.CASCADE,
        related_name="olcme_dersleri",
        verbose_name="Sınav",
    )
    bolum = models.CharField(
        max_length=10,
        choices=Bolum.choices,
        default=Bolum.GENEL,
        verbose_name="Bölüm",
    )
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.PROTECT,
        related_name="olcme_sinav_dersleri",
        verbose_name="Ders",
    )
    soru_sayisi = models.PositiveSmallIntegerField(default=0, verbose_name="Soru sayısı")
    katsayi = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        verbose_name="Katsayı",
    )
    sira = models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")

    class Meta:
        verbose_name = "Sınav ders bloğu"
        verbose_name_plural = "Sınav ders blokları"
        ordering = ["sinav_id", "sira", "id"]

    def __str__(self):
        return f"{self.sinav.ad} · {self.ders.ad}"


class OlcumSoru(models.Model):
    class BeceriTuru(models.TextChoices):
        BILGI = "bilgi", "Bilgi"
        KAVRAMA = "kavrama", "Kavrama"
        UYGULAMA = "uygulama", "Uygulama"
        ANALIZ = "analiz", "Analiz"
        PROBLEM = "problem", "Problem çözme"

    class Zorluk(models.TextChoices):
        KOLAY = "kolay", "Kolay"
        ORTA = "orta", "Orta"
        ZOR = "zor", "Zor"

    class SoruTuru(models.TextChoices):
        COKTAN_SECMELI = "coktan_secmeli", "Çoktan seçmeli"
        DOGRU_YANLIS = "dogru_yanlis", "Doğru / Yanlış"

    sinav = models.ForeignKey(
        "KttSinav",
        on_delete=models.CASCADE,
        related_name="olcme_sorulari",
        verbose_name="Sınav",
    )
    soru_no = models.PositiveSmallIntegerField(verbose_name="Soru no")
    sinav_ders = models.ForeignKey(
        OlcumSinavDers,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sorular",
        verbose_name="Ders bloğu",
    )
    bolum = models.CharField(
        max_length=10,
        choices=OlcumSinavDers.Bolum.choices,
        default=OlcumSinavDers.Bolum.GENEL,
        verbose_name="Bölüm",
    )
    unite = models.ForeignKey(
        OlcumUnite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sorular",
        verbose_name="Ünite",
    )
    konu = models.ForeignKey(
        "KonuKatalogu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olcme_sorulari",
        verbose_name="Konu",
    )
    kazanim = models.ForeignKey(
        OlcumKazanim,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sorular",
        verbose_name="Kazanım",
    )
    beceri_turu = models.CharField(
        max_length=20,
        choices=BeceriTuru.choices,
        blank=True,
        verbose_name="Beceri türü",
    )
    zorluk = models.CharField(
        max_length=10,
        choices=Zorluk.choices,
        blank=True,
        verbose_name="Zorluk",
    )
    soru_turu = models.CharField(
        max_length=20,
        choices=SoruTuru.choices,
        default=SoruTuru.COKTAN_SECMELI,
        verbose_name="Soru türü",
    )
    ogretmen_notu = models.CharField(max_length=300, blank=True, verbose_name="Öğretmen notu")
    zimmet_tamam = models.BooleanField(default=False, editable=False, verbose_name="Zimmet tamam")

    class Meta:
        verbose_name = "Sınav sorusu"
        verbose_name_plural = "Sınav soruları"
        ordering = ["sinav_id", "soru_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["sinav", "soru_no"],
                name="olcum_soru_no_benzersiz",
            )
        ]

    def __str__(self):
        return f"S{self.soru_no} · {self.sinav.ad}"

    def zimmet_durumu_guncelle(self, kazanim_zorunlu: bool = False) -> None:
        tamam = bool(self.sinav_ders_id and self.konu_id)
        if kazanim_zorunlu:
            tamam = tamam and bool(self.kazanim_id)
        if self.zimmet_tamam != tamam:
            self.zimmet_tamam = tamam
            self.save(update_fields=["zimmet_tamam"])


class OlcumCevapAnahtari(models.Model):
    class Kitapcik(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"

    class Secenek(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"
        E = "E", "E"

    soru = models.ForeignKey(
        OlcumSoru,
        on_delete=models.CASCADE,
        related_name="cevap_anahtarlari",
        verbose_name="Soru",
    )
    kitapcik = models.CharField(
        max_length=1,
        choices=Kitapcik.choices,
        default=Kitapcik.A,
        verbose_name="Kitapçık",
    )
    dogru_secenek = models.CharField(max_length=1, choices=Secenek.choices, verbose_name="Doğru şık")
    iptal = models.BooleanField(default=False, verbose_name="İptal edildi")
    ek_dogru_secenekler = models.JSONField(default=list, blank=True, verbose_name="Ek doğru şıklar")

    class Meta:
        verbose_name = "Cevap anahtarı"
        verbose_name_plural = "Cevap anahtarları"
        constraints = [
            models.UniqueConstraint(
                fields=["soru", "kitapcik"],
                name="olcum_anahtar_kitapcik_benzersiz",
            )
        ]

    def __str__(self):
        return f"S{self.soru.soru_no} [{self.kitapcik}] → {self.dogru_secenek}"


class OlcumIslemGecmisi(models.Model):
    sinav = models.ForeignKey(
        "KttSinav",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="olcme_islem_gecmisi",
        verbose_name="Sınav",
    )
    soru = models.ForeignKey(
        OlcumSoru,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="islem_gecmisi",
        verbose_name="Soru",
    )
    islem = models.CharField(max_length=40, verbose_name="İşlem")
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    eski_deger = models.JSONField(default=dict, blank=True)
    yeni_deger = models.JSONField(default=dict, blank=True)
    kullanici = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olcme_islemleri",
        verbose_name="Kullanıcı",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ölçme işlem geçmişi"
        verbose_name_plural = "Ölçme işlem geçmişi"
        ordering = ["-olusturulma", "-id"]


class OlcumSinavSablon(models.Model):
    ad = models.CharField(max_length=200, verbose_name="Şablon adı")
    sinav_turu = models.CharField(max_length=20, verbose_name="Sınav türü")
    sinif_seviyesi = models.CharField(max_length=30, verbose_name="Sınıf seviyesi")
    soru_sayisi = models.PositiveSmallIntegerField(verbose_name="Soru sayısı")
    secenek_sayisi = models.PositiveSmallIntegerField(default=4)
    aciklama = models.TextField(blank=True)
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_olcme_sablonlari",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sınav şablonu"
        verbose_name_plural = "Sınav şablonları"
        ordering = ["-olusturulma"]


class OlcumSablonDers(models.Model):
    sablon = models.ForeignKey(
        OlcumSinavSablon,
        on_delete=models.CASCADE,
        related_name="dersler",
        verbose_name="Şablon",
    )
    bolum = models.CharField(max_length=10, default=OlcumSinavDers.Bolum.GENEL)
    ders = models.ForeignKey("Ders", on_delete=models.PROTECT, verbose_name="Ders")
    soru_sayisi = models.PositiveSmallIntegerField(default=0)
    katsayi = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    sira = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["sablon_id", "sira"]


class OlcumSablonSoru(models.Model):
    sablon = models.ForeignKey(
        OlcumSinavSablon,
        on_delete=models.CASCADE,
        related_name="sorular",
        verbose_name="Şablon",
    )
    soru_no = models.PositiveSmallIntegerField()
    bolum = models.CharField(max_length=10, default=OlcumSinavDers.Bolum.GENEL)
    ders = models.ForeignKey("Ders", on_delete=models.PROTECT, null=True, blank=True)
    unite = models.ForeignKey(OlcumUnite, on_delete=models.SET_NULL, null=True, blank=True)
    konu = models.ForeignKey("KonuKatalogu", on_delete=models.SET_NULL, null=True, blank=True)
    kazanim = models.ForeignKey(OlcumKazanim, on_delete=models.SET_NULL, null=True, blank=True)
    beceri_turu = models.CharField(max_length=20, blank=True)
    zorluk = models.CharField(max_length=10, blank=True)
    dogru_secenek = models.CharField(max_length=1, blank=True)

    class Meta:
        ordering = ["sablon_id", "soru_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["sablon", "soru_no"],
                name="olcum_sablon_soru_no_benzersiz",
            )
        ]


class OlcumTalebeCevap(models.Model):
    class Secenek(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"
        E = "E", "E"
        BOS = "BOS", "Boş"

    sinav = models.ForeignKey(
        "KttSinav",
        on_delete=models.CASCADE,
        related_name="talebe_cevaplari",
        verbose_name="Sınav",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="olcme_cevaplari",
        verbose_name="Talebe",
    )
    soru = models.ForeignKey(
        OlcumSoru,
        on_delete=models.CASCADE,
        related_name="talebe_cevaplari",
        verbose_name="Soru",
    )
    secilen = models.CharField(
        max_length=4,
        choices=Secenek.choices,
        default=Secenek.BOS,
        verbose_name="Seçilen şık",
    )
    dogru_mu = models.BooleanField(null=True, editable=False, verbose_name="Doğru mu")
    kitapcik = models.CharField(max_length=1, default="A", verbose_name="Kitapçık")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Talebe soru cevabı"
        verbose_name_plural = "Talebe soru cevapları"
        constraints = [
            models.UniqueConstraint(
                fields=["sinav", "talebe", "soru"],
                name="olcum_talebe_soru_cevap_benzersiz",
            )
        ]
