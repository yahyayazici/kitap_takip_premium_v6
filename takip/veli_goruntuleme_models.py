"""Veli paneli içerik görüntüleme kayıtları."""

from __future__ import annotations

from django.db import models


class VeliIcerikGoruntuleme(models.Model):
    class Tur(models.TextChoices):
        SAYFA = "sayfa", "Sayfa"
        DUYURU = "duyuru", "Duyuru"
        KTT = "ktt", "KTT"
        DENEME = "deneme", "Deneme"
        YAZILI = "yazili", "Yazılı"
        DINI_DERS = "dini_ders", "Dini Ders"
        AIDAT = "aidat", "Aidat"

    veli = models.ForeignKey(
        "VeliHesap",
        on_delete=models.CASCADE,
        related_name="icerik_goruntulemeleri",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="veli_icerik_goruntulemeleri",
    )
    tur = models.CharField(max_length=20, choices=Tur.choices)
    referans_id = models.PositiveIntegerField(
        default=0,
        help_text="İçerik birincil anahtarı; sayfa kayıtları için 0.",
    )
    sayfa = models.CharField(max_length=80, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    ilk_goruntulenme = models.DateTimeField(auto_now_add=True)
    son_goruntulenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Veli içerik görüntüleme"
        verbose_name_plural = "Veli içerik görüntülemeleri"
        constraints = [
            models.UniqueConstraint(
                fields=["veli", "talebe", "tur", "referans_id"],
                name="uniq_veli_icerik_goruntuleme",
            ),
        ]
        indexes = [
            models.Index(fields=["veli", "tur"]),
            models.Index(fields=["veli", "son_goruntulenme"]),
        ]

    def __str__(self) -> str:
        return f"{self.veli.ad_soyad} · {self.get_tur_display()} · {self.referans_id}"
