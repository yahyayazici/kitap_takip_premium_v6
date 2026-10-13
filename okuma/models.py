"""Deneme → Test → Soru (A sırası) → KitapçıkSıra; Optik yükleme → satır → sonuç.

Soruların ana sırası A kitapçığıdır. Diğer kitapçıklar `KitapcikSira` ile
A'daki soruya bağlanır, böylece kazanım ve madde analizi kitapçıktan bağımsızdır.
"""

from django.conf import settings
from django.db import models


class Ogrenci(models.Model):
    numara = models.CharField("Numara", max_length=20, unique=True)
    ad_soyad = models.CharField("Ad soyad", max_length=120, blank=True)
    sinif_seviyesi = models.CharField("Sınıf seviyesi", max_length=10, blank=True)
    sube = models.CharField("Şube", max_length=10, blank=True)
    # Ana sitedeki talebe kaydıyla eşleştirme için (ileride doldurulacak).
    dis_kimlik = models.CharField("Ana site kimliği", max_length=40, blank=True)
    aktif = models.BooleanField(default=True)
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Öğrenci"
        verbose_name_plural = "Öğrenciler"
        ordering = ["sinif_seviyesi", "sube", "numara"]

    def __str__(self):
        return f"{self.numara} {self.ad_soyad}".strip()


class Kazanim(models.Model):
    ders = models.CharField("Ders", max_length=60)
    kod = models.CharField("Kod", max_length=40, blank=True)
    metin = models.CharField("Kazanım", max_length=400)

    class Meta:
        verbose_name = "Kazanım"
        verbose_name_plural = "Kazanımlar"
        ordering = ["ders", "kod", "metin"]
        constraints = [
            models.UniqueConstraint(fields=["ders", "kod", "metin"], name="kazanim_benzersiz"),
        ]

    def __str__(self):
        return f"{self.kod} {self.metin}".strip()


class OptikSablon(models.Model):
    """Okuyucu çıktısındaki sabit genişlikli alanlar. Sütunlar 1'den başlar."""

    ad = models.CharField("Şablon adı", max_length=120, unique=True)
    kodlama = models.CharField("Dosya kodlaması", max_length=20, default="cp1254")
    numara_bas = models.PositiveSmallIntegerField("Numara başlangıç sütunu")
    numara_uzunluk = models.PositiveSmallIntegerField("Numara uzunluğu")
    kitapcik_bas = models.PositiveSmallIntegerField("Kitapçık sütunu", null=True, blank=True)
    sinif_bas = models.PositiveSmallIntegerField("Sınıf sütunu", null=True, blank=True)
    sinif_uzunluk = models.PositiveSmallIntegerField("Sınıf uzunluğu", default=1)
    sube_bas = models.PositiveSmallIntegerField("Şube sütunu", null=True, blank=True)
    sube_uzunluk = models.PositiveSmallIntegerField("Şube uzunluğu", default=1)
    ad_bas = models.PositiveSmallIntegerField("Ad soyad başlangıç sütunu", null=True, blank=True)
    ad_uzunluk = models.PositiveSmallIntegerField("Ad soyad uzunluğu", default=0)
    cevap_bas = models.PositiveSmallIntegerField("Cevaplar başlangıç sütunu")
    aciklama = models.TextField(blank=True)

    class Meta:
        verbose_name = "Optik şablon"
        verbose_name_plural = "Optik şablonlar"
        ordering = ["ad"]

    def __str__(self):
        return self.ad


class DenemeTuru(models.Model):
    """Bir sınıf düzeyi için hazır deneme yapısı (ör. 7. sınıf · 90 soru).

    Hepsi aynı fiziksel optik formu kullanır; dersin formdaki blok genişliği
    (`optik_blok`) sabittir, denemedeki soru sayısı bloktan az olabilir.
    """

    ad = models.CharField("Ad", max_length=80, unique=True)
    sinif_seviyesi = models.CharField("Sınıf", max_length=10)
    sablon = models.ForeignKey(OptikSablon, on_delete=models.PROTECT, verbose_name="Optik şablon")
    sira = models.PositiveSmallIntegerField(default=0)
    aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Deneme türü"
        verbose_name_plural = "Deneme türleri"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad

    @property
    def soru_toplam(self) -> int:
        return sum(d.soru_sayisi for d in self.dersler.all())

    @property
    def optik_uzunluk(self) -> int:
        return sum(d.optik_blok for d in self.dersler.all())


