"""Sınav başvurusu WhatsApp mesaj anları ve gönderim logları."""

from __future__ import annotations

from django.db import models


class SinavBasvuruMesajSablon(models.Model):
    class AnKodu(models.TextChoices):
        BASVURU_ALINDI = "basvuru_alindi", "Başvuru alındı"
        SINAV_DAVETI = "sinav_daveti", "Sınav daveti"
        SONUC_BILDIRIMI = "sonuc_bildirimi", "Sonuç bildirimi"
        KABUL = "kabul", "Kabul"
        RED = "red", "Red"

    class Alici(models.TextChoices):
        BABA = "baba", "Sadece baba"
        ANNE = "anne", "Sadece anne"
        IKISI = "ikisi", "Baba ve anne"

    an_kodu = models.CharField(
        max_length=40,
        choices=AnKodu.choices,
        unique=True,
        verbose_name="Mesaj anı",
    )
    baslik = models.CharField(max_length=120, verbose_name="Başlık")
    metin = models.TextField(
        verbose_name="Mesaj metni",
        help_text="Değişkenler: {ad_soyad}, {sinav_adi}, {il}, {ilce}, {baba_adi}, {anne_adi}",
    )
    aktif = models.BooleanField(default=False, verbose_name="Aktif")
    alici = models.CharField(
        max_length=10,
        choices=Alici.choices,
        default=Alici.IKISI,
        verbose_name="Alıcı",
    )
    wa_template_name = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="WhatsApp template adı",
        help_text="Meta’da onaylı template adı. Boşsa metin mesajı denenir.",
    )
    wa_template_lang = models.CharField(
        max_length=20,
        default="tr",
        verbose_name="Template dili",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sınav başvuru mesaj anı"
        verbose_name_plural = "Sınav başvuru mesaj anları"
        ordering = ["sira", "an_kodu"]

    def __str__(self) -> str:
        durum = "aktif" if self.aktif else "pasif"
        return f"{self.get_an_kodu_display()} ({durum})"


class SinavBasvuruMesajLog(models.Model):
    class Durum(models.TextChoices):
        BEKLEMEDE = "beklemede", "Beklemede"
        GONDERILDI = "gonderildi", "Gönderildi"
        HATA = "hata", "Hata"
        ATLANDI = "atlandi", "Atlandı"

    basvuru = models.ForeignKey(
        "SinavBasvuru",
        on_delete=models.CASCADE,
        related_name="mesaj_loglari",
        verbose_name="Başvuru",
    )
    sablon = models.ForeignKey(
        SinavBasvuruMesajSablon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loglar",
        verbose_name="Şablon",
    )
    an_kodu = models.CharField(max_length=40, verbose_name="Mesaj anı")
    telefon = models.CharField(max_length=20, verbose_name="Telefon")
    alici_etiket = models.CharField(max_length=20, blank=True, verbose_name="Alıcı")
    metin = models.TextField(blank=True, verbose_name="Gönderilen metin")
    durum = models.CharField(
        max_length=20,
        choices=Durum.choices,
        default=Durum.BEKLEMEDE,
        verbose_name="Durum",
    )
    provider_yanit = models.TextField(blank=True, verbose_name="Sağlayıcı yanıtı")
    olusturulma = models.DateTimeField(auto_now_add=True, verbose_name="Zaman")

    class Meta:
        verbose_name = "Sınav başvuru mesaj logu"
        verbose_name_plural = "Sınav başvuru mesaj logları"
        ordering = ["-olusturulma"]

    def __str__(self) -> str:
        return f"{self.an_kodu} → {self.telefon} ({self.durum})"
