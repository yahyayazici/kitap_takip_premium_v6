"""E-Kitap (``ekitap.<domain>``) — akıllı tahtada gösterilen deneme kitapçıkları.

Bu modeller ana sitenin kullanıcı/öğrenci sistemine **hiçbir** ilişki kurmaz:
User, Talebe veya yetki tablosuna yabancı anahtar yoktur. Yönetici girişi ortam
değişkenindeki şifreyle, görüntüleme ise yöneticinin belirlediği PIN ile yapılır.
"""

from __future__ import annotations

from django.db import models

from takip.ekitap_storage import ekitap_depolama


class EKitap(models.Model):
    ad = models.CharField("Kitap adı", max_length=160)
    gorunur = models.BooleanField(
        "Görüntüleme sayfasında göster",
        default=True,
        help_text="Kapalıysa kitap tahtadaki listede görünmez.",
    )
    sira = models.PositiveIntegerField("Sıra", default=0)
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sira", "-olusturulma"]
        verbose_name = "E-kitap"
        verbose_name_plural = "E-kitaplar"

    def __str__(self) -> str:
        return self.ad

    def hazir_bolumler(self):
        return self.bolumler.filter(islem_durumu=EKitapBolum.IslemDurumu.HAZIR)


class EKitapBolum(models.Model):
    """Kitabın bir PDF'i — ör. "Sayısal", "Sözel". Tahtada sekme olarak görünür."""

    class IslemDurumu(models.TextChoices):
        BEKLIYOR = "bekliyor", "İşleniyor"
        HAZIR = "hazir", "Hazır"
        HATA = "hata", "Hata"

    kitap = models.ForeignKey(EKitap, on_delete=models.CASCADE, related_name="bolumler")
    ad = models.CharField("Bölüm adı", max_length=80)
    sira = models.PositiveIntegerField("Sıra", default=0)
    pdf = models.FileField("PDF", storage=ekitap_depolama, upload_to="pdf/", max_length=255)
    sayfa_sayisi = models.PositiveIntegerField(default=0)
    islem_durumu = models.CharField(
        max_length=12, choices=IslemDurumu.choices, default=IslemDurumu.BEKLIYOR
    )
    islem_notu = models.CharField(max_length=255, blank=True)
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sira", "id"]
        verbose_name = "E-kitap bölümü"
        verbose_name_plural = "E-kitap bölümleri"

    def __str__(self) -> str:
        return f"{self.kitap.ad} · {self.ad}"


class EKitapSayfa(models.Model):
    bolum = models.ForeignKey(EKitapBolum, on_delete=models.CASCADE, related_name="sayfalar")
    sira = models.PositiveIntegerField()
    gorsel = models.ImageField(storage=ekitap_depolama, upload_to="sayfa/", max_length=255)
    kucuk = models.ImageField(storage=ekitap_depolama, upload_to="kucuk/", max_length=255, blank=True)
    genislik = models.PositiveIntegerField(default=0)
    yukseklik = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sira"]
        constraints = [
            models.UniqueConstraint(fields=["bolum", "sira"], name="benzersiz_ekitap_sayfa"),
        ]


class EKitapAyar(models.Model):
    """Tek satırlık ayar tablosu (pk=1): görüntüleme PIN'inin özeti."""

    pin_hash = models.CharField(max_length=255, blank=True)
    pin_surumu = models.PositiveIntegerField(
        default=0,
        help_text="PIN değişince artar; eski PIN ile açılmış tahtalar yeniden PIN ister.",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "E-kitap ayarı"

    @classmethod
    def al(cls) -> EKitapAyar:
        ayar, _ = cls.objects.get_or_create(pk=1)
        return ayar
