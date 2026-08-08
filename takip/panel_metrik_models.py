"""Ana sayfa özet metrik kartları — yönetici aç/kapa ve hedef seçer."""

from __future__ import annotations

from django.db import models


class PanelMetrik(models.Model):
    """Dashboard üst şeritteki özet kart (Talebe, Sınav, Deneme vb.)."""

    class Ton(models.TextChoices):
        BLUE = "blue", "Mavi"
        GREEN = "green", "Yeşil"
        AMBER = "amber", "Turuncu"
        VIOLET = "violet", "Mor"

    anahtar = models.SlugField(
        max_length=40,
        unique=True,
        verbose_name="Anahtar",
        help_text="Örn. talebe, bugun_okunan, aktif_deneme",
    )
    baslik = models.CharField(max_length=60, verbose_name="Başlık")
    not_metni = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Alt not",
        help_text="Boş bırakılırsa varsayılan not kullanılır.",
    )
    ton = models.CharField(
        max_length=12,
        choices=Ton.choices,
        default=Ton.BLUE,
        verbose_name="Renk",
    )
    icon = models.CharField(
        max_length=20,
        default="users",
        verbose_name="İkon",
    )
    goster_personel = models.BooleanField(default=True, verbose_name="Personel")
    goster_yonetim = models.BooleanField(default=False, verbose_name="Yönetim")
    goster_veli = models.BooleanField(default=False, verbose_name="Veli")
    goster_ogretmen = models.BooleanField(default=False, verbose_name="Öğretmen")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Panel metriği"
        verbose_name_plural = "Panel metrikleri"
        ordering = ["sira", "id"]

    def __str__(self) -> str:
        return self.baslik
