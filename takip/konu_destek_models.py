"""Konu destek merkezi — video yönlendirme, izleme ve mini test modelleri."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


class KonuKatalogu(models.Model):
    class Brans(models.TextChoices):
        TURKCE = "turkce", "Türkçe"
        MATEMATIK = "matematik", "Matematik"
        FEN = "fen", "Fen Bilimleri"
        SOSYAL = "sosyal", "Sosyal Bilgiler"
        DIN = "din", "Din Kültürü"
        INGILIZCE = "ingilizce", "İngilizce"

    sinif_seviyesi = models.CharField(
        max_length=30,
        verbose_name="Sınıf seviyesi",
        help_text="Örn. 5, 6, 7, 8",
    )
    brans = models.CharField(max_length=20, choices=Brans.choices, verbose_name="Branş")
    konu_ad = models.CharField(max_length=200, verbose_name="Konu adı")
    slug = models.SlugField(max_length=220, blank=True)
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Konu kataloğu"
        verbose_name_plural = "Konu kataloğu"
        ordering = ["sinif_seviyesi", "brans", "konu_ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["sinif_seviyesi", "brans", "konu_ad"],
                name="konu_katalog_benzersiz",
            )
        ]

    def __str__(self):
        return f"{self.sinif_seviyesi}. sınıf · {self.get_brans_display()} · {self.konu_ad}"

    def save(self, *args, **kwargs):
        if not self.slug:
            taban = slugify(f"{self.sinif_seviyesi}-{self.brans}-{self.konu_ad}") or "konu"
            self.slug = taban[:220]
        super().save(*args, **kwargs)

    @property
    def brans_etiket(self) -> str:
        return self.get_brans_display()

    @property
    def arama_metni(self) -> str:
        return f"{self.sinif_seviyesi}. sınıf {self.get_brans_display()} {self.konu_ad} konu anlatımı LGS"


class KonuEgitimVideosu(models.Model):
    class Tur(models.TextChoices):
        ANLATIM = "anlatim", "Konu anlatımı"
        COZUM = "cozum", "Soru çözümü"
        TEKRAR = "tekrar", "Kısa tekrar"

    konu = models.ForeignKey(
        KonuKatalogu,
        on_delete=models.CASCADE,
        related_name="videolar",
        verbose_name="Konu",
    )
    baslik = models.CharField(max_length=300, verbose_name="Video başlığı")
    youtube_id = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="YouTube video ID",
        help_text="Boş bırakılırsa arama sorgusu kullanılır.",
    )
    arama_sorgusu = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="YouTube arama sorgusu",
        help_text="Video ID yoksa panel içi arama oynatıcısı için kullanılır.",
    )
    tur = models.CharField(
        max_length=20,
        choices=Tur.choices,
        default=Tur.ANLATIM,
        verbose_name="Tür",
    )
    sira = models.PositiveSmallIntegerField(default=1, verbose_name="Sıra (1-3)")
    sure_dk = models.PositiveSmallIntegerField(default=10, verbose_name="Süre (dk)")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Eğitim videosu"
        verbose_name_plural = "Eğitim videoları"
        ordering = ["konu_id", "sira", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["konu", "sira"],
                name="konu_video_sira_benzersiz",
            )
        ]

    def __str__(self):
        return self.baslik

    def clean(self):
        super().clean()
        if not self.youtube_id and not self.arama_sorgusu:
            raise ValidationError("YouTube ID veya arama sorgusu girilmelidir.")

    @property
    def panel_embed(self) -> bool:
        return bool((self.youtube_id or "").strip())

    @property
    def youtube_arama_url(self) -> str:
        from urllib.parse import quote_plus

        sorgu = self.arama_sorgusu or self.konu.arama_metni
        return (
            "https://www.youtube.com/results"
            f"?search_query={quote_plus(sorgu)}&sp=EgIQAQ%253D%253D"
        )

    @property
    def embed_url(self) -> str:
        if not self.panel_embed:
            return ""
        from urllib.parse import quote

        from django.conf import settings

        origin = getattr(settings, "SITE_URL", "http://127.0.0.1:8000")
        return (
            f"https://www.youtube-nocookie.com/embed/{self.youtube_id}"
            f"?rel=0&modestbranding=1&playsinline=1"
            f"&origin={quote(origin, safe='')}"
        )


class TalebeKonuEksigi(models.Model):
    class Kaynak(models.TextChoices):
        KTT = "ktt", "KTT"
        DENEME = "deneme", "Deneme"
        EXCEL = "excel", "Excel analiz"
        AI = "ai", "Yapay zeka"
        MANUEL = "manuel", "Manuel"

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="konu_eksikleri",
        verbose_name="Talebe",
    )
    konu = models.ForeignKey(
        KonuKatalogu,
        on_delete=models.CASCADE,
        related_name="talebe_eksikleri",
        verbose_name="Konu",
    )
    kaynak = models.CharField(max_length=20, choices=Kaynak.choices, verbose_name="Kaynak")
    skor = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Skor / puan",
    )
    oncelik = models.PositiveSmallIntegerField(default=50, verbose_name="Öncelik")
    tespit_tarihi = models.DateField(verbose_name="Tespit tarihi")
    cozuldu = models.BooleanField(default=False, verbose_name="Tamamlandı")
    notlar = models.TextField(blank=True, verbose_name="Not")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Talebe konu eksiği"
        verbose_name_plural = "Talebe konu eksikleri"
        ordering = ["-oncelik", "-tespit_tarihi", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["talebe", "konu", "kaynak"],
                name="talebe_konu_kaynak_benzersiz",
            )
        ]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.konu.konu_ad}"


class KonuVideoIzleme(models.Model):
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="konu_video_izlemeleri",
        verbose_name="Talebe",
    )
    konu = models.ForeignKey(
        KonuKatalogu,
        on_delete=models.CASCADE,
        related_name="video_izlemeleri",
        verbose_name="Konu",
    )
    video = models.ForeignKey(
        KonuEgitimVideosu,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="izlemeler",
        verbose_name="Video",
    )
    video_baslik = models.CharField(max_length=300, verbose_name="Video başlığı")
    baslama = models.DateTimeField(verbose_name="Başlangıç")
    bitis = models.DateTimeField(null=True, blank=True, verbose_name="Bitiş")
    sure_sn = models.PositiveIntegerField(default=0, verbose_name="İzleme süresi (sn)")
    tamamlandi = models.BooleanField(default=False, verbose_name="Tamamlandı")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Video izleme kaydı"
        verbose_name_plural = "Video izleme kayıtları"
        ordering = ["-baslama", "-id"]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.video_baslik}"


class KonuSorusu(models.Model):
    class DogruSecenek(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"

    konu = models.ForeignKey(
        KonuKatalogu,
        on_delete=models.CASCADE,
        related_name="sorular",
        verbose_name="Konu",
    )
    soru_metni = models.TextField(verbose_name="Soru metni")
    secenek_a = models.CharField(max_length=500, verbose_name="A şıkkı")
    secenek_b = models.CharField(max_length=500, verbose_name="B şıkkı")
    secenek_c = models.CharField(max_length=500, verbose_name="C şıkkı")
    secenek_d = models.CharField(max_length=500, verbose_name="D şıkkı")
    dogru_secenek = models.CharField(
        max_length=1,
        choices=DogruSecenek.choices,
        verbose_name="Doğru cevap",
    )
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    sira = models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Konu sorusu"
        verbose_name_plural = "Konu soruları"
        ordering = ["konu_id", "sira", "id"]

    def __str__(self):
        return f"{self.konu.konu_ad} — Soru {self.sira}"

    def secenekler(self) -> list[tuple[str, str]]:
        return [
            ("A", self.secenek_a),
            ("B", self.secenek_b),
            ("C", self.secenek_c),
            ("D", self.secenek_d),
        ]


class KonuTestOturu(models.Model):
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="konu_test_oturumlari",
        verbose_name="Talebe",
    )
    konu = models.ForeignKey(
        KonuKatalogu,
        on_delete=models.CASCADE,
        related_name="test_oturumlari",
        verbose_name="Konu",
    )
    baslama = models.DateTimeField(auto_now_add=True)
    bitis = models.DateTimeField(null=True, blank=True)
    dogru_sayisi = models.PositiveSmallIntegerField(default=0)
    toplam_soru = models.PositiveSmallIntegerField(default=0)
    basari_yuzde = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        verbose_name = "Konu test oturumu"
        verbose_name_plural = "Konu test oturumları"
        ordering = ["-baslama", "-id"]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.konu.konu_ad}"

    def guncelle_sonuc(self) -> None:
        cevaplar = self.cevaplar.all()
        toplam = cevaplar.count()
        dogru = cevaplar.filter(dogru_mu=True).count()
        self.toplam_soru = toplam
        self.dogru_sayisi = dogru
        if toplam:
            yuzde = (Decimal(dogru) * Decimal("100") / Decimal(toplam)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            yuzde = Decimal("0.00")
        self.basari_yuzde = yuzde
        self.save(update_fields=["toplam_soru", "dogru_sayisi", "basari_yuzde"])


class KonuTestCevabi(models.Model):
    oturum = models.ForeignKey(
        KonuTestOturu,
        on_delete=models.CASCADE,
        related_name="cevaplar",
        verbose_name="Oturum",
    )
    soru = models.ForeignKey(
        KonuSorusu,
        on_delete=models.CASCADE,
        related_name="cevaplar",
        verbose_name="Soru",
    )
    secilen = models.CharField(max_length=1, verbose_name="Seçilen şık")
    dogru_mu = models.BooleanField(default=False)
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Konu test cevabı"
        verbose_name_plural = "Konu test cevapları"
        constraints = [
            models.UniqueConstraint(
                fields=["oturum", "soru"],
                name="konu_test_soru_tek_cevap",
            )
        ]

    def __str__(self):
        return f"{self.oturum_id} — {self.soru_id} — {self.secilen}"
