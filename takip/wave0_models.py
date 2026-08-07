"""Wave 0 — RBAC, kernel, gelişim dosyası ve audit modelleri."""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class YetkiModul(models.Model):
    kod = models.CharField(max_length=50, unique=True, verbose_name="Modül kodu")
    ad = models.CharField(max_length=120, verbose_name="Modül adı")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Yetki modülü"
        verbose_name_plural = "Yetki modülleri"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad


class YetkiIslem(models.Model):
    modul = models.ForeignKey(
        YetkiModul,
        on_delete=models.CASCADE,
        related_name="islemler",
        verbose_name="Modül",
    )
    kod = models.CharField(max_length=40, verbose_name="İşlem kodu")
    ad = models.CharField(max_length=80, verbose_name="İşlem adı")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Yetki işlemi"
        verbose_name_plural = "Yetki işlemleri"
        ordering = ["modul__sira", "sira", "kod"]
        constraints = [
            models.UniqueConstraint(
                fields=["modul", "kod"],
                name="benzersiz_modul_islem",
            )
        ]

    def __str__(self):
        return f"{self.modul.ad} — {self.ad}"


class Rol(models.Model):
    slug = models.SlugField(max_length=40, unique=True, verbose_name="Kod")
    ad = models.CharField(max_length=120, verbose_name="Rol adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    sistem_rolu = models.BooleanField(
        default=False,
        verbose_name="Sistem rolü",
        help_text="Silinemez ve temel yapılandırma korunur.",
    )
    legacy_ana_rol = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Eski ana rol kodu",
        help_text="PersonelProfili.ana_rol ile eşleştirme.",
    )
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Rol"
        verbose_name_plural = "Roller"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad


class RolModulErisim(models.Model):
    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE,
        related_name="modul_erisimleri",
        verbose_name="Rol",
    )
    modul = models.ForeignKey(
        YetkiModul,
        on_delete=models.CASCADE,
        related_name="rol_erisimleri",
        verbose_name="Modül",
    )
    erisim = models.BooleanField(default=False, verbose_name="Erişim")

    class Meta:
        verbose_name = "Rol modül erişimi"
        verbose_name_plural = "Rol modül erişimleri"
        constraints = [
            models.UniqueConstraint(
                fields=["rol", "modul"],
                name="benzersiz_rol_modul",
            )
        ]

    def __str__(self):
        durum = "✓" if self.erisim else "✗"
        return f"{self.rol.ad} / {self.modul.ad} {durum}"


class RolIslemYetki(models.Model):
    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE,
        related_name="islem_yetkileri",
        verbose_name="Rol",
    )
    islem = models.ForeignKey(
        YetkiIslem,
        on_delete=models.CASCADE,
        related_name="rol_yetkileri",
        verbose_name="İşlem",
    )
    izin = models.BooleanField(default=False, verbose_name="İzin")

    class Meta:
        verbose_name = "Rol işlem yetkisi"
        verbose_name_plural = "Rol işlem yetkileri"
        constraints = [
            models.UniqueConstraint(
                fields=["rol", "islem"],
                name="benzersiz_rol_islem",
            )
        ]


class RolKapsam(models.Model):
    class KapsamTipi(models.TextChoices):
        TUM = "tum", "Tüm talebeler"
        ETUT_GRUBU = "etut_grubu", "Etüt grubu"
        SINIF_LISTESI = "sinif_listesi", "Sınıf listesi"
        DINI_SEVIYE = "dini_seviye", "Dini ders seviyesi"

    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE,
        related_name="kapsamlar",
        verbose_name="Rol",
    )
    tip = models.CharField(
        max_length=20,
        choices=KapsamTipi.choices,
        default=KapsamTipi.ETUT_GRUBU,
        verbose_name="Kapsam tipi",
    )
    deger = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Kapsam değeri",
        help_text='Örn. {"sinif_sube_ids": [1, 2]}',
    )

    class Meta:
        verbose_name = "Rol kapsamı"
        verbose_name_plural = "Rol kapsamları"

    def __str__(self):
        return f"{self.rol.ad} — {self.get_tip_display()}"


