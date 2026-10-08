from django.db import models


class OptikForm(models.Model):
    """Bir optik kâğıdın kolon haritası. Okuyucu tek; kâğıtlar kayıttır."""

    ad = models.CharField(max_length=120, unique=True, verbose_name="Form adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    satir_uzunluk = models.PositiveIntegerField(verbose_name="Satır uzunluğu")
    kodlama = models.CharField(
        max_length=20,
        default="cp1254",
        verbose_name="Harf düzeni",
        help_text="cp1254 Türkçe Windows, utf-8 düz metin.",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Optik form"
        verbose_name_plural = "Optik formlar"
        ordering = ["ad"]

    def __str__(self):
        return self.ad


class OptikFormAlani(models.Model):
    class Tur(models.TextChoices):
        TC = "tc", "TC"
        NUMARA = "numara", "Öğrenci no"
        NUMARA_KONTROL = "numara_kontrol", "Numara taşma kontrolü"
        KITAPCIK = "kitapcik", "Kitapçık"
        SINIF = "sinif", "Sınıf"
        SUBE = "sube", "Şube"
        AD = "ad", "Ad soyad"
        SIK = "sik", "Şık bölgesi"

    form = models.ForeignKey(
        OptikForm,
        on_delete=models.CASCADE,
        related_name="alanlar",
        verbose_name="Form",
    )
    tur = models.CharField(max_length=20, choices=Tur.choices, verbose_name="Tür")
    baslangic = models.PositiveIntegerField(verbose_name="Başlangıç kolonu")
    bitis = models.PositiveIntegerField(verbose_name="Bitiş kolonu")
    sira = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Optik form alanı"
        verbose_name_plural = "Optik form alanları"
        ordering = ["sira", "id"]

    def __str__(self):
        return f"{self.form.ad} · {self.tur} {self.baslangic}-{self.bitis}"


class Sinav(models.Model):
    """Bu alandaki sınav. Ana sitedeki deneme kaydına bağlı değildir."""

    ad = models.CharField(max_length=200, verbose_name="Sınav adı")
    tarih = models.DateField(verbose_name="Sınav tarihi")
    form = models.ForeignKey(
        OptikForm,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sinavlar",
        verbose_name="Optik form",
    )
    anahtar_a = models.TextField(blank=True, verbose_name="A kitapçık anahtarı")
    anahtar_b = models.TextField(blank=True, verbose_name="B kitapçık anahtarı")
    dagilim = models.TextField(
        blank=True,
        verbose_name="Ders sırası",
        help_text="Şeritteki sıra. Her satır: turkce 15",
    )
    kazanimlar = models.TextField(
        blank=True,
        verbose_name="Soru kazanımları",
        help_text="İsteğe bağlı. Her satır bir soru, şeritteki sırayla.",
    )
    okuma_notu = models.TextField(blank=True, verbose_name="Son okuma notu")
    son_dosya = models.CharField(max_length=255, blank=True, verbose_name="Son dosya")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sınav"
        verbose_name_plural = "Sınavlar"
        ordering = ["-tarih", "-id"]

    def __str__(self):
        return self.ad


class SinavSatiri(models.Model):
    """Optik dosyadaki bir öğrenci satırı. Numarası kaymış olsa da saklanır."""

    sinav = models.ForeignKey(
        Sinav,
        on_delete=models.CASCADE,
        related_name="satirlar",
        verbose_name="Sınav",
    )
    satir_no = models.PositiveIntegerField(verbose_name="Dosya satırı")
    ogrenci_no = models.CharField(max_length=32, blank=True, verbose_name="Öğrenci no")
    ad = models.CharField(max_length=200, verbose_name="Ad soyad")
    kitapcik = models.CharField(max_length=4, blank=True, verbose_name="Kitapçık")
    sinif_metni = models.CharField(max_length=120, blank=True, verbose_name="Sınıf")
    uyarilar = models.TextField(blank=True, verbose_name="Notlar")
    cevaplar = models.TextField(blank=True, verbose_name="Şık şeridi")
    puanlandi = models.BooleanField(default=False, verbose_name="Puanlandı")
    dogru = models.PositiveIntegerField(default=0)
    yanlis = models.PositiveIntegerField(default=0)
    bos = models.PositiveIntegerField(default=0)
    net = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    puan = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Sınav satırı"
        verbose_name_plural = "Sınav satırları"
        ordering = ["satir_no", "id"]

    def __str__(self):
        return f"{self.sinav.ad} · {self.ad}"


class SinavSoru(models.Model):
    satir = models.ForeignKey(
        SinavSatiri,
        on_delete=models.CASCADE,
        related_name="sorular",
        verbose_name="Satır",
    )
    ders_key = models.CharField(max_length=40)
    soru_no = models.PositiveIntegerField()
    sonuc = models.CharField(max_length=10)
    konu_ad = models.CharField(max_length=300, blank=True)
    sira = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Sınav sorusu"
        verbose_name_plural = "Sınav soruları"
        ordering = ["sira", "id"]
