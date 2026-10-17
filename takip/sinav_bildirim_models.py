"""Sınav başvurusu — uygulama (web push) bildirimleri.

Başvuran veliler giriş yapmadığı için abonelik kullanıcıya değil başvuruya bağlanır.
"""

from __future__ import annotations

from django.db import models


class SinavTakvim(models.Model):
    sinav_adi = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Sınav adı",
        help_text="Başvurulardaki sınav adıyla birebir aynı olmalı.",
    )
    baslangic = models.DateTimeField(verbose_name="Sınav başlangıcı")
    bitis = models.DateTimeField(verbose_name="Sınav bitişi")
    yer = models.CharField(max_length=200, blank=True, verbose_name="Yer")
    bildirim_aktif = models.BooleanField(default=True, verbose_name="Hatırlatmalar açık")
    sonuc_mesaji = models.TextField(blank=True, verbose_name="Sonuç e-posta mesajı")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sınav takvimi"
        verbose_name_plural = "Sınav takvimleri"
        ordering = ["-baslangic"]

    def __str__(self) -> str:
        return self.sinav_adi


class SinavBasvuruPushAbonelik(models.Model):
    basvuru = models.ForeignKey(
        "SinavBasvuru",
        on_delete=models.CASCADE,
        related_name="push_abonelikleri",
        verbose_name="Başvuru",
    )
    endpoint = models.URLField(max_length=500, verbose_name="Endpoint")
    p256dh = models.CharField(max_length=255, verbose_name="p256dh anahtarı")
    auth = models.CharField(max_length=255, verbose_name="Auth anahtarı")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="Cihaz/Tarayıcı")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Başvuru bildirim aboneliği"
        verbose_name_plural = "Başvuru bildirim abonelikleri"
        ordering = ["-olusturulma"]
        constraints = [
            models.UniqueConstraint(
                fields=["basvuru", "endpoint"],
                name="uniq_sinav_basvuru_push_endpoint",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.basvuru_id} — {self.endpoint[:40]}…"


class SinavBildirimLog(models.Model):
    """Her başvuru × bildirim anı için tek satır: aynı bildirim iki kez gitmez."""

    basvuru = models.ForeignKey(
        "SinavBasvuru",
        on_delete=models.CASCADE,
        related_name="bildirim_loglari",
        verbose_name="Başvuru",
    )
    an_kodu = models.CharField(max_length=40, verbose_name="Bildirim anı")
    baslik = models.CharField(max_length=120, blank=True, verbose_name="Başlık")
    mesaj = models.TextField(blank=True, verbose_name="Mesaj")
    gonderilen = models.PositiveSmallIntegerField(default=0, verbose_name="Ulaşan cihaz")
    eposta_gonderildi = models.BooleanField(default=False, verbose_name="E-posta gönderildi")
    push_hata = models.TextField(blank=True, verbose_name="Bildirim hatası")
    olusturulma = models.DateTimeField(auto_now_add=True, verbose_name="Zaman")

    class Meta:
        verbose_name = "Sınav bildirim kaydı"
        verbose_name_plural = "Sınav bildirim kayıtları"
        ordering = ["-olusturulma"]
        constraints = [
            models.UniqueConstraint(
                fields=["basvuru", "an_kodu"],
                name="uniq_sinav_bildirim_basvuru_an",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.an_kodu} → {self.basvuru_id} ({self.gonderilen})"
