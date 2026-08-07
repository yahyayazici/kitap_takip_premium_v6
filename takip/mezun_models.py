"""Mezun takip merkezi modelleri."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class MezunProfil(models.Model):
    class IletisimDurumu(models.TextChoices):
        ILETISIMDE = "iletisimde", "İletişimde"
        DUZENLI = "duzenli", "Düzenli İletişim"
        PASIF = "pasif", "Pasif"
        GORUSULMEDI = "gorusulmedi", "Görüşülmedi"

    class KurumBagi(models.TextChoices):
        AKTIF = "aktif", "Aktif"
        DUZENLI = "duzenli_iletisim", "Düzenli İletişim"
        ETKINLIK = "etkinlik_katilimci", "Etkinlik Katılımcısı"
        UZUN_SURE = "uzun_sure", "Uzun Süredir Görüşülmedi"

    talebe = models.OneToOneField(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="mezun_profili",
        verbose_name="Talebe",
    )
    mezuniyet_yili = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Mezuniyet yılı",
    )
    mezuniyet_tarihi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Mezuniyet tarihi",
    )
    donem = models.ForeignKey(
        "Donem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mezun_profilleri",
        verbose_name="Dönem",
    )
    lgs_puani = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="LGS puanı",
    )
    lgs_sira = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="LGS sıra",
    )
    lgs_yuzdelik = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="LGS yüzdelik dilim",
    )
    yerlestigi_lise = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Yerleştiği lise",
    )
    lise_yerlesme_yili = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Lise yerleşme yılı",
    )
    universite = models.CharField(max_length=200, blank=True, verbose_name="Üniversite")
    bolum = models.CharField(max_length=200, blank=True, verbose_name="Bölüm")
    universite_yerlesme_yili = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Üniversite yerleşme yılı",
    )
    yks_puani = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="YKS puanı",
    )
    yks_sira = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="YKS başarı sırası",
    )
    meslek = models.CharField(max_length=120, blank=True, verbose_name="Meslek")
    calistigi_kurum = models.CharField(max_length=200, blank=True, verbose_name="Çalıştığı kurum")
    sehir = models.CharField(max_length=80, blank=True, verbose_name="Şehir")
    ulke = models.CharField(max_length=80, blank=True, default="Türkiye", verbose_name="Ülke")
    iletisim_telefon = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    iletisim_eposta = models.EmailField(blank=True, verbose_name="E-posta")
    iletisim_adres = models.TextField(blank=True, verbose_name="Adres")
    iletisim_durumu = models.CharField(
        max_length=16,
        choices=IletisimDurumu.choices,
        default=IletisimDurumu.ILETISIMDE,
        verbose_name="İletişim durumu",
    )
    kurum_bagi = models.CharField(
        max_length=20,
        choices=KurumBagi.choices,
        default=KurumBagi.AKTIF,
        verbose_name="Kurum bağı",
    )
    son_gorusme_tarihi = models.DateField(null=True, blank=True, verbose_name="Son görüşme")
    notlar = models.TextField(blank=True, verbose_name="Notlar")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mezun profili"
        verbose_name_plural = "Mezun profilleri"
        ordering = ["-mezuniyet_tarihi", "-id"]

    def __str__(self) -> str:
        return f"{self.talebe.ad_soyad} — Mezun"

    @property
    def yuzdelik_goster(self) -> str:
        if self.lgs_yuzdelik is not None:
            return f"%{self.lgs_yuzdelik}"
        return "—"


class MezunYolculukOlay(models.Model):
    class Tur(models.TextChoices):
        MEZUNIYET = "mezuniyet", "Mezuniyet"
        LGS = "lgs", "LGS"
        LISE = "lise", "Lise"
        ETKINLIK = "etkinlik", "Etkinlik"
        YKS = "yks", "YKS"
        UNIVERSITE = "universite", "Üniversite"
        KARIYER = "kariyer", "Kariyer"
        DIGER = "diger", "Diğer"

    profil = models.ForeignKey(
        MezunProfil,
        on_delete=models.CASCADE,
        related_name="yolculuk_olaylari",
        verbose_name="Mezun profili",
    )
    yil = models.PositiveSmallIntegerField(verbose_name="Yıl")
    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    tur = models.CharField(max_length=16, choices=Tur.choices, default=Tur.DIGER)
    tarih = models.DateField(null=True, blank=True, verbose_name="Tarih")
    otomatik = models.BooleanField(default=False, verbose_name="Otomatik")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mezun yolculuk olayı"
        verbose_name_plural = "Mezun yolculuk olayları"
        ordering = ["-yil", "-tarih", "-sira", "-id"]


class MezunIletisim(models.Model):
    class Tur(models.TextChoices):
        TELEFON = "telefon", "Telefon"
        WHATSAPP = "whatsapp", "WhatsApp"
        ZIYARET = "ziyaret", "Ziyaret"
        SEMINER = "seminer", "Seminer"
        BULUSMA = "bulusma", "Mezun Buluşması"
        KARIYER = "kariyer", "Kariyer Görüşmesi"
        DIGER = "diger", "Diğer"

    profil = models.ForeignKey(
        MezunProfil,
        on_delete=models.CASCADE,
        related_name="iletisim_kayitlari",
        verbose_name="Mezun profili",
    )
    tur = models.CharField(max_length=16, choices=Tur.choices, default=Tur.TELEFON)
    tarih = models.DateField(verbose_name="Tarih")
    aciklama = models.TextField(verbose_name="Açıklama")
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mezun_iletisim_kayitlari",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mezun iletişim kaydı"
        verbose_name_plural = "Mezun iletişim kayıtları"
        ordering = ["-tarih", "-id"]


class MezunBasari(models.Model):
    class Kategori(models.TextChoices):
        LGS = "lgs", "LGS Başarısı"
        YKS = "yks", "YKS Başarısı"
        AKADEMIK = "akademik", "Akademik Başarı"
        MESLEKI = "mesleki", "Mesleki Başarı"
        SPOR = "spor", "Spor"
        SANAT = "sanat", "Sanat"
        ODUL = "odul", "Ödül"
        PROJE = "proje", "Proje"
        DIGER = "diger", "Diğer"

    profil = models.ForeignKey(
        MezunProfil,
        on_delete=models.CASCADE,
        related_name="basarilar",
        verbose_name="Mezun profili",
    )
    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    kategori = models.CharField(max_length=16, choices=Kategori.choices, default=Kategori.DIGER)
    tarih = models.DateField(verbose_name="Tarih")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    kurum_yarisma = models.CharField(max_length=200, blank=True, verbose_name="Kurum / Yarışma")
    arsivde_goster = models.BooleanField(default=False, verbose_name="Başarı arşivinde göster")
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_mezun_basarilari",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mezun başarısı"
        verbose_name_plural = "Mezun başarıları"
        ordering = ["-tarih", "-id"]


class MezunEtkinlik(models.Model):
    class Tur(models.TextChoices):
        BULUSMA = "bulusma", "Mezun Buluşması"
        SEMINER = "seminer", "Seminer"
        KARIYER = "kariyer", "Kariyer Günü"
        SOYLESI = "soylesi", "Söyleşi"
        TANITIM = "tanitim", "Tanıtım Günü"
        ZIYARET = "ziyaret", "Kurum Ziyareti"

    ad = models.CharField(max_length=200, verbose_name="Etkinlik adı")
    tur = models.CharField(max_length=16, choices=Tur.choices, default=Tur.BULUSMA)
    tarih = models.DateField(verbose_name="Tarih")
    saat = models.TimeField(null=True, blank=True, verbose_name="Saat")
    yer = models.CharField(max_length=200, blank=True, verbose_name="Yer")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_mezun_etkinlikleri",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mezun etkinliği"
        verbose_name_plural = "Mezun etkinlikleri"
        ordering = ["-tarih", "-id"]

    def __str__(self) -> str:
        return self.ad


class MezunEtkinlikKatilim(models.Model):
    class Durum(models.TextChoices):
        KATILDI = "katildi", "Katıldı"
        KATILMADI = "katilmadi", "Katılmadı"
        DAVET = "davet", "Davet Edildi"
        BEKLEMEDE = "beklemede", "Cevap Bekleniyor"

    etkinlik = models.ForeignKey(
        MezunEtkinlik,
        on_delete=models.CASCADE,
        related_name="katilimlar",
        verbose_name="Etkinlik",
    )
    profil = models.ForeignKey(
        MezunProfil,
        on_delete=models.CASCADE,
        related_name="etkinlik_katilimlari",
        verbose_name="Mezun",
    )
    durum = models.CharField(max_length=12, choices=Durum.choices, default=Durum.DAVET)
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Etkinlik katılımı"
        verbose_name_plural = "Etkinlik katılımları"
        constraints = [
            models.UniqueConstraint(
                fields=["etkinlik", "profil"],
                name="benzersiz_mezun_etkinlik_katilim",
            )
        ]


class MezunGuncellemeGorevi(models.Model):
    baslik = models.CharField(max_length=200, verbose_name="Görev başlığı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    sorumlu = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mezun_guncelleme_gorevleri",
        verbose_name="Sorumlu personel",
    )
    son_tarih = models.DateField(verbose_name="Son tarih")
    talep_edilen_alanlar = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Talep edilen alanlar",
    )
    mezuniyet_yili = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Mezuniyet yılı filtresi",
    )
    tamamlandi = models.BooleanField(default=False, verbose_name="Tamamlandı")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_mezun_gorevleri",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mezun güncelleme görevi"
        verbose_name_plural = "Mezun güncelleme görevleri"
        ordering = ["-olusturulma"]


class MezunGuncellemeGorevKayit(models.Model):
    gorev = models.ForeignKey(
        MezunGuncellemeGorevi,
        on_delete=models.CASCADE,
        related_name="kayitlar",
        verbose_name="Görev",
    )
    profil = models.ForeignKey(
        MezunProfil,
        on_delete=models.CASCADE,
        related_name="guncelleme_gorevleri",
        verbose_name="Mezun",
    )
    tamamlandi = models.BooleanField(default=False, verbose_name="Tamamlandı")
    notlar = models.TextField(blank=True, verbose_name="Notlar")
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Görev kaydı"
        verbose_name_plural = "Görev kayıtları"
        constraints = [
            models.UniqueConstraint(
                fields=["gorev", "profil"],
                name="benzersiz_mezun_gorev_kayit",
            )
        ]
