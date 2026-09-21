"""Akıllı Tahta Dosya Merkezi — veri modelleri.

Hedefleme her zaman sınıf SEVİYESİ (5/6/7/8) üzerindendir, şube (SinifSube)
üzerinden DEĞİL — "5-A ve 5-B ayrı olmayacak" isteği. Proje genelinde zaten
``SinifSube.sinif`` düz bir CharField olarak sorgulanıyor (ayrı bir seviye
modeli yok); bu modül de aynı deseni izler.
"""

from __future__ import annotations

from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from takip.akilli_tahta_storage import akilli_tahta_depolama


class SinifSeviyesi(models.TextChoices):
    BES = "5", "5. Sınıflar"
    ALTI = "6", "6. Sınıflar"
    YEDI = "7", "7. Sınıflar"
    SEKIZ = "8", "8. Sınıflar"


class AkilliTahtaHesap(models.Model):
    """Bir sınıf seviyesine bağlı, kısıtlı akıllı tahta hesabı.

    Normal personel/öğretmen hesabı DEĞİLDİR — yetki sistemine hiç girmez;
    ``kullanici_tahta_mi()`` ile ayrı bir yönlendirme dalında ele alınır.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="akilli_tahta_hesabi",
        verbose_name="Kullanıcı hesabı",
    )
    sinif_seviyesi = models.CharField(
        max_length=1,
        choices=SinifSeviyesi.choices,
        verbose_name="Sınıf seviyesi",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_tahta_hesaplari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Akıllı tahta hesabı"
        verbose_name_plural = "Akıllı tahta hesapları"
        ordering = ["sinif_seviyesi"]

    def __str__(self):
        return f"{self.get_sinif_seviyesi_display()} akıllı tahtası"


class AkilliTahtaDosya(models.Model):
    class IcerikTuru(models.TextChoices):
        DENEME = "deneme", "Deneme"
        TEST = "test", "Test"
        CALISMA_KAGIDI = "calisma_kagidi", "Çalışma Kâğıdı"
        GORSEL = "gorsel", "Görsel"
        VIDEO = "video", "Video"

    class DosyaTuru(models.TextChoices):
        PDF = "pdf", "PDF"
        JPG = "jpg", "JPG"
        JPEG = "jpeg", "JPEG"
        PNG = "png", "PNG"
        WEBP = "webp", "WEBP"
        MP4 = "mp4", "MP4"

    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        YAYINDA = "yayinda", "Yayında"
        ARSIVLENDI = "arsivlendi", "Arşivlendi"

    baslik = models.CharField(max_length=200, verbose_name="Dosya başlığı")
    dosya = models.FileField(
        storage=akilli_tahta_depolama,
        upload_to="",
        verbose_name="Dosya",
    )
    dosya_turu = models.CharField(
        max_length=10,
        choices=DosyaTuru.choices,
        verbose_name="Dosya türü",
        help_text="Yüklemede içeriğin ilk baytlarından (magic number) tespit edilir.",
    )
    icerik_turu = models.CharField(
        max_length=20,
        choices=IcerikTuru.choices,
        verbose_name="İçerik türü",
    )
    ders = models.ForeignKey(
        "takip.Ders",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="akilli_tahta_dosyalari",
        verbose_name="Ders",
    )
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")

    tum_siniflar = models.BooleanField(
        default=False,
        verbose_name="Tüm sınıflara gönder",
    )
    ust_sirada = models.BooleanField(
        default=False,
        verbose_name="Üst sırada göster",
    )
    indirme_izni = models.BooleanField(
        default=True,
        verbose_name="İndirmeye izin ver",
    )

    yayin_baslangic = models.DateTimeField(verbose_name="Yayın başlangıç tarihi/saati")
    yayin_bitis = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Yayından kaldırılma tarihi/saati",
    )

    durum = models.CharField(
        max_length=10,
        choices=Durum.choices,
        default=Durum.TASLAK,
        verbose_name="Durum",
    )

    yukleyen = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="yukledigi_akilli_tahta_dosyalari",
        verbose_name="Yükleyen",
    )

    dosya_hash = models.CharField(max_length=64, db_index=True, verbose_name="SHA-256")
    dosya_boyutu = models.PositiveBigIntegerField(default=0, verbose_name="Dosya boyutu (bayt)")
    mime = models.CharField(max_length=100, blank=True, verbose_name="MIME türü")

    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Akıllı tahta dosyası"
        verbose_name_plural = "Akıllı tahta dosyaları"
        ordering = ["-ust_sirada", "-olusturulma"]

    def __str__(self):
        return self.baslik

    @property
    def gorunur_durum(self) -> str:
        """Taslak/Planlanmış/Yayında/Süresi dolmuş/Arşivlenmiş — hesaplanır."""
        if self.durum == self.Durum.TASLAK:
            return "taslak"
        if self.durum == self.Durum.ARSIVLENDI:
            return "arsivlendi"

        simdi = timezone.now()
        if self.yayin_baslangic and self.yayin_baslangic > simdi:
            return "planlanmis"
        if self.yayin_bitis and self.yayin_bitis <= simdi:
            return "suresi_dolmus"
        return "yayinda"

    def hedefliyor_mu(self, sinif_seviyesi: str) -> bool:
        if self.tum_siniflar:
            return True
        return self.hedefler.filter(sinif_seviyesi=sinif_seviyesi).exists()


class AkilliTahtaHedef(models.Model):
    """``tum_siniflar=False`` olan dosyalar için hedef sınıf seviyeleri."""

    dosya = models.ForeignKey(
        AkilliTahtaDosya,
        on_delete=models.CASCADE,
        related_name="hedefler",
        verbose_name="Dosya",
    )
    sinif_seviyesi = models.CharField(
        max_length=1,
        choices=SinifSeviyesi.choices,
        verbose_name="Sınıf seviyesi",
    )

    class Meta:
        verbose_name = "Akıllı tahta hedefi"
        verbose_name_plural = "Akıllı tahta hedefleri"
        constraints = [
            models.UniqueConstraint(
                fields=["dosya", "sinif_seviyesi"],
                name="benzersiz_akilli_tahta_hedef",
            )
        ]

    def __str__(self):
        return f"{self.dosya.baslik} → {self.get_sinif_seviyesi_display()}"


class AkilliTahtaIslemKaydi(models.Model):
    """Denetim izi — kim, ne zaman, ne yaptı."""

    kullanici = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="akilli_tahta_islemleri",
        verbose_name="Kullanıcı",
    )
    aksiyon = models.CharField(max_length=50, verbose_name="Aksiyon")
    dosya = models.ForeignKey(
        AkilliTahtaDosya,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="islem_kayitlari",
        verbose_name="Dosya",
    )
    hesap = models.ForeignKey(
        AkilliTahtaHesap,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="islem_kayitlari",
        verbose_name="Tahta hesabı",
    )
    detay = models.TextField(blank=True, verbose_name="Detay")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Akıllı tahta işlem kaydı"
        verbose_name_plural = "Akıllı tahta işlem kayıtları"
        ordering = ["-olusturulma"]

    def __str__(self):
        return f"{self.aksiyon} — {self.olusturulma:%d.%m.%Y %H:%M}"