class KullaniciRol(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="atanan_roller",
        verbose_name="Kullanıcı",
    )
    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE,
        related_name="kullanicilar",
        verbose_name="Rol",
    )
    birincil = models.BooleanField(default=True, verbose_name="Birincil rol")

    class Meta:
        verbose_name = "Kullanıcı rolü"
        verbose_name_plural = "Kullanıcı rolleri"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "rol"],
                name="benzersiz_kullanici_rol",
            )
        ]

    def __str__(self):
        return f"{self.user.username} — {self.rol.ad}"


class KullaniciYetkiOverride(models.Model):
    class Etki(models.TextChoices):
        GRANT = "grant", "İzin ver"
        DENY = "deny", "Engelle"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="yetki_overrides",
        verbose_name="Kullanıcı",
    )
    modul = models.ForeignKey(
        YetkiModul,
        on_delete=models.CASCADE,
        related_name="kullanici_overrides",
        verbose_name="Modül",
    )
    islem_kod = models.CharField(max_length=40, verbose_name="İşlem kodu")
    etki = models.CharField(
        max_length=10,
        choices=Etki.choices,
        default=Etki.GRANT,
        verbose_name="Etki",
    )
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Açıklama")

    class Meta:
        verbose_name = "Kullanıcı yetki override"
        verbose_name_plural = "Kullanıcı yetki override'ları"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "modul", "islem_kod"],
                name="benzersiz_kullanici_modul_islem",
            )
        ]


class EgitimYili(models.Model):
    ad = models.CharField(max_length=40, verbose_name="Eğitim yılı")
    baslangic = models.DateField(verbose_name="Başlangıç")
    bitis = models.DateField(verbose_name="Bitiş")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Eğitim yılı"
        verbose_name_plural = "Eğitim yılları"
        ordering = ["-baslangic"]

    def __str__(self):
        return self.ad


class Donem(models.Model):
    egitim_yili = models.ForeignKey(
        EgitimYili,
        on_delete=models.CASCADE,
        related_name="donemler",
        verbose_name="Eğitim yılı",
    )
    ad = models.CharField(max_length=80, verbose_name="Dönem adı")
    baslangic = models.DateField(verbose_name="Başlangıç")
    bitis = models.DateField(verbose_name="Bitiş")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Dönem"
        verbose_name_plural = "Dönemler"
        ordering = ["-baslangic"]

    def __str__(self):
        return f"{self.egitim_yili.ad} — {self.ad}"


class Brans(models.Model):
    ad = models.CharField(max_length=80, unique=True, verbose_name="Branş")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Branş"
        verbose_name_plural = "Branşlar"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad


class Ders(models.Model):
    ad = models.CharField(max_length=120, verbose_name="Ders adı")
    brans = models.ForeignKey(
        Brans,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dersler",
        verbose_name="Branş",
    )
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Ders"
        verbose_name_plural = "Dersler"
        ordering = ["sira", "ad"]

    def __str__(self):
        if self.brans_id:
            return f"{self.ad} ({self.brans.ad})"
        return self.ad


class DiniDersSeviyesi(models.Model):
    ad = models.CharField(max_length=80, unique=True, verbose_name="Seviye adı")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    hocalar = models.ManyToManyField(
        "EtutHocasi",
        blank=True,
        related_name="sorumlu_dini_ders_seviyeleri",
        verbose_name="Sorumlu hocalar",
    )

    class Meta:
        verbose_name = "Dini ders seviyesi"
        verbose_name_plural = "Dini ders seviyeleri"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad


class VeliKisi(models.Model):
    class Yakinlik(models.TextChoices):
        ANNE = "anne", "Anne"
        BABA = "baba", "Baba"
        VELI = "veli", "Veli"
        DIGER = "diger", "Diğer"

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="veli_kisileri",
        verbose_name="Talebe",
    )
    yakinlik = models.CharField(
        max_length=10,
        choices=Yakinlik.choices,
        default=Yakinlik.VELI,
        verbose_name="Yakınlık",
    )
    ad_soyad = models.CharField(max_length=120, verbose_name="Ad soyad")
    telefon = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    eposta = models.EmailField(blank=True, verbose_name="E-posta")
    birincil = models.BooleanField(default=False, verbose_name="Birincil iletişim")

    class Meta:
        verbose_name = "Veli kişi"
        verbose_name_plural = "Veli kişiler"
        ordering = ["-birincil", "ad_soyad"]

    def __str__(self):
        return f"{self.ad_soyad} ({self.get_yakinlik_display()})"