class Deneme(models.Model):
    class SinavTuru(models.TextChoices):
        LGS = "LGS", "LGS tarzı"
        GENEL = "GENEL", "Genel / kurum içi"

    class PuanModu(models.TextChoices):
        YOK = "yok", "Puan hesaplanmasın (yalnız net)"
        LGS_TABLO = "lgs_tablo", "LGS — geçmiş yıl katsayıları (tahmini)"
        DENEME_ICI = "deneme_ici", "LGS formülü — deneme içi standart puan"

    ad = models.CharField("Deneme adı", max_length=200)
    tur = models.ForeignKey(
        DenemeTuru, on_delete=models.PROTECT, null=True, blank=True, related_name="denemeler", verbose_name="Deneme türü"
    )
    tarih = models.DateField("Tarih")
    sinif_seviyesi = models.CharField("Sınıf seviyesi", max_length=10)
    sinav_turu = models.CharField("Sınav türü", max_length=10, choices=SinavTuru.choices, default=SinavTuru.LGS)
    yanlis_katsayi = models.PositiveSmallIntegerField(
        "Kaç yanlış bir doğruyu götürür",
        default=3,
        help_text="LGS'de 3 yanlış 1 doğruyu götürür; değiştirmeyin. Yanlış götürmüyorsa 0.",
    )
    puan_modu = models.CharField("Puan modu", max_length=20, choices=PuanModu.choices, default=PuanModu.LGS_TABLO)
    lgs_yili = models.PositiveSmallIntegerField("LGS katsayı yılı", default=2025)
    kitapciklar = models.CharField("Kitapçık türleri", max_length=20, default="A,B")
    sablon = models.ForeignKey(
        OptikSablon, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Varsayılan optik şablon"
    )
    aciklama = models.TextField("Açıklama", blank=True)
    hesaplanma = models.DateTimeField("Son hesaplama", null=True, blank=True)
    olusturan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Deneme"
        verbose_name_plural = "Denemeler"
        ordering = ["-tarih", "-id"]

    def __str__(self):
        return self.ad

    @property
    def kitapcik_listesi(self) -> list[str]:
        return [k.strip().upper() for k in self.kitapciklar.split(",") if k.strip()]

    @property
    def toplam_soru(self) -> int:
        return sum(t.soru_sayisi for t in self.testler.all())

    @property
    def optik_uzunluk(self) -> int:
        """Optik formda cevaplara ayrılan toplam kutu sayısı."""
        return sum(t.blok for t in self.testler.all())


class Test(models.Model):
    """Bir ders bloğu. Optik formda testler `sira` düzeninde art arda gelir;
    her biri formda `optik_blok` kadar yer kaplar (0 ise soru sayısı kadar)."""

    class LgsDers(models.TextChoices):
        TURKCE = "turkce", "Türkçe"
        MATEMATIK = "matematik", "Matematik"
        FEN = "fen", "Fen Bilimleri"
        INKILAP = "inkilap", "İnkılap / Sosyal"
        DIN = "din", "Din Kültürü"
        YABANCI_DIL = "yabanci_dil", "Yabancı Dil"

    deneme = models.ForeignKey(Deneme, on_delete=models.CASCADE, related_name="testler")
    ad = models.CharField("Test adı", max_length=80)
    ders = models.CharField("Ders", max_length=60)
    oturum = models.CharField("Oturum", max_length=40, blank=True)
    sira = models.PositiveSmallIntegerField("Sıra")
    soru_sayisi = models.PositiveSmallIntegerField("Soru sayısı")
    optik_blok = models.PositiveSmallIntegerField("Optik blok genişliği", default=0)
    katsayi = models.DecimalField("Katsayı", max_digits=5, decimal_places=2, default=1)
    lgs_ders = models.CharField("LGS dersi", max_length=20, choices=LgsDers.choices, blank=True)

    @property
    def blok(self) -> int:
        return max(self.optik_blok, self.soru_sayisi)

    class Meta:
        verbose_name = "Test"
        verbose_name_plural = "Testler"
        ordering = ["deneme", "sira"]
        constraints = [models.UniqueConstraint(fields=["deneme", "sira"], name="test_sira_benzersiz")]

    def __str__(self):
        return f"{self.deneme} / {self.ders}"


class DenemeTuruDers(models.Model):
    tur = models.ForeignKey(DenemeTuru, on_delete=models.CASCADE, related_name="dersler")
    sira = models.PositiveSmallIntegerField("Sıra")
    ders = models.CharField("Ders", max_length=60)
    oturum = models.CharField("Oturum", max_length=40, blank=True)
    soru_sayisi = models.PositiveSmallIntegerField("Soru sayısı")
    optik_blok = models.PositiveSmallIntegerField("Optikteki kutu sayısı")
    katsayi = models.DecimalField("Katsayı", max_digits=5, decimal_places=2, default=1)
    lgs_ders = models.CharField("LGS dersi", max_length=20, choices=Test.LgsDers.choices, blank=True)

    class Meta:
        ordering = ["tur", "sira"]
        constraints = [models.UniqueConstraint(fields=["tur", "sira"], name="tur_ders_sira_benzersiz")]

    def __str__(self):
        return f"{self.tur} / {self.ders}"


