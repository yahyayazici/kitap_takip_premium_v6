"""İletişim Merkezi — paylaşım paketi, şablon ve olay modelleri."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class IletisimKurumAyar(models.Model):
    """Kurumsal mesaj standardı — tek satır (singleton)."""

    varsayilan_hitap = models.CharField(
        max_length=120,
        default="Değerli Velimiz,",
        verbose_name="Varsayılan hitap",
    )
    varsayilan_kapanis = models.CharField(
        max_length=200,
        default="Saygılarımızla,",
        verbose_name="Varsayılan kapanış",
    )
    kurum_imza = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Kurum imzası",
        help_text="Mesaj sonunda görünür; boş bırakılırsa panel adı kullanılır.",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "İletişim kurum ayarı"
        verbose_name_plural = "İletişim kurum ayarları"

    def __str__(self) -> str:
        return "Kurumsal iletişim ayarları"


class IletisimSablon(models.Model):
    class Kategori(models.TextChoices):
        AKADEMIK = "akademik", "Akademik"
        KITAP = "kitap", "Kitap"
        DINI = "dini", "Dinî Eğitim"
        PROGRAM = "program", "Program"
        ETKINLIK = "etkinlik", "Etkinlik"
        IDARI = "idari", "İdari"

    kod = models.SlugField(max_length=80, unique=True, verbose_name="Kod")
    ad = models.CharField(max_length=160, verbose_name="Şablon adı")
    kategori = models.CharField(
        max_length=20,
        choices=Kategori.choices,
        default=Kategori.AKADEMIK,
        verbose_name="Kategori",
    )
    kaynak_moduller = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Kaynak modüller",
        help_text='Örn. ["ktt", "deneme"] — boş ise tüm modüllerde.',
    )
    icerik = models.TextField(verbose_name="Mesaj şablonu")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    varsayilan = models.BooleanField(default=False, verbose_name="Varsayılan")
    sira = models.PositiveSmallIntegerField(default=50, verbose_name="Sıra")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_iletisim_sablonlari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "İletişim şablonu"
        verbose_name_plural = "İletişim şablonları"
        ordering = ["sira", "ad"]

    def __str__(self) -> str:
        return self.ad


class IletisimPaketi(models.Model):
    class KaynakModul(models.TextChoices):
        KTT = "ktt", "KTT"
        DENEME = "deneme", "Deneme"
        KITAP = "kitap", "Kitap"
        KARNE = "karne", "Karne"
        DINI = "dini_egitim", "Dinî Eğitim"
        PROGRAM = "program", "Program"
        YAZILI = "yazili", "Yazılı"
        DUYURU = "duyuru", "Duyuru"
        MANUEL = "manuel", "Manuel"

    class HedefTur(models.TextChoices):
        SINIF_VELILERI = "sinif_velileri", "Sınıf Velileri"
        BIREYSEL_VELI = "bireysel_veli", "Bireysel Veli"
        TUM_VELILER = "tum_veliler", "Tüm Veliler"
        OZEL = "ozel", "Özel"

    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        HAZIR = "hazir", "Paylaşmaya Hazır"
        PAYLASIM_BASLATILDI = "paylasim_baslatildi", "Paylaşım Başlatıldı"

    class Kanal(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"

    baslik = models.CharField(max_length=240, verbose_name="Başlık")
    kaynak_modul = models.CharField(
        max_length=30,
        choices=KaynakModul.choices,
        default=KaynakModul.MANUEL,
        verbose_name="Kaynak modül",
    )
    kaynak_tur = models.CharField(max_length=60, blank=True, verbose_name="Kaynak tür")
    kaynak_id = models.CharField(max_length=64, blank=True, verbose_name="Kaynak ID")
    kaynak_imza = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Kaynak imza",
        help_text="Kaynak güncellendiğinde paket yenilenmesi için.",
    )
    hedef_tur = models.CharField(
        max_length=30,
        choices=HedefTur.choices,
        default=HedefTur.SINIF_VELILERI,
        verbose_name="Hedef tür",
    )
    hedef_etiket = models.CharField(max_length=200, verbose_name="Hedef etiket")
    sinif_sube = models.ForeignKey(
        "SinifSube",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="iletisim_paketleri",
        verbose_name="Sınıf / şube",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="iletisim_paketleri",
        verbose_name="Talebe",
    )
    sablon = models.ForeignKey(
        IletisimSablon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paketler",
        verbose_name="Şablon",
    )
    mesaj = models.TextField(verbose_name="Mesaj metni")
    kanal = models.CharField(
        max_length=20,
        choices=Kanal.choices,
        default=Kanal.WHATSAPP,
        verbose_name="Kanal",
    )
    durum = models.CharField(
        max_length=24,
        choices=Durum.choices,
        default=Durum.HAZIR,
        verbose_name="Durum",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_iletisim_paketleri",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "İletişim paketi"
        verbose_name_plural = "İletişim paketleri"
        ordering = ["-guncellenme", "-id"]
        indexes = [
            models.Index(fields=["durum", "-guncellenme"]),
            models.Index(fields=["kaynak_modul", "kaynak_tur", "kaynak_id"]),
            models.Index(fields=["talebe", "-guncellenme"]),
        ]

    def __str__(self) -> str:
        return self.baslik


class IletisimEki(models.Model):
    class Kaynak(models.TextChoices):
        URETILEN_PDF = "uretilen_pdf", "Üretilen PDF"
        MEVCUT_DOSYA = "mevcut_dosya", "Mevcut dosya"

    paket = models.ForeignKey(
        IletisimPaketi,
        on_delete=models.CASCADE,
        related_name="ekler",
        verbose_name="Paket",
    )
    dosya = models.FileField(
        upload_to="iletisim/ekler/%Y/%m/",
        verbose_name="Dosya",
    )
    dosya_adi = models.CharField(max_length=240, verbose_name="Dosya adı")
    mime_type = models.CharField(max_length=80, default="application/pdf")
    kaynak = models.CharField(
        max_length=20,
        choices=Kaynak.choices,
        default=Kaynak.URETILEN_PDF,
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="iletisim_ekleri",
        verbose_name="İlişkili talebe",
        help_text="Bireysel belgelerde doğrulama için.",
    )
    kaynak_modul = models.CharField(max_length=30, blank=True)
    kaynak_id = models.CharField(max_length=64, blank=True)
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "İletişim eki"
        verbose_name_plural = "İletişim ekleri"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.dosya_adi


class IletisimOlay(models.Model):
    class OlayTur(models.TextChoices):
        PACKAGE_CREATED = "package_created", "Paket oluşturuldu"
        PDF_GENERATED = "pdf_generated", "PDF oluşturuldu"
        MESSAGE_COPIED = "message_copied", "Mesaj kopyalandı"
        FILE_DOWNLOADED = "file_downloaded", "Dosya indirildi"
        WHATSAPP_SHARE_OPENED = "whatsapp_share_opened", "WhatsApp paylaşımı açıldı"
        NATIVE_SHARE_OPENED = "native_share_opened", "Cihaz paylaşımı açıldı"
        DRAFT_SAVED = "draft_saved", "Taslak kaydedildi"

    paket = models.ForeignKey(
        IletisimPaketi,
        on_delete=models.CASCADE,
        related_name="olaylar",
        verbose_name="Paket",
    )
    olay_tur = models.CharField(max_length=40, choices=OlayTur.choices)
    kullanici = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="iletisim_olaylari",
    )
    meta = models.JSONField(default=dict, blank=True)
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "İletişim olayı"
        verbose_name_plural = "İletişim olayları"
        ordering = ["-olusturulma"]
        indexes = [
            models.Index(fields=["olay_tur", "-olusturulma"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_olay_tur_display()} · {self.paket_id}"
