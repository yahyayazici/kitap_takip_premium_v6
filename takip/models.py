from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max
from django.utils import timezone


class TimeStampedModel(models.Model):
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_olusturdu",
    )
    son_duzenleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_duzenledi",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SinifSube(models.Model):
    sinif = models.CharField(
        max_length=30,
        verbose_name="Sınıf",
        help_text="Örn. 3, 4, 5, Hazırlık, Mezun",
    )

    sube = models.CharField(
        max_length=20,
        verbose_name="Şube",
        help_text="Örn. A, B, C",
    )

    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )

    class Meta:
        verbose_name = "Sınıf ve şube"
        verbose_name_plural = "Sınıf ve şubeler"
        ordering = ["sinif", "sube"]
        constraints = [
            models.UniqueConstraint(
                fields=["sinif", "sube"],
                name="benzersiz_sinif_sube",
            )
        ]

    def __str__(self):
        return f"{self.sinif}/{self.sube}"


class EtutHocasi(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="etut_profili",
        verbose_name="Kullanıcı hesabı",
    )
    ad_soyad = models.CharField(
        max_length=120,
        verbose_name="Ad soyad",
    )
    sorumlu_sinif_subeler = models.ManyToManyField(
        SinifSube,
        blank=True,
        related_name="etut_hocalari",
        verbose_name="Sorumlu olduğu sınıf ve şubeler",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )

    class Meta:
        verbose_name = "Etüt hocası"
        verbose_name_plural = "Etüt hocaları"
        ordering = ["ad_soyad"]

    def __str__(self):
        return self.ad_soyad

    @property
    def sorumlu_gruplar(self):
        gruplar = self.sorumlu_sinif_subeler.filter(aktif=True)
        return ", ".join(str(grup) for grup in gruplar) or "Sınıf atanmamış"


