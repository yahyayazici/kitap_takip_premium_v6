"""Talebe paneli — hesap, konum ve ev günü modelleri."""

from django.contrib.auth.models import User
from django.db import models


class TalebeHesap(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="talebe_hesabi",
        verbose_name="Kullanıcı hesabı",
    )
    talebe = models.OneToOneField(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="talebe_hesabi",
        verbose_name="Talebe",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Talebe hesabı"
        verbose_name_plural = "Talebe hesapları"

    def __str__(self):
        return self.talebe.ad_soyad


class TalebeKonumKaydi(models.Model):
    class Mod(models.TextChoices):
        KURS = "kurs", "Kurs"
        EV = "ev", "Ev"
        IZIN = "izin", "İzin"

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="konum_kayitlari",
        verbose_name="Talebe",
    )
    tarih = models.DateField(verbose_name="Tarih")
    mod = models.CharField(
        max_length=10,
        choices=Mod.choices,
        verbose_name="Konum",
    )
    aciklama = models.CharField(max_length=255, blank=True, verbose_name="Açıklama")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Talebe konum kaydı"
        verbose_name_plural = "Talebe konum kayıtları"
        ordering = ["-tarih", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["talebe", "tarih"],
                name="benzersiz_talebe_konum_tarih",
            )
        ]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.tarih:%d.%m.%Y} ({self.get_mod_display()})"


class TalebeEvGunu(models.Model):
    weekday = models.PositiveSmallIntegerField(
        verbose_name="Haftanın günü",
        help_text="0=Pazartesi … 6=Pazar",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Talebe ev günü"
        verbose_name_plural = "Talebe ev günleri"
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(
                fields=["weekday"],
                name="benzersiz_talebe_ev_gunu",
            )
        ]

    def __str__(self):
        gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        ad = gunler[self.weekday] if 0 <= self.weekday <= 6 else str(self.weekday)
        return f"{ad} ({'aktif' if self.aktif else 'pasif'})"
