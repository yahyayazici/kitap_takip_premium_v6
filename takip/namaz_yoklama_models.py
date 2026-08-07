"""Namaz yoklama modelleri."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class NamazVakti(models.TextChoices):
    SABAH = "sabah", "Sabah"
    OGLE = "ogle", "Öğle"
    IKINDI = "ikindi", "İkindi"
    AKSAM = "aksam", "Akşam"
    YATSI = "yatsi", "Yatsı"


class NamazDurumu(models.TextChoices):
    GELMEDI = "G", "Gelmedi"
    TAKKE_TESBIH = "TT", "Takke & Tesbih Eksik"
    IZINLI = "I", "İzinli"


VAKIT_ETIKETLERI = {
    NamazVakti.SABAH: "Sabah Namazına Gelmedi",
    NamazVakti.OGLE: "Öğle Namazına Gelmedi",
    NamazVakti.IKINDI: "İkindi Namazına Gelmedi",
    NamazVakti.AKSAM: "Akşam Namazına Gelmedi",
    NamazVakti.YATSI: "Yatsı Namazına Gelmedi",
}


class NamazYoklamaOturum(models.Model):
    tarih = models.DateField(verbose_name="Tarih")
    vakit = models.CharField(
        max_length=10,
        choices=NamazVakti.choices,
        verbose_name="Namaz vakti",
    )
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_namaz_yoklamalari",
        verbose_name="Kaydeden",
    )
    kaydedilme = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Namaz yoklama oturumu"
        verbose_name_plural = "Namaz yoklama oturumları"
        ordering = ["-tarih", "vakit"]
        constraints = [
            models.UniqueConstraint(
                fields=["tarih", "vakit"],
                name="benzersiz_namaz_oturum",
            )
        ]

    def __str__(self):
        return f"{self.get_vakit_display()} · {self.tarih:%d.%m.%Y}"


class NamazYoklamaKaydi(models.Model):
    oturum = models.ForeignKey(
        NamazYoklamaOturum,
        on_delete=models.CASCADE,
        related_name="kayitlar",
        verbose_name="Oturum",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="namaz_yoklama_kayitlari",
        verbose_name="Talebe",
    )
    durum = models.CharField(
        max_length=2,
        choices=NamazDurumu.choices,
        verbose_name="Durum",
    )

    class Meta:
        verbose_name = "Namaz yoklama kaydı"
        verbose_name_plural = "Namaz yoklama kayıtları"
        constraints = [
            models.UniqueConstraint(
                fields=["oturum", "talebe"],
                name="benzersiz_namaz_talebe_kaydi",
            )
        ]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.durum}"