class Soru(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="sorular")
    no = models.PositiveSmallIntegerField("A kitapçığı soru no")
    dogru = models.CharField("Doğru cevap", max_length=1)
    ek_dogrular = models.CharField("Ek doğru şıklar", max_length=5, blank=True)
    iptal = models.BooleanField("İptal", default=False)
    kazanimlar = models.ManyToManyField(Kazanim, blank=True, related_name="sorular")

    class Meta:
        verbose_name = "Soru"
        verbose_name_plural = "Sorular"
        ordering = ["test__sira", "no"]
        constraints = [models.UniqueConstraint(fields=["test", "no"], name="soru_no_benzersiz")]

    def __str__(self):
        return f"{self.test.ders} {self.no}"

    @property
    def dogru_kume(self) -> set[str]:
        return {self.dogru, *self.ek_dogrular}


class KitapcikSira(models.Model):
    soru = models.ForeignKey(Soru, on_delete=models.CASCADE, related_name="kitapcik_siralari")
    kitapcik = models.CharField("Kitapçık", max_length=1)
    no = models.PositiveSmallIntegerField("Bu kitapçıktaki soru no")

    class Meta:
        verbose_name = "Kitapçık sırası"
        verbose_name_plural = "Kitapçık sıraları"
        constraints = [models.UniqueConstraint(fields=["soru", "kitapcik"], name="kitapcik_sira_benzersiz")]


class OptikYukleme(models.Model):
    deneme = models.ForeignKey(Deneme, on_delete=models.CASCADE, related_name="yuklemeler")
    sablon = models.ForeignKey(OptikSablon, on_delete=models.PROTECT)
    dosya_adi = models.CharField(max_length=255)
    yukleyen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Optik yükleme"
        verbose_name_plural = "Optik yüklemeler"
        ordering = ["-olusturma"]

    def __str__(self):
        return self.dosya_adi


class OptikSatir(models.Model):
    class Durum(models.TextChoices):
        TAMAM = "tamam", "Tamam"
        UYARI = "uyari", "Uyarı"
        HATA = "hata", "Hata"

    yukleme = models.ForeignKey(OptikYukleme, on_delete=models.CASCADE, related_name="satirlar")
    satir_no = models.PositiveIntegerField()
    ham = models.TextField()
    numara = models.CharField(max_length=20, blank=True)
    kitapcik = models.CharField(max_length=1, blank=True)
    sinif = models.CharField(max_length=10, blank=True)
    sube = models.CharField(max_length=10, blank=True)
    ad_soyad = models.CharField(max_length=120, blank=True)
    cevaplar = models.TextField(blank=True)
    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.SET_NULL, null=True, blank=True)
    durum = models.CharField(max_length=10, choices=Durum.choices, default=Durum.TAMAM)
    mesaj = models.CharField(max_length=300, blank=True)
    dahil = models.BooleanField("Hesaba kat", default=True)

    class Meta:
        verbose_name = "Optik satır"
        verbose_name_plural = "Optik satırlar"
        ordering = ["yukleme", "satir_no"]


class Sonuc(models.Model):
    deneme = models.ForeignKey(Deneme, on_delete=models.CASCADE, related_name="sonuclar")
    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.CASCADE, related_name="sonuclar")
    satir = models.ForeignKey(OptikSatir, on_delete=models.SET_NULL, null=True, blank=True)
    kitapcik = models.CharField(max_length=1)
    sube = models.CharField(max_length=10, blank=True)
    # Kitapçıktan bağımsız, A sırasına çevrilmiş cevaplar (testler art arda).
    cevaplar_a = models.TextField()
    dogru = models.PositiveSmallIntegerField(default=0)
    yanlis = models.PositiveSmallIntegerField(default=0)
    bos = models.PositiveSmallIntegerField(default=0)
    net = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    puan = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    sira_kurum = models.PositiveIntegerField(null=True, blank=True)
    sira_sube = models.PositiveIntegerField(null=True, blank=True)
    katilimci = models.PositiveIntegerField(null=True, blank=True)
    yuzdelik = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Sonuç"
        verbose_name_plural = "Sonuçlar"
        ordering = ["deneme", "sira_kurum"]
        constraints = [models.UniqueConstraint(fields=["deneme", "ogrenci"], name="sonuc_benzersiz")]


class TestSonuc(models.Model):
    sonuc = models.ForeignKey(Sonuc, on_delete=models.CASCADE, related_name="test_sonuclari")
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    dogru = models.PositiveSmallIntegerField(default=0)
    yanlis = models.PositiveSmallIntegerField(default=0)
    bos = models.PositiveSmallIntegerField(default=0)
    net = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        ordering = ["test__sira"]
        constraints = [models.UniqueConstraint(fields=["sonuc", "test"], name="test_sonuc_benzersiz")]