class Talebe(models.Model):
    ad_soyad = models.CharField(
        max_length=120,
        verbose_name="Ad soyad",
    )
    talebe_no = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Talebe numarası",
    )

    # Eski ekranların ve mevcut verilerin bozulmaması için korunur.
    sinif = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Sınıf",
    )
    sube = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="Şube",
    )

    sinif_sube = models.ForeignKey(
        SinifSube,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="talebeler",
        verbose_name="Sınıf ve şube",
    )
    etut_hocasi = models.ForeignKey(
        EtutHocasi,
        on_delete=models.PROTECT,
        related_name="talebeler",
        verbose_name="Etüt hocası",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )

    class Meta:
        verbose_name = "Talebe"
        verbose_name_plural = "Talebeler"
        ordering = ["sinif", "sube", "ad_soyad"]

    def clean(self):
        super().clean()

        if self.sinif_sube_id and self.etut_hocasi_id:
            yetkili = self.etut_hocasi.sorumlu_sinif_subeler.filter(
                pk=self.sinif_sube_id,
                aktif=True,
            ).exists()

            if not yetkili:
                raise ValidationError(
                    {
                        "etut_hocasi": (
                            "Seçilen etüt hocası bu sınıf ve şubeden "
                            "sorumlu değildir."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        if self.sinif_sube_id:
            self.sinif = self.sinif_sube.sinif
            self.sube = self.sinif_sube.sube

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        grup = (
            str(self.sinif_sube)
            if self.sinif_sube_id
            else f"{self.sinif}{('/' + self.sube) if self.sube else ''}"
        )
        return f"{self.ad_soyad} — {grup}"


class Kitap(TimeStampedModel):
    ad = models.CharField(max_length=220)
    yazar = models.CharField(max_length=160, blank=True)
    yayinevi = models.CharField(max_length=160, blank=True)
    toplam_sayfa = models.PositiveIntegerField()
    sinif_seviyesi = models.CharField(max_length=40, blank=True)
    aciklama = models.TextField(blank=True)
    aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Kitap"
        verbose_name_plural = "Kitaplar"
        ordering = ["ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["ad", "yazar"],
                name="benzersiz_kitap_yazar",
            )
        ]

    def __str__(self):
        return self.ad


class Zimmet(TimeStampedModel):
    DURUMLAR = [
        ("okunuyor", "Okunuyor"),
        ("tamamlandi", "Tamamlandı"),
        ("sinav_bekliyor", "Sınav Bekliyor"),
        ("sinav_yapildi", "Sınav Yapıldı"),
        ("yarim", "Yarım Bırakıldı"),
        ("iade", "İade Edildi"),
    ]

    talebe = models.ForeignKey(
        Talebe,
        on_delete=models.CASCADE,
        related_name="zimmetler",
    )
    kitap = models.ForeignKey(
        Kitap,
        on_delete=models.PROTECT,
        related_name="zimmetler",
    )
    etut_hocasi = models.ForeignKey(
        EtutHocasi,
        on_delete=models.PROTECT,
        related_name="zimmetler",
    )
    zimmet_tarihi = models.DateField(default=timezone.localdate)
    hedef_bitis_tarihi = models.DateField(null=True, blank=True)
    baslangic_sayfasi = models.PositiveIntegerField(default=0)
    durum = models.CharField(
        max_length=30,
        choices=DURUMLAR,
        default="okunuyor",
    )

    class Meta:
        verbose_name = "Kitap zimmeti"
        verbose_name_plural = "Kitap zimmetleri"
        ordering = ["-zimmet_tarihi"]

    def clean(self):
        if (
            self.talebe_id
            and self.etut_hocasi_id
            and self.talebe.etut_hocasi_id != self.etut_hocasi_id
        ):
            raise ValidationError("Talebe bu etüt hocasına bağlı değil.")

        if (
            self.kitap_id
            and self.baslangic_sayfasi > self.kitap.toplam_sayfa
        ):
            raise ValidationError(
                "Başlangıç sayfası kitap sayfasını geçemez."
            )

    @property
    def son_sayfa(self):
        son = self.okuma_kayitlari.aggregate(
            Max("son_sayfa")
        )["son_sayfa__max"]

        return son if son is not None else self.baslangic_sayfasi

    @property
    def ilerleme_yuzdesi(self):
        if not self.kitap.toplam_sayfa:
            return 0

        return min(
            100,
            round(
                (self.son_sayfa / self.kitap.toplam_sayfa) * 100
            ),
        )

    def __str__(self):
        return f"{self.talebe.ad_soyad} — {self.kitap.ad}"


class OkumaKaydi(TimeStampedModel):
    zimmet = models.ForeignKey(
        Zimmet,
        on_delete=models.CASCADE,
        related_name="okuma_kayitlari",
    )
    tarih = models.DateField(default=timezone.localdate)
    son_sayfa = models.PositiveIntegerField()
    not_metni = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "Günlük okuma kaydı"
        verbose_name_plural = "Günlük okuma kayıtları"
        ordering = ["-tarih", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["zimmet", "tarih"],
                name="zimmet_gunluk_tek_kayit",
            )
        ]

    def clean(self):
        if self.son_sayfa > self.zimmet.kitap.toplam_sayfa:
            raise ValidationError(
                "Son sayfa, kitabın toplam sayfasını geçemez."
            )

        onceki = (
            OkumaKaydi.objects.filter(zimmet=self.zimmet)
            .exclude(pk=self.pk)
            .order_by("-tarih", "-id")
            .first()
        )

        alt_sinir = (
            onceki.son_sayfa
            if onceki
            else self.zimmet.baslangic_sayfasi
        )

        if self.son_sayfa < alt_sinir:
            raise ValidationError(
                f"Son sayfa önceki kayıttan ({alt_sinir}) küçük olamaz."
            )

    @property
    def okunan_sayfa(self):
        onceki = (
            OkumaKaydi.objects.filter(zimmet=self.zimmet)
            .filter(
                models.Q(tarih__lt=self.tarih)
                | models.Q(tarih=self.tarih, id__lt=self.id)
            )
            .order_by("-tarih", "-id")
            .first()
        )

        onceki_sayfa = (
            onceki.son_sayfa
            if onceki
            else self.zimmet.baslangic_sayfasi
        )

        return max(0, self.son_sayfa - onceki_sayfa)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        if (
            self.son_sayfa >= self.zimmet.kitap.toplam_sayfa
            and self.zimmet.durum == "okunuyor"
        ):
            self.zimmet.durum = "sinav_bekliyor"
            self.zimmet.save(update_fields=["durum"])

    def __str__(self):
        return f"{self.zimmet.talebe.ad_soyad} — {self.tarih}"


class KitapSinavi(TimeStampedModel):
    zimmet = models.OneToOneField(
        Zimmet,
        on_delete=models.CASCADE,
        related_name="sinav",
    )
    tarih = models.DateField(default=timezone.localdate)
    toplam_soru = models.PositiveIntegerField(default=10)
    dogru = models.PositiveIntegerField(default=0)
    yanlis = models.PositiveIntegerField(default=0)
    bos = models.PositiveIntegerField(default=0)
    puan = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    degerlendirme = models.TextField(blank=True)

    class Meta:
        verbose_name = "Kitap sınavı"
        verbose_name_plural = "Kitap sınavları"
        ordering = ["-tarih"]

    def clean(self):
        if (
            self.dogru + self.yanlis + self.bos
            != self.toplam_soru
        ):
            raise ValidationError(
                "Doğru + yanlış + boş toplamı, "
                "toplam soru sayısına eşit olmalı."
            )

    def save(self, *args, **kwargs):
        if self.toplam_soru:
            self.puan = (
                Decimal(self.dogru)
                * Decimal("100")
                / Decimal(self.toplam_soru)
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        else:
            self.puan = Decimal("0.00")

        self.full_clean()
        super().save(*args, **kwargs)

        self.zimmet.durum = "sinav_yapildi"
        self.zimmet.save(update_fields=["durum"])

    def __str__(self):
        return (
            f"{self.zimmet.talebe.ad_soyad} "
            f"— {self.zimmet.kitap.ad}"
        )


class Sinav(models.Model):
    etut_hocasi = models.ForeignKey(
        EtutHocasi,
        on_delete=models.PROTECT,
        related_name="sinavlar",
        verbose_name="Etüt hocası",
    )
    kitap = models.ForeignKey(
        Kitap,
        on_delete=models.PROTECT,
        related_name="sinavlar",
        verbose_name="Kitap",
    )
    ad = models.CharField(
        max_length=200,
        verbose_name="Sınav adı",
    )
    soru_sayisi = models.PositiveIntegerField(
        verbose_name="Soru sayısı",
    )
    sinav_tarihi = models.DateField(
        verbose_name="Sınav tarihi",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_sinavlar",
        verbose_name="Oluşturan kullanıcı",
    )
    olusturulma_tarihi = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Oluşturulma tarihi",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )

    class Meta:
        verbose_name = "Sınav"
        verbose_name_plural = "Sınavlar"
        ordering = ["-sinav_tarihi", "-id"]

    def __str__(self):
        return self.ad


class SinavSonucu(models.Model):
    sinav = models.ForeignKey(
        Sinav,
        on_delete=models.CASCADE,
        related_name="sonuclar",
        verbose_name="Sınav",
    )
    talebe = models.ForeignKey(
        Talebe,
        on_delete=models.CASCADE,
        related_name="sinav_sonuclari",
        verbose_name="Talebe",
    )
    dogru = models.PositiveIntegerField(
        default=0,
        verbose_name="Doğru",
    )
    yanlis = models.PositiveIntegerField(
        default=0,
        verbose_name="Yanlış",
    )
    bos = models.PositiveIntegerField(
        default=0,
        verbose_name="Boş",
    )
    puan = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
        verbose_name="Puan",
    )
    kaydeden = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kaydettigi_sinav_sonuclari",
        verbose_name="Kaydeden kullanıcı",
    )
    kayit_tarihi = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Kayıt tarihi",
    )
    guncellenme_tarihi = models.DateTimeField(
        auto_now=True,
        verbose_name="Güncellenme tarihi",
    )

    class Meta:
        verbose_name = "Sınav sonucu"
        verbose_name_plural = "Sınav sonuçları"
        ordering = [
            "-puan",
            "-dogru",
            "talebe__ad_soyad",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sinav", "talebe"],
                name="sinav_talebe_tek_sonuc",
            )
        ]

    def clean(self):
        if not self.sinav_id:
            return

        toplam = (
            int(self.dogru or 0)
            + int(self.yanlis or 0)
            + int(self.bos or 0)
        )

        if toplam != self.sinav.soru_sayisi:
            raise ValidationError(
                {
                    "dogru": (
                        "Doğru + yanlış + boş toplamı, "
                        f"{self.sinav.soru_sayisi} olmalıdır."
                    )
                }
            )

        if self.dogru > self.sinav.soru_sayisi:
            raise ValidationError(
                {
                    "dogru": (
                        "Doğru sayısı toplam soru sayısını geçemez."
                    )
                }
            )

    def puani_hesapla(self):
        if not self.sinav_id or not self.sinav.soru_sayisi:
            return Decimal("0.00")

        return (
            Decimal(int(self.dogru or 0))
            * Decimal("100")
            / Decimal(int(self.sinav.soru_sayisi))
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def save(self, *args, **kwargs):
        self.puan = self.puani_hesapla()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.sinav.ad} — "
            f"{self.talebe.ad_soyad} — "
            f"{self.puan}"
        )
