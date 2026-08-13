"""Dinî eğitim müfredat planı ve ilerleme eşikleri."""

from __future__ import annotations

from django.db import models


class DiniAlanPlani(models.Model):
    """Seviye × alan × eğitim yılı hedef planı (otomatik beklenen ilerleme kaynağı)."""

    egitim_yili = models.ForeignKey(
        "EgitimYili",
        on_delete=models.CASCADE,
        related_name="dini_alan_planlari",
        verbose_name="Eğitim yılı",
    )
    seviye = models.ForeignKey(
        "DiniDersSeviyesi",
        on_delete=models.CASCADE,
        related_name="alan_planlari",
        verbose_name="Seviye",
    )
    alan = models.ForeignKey(
        "DiniDersTakipAlani",
        on_delete=models.CASCADE,
        related_name="seviye_planlari",
        verbose_name="Takip alanı",
    )
    birinci_donem_hedef = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="1. dönem sonu hedef (konu adedi)",
        help_text="0 ise yıl içi doğrusal dağılım kullanılır.",
    )
    yil_sonu_hedef = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Yıl sonu hedef (konu adedi)",
        help_text="0 ise tüm aktif konu sayısı hedef kabul edilir.",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dini alan planı"
        verbose_name_plural = "Dini alan planları"
        constraints = [
            models.UniqueConstraint(
                fields=["egitim_yili", "seviye", "alan"],
                name="dini_alan_plani_benzersiz",
            )
        ]
        ordering = ["egitim_yili__baslangic", "seviye__sira", "alan__sira"]

    def __str__(self):
        return f"{self.egitim_yili.ad} · {self.seviye.ad} · {self.alan.ad}"


class DiniKonuHedefTarihi(models.Model):
    """İsteğe bağlı: belirli konunun hedeflenen tamamlanma tarihi."""

    konu = models.OneToOneField(
        "DiniDersKonu",
        on_delete=models.CASCADE,
        related_name="hedef_tarihi_kaydi",
        verbose_name="Konu",
    )
    hedef_tarih = models.DateField(verbose_name="Hedef tarih")
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Açıklama")

    class Meta:
        verbose_name = "Dini konu hedef tarihi"
        verbose_name_plural = "Dini konu hedef tarihleri"
        ordering = ["hedef_tarih"]

    def __str__(self):
        return f"{self.konu.ad} → {self.hedef_tarih:%d.%m.%Y}"


class DiniIlerlemeEsik(models.Model):
    """Durum motoru eşikleri — yönetim tarafından ayarlanabilir."""

    egitim_yili = models.OneToOneField(
        "EgitimYili",
        on_delete=models.CASCADE,
        related_name="dini_ilerleme_esikleri",
        verbose_name="Eğitim yılı",
    )
    plan_onunde_puan = models.PositiveSmallIntegerField(
        default=8,
        verbose_name="Planın önünde (puan farkı)",
    )
    geride_puan = models.SmallIntegerField(
        default=-8,
        verbose_name="Planın gerisinde (puan farkı)",
    )
    grupla_uyumlu_puan = models.PositiveSmallIntegerField(
        default=5,
        verbose_name="Grupla uyumlu (± puan)",
    )
    hiz_artis_esik_puan = models.PositiveSmallIntegerField(
        default=5,
        verbose_name="Son dönem hız artışı (puan)",
    )

    class Meta:
        verbose_name = "Dini ilerleme eşiği"
        verbose_name_plural = "Dini ilerleme eşikleri"

    def __str__(self):
        return f"Eşikler · {self.egitim_yili.ad}"