class VeliHesap(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="veli_hesabi",
        verbose_name="Kullanıcı hesabı",
    )
    ad_soyad = models.CharField(max_length=120, verbose_name="Ad soyad")
    telefon = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Veli hesabı"
        verbose_name_plural = "Veli hesapları"

    def __str__(self):
        return self.ad_soyad


class VeliTalebeBaglantisi(models.Model):
    veli = models.ForeignKey(
        VeliHesap,
        on_delete=models.CASCADE,
        related_name="talebe_baglantilari",
        verbose_name="Veli",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="veli_baglantilari",
        verbose_name="Talebe",
    )
    yakinlik = models.CharField(
        max_length=10,
        choices=VeliKisi.Yakinlik.choices,
        default=VeliKisi.Yakinlik.VELI,
        verbose_name="Yakınlık",
    )

    class Meta:
        verbose_name = "Veli–talebe bağlantısı"
        verbose_name_plural = "Veli–talebe bağlantıları"
        constraints = [
            models.UniqueConstraint(
                fields=["veli", "talebe"],
                name="benzersiz_veli_talebe",
            )
        ]


class TalebeGenelDurum(models.Model):
    class DurumKodu(models.TextChoices):
        IYI = "iyi", "Çok iyi"
        TAKIP = "takip", "Takip ediliyor"
        RISK = "risk", "Riskli"
        PASIF = "pasif", "Pasif"

    talebe = models.OneToOneField(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="genel_durum",
        verbose_name="Talebe",
    )
    durum_kodu = models.CharField(
        max_length=12,
        choices=DurumKodu.choices,
        default=DurumKodu.TAKIP,
        verbose_name="Genel durum",
    )
    ozet = models.TextField(blank=True, verbose_name="Genel durum özeti")
    guncelleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guncelledigi_genel_durumlar",
        verbose_name="Son güncelleyen",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Talebe genel durum"
        verbose_name_plural = "Talebe genel durumlar"


class TalebePersonelNotu(models.Model):
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="personel_notlari",
        verbose_name="Talebe",
    )
    yazar = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="yazdigi_talebe_notlari",
        verbose_name="Yazar",
    )
    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    icerik = models.TextField(verbose_name="İçerik")
    staff_only = models.BooleanField(
        default=True,
        verbose_name="Yalnızca personel",
    )
    veliye_goster = models.BooleanField(
        default=False,
        verbose_name="Veli panelinde göster",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Talebe personel notu"
        verbose_name_plural = "Talebe personel notları"
        ordering = ["-olusturulma"]


class TalebeDosyasi(models.Model):
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="dosyalar",
        verbose_name="Talebe",
    )
    dosya = models.FileField(
        upload_to="talebe_dosyalari/%Y/%m/",
        verbose_name="Dosya",
    )
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Açıklama")
    yukleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="yukledigi_talebe_dosyalari",
        verbose_name="Yükleyen",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Talebe dosyası"
        verbose_name_plural = "Talebe dosyaları"
        ordering = ["-olusturulma"]


class AuditLog(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_kayitlari",
        verbose_name="Kullanıcı",
    )
    islem = models.CharField(max_length=80, verbose_name="İşlem")
    modul = models.CharField(max_length=50, blank=True, verbose_name="Modül")
    nesne_tipi = models.CharField(max_length=80, blank=True, verbose_name="Nesne tipi")
    nesne_id = models.CharField(max_length=40, blank=True, verbose_name="Nesne ID")
    detay = models.JSONField(default=dict, blank=True, verbose_name="Detay")
    olusturulma = models.DateTimeField(default=timezone.now, verbose_name="Tarih")

    class Meta:
        verbose_name = "Audit kaydı"
        verbose_name_plural = "Audit kayıtları"
        ordering = ["-olusturulma"]
