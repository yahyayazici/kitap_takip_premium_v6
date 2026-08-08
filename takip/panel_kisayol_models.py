"""Panel kısayol kartları — yönetici tanımlar, hedef kitleye göre gösterilir."""

from __future__ import annotations

from django.db import models


class PanelKisayol(models.Model):
    """Ana sayfa kısayolu — personel / yönetim / veli / öğretmen panellerinde gösterilebilir."""

    anahtar = models.SlugField(
        max_length=40,
        unique=True,
        verbose_name="Anahtar",
        help_text="Örn. kitap, talebeler, ozel-duyuru",
    )
    baslik = models.CharField(max_length=80, verbose_name="Başlık")
    alt_baslik = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Alt yazı",
    )
    icon = models.CharField(
        max_length=20,
        default="book",
        verbose_name="İkon",
        help_text="book, users, groups, clipboard, chat, phone, chart, target, check, folder, calendar, pie, settings",
    )
    mark = models.CharField(
        max_length=8,
        blank=True,
        verbose_name="Kısaltma",
        help_text="Banner sağ üst (ör. KT)",
    )
    url_name = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="URL adı",
        help_text="Django url name (ör. kitap_listesi, yonetim:talebe_listesi, veli_duyurular)",
    )
    url_ozel = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="Özel URL",
        help_text="Doğrudan yol: /panel/... veya https://...",
    )
    gorsel = models.ImageField(
        upload_to="panel_kisayol/",
        blank=True,
        null=True,
        verbose_name="Banner görseli",
        help_text="Önerilen: 640×400 (16:10).",
    )
    goster_personel = models.BooleanField(default=True, verbose_name="Personel")
    goster_yonetim = models.BooleanField(default=False, verbose_name="Yönetim / Admin")
    goster_veli = models.BooleanField(default=False, verbose_name="Veli")
    goster_ogretmen = models.BooleanField(default=False, verbose_name="Öğretmen")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Panel kısayolu"
        verbose_name_plural = "Panel kısayolları"
        ordering = ["sira", "id"]

    def __str__(self) -> str:
        return self.baslik


# Geriye dönük uyumluluk — eski görsel modeli
class PanelKisayolGorsel(models.Model):
    anahtar = models.SlugField(max_length=40, unique=True)
    baslik = models.CharField(max_length=80, blank=True)
    gorsel = models.ImageField(upload_to="panel_kisayol/", blank=True, null=True)
    aktif = models.BooleanField(default=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Panel kısayol görseli (eski)"
        verbose_name_plural = "Panel kısayol görselleri (eski)"
        ordering = ["anahtar"]

    def __str__(self) -> str:
        return self.baslik or self.anahtar
