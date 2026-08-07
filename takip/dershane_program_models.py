"""Dershane programı — haftalık gün × saat × etüt grubu planlayıcı."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class DershaneProgrami(models.Model):
    ad = models.CharField(max_length=200, verbose_name="Program adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    baslangic_tarihi = models.DateField(verbose_name="Başlangıç tarihi")
    bitis_tarihi = models.DateField(verbose_name="Bitiş tarihi")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    surum_no = models.PositiveIntegerField(default=1, verbose_name="Sürüm no")
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_dershane_programlari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dershane programı"
        verbose_name_plural = "Dershane programları"
        ordering = ["-baslangic_tarihi", "-id"]

    def __str__(self) -> str:
        return self.ad

    def clean(self):
        super().clean()
        if (
            self.baslangic_tarihi
            and self.bitis_tarihi
            and self.bitis_tarihi < self.baslangic_tarihi
        ):
            raise ValidationError(
                {"bitis_tarihi": "Bitiş tarihi başlangıçtan önce olamaz."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def tarih_araligi_goster(self) -> str:
        return (
            f"{self.baslangic_tarihi.strftime('%d.%m.%Y')}"
            f" – {self.bitis_tarihi.strftime('%d.%m.%Y')}"
        )


class DershaneProgramGun(models.Model):
    class Durum(models.TextChoices):
        BOS = "bos", "Boş"
        DUZENLENIYOR = "duzenleniyor", "Düzenleniyor"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"

    program = models.ForeignKey(
        DershaneProgrami,
        on_delete=models.CASCADE,
        related_name="gunler",
        verbose_name="Program",
    )
    gun = models.PositiveSmallIntegerField(verbose_name="Gün (0=Pzt)")
    durum = models.CharField(
        max_length=16,
        choices=Durum.choices,
        default=Durum.BOS,
        verbose_name="Durum",
    )

    class Meta:
        verbose_name = "Dershane program günü"
        verbose_name_plural = "Dershane program günleri"
        constraints = [
            models.UniqueConstraint(
                fields=["program", "gun"],
                name="dershane_program_gun_tek",
            )
        ]
        ordering = ["gun"]

    def __str__(self) -> str:
        return f"{self.program.ad} · gün {self.gun}"


class DershaneEtutGrubu(models.Model):
    program = models.ForeignKey(
        DershaneProgrami,
        on_delete=models.CASCADE,
        related_name="etut_gruplari",
        verbose_name="Program",
    )
    etiket = models.CharField(max_length=120, verbose_name="Etüt grubu")
    sinif_seviye = models.CharField(max_length=10, verbose_name="Sınıf seviyesi")
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dershane_gruplari",
        verbose_name="Etüt hocası",
    )
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Dershane etüt grubu"
        verbose_name_plural = "Dershane etüt grupları"
        ordering = ["sira", "etiket"]

    def __str__(self) -> str:
        return self.etiket


class DershaneSaatBloku(models.Model):
    class Tur(models.TextChoices):
        DERS = "ders", "Ders"
        NAMAZ = "namaz", "Namaz"
        YEMEK = "yemek", "Yemek"
        MOLA = "mola", "Mola"
        ETUT = "etut", "Etüt"
        REHBERLIK = "rehberlik", "Rehberlik"

    program = models.ForeignKey(
        DershaneProgrami,
        on_delete=models.CASCADE,
        related_name="saat_bloklari",
        verbose_name="Program",
    )
    gun = models.PositiveSmallIntegerField(verbose_name="Gün (0=Pzt)")
    baslangic_saati = models.TimeField(verbose_name="Başlangıç")
    bitis_saati = models.TimeField(verbose_name="Bitiş")
    tur = models.CharField(
        max_length=16,
        choices=Tur.choices,
        default=Tur.DERS,
        verbose_name="Tür",
    )
    aciklama = models.CharField(max_length=200, verbose_name="Açıklama")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Dershane saat bloğu"
        verbose_name_plural = "Dershane saat blokları"
        ordering = ["gun", "sira", "baslangic_saati", "id"]

    def __str__(self) -> str:
        return (
            f"{self.baslangic_saati:%H:%M}–{self.bitis_saati:%H:%M} "
            f"({self.get_tur_display()})"
        )

    @property
    def saat_goster(self) -> str:
        return f"{self.baslangic_saati:%H:%M} – {self.bitis_saati:%H:%M}"

    @property
    def ders_atamasi_gerektirir(self) -> bool:
        return self.tur in {
            self.Tur.DERS,
            self.Tur.ETUT,
            self.Tur.REHBERLIK,
        }


class DershaneDersAtamasi(models.Model):
    program = models.ForeignKey(
        DershaneProgrami,
        on_delete=models.CASCADE,
        related_name="ders_atamalari",
        verbose_name="Program",
    )
    saat_bloku = models.ForeignKey(
        DershaneSaatBloku,
        on_delete=models.CASCADE,
        related_name="atamalar",
        verbose_name="Saat bloğu",
    )
    etut_grubu = models.ForeignKey(
        DershaneEtutGrubu,
        on_delete=models.CASCADE,
        related_name="atamalar",
        verbose_name="Etüt grubu",
    )
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dershane_atamalari",
        verbose_name="Ders",
    )
    ders_adi = models.CharField(max_length=120, blank=True, verbose_name="Ders adı")
    ogretmen = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dershane_atamalari",
        verbose_name="Öğretmen",
    )
    ogretmen_adi = models.CharField(max_length=120, blank=True, verbose_name="Öğretmen adı")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dershane ders ataması"
        verbose_name_plural = "Dershane ders atamaları"
        constraints = [
            models.UniqueConstraint(
                fields=["saat_bloku", "etut_grubu"],
                name="dershane_atama_tek",
            )
        ]

    def __str__(self) -> str:
        return f"{self.etut_grubu.etiket} · {self.gorunen_ders}"

    @property
    def gorunen_ders(self) -> str:
        if self.ders_id and self.ders:
            return self.ders.ad
        return self.ders_adi or "—"

    @property
    def gorunen_ogretmen(self) -> str:
        if self.ogretmen_id and self.ogretmen:
            return self.ogretmen.ad_soyad
        return self.ogretmen_adi or "—"


class DershaneGrupDersOgretmen(models.Model):
    """Etüt grubu + ders için varsayılan öğretmen eşlemesi."""

    program = models.ForeignKey(
        DershaneProgrami,
        on_delete=models.CASCADE,
        related_name="grup_ders_ogretmenleri",
        verbose_name="Program",
    )
    etut_grubu = models.ForeignKey(
        DershaneEtutGrubu,
        on_delete=models.CASCADE,
        related_name="ders_ogretmenleri",
        verbose_name="Etüt grubu",
    )
    ders = models.ForeignKey(
        "Ders",
        on_delete=models.CASCADE,
        related_name="dershane_grup_ogretmenleri",
        verbose_name="Ders",
    )
    ogretmen = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dershane_grup_dersleri",
        verbose_name="Öğretmen",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Grup ders öğretmeni"
        verbose_name_plural = "Grup ders öğretmenleri"
        constraints = [
            models.UniqueConstraint(
                fields=["program", "etut_grubu", "ders"],
                name="dershane_grup_ders_ogretmen_tek",
            )
        ]

    def __str__(self) -> str:
        return f"{self.etut_grubu.etiket} · {self.ders.ad} → {self.ogretmen}"


class DershaneProgramSablon(models.Model):
    ad = models.CharField(max_length=200, verbose_name="Şablon adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    veri = models.JSONField(default=dict, verbose_name="Program verisi")
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dershane_sablonlari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dershane program şablonu"
        verbose_name_plural = "Dershane program şablonları"
        ordering = ["-olusturulma", "ad"]

    def __str__(self) -> str:
        return self.ad


class DershaneProgramSurum(models.Model):
    program = models.ForeignKey(
        DershaneProgrami,
        on_delete=models.CASCADE,
        related_name="surumler",
        verbose_name="Program",
    )
    surum_no = models.PositiveIntegerField(verbose_name="Sürüm no")
    etiket = models.CharField(max_length=120, verbose_name="Etiket")
    veri = models.JSONField(default=dict, verbose_name="Anlık görüntü")
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dershane_surumleri",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(default=timezone.now, verbose_name="Oluşturulma")

    class Meta:
        verbose_name = "Dershane program sürümü"
        verbose_name_plural = "Dershane program sürümleri"
        ordering = ["-surum_no", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "surum_no"],
                name="dershane_surum_tek",
            )
        ]

    def __str__(self) -> str:
        return f"{self.program.ad} · {self.etiket}"
