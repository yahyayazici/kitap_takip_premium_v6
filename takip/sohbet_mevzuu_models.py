"""Haftalık sohbet mevzuu — yönetim girer, veli panelinde görünür."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import localdate


class HaftalikSohbetMevzuu(models.Model):
    baslik = models.CharField(max_length=200, verbose_name="Sohbet başlığı")
    icerik = models.TextField(verbose_name="İçerik")
    hafta_baslangic = models.DateField(
        verbose_name="Hafta başlangıcı",
        help_text="Haftanın pazartesi tarihi.",
        default=localdate,
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_sohbet_mevzulari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Haftalık sohbet mevzuu"
        verbose_name_plural = "Haftalık sohbet mevzuları"
        ordering = ["-hafta_baslangic", "-id"]

    def __str__(self) -> str:
        return f"{self.baslik} · {self.hafta_baslangic:%d.%m.%Y}"
