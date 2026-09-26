"""Deneme sınavı modelleri — kitap sınavı ve KTT'den ayrı."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.db import models


class DenemeSinavi(models.Model):
    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        AKTIF = "aktif", "Aktif"
        ARSIV = "arsiv", "Arşiv"

    class Tur(models.TextChoices):
        GRUP = "grup", "Grup denemesi"
        BIREYSEL = "bireysel", "Bireysel deneme"

    ad = models.CharField(max_length=200, verbose_name="Deneme adı")
    sinav_tarihi = models.DateField(verbose_name="Sınav tarihi")
    sinif_seviyesi = models.CharField(
        max_length=30,
        verbose_name="Sınıf seviyesi",
        help_text="Örn. 6, 7, 8",
    )
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    durum = models.CharField(
        max_length=10,
        choices=Durum.choices,
        default=Durum.TASLAK,
        verbose_name="Durum",
    )
    tur = models.CharField(
        max_length=10,
        choices=Tur.choices,
        default=Tur.GRUP,
        verbose_name="Deneme türü",
    )
    sira_no = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Sıra numarası",
        help_text="Eğitim yılı + sınıf seviyesi içinde kurum sırası (örn. 4. Deneme).",
    )
    yayin = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Yayın",
        help_text="Denemenin gerçek adı/yayını (sıra numarasını belirlemez).",
    )
    egitim_yili = models.ForeignKey(
        "EgitimYili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="denemeler",
        verbose_name="Eğitim yılı",
    )
    toplam_soru = models.PositiveIntegerField(
        default=0,
        verbose_name="Toplam soru",
    )
    excel_dosyasi = models.FileField(
        upload_to="deneme/excel/%Y/%m/",
        null=True,
        blank=True,
        verbose_name="Excel dosyası",
    )
    hedef_sinif_subeler = models.ManyToManyField(
        "SinifSube",
        blank=True,
        related_name="hedefli_denemeler",
        verbose_name="Hedef sınıflar",
        help_text="Boşsa tüm sınıf seviyesi kapsanır (grup denemesi).",
    )
    bireysel_talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bireysel_denemeleri",
        verbose_name="Bireysel deneme sahibi",
        help_text="Yalnızca bireysel deneme türü için.",
    )
    yukleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="yukledigi_denemeler",
        verbose_name="Excel yükleyen",
    )
    yuklenme_zamani = models.DateTimeField(null=True, blank=True)
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_denemeler",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Deneme sınavı"
        verbose_name_plural = "Deneme sınavları"
        ordering = ["-sinav_tarihi", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["egitim_yili", "sinif_seviyesi", "sira_no"],
                condition=models.Q(sira_no__isnull=False),
                name="deneme_sira_no_benzersiz",
            )
        ]

    def __str__(self):
        return self.ad

    @property
    def grup_mu(self) -> bool:
        return self.tur == self.Tur.GRUP


class DenemeSonucu(models.Model):
    deneme = models.ForeignKey(
        DenemeSinavi,
        on_delete=models.CASCADE,
        related_name="sonuclar",
        verbose_name="Deneme",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="deneme_sonuclari",
        verbose_name="Talebe",
    )
    toplam_dogru = models.PositiveIntegerField(default=0)
    toplam_yanlis = models.PositiveIntegerField(default=0)
    toplam_bos = models.PositiveIntegerField(default=0)
    toplam_net = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    puan = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    sinif_sirasi = models.PositiveIntegerField(null=True, blank=True, verbose_name="Sınıf sırası")
    sinif_toplam = models.PositiveIntegerField(null=True, blank=True, verbose_name="Sınıf mevcudu")
    seviye_sirasi = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Sınıf seviyesi sırası"
    )
    seviye_toplam = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Sınıf seviyesi mevcudu"
    )
    kurum_sirasi = models.PositiveIntegerField(null=True, blank=True, verbose_name="Kurum sırası")
    kurum_toplam = models.PositiveIntegerField(null=True, blank=True, verbose_name="Kurum mevcudu")
    dis_siralama_metni = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Harici sıralama",
        help_text="Excel'de bulunan yayın/Türkiye geneli sıralaması (ham metin, kurum içi sıralamayla karıştırılmaz).",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Deneme sonucu"
        verbose_name_plural = "Deneme sonuçları"
        constraints = [
            models.UniqueConstraint(
                fields=["deneme", "talebe"],
                name="deneme_talebe_tek_sonuc",
            )
        ]
        ordering = ["-puan", "-toplam_net", "talebe__ad_soyad"]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.deneme.ad}"


class DenemeBransSonucu(models.Model):
    class Brans(models.TextChoices):
        TURKCE = "turkce", "Türkçe"
        MATEMATIK = "matematik", "Matematik"
        FEN = "fen", "Fen Bilimleri"
        SOSYAL = "sosyal", "Sosyal Bilgiler"
        DIN = "din", "Din Kültürü"
        INGILIZCE = "ingilizce", "İngilizce"

    sonuc = models.ForeignKey(
        DenemeSonucu,
        on_delete=models.CASCADE,
        related_name="brans_satirlari",
        verbose_name="Sonuç",
    )
    brans = models.CharField(max_length=20, choices=Brans.choices, verbose_name="Branş")
    dogru = models.PositiveIntegerField(default=0)
    yanlis = models.PositiveIntegerField(default=0)
    bos = models.PositiveIntegerField(default=0)
    net = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        verbose_name = "Deneme branş sonucu"
        verbose_name_plural = "Deneme branş sonuçları"
        constraints = [
            models.UniqueConstraint(
                fields=["sonuc", "brans"],
                name="deneme_sonuc_brans_benzersiz",
            )
        ]

    @staticmethod
    def net_hesapla(dogru: int, yanlis: int) -> Decimal:
        net = Decimal(int(dogru or 0)) - (Decimal(int(yanlis or 0)) / Decimal("4"))
        if net < 0:
            net = Decimal("0.00")
        return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class DenemeEslestirmeAlias(models.Model):
    excel_adi = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Excel ad soyad (normalize)",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="deneme_eslestirme_aliaslari",
        verbose_name="Talebe",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Deneme eşleştirme alias"
        verbose_name_plural = "Deneme eşleştirme aliasları"

    def __str__(self):
        return f"{self.excel_adi} → {self.talebe.ad_soyad}"


class DenemeKazanimSonucu(models.Model):
    """KonuKazanimDetay Excel satırı — kazanım yüzdesi ve net."""

    deneme = models.ForeignKey(
        DenemeSinavi,
        on_delete=models.CASCADE,
        related_name="kazanim_sonuclari",
        verbose_name="Deneme",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="deneme_kazanim_sonuclari",
        verbose_name="Talebe",
    )
    ders_ad = models.CharField(max_length=120, verbose_name="Ders")
    konu_ad = models.CharField(max_length=300, verbose_name="Kazanım / konu")
    ders_key = models.CharField(max_length=120, db_index=True)
    konu_key = models.CharField(max_length=300, db_index=True)
    yuzde = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Başarı %",
    )
    net_dogru = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Net doğru",
    )
    net_toplam = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Net toplam",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Deneme kazanım sonucu"
        verbose_name_plural = "Deneme kazanım sonuçları"
        ordering = ["ders_ad", "konu_ad", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["deneme", "talebe", "ders_key", "konu_key"],
                name="deneme_kazanim_benzersiz",
            )
        ]
        indexes = [
            models.Index(fields=["deneme", "talebe"]),
            models.Index(fields=["deneme", "konu_key"]),
        ]

    def __str__(self):
        return f"{self.talebe_id} · {self.konu_ad} ({self.yuzde}%)"


class DenemeExcelYukleme(models.Model):
    """Aynı Excel'in yanlışlıkla iki kez yüklenmesini tespit etmek için log."""

    deneme = models.ForeignKey(
        DenemeSinavi,
        on_delete=models.CASCADE,
        related_name="excel_yuklemeleri",
        verbose_name="Deneme",
    )
    dosya_hash = models.CharField(max_length=64, verbose_name="Dosya hash (sha256)")
    dosya_adi = models.CharField(max_length=255, blank=True, verbose_name="Dosya adı")
    yukleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deneme_excel_yuklemeleri",
        verbose_name="Yükleyen",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Deneme Excel yüklemesi"
        verbose_name_plural = "Deneme Excel yüklemeleri"
        ordering = ["-olusturulma", "-id"]
        indexes = [
            models.Index(fields=["deneme", "dosya_hash"], name="deneme_excel_hash_idx"),
        ]

    def __str__(self):
        return f"{self.dosya_adi or self.dosya_hash[:8]} · {self.deneme.ad}"
