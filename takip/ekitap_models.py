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

    class TespitDurumu(models.TextChoices):
        YOK = "yok", "Yapılmadı"
        ARANIYOR = "araniyor", "Aranıyor"
        TAMAM = "tamam", "Tamam"
        TARANMIS = "taranmis", "Taranmış PDF"
        BOS = "bos", "Soru bulunamadı"
        HATA = "hata", "Hata"

    tespit_durumu = models.CharField(
        max_length=12, choices=TespitDurumu.choices, default=TespitDurumu.YOK
    )
    tespit_notu = models.CharField(max_length=255, blank=True)
    pdf_ozeti = models.CharField(
        max_length=64, blank=True, help_text="Son soru tespitinde PDF'in SHA-256 özeti."
    )
    sira_elle = models.BooleanField(
        default=False, help_text="Okuma sırası yönetimde elle düzenlendi; yeniden tespit sırayı bozmaz."
    )
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
    metinli = models.BooleanField(default=True, help_text="Sayfada yazı katmanı var mı (taranmış değil).")
    kontrol_gerekli = models.BooleanField(default=False)
    kontrol_notu = models.CharField(max_length=500, blank=True)
    onaylandi = models.BooleanField(
        default=False, help_text="Yönetici sayfayı onayladı; yeniden tespit 'Kontrol edin' işaretini geri getirmez."
    )

    class Meta:
        ordering = ["sira"]
        constraints = [
            models.UniqueConstraint(fields=["bolum", "sira"], name="benzersiz_ekitap_sayfa"),
        ]


class EKitapSoru(models.Model):
    """Bir bölümde tespit edilen (ya da elle işaretlenen) soru.

    Alanlar sayfa kaydına değil sayfa sırasına bağlıdır: PDF yeniden
    işlendiğinde sayfa kayıtları yeniden oluşur, elle yapılan düzeltmeler kalır.
    """

    class Kaynak(models.TextChoices):
        OTOMATIK = "otomatik", "Otomatik"
        ELLE = "elle", "Elle"

    bolum = models.ForeignKey(EKitapBolum, on_delete=models.CASCADE, related_name="sorular")
    test_no = models.PositiveSmallIntegerField(
        default=1, help_text="Bölüm içindeki test; numaralar her testte 1'den başlar."
    )
    no = models.PositiveSmallIntegerField("Soru numarası")
    sira = models.PositiveIntegerField("Okuma sırası", default=0)
    guven = models.FloatField("Tespit güveni", default=1.0)
    kaynak = models.CharField(max_length=10, choices=Kaynak.choices, default=Kaynak.OTOMATIK)
    onayli = models.BooleanField(
        default=False, help_text="Yönetici onayladı; otomatik tespit yeniden çalışınca korunur."
    )
    inceleme_gerekli = models.BooleanField(
        default=False, help_text="Onaydan sonra PDF değişti; alanları yeniden inceleyin."
    )
    gizli = models.BooleanField(
        default=False,
        help_text="Yönetimde silindi: tahtada görünmez, yeniden tespitte geri gelmez.",
    )
    pdf_ozeti = models.CharField(max_length=64, blank=True)
    # Şık perdesi: şıkların başladığı alan (sıra) ve o sayfadaki y (0–1). Bilinmiyorsa boş;
    # öğretmen perde aracıyla elle seçer.
    siklar_alan = models.PositiveSmallIntegerField(null=True, blank=True)
    siklar_y = models.FloatField(null=True, blank=True)
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["bolum", "sira", "id"]
        verbose_name = "E-kitap sorusu"
        verbose_name_plural = "E-kitap soruları"

    def __str__(self) -> str:
        return f"{self.bolum} · T{self.test_no} · {self.no}"


class EKitapSoruAlan(models.Model):
    """Sorunun bir sayfadaki dikdörtgeni. Koordinatlar 0–1, sol üst orijinli.

    Sonraki sayfada (ya da sütunda) devam eden soruların birden fazla alanı olur.
    """

    soru = models.ForeignKey(EKitapSoru, on_delete=models.CASCADE, related_name="alanlar")
    sira = models.PositiveSmallIntegerField(default=0)
    sayfa_sira = models.PositiveIntegerField("Sayfa (0'dan)")
    x0 = models.FloatField()
    y0 = models.FloatField()
    x1 = models.FloatField()
    y1 = models.FloatField()
    gorsel = models.ImageField(storage=ekitap_depolama, upload_to="soru/", max_length=255, blank=True)
    gorsel_imza = models.CharField(max_length=40, blank=True)
    genislik = models.PositiveIntegerField(default=0)
    yukseklik = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["soru", "sira", "id"]


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
