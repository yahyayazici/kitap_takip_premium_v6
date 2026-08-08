"""Öğretmen haftalık değerlendirme ve sınıf yoklaması modelleri."""

from __future__ import annotations

from decimal import Decimal

from django.db import models


class OgretmenSinavNotu(models.Model):
    """Haftalık ders değerlendirmesi — Katılım %30, Takip %30, Disiplin %40."""

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="ogretmen_sinav_notlari",
        verbose_name="Talebe",
    )
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.CASCADE,
        related_name="girdigi_sinav_notlari",
        verbose_name="Etüt hocası",
    )
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.PROTECT,
        related_name="ogretmen_sinav_notlari",
        verbose_name="Ders",
    )
    hafta_baslangic = models.DateField(
        verbose_name="Hafta başlangıcı",
        help_text="Haftanın pazartesi tarihi.",
    )
    katilim = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Katılım (%30)",
    )
    takip = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Takip (%30)",
    )
    disiplin = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Disiplin (%40)",
    )
    puan = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Ağırlıklı puan",
    )
    aciklama = models.TextField(blank=True, verbose_name="Değerlendirme notu")
    veliye_goster = models.BooleanField(default=True, verbose_name="Veliye göster")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    # Eski alanlar — geriye dönük uyumluluk
    tur = models.CharField(max_length=10, blank=True, default="", verbose_name="Tür (eski)")
    tarih = models.DateField(null=True, blank=True, verbose_name="Tarih (eski)")

    class Meta:
        verbose_name = "Öğretmen haftalık notu"
        verbose_name_plural = "Öğretmen haftalık notları"
        ordering = ["-hafta_baslangic", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=("talebe", "etut_hocasi", "ders", "hafta_baslangic"),
                name="benzersiz_ogretmen_haftalik_not",
            )
        ]

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.ders.ad} ({self.hafta_baslangic}): {self.puan}"

    @staticmethod
    def agirlikli_puan(katilim, takip, disiplin) -> Decimal | None:
        degerler = []
        if katilim is not None:
            degerler.append((Decimal(katilim), Decimal("0.30")))
        if takip is not None:
            degerler.append((Decimal(takip), Decimal("0.30")))
        if disiplin is not None:
            degerler.append((Decimal(disiplin), Decimal("0.40")))
        if not degerler:
            return None
        toplam_agirlik = sum(a for _, a in degerler)
        if toplam_agirlik <= 0:
            return None
        ham = sum(p * a for p, a in degerler)
        return (ham / toplam_agirlik).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        self.puan = self.agirlikli_puan(self.katilim, self.takip, self.disiplin)
        if self.hafta_baslangic and not self.tarih:
            self.tarih = self.hafta_baslangic
        super().save(*args, **kwargs)

    def get_tur_display(self) -> str:
        return "Haftalık değerlendirme"


class OgretmenHaftalikKonu(models.Model):
    sinif_sube = models.ForeignKey(
        "SinifSube",
        on_delete=models.CASCADE,
        related_name="ogretmen_haftalik_konular",
        verbose_name="Sınıf",
    )
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.CASCADE,
        related_name="haftalik_konulari",
        verbose_name="Öğretmen",
    )
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.PROTECT,
        related_name="ogretmen_haftalik_konular",
        verbose_name="Ders",
    )
    hafta_baslangic = models.DateField(verbose_name="Hafta başlangıcı")
    konu = models.CharField(max_length=300, blank=True, verbose_name="İşlenen konu")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Öğretmen haftalık konu"
        verbose_name_plural = "Öğretmen haftalık konular"
        constraints = [
            models.UniqueConstraint(
                fields=("sinif_sube", "etut_hocasi", "ders", "hafta_baslangic"),
                name="benzersiz_ogretmen_haftalik_konu",
            )
        ]

    def __str__(self):
        return f"{self.sinif_sube} · {self.ders.ad} · {self.hafta_baslangic}"


class OgretmenSinifYoklama(models.Model):
    """Günlük sınıf yoklaması — işaretlenen talebe yok sayılır."""

    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        related_name="ogretmen_sinif_yoklamalari",
        verbose_name="Talebe",
    )
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.CASCADE,
        related_name="girdigi_sinif_yoklamalari",
        verbose_name="Öğretmen",
    )
    tarih = models.DateField(verbose_name="Tarih")
    yok = models.BooleanField(default=True, verbose_name="Yok")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Öğretmen sınıf yoklaması"
        verbose_name_plural = "Öğretmen sınıf yoklamaları"
        ordering = ["-tarih", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=("talebe", "etut_hocasi", "tarih"),
                name="benzersiz_ogretmen_sinif_yoklama",
            )
        ]

    def __str__(self):
        durum = "YOK" if self.yok else "VAR"
        return f"{self.talebe.ad_soyad} · {self.tarih} · {durum}"
