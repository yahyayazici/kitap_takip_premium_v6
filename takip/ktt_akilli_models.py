"""KTT akıllı takip — konu eşleştirme, müdahale ve eksik kapatma modelleri."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models


class KonuAlias(models.Model):
    """Onaylı sınıf + branş + ham ifade → standart konu eşlemesi."""

    sinif_seviyesi = models.CharField(max_length=30, verbose_name="Sınıf seviyesi")
    brans = models.CharField(max_length=20, verbose_name="Branş")
    ham_normalize = models.CharField(
        max_length=220,
        verbose_name="Normalize ham ifade",
        help_text="Küçük harf, noktalama temizlenmiş eşleştirme anahtarı.",
    )
    konu = models.ForeignKey(
        "KonuKatalogu",
        on_delete=models.CASCADE,
        related_name="konu_aliaslari",
        verbose_name="Standart konu",
    )
    onaylandi = models.BooleanField(default=True, verbose_name="Onaylı")
    kullanim_sayisi = models.PositiveIntegerField(default=0, verbose_name="Kullanım sayısı")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_konu_aliaslari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Konu alias"
        verbose_name_plural = "Konu aliasları"
        constraints = [
            models.UniqueConstraint(
                fields=["sinif_seviyesi", "brans", "ham_normalize"],
                name="konu_alias_benzersiz",
            )
        ]
        ordering = ["sinif_seviyesi", "brans", "ham_normalize"]

    def __str__(self):
        return f"{self.ham_normalize} → {self.konu.konu_ad}"


class KonuEslestirmeInceleme(models.Model):
    class Durum(models.TextChoices):
        BEKLIYOR = "bekliyor", "İnceleme bekliyor"
        ONAYLANDI = "onaylandi", "Onaylandı"
        REDDEDILDI = "reddedildi", "Reddedildi"

    sinif_seviyesi = models.CharField(max_length=30, verbose_name="Sınıf seviyesi")
    brans = models.CharField(max_length=20, verbose_name="Branş")
    ham_metin = models.CharField(max_length=200, verbose_name="Girilen konu")
    ham_normalize = models.CharField(max_length=220, verbose_name="Normalize ham")
    onerilen_konu = models.ForeignKey(
        "KonuKatalogu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eslestirme_incelemeleri",
        verbose_name="Önerilen standart konu",
    )
    guven_yuzde = models.PositiveSmallIntegerField(default=0, verbose_name="Güven %")
    durum = models.CharField(
        max_length=20,
        choices=Durum.choices,
        default=Durum.BEKLIYOR,
        verbose_name="Durum",
    )
    ktt = models.ForeignKey(
        "KttSinav",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="konu_eslestirme_incelemeleri",
        verbose_name="İlgili KTT",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Konu eşleştirme incelemesi"
        verbose_name_plural = "Konu eşleştirme incelemeleri"
        ordering = ["-olusturulma"]

    def __str__(self):
        return f"{self.ham_metin} ({self.guven_yuzde}%)"


class KttEslestirmeEsik(models.Model):
    """Merkezi eşleştirme ve eksik kapatma eşikleri."""

    yuksek_guven = models.PositiveSmallIntegerField(
        default=88,
        verbose_name="Yüksek güven (otomatik eşleştir)",
    )
    orta_guven = models.PositiveSmallIntegerField(
        default=72,
        verbose_name="Orta güven (inceleme öner)",
    )
    kapanma_gelisim_puan = models.PositiveSmallIntegerField(
        default=15,
        verbose_name="Eksik kapanma — min. gelişim puanı",
    )
    zayif_ktt_puan = models.PositiveSmallIntegerField(
        default=70,
        verbose_name="Zayıf KTT eşiği (puan altı)",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "KTT eşleştirme eşiği"
        verbose_name_plural = "KTT eşleştirme eşikleri"

    def __str__(self):
        return "KTT eşleştirme eşikleri"


class KttEtutMudahale(models.Model):
    """Etüt hocasının eksik konu üzerinde yaptığı hızlı müdahale kaydı."""

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="ktt_etut_mudahaleleri",
        verbose_name="Talebe",
    )
    konu = models.ForeignKey(
        "KonuKatalogu",
        on_delete=models.CASCADE,
        related_name="ktt_mudahaleleri",
        verbose_name="Standart konu",
    )
    eksik = models.ForeignKey(
        "TalebeKonuEksigi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ktt_mudahaleleri",
        verbose_name="Konu eksiği",
    )
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.PROTECT,
        related_name="ktt_mudahaleleri",
        verbose_name="Etüt hocası",
    )
    mudahale_tarihi = models.DateField(verbose_name="Müdahale tarihi")
    tetikleyen_sonuc = models.ForeignKey(
        "KttSonucu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tetikledigi_mudahaleler",
        verbose_name="Tetikleyen KTT sonucu",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_ktt_mudahaleleri",
        verbose_name="Kaydeden",
    )
    notlar = models.CharField(max_length=300, blank=True, verbose_name="Not")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "KTT etüt müdahalesi"
        verbose_name_plural = "KTT etüt müdahaleleri"
        ordering = ["-mudahale_tarihi", "-id"]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.konu.konu_ad}"
