"""Pazar izin dönüşü yoklama modelleri."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class PazarIzinDonusDurumu(models.TextChoices):
    GELDI = "geldi", "GELDİ"
    IZINLI = "izinli", "İZİNLİ"
    GEC_GELDI = "gec_geldi", "GEÇ GELDİ"
    GELMEDI = "gelmedi", "GELMEDİ"


class PazarIzinDonusGunAyar(models.Model):
    """Belirli bir pazar günü için tüm sınıflara uygulanan beklenen dönüş saati."""

    tarih = models.DateField(
        unique=True,
        verbose_name="Yoklama tarihi",
        help_text="Pazar izin dönüşü yoklama günü.",
    )
    beklenen_giris_tarihi = models.DateField(verbose_name="Beklenen giriş tarihi")
    beklenen_giris_saati = models.TimeField(verbose_name="Beklenen giriş saati")
    guncelleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guncelledigi_pazar_izin_gun_ayarlari",
        verbose_name="Güncelleyen",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pazar izin dönüş gün ayarı"
        verbose_name_plural = "Pazar izin dönüş gün ayarları"
        ordering = ["-tarih"]

    def __str__(self) -> str:
        return f"{self.tarih:%d.%m.%Y} · {self.beklenen_giris_saati:%H:%M}"


class PazarIzinDonusOturum(models.Model):
    sinif_sube = models.ForeignKey(
        "SinifSube",
        on_delete=models.CASCADE,
        related_name="pazar_izin_donus_oturumlari",
        verbose_name="Sınıf",
    )
    tarih = models.DateField(verbose_name="Yoklama tarihi")
    beklenen_giris_tarihi = models.DateField(verbose_name="Beklenen giriş tarihi")
    beklenen_giris_saati = models.TimeField(verbose_name="Beklenen giriş saati")
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_pazar_izin_oturumlari",
        verbose_name="Kaydeden",
    )
    kaydedilme = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pazar izin dönüş oturumu"
        verbose_name_plural = "Pazar izin dönüş oturumları"
        ordering = ["-tarih", "sinif_sube__sinif", "sinif_sube__sube"]
        constraints = [
            models.UniqueConstraint(
                fields=["sinif_sube", "tarih"],
                name="benzersiz_pazar_izin_oturum",
            )
        ]

    def __str__(self) -> str:
        return f"{self.sinif_sube} · {self.tarih:%d.%m.%Y}"


class PazarIzinDonusKaydi(models.Model):
    oturum = models.ForeignKey(
        PazarIzinDonusOturum,
        on_delete=models.CASCADE,
        related_name="kayitlar",
        verbose_name="Oturum",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="pazar_izin_donus_kayitlari",
        verbose_name="Talebe",
    )
    durum = models.CharField(
        max_length=12,
        choices=PazarIzinDonusDurumu.choices,
        default=PazarIzinDonusDurumu.GELMEDI,
        verbose_name="Durum",
    )
    giris_tarihi = models.DateField(null=True, blank=True, verbose_name="Giriş tarihi")
    giris_saati = models.TimeField(null=True, blank=True, verbose_name="Giriş saati")
    gecikme_dk = models.PositiveIntegerField(default=0, verbose_name="Gecikme (dk)")
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")

    class Meta:
        verbose_name = "Pazar izin dönüş kaydı"
        verbose_name_plural = "Pazar izin dönüş kayıtları"
        constraints = [
            models.UniqueConstraint(
                fields=["oturum", "talebe"],
                name="benzersiz_pazar_izin_talebe",
            )
        ]

    def __str__(self) -> str:
        return f"{self.talebe.ad_soyad} — {self.get_durum_display()}"
