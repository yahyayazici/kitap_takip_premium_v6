"""Uygulama içi bildirim modeli — personel, öğretmen, veli ortak."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Bildirim(models.Model):
    class Tur(models.TextChoices):
        GENEL = "genel", "Genel"
        VAZIFE = "vazife", "Vazife"
        DUYURU = "duyuru", "Duyuru"
        PROGRAM = "program", "Program"
        SISTEM = "sistem", "Sistem"

    alici = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bildirimler",
        verbose_name="Alıcı",
    )
    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    mesaj = models.TextField(blank=True, verbose_name="Mesaj")
    tur = models.CharField(
        max_length=20,
        choices=Tur.choices,
        default=Tur.GENEL,
        verbose_name="Tür",
    )
    link = models.CharField(max_length=500, blank=True, verbose_name="Bağlantı")
    bitis = models.DateField(
        null=True,
        blank=True,
        verbose_name="Geçerlilik (şu güne kadar)",
        help_text="Doluysa bu tarihe kadar aktif bildirim sayılır.",
    )
    okundu = models.BooleanField(default=False, verbose_name="Okundu")
    okunma_zamani = models.DateTimeField(null=True, blank=True)
    email_gonderildi = models.BooleanField(default=False)
    kaynak_model = models.CharField(max_length=80, blank=True)
    kaynak_id = models.PositiveIntegerField(null=True, blank=True)
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gonderdigi_bildirimler",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bildirim"
        verbose_name_plural = "Bildirimler"
        ordering = ["-olusturulma", "-id"]
        indexes = [
            models.Index(fields=["alici", "okundu", "-olusturulma"]),
            models.Index(fields=["alici", "bitis"]),
        ]

    def __str__(self) -> str:
        return f"{self.baslik} → {self.alici_id}"

    @property
    def aktif_mi(self) -> bool:
        if self.bitis is None:
            return True
        return self.bitis >= timezone.localdate()

    def okundu_isaretle(self) -> None:
        if self.okundu:
            return
        self.okundu = True
        self.okunma_zamani = timezone.now()
        self.save(update_fields=["okundu", "okunma_zamani"])
