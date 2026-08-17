from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta

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

    @property
    def etiket(self) -> str:
        return f"{self.sinif}-{self.sube}"


class PersonelProfili(models.Model):
    class Rol(models.TextChoices):
        IDARECI = "idareci", "İdareci"
        IC_MESUL = "ic_mesul", "İç Mesul"
        EGITIM_MESUL = "egitim_mesul", "Eğitim Mesulü"
        ETUT_MESUL = "etut_mesul", "Etüt Mesulü"
        SINIF_MESUL = "sinif_mesul", "Sınıf Mesulü"
        REHBER_OGRETMENI = "rehber_ogretmeni", "Rehber Öğretmeni"
        MUHASEBECI = "muhasebeci", "Muhasebeci"
        NEHARI_MESUL = "nehari_mesul", "Nehari Mesulü"
        MAHAL_SORUMLU = "mahal_sorumlusu", "Mahal Sorumlusu"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="personel_profili",
        verbose_name="Kullanıcı hesabı",
    )
    ad_soyad = models.CharField(
        max_length=120,
        verbose_name="Ad soyad",
    )
    ana_rol = models.CharField(
        max_length=30,
        choices=Rol.choices,
        default=Rol.ETUT_MESUL,
        verbose_name="Ana rol",
    )
    rol = models.ForeignKey(
        "Rol",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personel_profilleri",
        verbose_name="RBAC rolü",
    )
    etut_hocasi = models.OneToOneField(
        "EtutHocasi",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="personel_kaydi",
        verbose_name="Etüt hocası kaydı",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Personel profili"
        verbose_name_plural = "Personel profilleri"
        ordering = ["ad_soyad"]

    def __str__(self):
        return f"{self.ad_soyad} — {self.get_ana_rol_display()}"

    @property
    def rol_etiketi(self):
        return self.get_ana_rol_display()


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
    class Durum(models.TextChoices):
        AKTIF = "aktif", "Aktif"
        MEZUN = "mezun", "Mezun"
        AYRILDI = "ayrildi", "Ayrıldı"

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
    dini_ders_hocasi = models.ForeignKey(
        EtutHocasi,
        on_delete=models.PROTECT,
        related_name="dini_ders_talebeleri",
        verbose_name="Dini ders hocası",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )
    durum = models.CharField(
        max_length=10,
        choices=Durum.choices,
        default=Durum.AKTIF,
        verbose_name="Durum",
    )
    dini_ders_seviyesi = models.ForeignKey(
        "DiniDersSeviyesi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="talebeler",
        verbose_name="Dini ders seviyesi",
    )
    dogum_tarihi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Doğum tarihi",
    )
    telefon = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Telefon",
    )
    tc_kimlik = models.CharField(
        max_length=11,
        blank=True,
        verbose_name="TC kimlik no",
    )
    kimlik_adi = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Kimlikteki adı",
    )
    kimlik_soyadi = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Kimlikteki soyadı",
    )

    class Cinsiyet(models.TextChoices):
        ERKEK = "erkek", "Erkek"
        KADIN = "kadin", "Kadın"

    cinsiyet = models.CharField(
        max_length=10,
        choices=Cinsiyet.choices,
        blank=True,
        verbose_name="Cinsiyet",
    )
    baba_adi = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Baba adı",
    )
    anne_adi = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Anne adı",
    )
    dogum_yeri = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Doğum yeri",
    )
    memleket = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Memleket ili",
    )
    memleket_ilce = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Memleket ilçesi",
    )
    diller = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Bildiği diller",
    )
    dahili_seviye = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Dahili seviyesi",
    )
    dahili_ders_mesulu = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Dahili ders mesulü",
    )
    dahili_ders_grubu = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Dahili ders grubu",
    )
    okul_seviyesi = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Okul seviyesi",
    )
    ev_adresi = models.TextField(
        blank=True,
        verbose_name="Veli ev adresi",
    )

    class AileDurumu(models.TextChoices):
        BERABER = "beraber", "Anne – baba beraber"
        AYRI = "ayri", "Anne – baba ayrı"
        AYRI_BABA_UVEY = "ayri_baba_uvey", "Anne – baba ayrı – baba üvey"
        AYRI_ANNE_UVEY = "ayri_anne_uvey", "Anne – baba ayrı – anne üvey"
        ANNE_VEFAT = "anne_vefat", "Anne vefat"
        ANNE_VEFAT_ANNE_UVEY = "anne_vefat_anne_uvey", "Anne vefat – anne üvey"

    aile_durumu = models.CharField(
        max_length=30,
        choices=AileDurumu.choices,
        blank=True,
        verbose_name="Aile durumu",
    )
    eposta = models.EmailField(
        blank=True,
        verbose_name="E-posta",
    )
    biyometrik_foto = models.ImageField(
        upload_to="talebeler/biyometrik/",
        blank=True,
        null=True,
        verbose_name="Biyometrik fotoğraf",
        help_text="Vesikalık fotoğraf — profil ve not girişinde görünür.",
    )

    class Meta:
        verbose_name = "Talebe"
        verbose_name_plural = "Talebeler"
        ordering = ["sinif", "sube", "ad_soyad"]

    def save(self, *args, **kwargs):
        from django.db import IntegrityError

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            uf = set(update_fields)
            if self.durum == self.Durum.AKTIF:
                self.aktif = True
            else:
                self.aktif = False
            if uf <= {"aktif", "durum"}:
                kwargs["update_fields"] = list(uf | {"aktif"})
                super().save(*args, **kwargs)
                return

        if self.durum == self.Durum.AKTIF:
            self.aktif = True
        else:
            self.aktif = False

        if self.sinif_sube_id:
            self.sinif = self.sinif_sube.sinif
            self.sube = self.sinif_sube.sube

        if self.etut_hocasi_id and not self.dini_ders_hocasi_id:
            self.dini_ders_hocasi = self.etut_hocasi

        validate = kwargs.pop("validate", True)
        max_attempts = 3 if not self.pk else 1

        for attempt in range(max_attempts):
            if not self.talebe_no:
                self.talebe_no = self._yeni_talebe_no()
            if validate:
                self.full_clean()
            try:
                super().save(*args, **kwargs)
                return
            except IntegrityError:
                if self.pk or attempt >= max_attempts - 1:
                    raise
                self.talebe_no = None

        raise ValidationError(
            "Talebe kaydı oluşturulamadı. Lütfen birkaç saniye sonra tekrar deneyin."
        )

    @classmethod
    def _yeni_talebe_no(cls) -> str:
        """Veritabanında kullanılmayan ilk sıra numarasını ver (1'den başlar)."""
        kullanilan: set[int] = set()
        for numara in (
            cls.objects.exclude(talebe_no__isnull=True)
            .exclude(talebe_no="")
            .values_list("talebe_no", flat=True)
            .iterator(chunk_size=500)
        ):
            if str(numara).isdigit():
                kullanilan.add(int(numara))

        aday = 1
        while aday in kullanilan:
            aday += 1
        return str(aday)

    @classmethod
    def aktif_numaralari_yeniden_sirala(cls) -> int:
        """Aktif talebelere sınıf/ad sırasına göre 1'den başlayan numara ver."""
        from django.db import transaction

        talebeler = list(
            cls.objects.filter(aktif=True).order_by("sinif", "sube", "ad_soyad", "id")
        )
        if not talebeler:
            return 0

        with transaction.atomic():
            for talebe in talebeler:
                cls.objects.filter(pk=talebe.pk).update(
                    talebe_no=f"__tmp-{talebe.pk}"
                )
            for sira, talebe in enumerate(talebeler, start=1):
                cls.objects.filter(pk=talebe.pk).update(talebe_no=str(sira))

        return len(talebeler)

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

        if self.dini_ders_hocasi_id and not self.dini_ders_seviyesi_id:
            seviye = (
                self.dini_ders_hocasi.sorumlu_dini_ders_seviyeleri.filter(aktif=True)
                .order_by("sira", "ad")
                .first()
            )
            if seviye:
                self.dini_ders_seviyesi = seviye

        if self.dini_ders_seviyesi_id and self.dini_ders_hocasi_id:
            if not self.dini_ders_seviyesi.hocalar.filter(
                pk=self.dini_ders_hocasi_id
            ).exists():
                raise ValidationError(
                    {
                        "dini_ders_hocasi": (
                            f"Seçilen hoca «{self.dini_ders_seviyesi.ad}» seviyesinden "
                            "sorumlu değil."
                        )
                    }
                )

    @property
    def zimmet_hocalari_ayni(self) -> bool:
        return self.etut_hocasi_id == self.dini_ders_hocasi_id

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


class Duyuru(models.Model):
    class Kategori(models.TextChoices):
        GENEL = "genel", "Genel"
        EGITIM = "egitim", "Eğitim"
        PROGRAM = "program", "Program"
        KURUM = "kurum", "Kurum"

    class HedefKitle(models.TextChoices):
        TUM_PERSONEL = "tum_personel", "Herkese (Personel + Öğretmen + Veli)"
        PERSONEL = "personel", "Yalnızca personel paneli"
        OGRETMEN = "ogretmen", "Yalnızca öğretmen paneli"
        VELI = "veli", "Yalnızca veli paneli"

    class Ton(models.TextChoices):
        NAVY = "navy", "Lacivert"
        VIOLET = "violet", "Mor"
        TEAL = "teal", "Turkuaz"
        AMBER = "amber", "Kehribar"

    baslik = models.CharField(
        max_length=200,
        verbose_name="Başlık",
    )
    ozet = models.TextField(
        max_length=4000,
        verbose_name="Kısa açıklama",
    )
    kategori = models.CharField(
        max_length=20,
        choices=Kategori.choices,
        default=Kategori.GENEL,
        verbose_name="Kategori",
    )
    hedef_kitle = models.CharField(
        max_length=20,
        choices=HedefKitle.choices,
        default=HedefKitle.TUM_PERSONEL,
        verbose_name="Hedef kitle",
    )
    dis_link = models.URLField(
        blank=True,
        verbose_name="Bağlantı",
        help_text="İsteğe bağlı. Duyuruya tıklanınca açılacak adres.",
    )
    gorsel = models.ImageField(
        upload_to="duyurular/",
        blank=True,
        null=True,
        verbose_name="Görsel",
        help_text="Sol tarafta gösterilecek fotoğraf.",
    )
    video_url = models.URLField(
        blank=True,
        verbose_name="Video bağlantısı",
        help_text="YouTube, Vimeo veya doğrudan .mp4 bağlantısı.",
    )
    video_dosya = models.FileField(
        upload_to="duyurular/videolar/",
        blank=True,
        null=True,
        verbose_name="Video dosyası",
        help_text="İsteğe bağlı. Yüklenen video sol tarafta oynatılır.",
    )
    ton = models.CharField(
        max_length=20,
        choices=Ton.choices,
        default=Ton.NAVY,
        verbose_name="Görsel ton",
    )
    baslangic = models.DateField(
        default=timezone.localdate,
        verbose_name="Yayın başlangıcı",
    )
    bitis = models.DateField(
        null=True,
        blank=True,
        verbose_name="Yayın bitişi",
    )
    sira = models.PositiveIntegerField(
        default=0,
        verbose_name="Sıra",
        help_text="Küçük numara önce gösterilir.",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_duyurular",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Duyuru"
        verbose_name_plural = "Duyurular"
        ordering = ["sira", "-baslangic", "-id"]

    def __str__(self):
        return self.baslik

    @property
    def ton_sinifi(self) -> str:
        return f"duyuru-tone-{self.ton}"

    @property
    def kategori_etiketi(self) -> str:
        return self.get_kategori_display()

    @property
    def ozet_maddeleri(self) -> list[str]:
        import re

        text = (self.ozet or "").strip()
        if not text:
            return []

        parcalar = re.split(r"[\n\r]+|(?:^|\s)[•\-–]\s*", text)
        maddeler = [p.strip().strip(".") for p in parcalar if p and p.strip()]
        if len(maddeler) <= 1:
            maddeler = [p.strip() for p in re.split(r"[.;]+", text) if p.strip()]
        return maddeler[:4]

    @property
    def yayinda_mi(self) -> bool:
        if not self.aktif:
            return False

        bugun = timezone.localdate()
        if self.baslangic > bugun:
            return False

        if self.bitis and self.bitis < bugun:
            return False

        return True

    @property
    def gorsel_var_mi(self) -> bool:
        if not self.gorsel:
            return False
        try:
            name = (self.gorsel.name or "").strip()
            if not name:
                return False
            return bool(self.gorsel.storage.exists(name))
        except Exception:
            return False

    @property
    def video_var_mi(self) -> bool:
        return bool(self.video_url or self.video_dosya)

    @property
    def medya_var_mi(self) -> bool:
        return self.gorsel_var_mi or self.video_var_mi

    @property
    def oto_gorsel_goster(self) -> bool:
        return not self.medya_var_mi

    @property
    def oto_gorsel_ozeti(self) -> str:
        maddeler = self.ozet_maddeleri
        if maddeler:
            return maddeler[0][:100]
        ozet = (self.ozet or "").strip()
        if not ozet:
            return ""
        tek_satir = " ".join(ozet.split())
        return tek_satir[:100]

    @property
    def oto_gorsel_harfi(self) -> str:
        baslik = (self.baslik or "").strip()
        if not baslik:
            return "D"
        return baslik[0].upper()

    @property
    def oto_gorsel_sahne(self) -> str:
        from takip.duyuru_service import duyuru_oto_sahne

        return duyuru_oto_sahne(self)

    @property
    def oto_sahne_ikonu(self) -> str:
        ikonlar = {
            "asistan": "🤖",
            "egitim": "📘",
            "program": "📅",
            "kurum": "🏛",
            "genel": "📣",
        }
        return ikonlar.get(self.oto_gorsel_sahne, "📣")

    @property
    def oto_gorsel_ikonu(self) -> str:
        ikonlar = {
            self.Kategori.EGITIM: "📘",
            self.Kategori.PROGRAM: "📅",
            self.Kategori.KURUM: "🏛",
            self.Kategori.GENEL: "📣",
        }
        return ikonlar.get(self.kategori, "📣")

    @property
    def video_gomme_url(self) -> str | None:
        from takip.duyuru_service import video_gomme_adresi

        if self.video_dosya:
            return self.video_dosya.url
        if self.video_url:
            return video_gomme_adresi(self.video_url)
        return None

    @property
    def video_gomme_mi(self) -> bool:
        adres = self.video_gomme_url or ""
        return "youtube.com/embed" in adres or "player.vimeo.com" in adres


class ProgramFaaliyetTuru(models.Model):
    """Günlük program satır türleri — yönetimden eklenebilir."""

    kod = models.SlugField(
        max_length=40,
        unique=True,
        verbose_name="Kod",
        help_text="Küçük harf, örn. ders, namaz, mola",
    )
    ad = models.CharField(max_length=80, verbose_name="Ad")
    renk = models.CharField(
        max_length=20,
        default="slate",
        verbose_name="Renk",
        help_text="green, blue, amber, sky, slate",
    )
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Program faaliyet türü"
        verbose_name_plural = "Program faaliyet türleri"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad


class ProgramPlan(models.Model):
    ad = models.CharField(
        max_length=200,
        verbose_name="Program adı",
    )
    aciklama = models.TextField(
        blank=True,
        verbose_name="Açıklama",
    )
    baslangic_tarihi = models.DateField(
        verbose_name="Başlangıç tarihi",
    )
    bitis_tarihi = models.DateField(
        verbose_name="Bitiş tarihi",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_programlar",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Program planı"
        verbose_name_plural = "Program planları"
        ordering = ["-baslangic_tarihi", "ad"]

    def __str__(self):
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
    def yayinda_mi(self) -> bool:
        if not self.aktif:
            return False

        bugun = timezone.localdate()
        return self.baslangic_tarihi <= bugun <= self.bitis_tarihi

    @property
    def tarih_araligi_goster(self) -> str:
        return (
            f"{self.baslangic_tarihi.strftime('%d.%m.%Y')}"
            f" – {self.bitis_tarihi.strftime('%d.%m.%Y')}"
        )


class ProgramSatir(models.Model):
    class FaaliyetTuru(models.TextChoices):
        DERS = "ders", "Ders"
        ETUT = "etut", "Etüt"
        NAMAZ = "namaz", "Namaz"
        YEMEK = "yemek", "Yemek"
        UYKU = "uyku", "Uyku"
        DINLENME = "dinlenme", "Dinlenme"
        SPOR = "spor", "Spor"
        GOREV = "gorev", "Görev"
        TOPLANTI = "toplanti", "Toplantı"
        DIGER = "diger", "Diğer"

    class FaaliyetDurumu(models.TextChoices):
        ETKIN = "etkin", "Etkin"
        PASIF = "pasif", "Pasif"

    program = models.ForeignKey(
        ProgramPlan,
        on_delete=models.CASCADE,
        related_name="satirlar",
        verbose_name="Program",
    )
    baslangic_saati = models.TimeField(
        verbose_name="Başlangıç",
    )
    bitis_saati = models.TimeField(
        verbose_name="Bitiş",
    )
    sure_dakika = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name="Süre (dk)",
    )
    faaliyet_turu = models.CharField(
        max_length=40,
        default=FaaliyetTuru.DERS,
        verbose_name="Faaliyet türü",
        help_text="Tür listesi Program faaliyet türlerinden yönetilir.",
    )
    faaliyet_adi = models.CharField(
        max_length=200,
        verbose_name="Faaliyet adı",
    )
    program_adi = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Program adı",
        help_text="Boş bırakılırsa üst program adı kullanılır.",
    )
    faaliyet_durumu = models.CharField(
        max_length=10,
        choices=FaaliyetDurumu.choices,
        default=FaaliyetDurumu.ETKIN,
        verbose_name="Durum",
    )
    sira = models.PositiveIntegerField(
        default=0,
        verbose_name="Sıra",
    )

    class Meta:
        verbose_name = "Program satırı"
        verbose_name_plural = "Program satırları"
        ordering = ["sira", "baslangic_saati", "id"]

    def __str__(self):
        return f"{self.baslangic_saati:%H:%M} {self.faaliyet_adi}"

    @classmethod
    def sure_dakika_hesapla(cls, baslangic, bitis) -> int:
        """Geceyi aşan aralıkları destekler (örn. 22:00–06:00 uyku)."""
        bas = datetime.combine(date.min, baslangic)
        bit = datetime.combine(date.min, bitis)

        if bit <= bas:
            bit += timedelta(days=1)

        return int((bit - bas).total_seconds() // 60)

    def clean(self):
        super().clean()

        if self.baslangic_saati and self.bitis_saati:
            self.sure_dakika = self.sure_dakika_hesapla(
                self.baslangic_saati,
                self.bitis_saati,
            )

    def save(self, *args, **kwargs):
        if self.baslangic_saati and self.bitis_saati:
            self.sure_dakika = self.sure_dakika_hesapla(
                self.baslangic_saati,
                self.bitis_saati,
            )

        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def sure_goster(self) -> str:
        saat, dakika = divmod(self.sure_dakika, 60)

        if saat and dakika:
            return f"{saat} sa {dakika} dk"

        if saat:
            return f"{saat} sa"

        return f"{dakika} dk"

    @property
    def gorunen_program_adi(self) -> str:
        return self.program_adi or self.program.ad

    @property
    def tur_etiket(self) -> str:
        tur = ProgramFaaliyetTuru.objects.filter(kod=self.faaliyet_turu).first()
        if tur:
            return tur.ad
        try:
            return ProgramSatir.FaaliyetTuru(self.faaliyet_turu).label
        except ValueError:
            return self.faaliyet_turu

    @property
    def tur_renk(self) -> str:
        tur = ProgramFaaliyetTuru.objects.filter(kod=self.faaliyet_turu).first()
        if tur and tur.renk:
            return tur.renk
        fallback = {
            "namaz": "green",
            "yemek": "amber",
            "ders": "blue",
            "etut": "blue",
            "uyku": "slate",
            "dinlenme": "slate",
            "mola": "slate",
            "serbest_zaman": "sky",
            "spor": "blue",
            "gorev": "slate",
            "toplanti": "slate",
            "diger": "sky",
        }
        return fallback.get(self.faaliyet_turu, "slate")


class ImamMuezzinListesi(models.Model):
    ad = models.CharField(
        max_length=200,
        verbose_name="Liste adı",
    )
    baslangic_tarihi = models.DateField(
        verbose_name="Başlangıç tarihi",
    )
    bitis_tarihi = models.DateField(
        verbose_name="Bitiş tarihi",
    )
    cumartesi_dahil = models.BooleanField(
        default=True,
        verbose_name="Cumartesi dahil",
    )
    pazar_dahil = models.BooleanField(
        default=False,
        verbose_name="Pazar dahil",
    )
    haric_tarihler = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Hariç tutulan günler",
        help_text="ISO formatında tarih listesi (YYYY-MM-DD).",
    )
    talebe_havuzu = models.ManyToManyField(
        Talebe,
        blank=True,
        related_name="imam_muezzin_listeleri",
        verbose_name="Talebe havuzu",
        help_text="Boş bırakılırsa tüm aktif talebeler kullanılır.",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_imam_listeleri",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "İmam müezzin listesi"
        verbose_name_plural = "İmam müezzin listeleri"
        ordering = ["-baslangic_tarihi", "ad"]

    def __str__(self):
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

    @property
    def tarih_araligi_goster(self) -> str:
        return (
            f"{self.baslangic_tarihi.strftime('%d.%m.%Y')}"
            f" – {self.bitis_tarihi.strftime('%d.%m.%Y')}"
        )

    @property
    def yayinda_mi(self) -> bool:
        if not self.aktif:
            return False

        bugun = timezone.localdate()
        return self.baslangic_tarihi <= bugun <= self.bitis_tarihi


class ImamMuezzinAtama(models.Model):
    liste = models.ForeignKey(
        ImamMuezzinListesi,
        on_delete=models.CASCADE,
        related_name="atamalar",
        verbose_name="Liste",
    )
    tarih = models.DateField(
        verbose_name="Tarih",
    )
    imam = models.ForeignKey(
        Talebe,
        on_delete=models.PROTECT,
        related_name="imam_gorevleri",
        verbose_name="İmam",
        null=True,
        blank=True,
    )
    muezzin = models.ForeignKey(
        Talebe,
        on_delete=models.PROTECT,
        related_name="muezzin_gorevleri",
        verbose_name="Müezzin",
        null=True,
        blank=True,
    )
    manuel_duzenlendi = models.BooleanField(
        default=False,
        verbose_name="Manuel düzenlendi",
    )

    class Meta:
        verbose_name = "İmam müezzin ataması"
        verbose_name_plural = "İmam müezzin atamaları"
        ordering = ["tarih"]
        constraints = [
            models.UniqueConstraint(
                fields=["liste", "tarih"],
                name="benzersiz_liste_gun_atama",
            )
        ]

    def __str__(self):
        return f"{self.tarih} — {self.imam} / {self.muezzin}"


class ImamMuezzinHavuzKaydi(models.Model):
    class Rol(models.TextChoices):
        IMAM = "imam", "İmam"
        MUEZZIN = "muezzin", "Müezzin"

    liste = models.ForeignKey(
        ImamMuezzinListesi,
        on_delete=models.CASCADE,
        related_name="havuz_kayitlari",
        verbose_name="Liste",
    )
    talebe = models.ForeignKey(
        Talebe,
        on_delete=models.CASCADE,
        related_name="imam_muezzin_havuz_kayitlari",
        verbose_name="Talebe",
    )
    rol = models.CharField(max_length=10, choices=Rol.choices, verbose_name="Rol")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "İmam müezzin havuz kaydı"
        verbose_name_plural = "İmam müezzin havuz kayıtları"
        ordering = ["rol", "sira", "talebe__ad_soyad"]
        constraints = [
            models.UniqueConstraint(
                fields=["liste", "rol", "talebe"],
                name="benzersiz_imam_muezzin_havuz",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_rol_display()} — {self.talebe.ad_soyad}"


class TemizlikAlani(models.Model):
    ad = models.CharField(
        max_length=120,
        verbose_name="Alan adı",
    )
    kat = models.ForeignKey(
        "TemizlikKati",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alanlar",
        verbose_name="Kat",
    )
    aciklama = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Açıklama",
    )
    sira = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Sıra",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )

    class Meta:
        verbose_name = "Temizlik alanı"
        verbose_name_plural = "Temizlik alanları"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad


class TemizlikListesi(models.Model):
    ad = models.CharField(
        max_length=200,
        verbose_name="Liste adı",
    )
    baslangic_tarihi = models.DateField(
        verbose_name="Başlangıç tarihi",
    )
    bitis_tarihi = models.DateField(
        verbose_name="Bitiş tarihi",
    )
    cumartesi_dahil = models.BooleanField(
        default=True,
        verbose_name="Cumartesi dahil",
    )
    pazar_dahil = models.BooleanField(
        default=False,
        verbose_name="Pazar dahil",
    )
    haric_tarihler = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Hariç tutulan günler",
        help_text="ISO formatında tarih listesi (YYYY-MM-DD).",
    )
    alanlar = models.ManyToManyField(
        TemizlikAlani,
        blank=True,
        related_name="temizlik_listeleri",
        verbose_name="Temizlik alanları",
        help_text="Boş bırakılırsa tüm aktif alanlar kullanılır.",
    )
    talebe_havuzu = models.ManyToManyField(
        Talebe,
        blank=True,
        related_name="temizlik_listeleri",
        verbose_name="Talebe havuzu",
        help_text="Boş bırakılırsa tüm aktif talebeler kullanılır.",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_temizlik_listeleri",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Temizlik listesi"
        verbose_name_plural = "Temizlik listeleri"
        ordering = ["-baslangic_tarihi", "ad"]

    def __str__(self):
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

    @property
    def tarih_araligi_goster(self) -> str:
        return (
            f"{self.baslangic_tarihi.strftime('%d.%m.%Y')}"
            f" – {self.bitis_tarihi.strftime('%d.%m.%Y')}"
        )

    @property
    def yayinda_mi(self) -> bool:
        if not self.aktif:
            return False

        bugun = timezone.localdate()
        return self.baslangic_tarihi <= bugun <= self.bitis_tarihi


class TemizlikAtama(models.Model):
    liste = models.ForeignKey(
        TemizlikListesi,
        on_delete=models.CASCADE,
        related_name="atamalar",
        verbose_name="Liste",
    )
    tarih = models.DateField(
        verbose_name="Tarih",
    )
    alan = models.ForeignKey(
        TemizlikAlani,
        on_delete=models.PROTECT,
        related_name="atamalar",
        verbose_name="Alan",
    )
    talebe = models.ForeignKey(
        Talebe,
        on_delete=models.PROTECT,
        related_name="temizlik_gorevleri",
        verbose_name="Sorumlu talebe",
        null=True,
        blank=True,
    )
    manuel_duzenlendi = models.BooleanField(
        default=False,
        verbose_name="Manuel düzenlendi",
    )

    class Meta:
        verbose_name = "Temizlik ataması"
        verbose_name_plural = "Temizlik atamaları"
        ordering = ["tarih", "alan__sira", "alan__ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["liste", "tarih", "alan"],
                name="benzersiz_temizlik_liste_gun_alan",
            )
        ]

    def __str__(self):
        return f"{self.tarih} — {self.alan}: {self.talebe}"


class TemizlikKati(models.Model):
    liste = models.ForeignKey(
        TemizlikListesi,
        on_delete=models.CASCADE,
        related_name="katlar",
        verbose_name="Liste",
    )
    ad = models.CharField(max_length=120, verbose_name="Kat adı")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Temizlik katı"
        verbose_name_plural = "Temizlik katları"
        ordering = ["sira", "ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["liste", "ad"],
                name="benzersiz_temizlik_liste_kat",
            )
        ]

    def __str__(self) -> str:
        return self.ad


class TemizlikKatSorumlusu(models.Model):
    kat = models.ForeignKey(
        TemizlikKati,
        on_delete=models.CASCADE,
        related_name="sorumlular",
        verbose_name="Kat",
    )
    personel = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="temizlik_kat_sorumluluklari",
        verbose_name="Sorumlu personel",
    )

    class Meta:
        verbose_name = "Kat sorumlusu"
        verbose_name_plural = "Kat sorumluları"
        constraints = [
            models.UniqueConstraint(
                fields=["kat", "personel"],
                name="benzersiz_temizlik_kat_sorumlu",
            )
        ]

    def __str__(self) -> str:
        return f"{self.kat.ad} — {self.personel}"


class TemizlikMahalSorumlusu(models.Model):
    alan = models.ForeignKey(
        TemizlikAlani,
        on_delete=models.CASCADE,
        related_name="mahal_sorumlulari",
        verbose_name="Mahal",
    )
    personel = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="temizlik_mahal_sorumluluklari",
        verbose_name="Sorumlu personel",
    )

    class Meta:
        verbose_name = "Mahal sorumlusu"
        verbose_name_plural = "Mahal sorumluları"
        constraints = [
            models.UniqueConstraint(
                fields=["alan", "personel"],
                name="benzersiz_temizlik_mahal_sorumlu",
            )
        ]

    def __str__(self) -> str:
        return f"{self.alan.ad} — {self.personel}"


class TemizlikGorevlisi(models.Model):
    liste = models.ForeignKey(
        TemizlikListesi,
        on_delete=models.CASCADE,
        related_name="gorevliler",
        verbose_name="Liste",
    )
    alan = models.ForeignKey(
        TemizlikAlani,
        on_delete=models.CASCADE,
        related_name="gorevliler",
        verbose_name="Mahal",
    )
    talebe = models.ForeignKey(
        Talebe,
        on_delete=models.CASCADE,
        related_name="temizlik_mahal_gorevleri",
        verbose_name="Görevli talebe",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Temizlik görevlisi"
        verbose_name_plural = "Temizlik görevlileri"
        ordering = ["alan__sira", "alan__ad", "talebe__ad_soyad"]
        constraints = [
            models.UniqueConstraint(
                fields=["liste", "alan", "talebe"],
                name="benzersiz_temizlik_liste_alan_gorevli",
            )
        ]

    def __str__(self) -> str:
        return f"{self.alan.ad} — {self.talebe.ad_soyad}"


class TemizlikGunlukKontrol(models.Model):
    class Durum(models.TextChoices):
        BEKLIYOR = "bekliyor", "Bekliyor"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"
        EKSIK = "eksik", "Eksik"
        KONTROL = "kontrol", "Kontrol Edildi"

    liste = models.ForeignKey(
        TemizlikListesi,
        on_delete=models.CASCADE,
        related_name="gunluk_kontroller",
        verbose_name="Liste",
    )
    alan = models.ForeignKey(
        TemizlikAlani,
        on_delete=models.CASCADE,
        related_name="gunluk_kontroller",
        verbose_name="Mahal",
    )
    tarih = models.DateField(verbose_name="Tarih")
    durum = models.CharField(
        max_length=12,
        choices=Durum.choices,
        default=Durum.BEKLIYOR,
        verbose_name="Durum",
    )
    notu = models.CharField(max_length=255, blank=True, verbose_name="Not")
    guncelleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="temizlik_kontrolleri",
        verbose_name="Güncelleyen",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Temizlik günlük kontrol"
        verbose_name_plural = "Temizlik günlük kontroller"
        constraints = [
            models.UniqueConstraint(
                fields=["liste", "alan", "tarih"],
                name="benzersiz_temizlik_gun_kontrol",
            )
        ]

    def __str__(self) -> str:
        return f"{self.tarih} · {self.alan.ad} · {self.get_durum_display()}"


class YemekOgun(models.Model):
    ad = models.CharField(
        max_length=120,
        verbose_name="Öğün adı",
    )
    aciklama = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Açıklama",
    )
    sira = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Sıra",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )

    class Meta:
        verbose_name = "Yemek öğünü"
        verbose_name_plural = "Yemek öğünleri"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad


class YemekciListesi(models.Model):
    ad = models.CharField(
        max_length=200,
        verbose_name="Liste adı",
    )
    baslangic_tarihi = models.DateField(
        verbose_name="Başlangıç tarihi",
    )
    bitis_tarihi = models.DateField(
        verbose_name="Bitiş tarihi",
    )
    cumartesi_dahil = models.BooleanField(
        default=True,
        verbose_name="Cumartesi dahil",
    )
    pazar_dahil = models.BooleanField(
        default=False,
        verbose_name="Pazar dahil",
    )
    haric_tarihler = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Hariç tutulan günler",
        help_text="ISO formatında tarih listesi (YYYY-MM-DD).",
    )
    ogunler = models.ManyToManyField(
        YemekOgun,
        blank=True,
        related_name="yemekci_listeleri",
        verbose_name="Öğünler",
        help_text="Boş bırakılırsa tüm aktif öğünler kullanılır.",
    )
    talebe_havuzu = models.ManyToManyField(
        Talebe,
        blank=True,
        related_name="yemekci_listeleri",
        verbose_name="Talebe havuzu",
        help_text="Boş bırakılırsa tüm aktif talebeler kullanılır.",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_yemekci_listeleri",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yemekçilik listesi"
        verbose_name_plural = "Yemekçilik listeleri"
        ordering = ["-baslangic_tarihi", "ad"]

    def __str__(self):
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

    @property
    def tarih_araligi_goster(self) -> str:
        return (
            f"{self.baslangic_tarihi.strftime('%d.%m.%Y')}"
            f" – {self.bitis_tarihi.strftime('%d.%m.%Y')}"
        )

    @property
    def yayinda_mi(self) -> bool:
        if not self.aktif:
            return False

        bugun = timezone.localdate()
        return self.baslangic_tarihi <= bugun <= self.bitis_tarihi


class YemekciAtama(models.Model):
    liste = models.ForeignKey(
        YemekciListesi,
        on_delete=models.CASCADE,
        related_name="atamalar",
        verbose_name="Liste",
    )
    tarih = models.DateField(
        verbose_name="Tarih",
    )
    ogun = models.ForeignKey(
        YemekOgun,
        on_delete=models.PROTECT,
        related_name="atamalar",
        verbose_name="Öğün",
    )
    talebe = models.ForeignKey(
        Talebe,
        on_delete=models.PROTECT,
        related_name="yemekci_gorevleri",
        verbose_name="Sorumlu talebe",
        null=True,
        blank=True,
    )
    yardimci = models.ForeignKey(
        Talebe,
        on_delete=models.PROTECT,
        related_name="yemekci_yardimci_gorevleri",
        verbose_name="Yardımcı talebe",
        null=True,
        blank=True,
    )
    manuel_duzenlendi = models.BooleanField(
        default=False,
        verbose_name="Manuel düzenlendi",
    )

    class Meta:
        verbose_name = "Yemekçilik ataması"
        verbose_name_plural = "Yemekçilik atamaları"
        ordering = ["tarih", "ogun__sira", "ogun__ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["liste", "tarih", "ogun"],
                name="benzersiz_yemekci_liste_gun_ogun",
            )
        ]

    def __str__(self):
        return f"{self.tarih} — {self.ogun}: {self.talebe} / {self.yardimci}"


from takip.wave0_models import (  # noqa: E402,F401
    AuditLog,
    Brans,
    Ders,
    DiniDersSeviyesi,
    Donem,
    EgitimYili,
    KullaniciRol,
    KullaniciYetkiOverride,
    RolIslemYetki,
    RolKapsam,
    RolModulErisim,
    Rol as YetkiRol,
    TalebeDosyasi,
    TalebeGenelDurum,
    TalebePersonelNotu,
    VeliHesap,
    VeliKisi,
    VeliTalebeBaglantisi,
    YetkiIslem,
    YetkiModul,
)

# PersonelProfili.rol FK hedefi — wave0_models.Rol ile aynı tablo
Rol = YetkiRol

from takip.ktt_models import KttSinav, KttSonucu  # noqa: E402,F401
from takip.ss_deneme_models import (  # noqa: E402,F401
    SozelSayisalBransSonuc,
    SozelSayisalDeneme,
    SozelSayisalSonuc,
)

from takip.soru_takip_models import GunlukSoruDersSatiri, GunlukSoruKaydi  # noqa: E402,F401

from takip.akademik_mudahale_models import AkademikMudahale, MudahaleTuru  # noqa: E402,F401
from takip.namaz_yoklama_models import (  # noqa: E402,F401
    NamazDurumu,
    NamazVakti,
    NamazYoklamaKaydi,
    NamazYoklamaOturum,
)

from takip.deneme_models import (  # noqa: E402,F401
    DenemeBransSonucu,
    DenemeEslestirmeAlias,
    DenemeGapRaporu,
    DenemeKonuSonucu,
    DenemeSinavi,
    DenemeSonucu,
)

from takip.etut_plan_models import (  # noqa: E402,F401
    EtutFaaliyetHavuzu,
    EtutGrupSaatBloku,
    EtutHaftaPlani,
    EtutPlanFaaliyet,
)

from takip.dini_ders_takip_models import (  # noqa: E402,F401
    DiniDersKonu,
    DiniDersKonuKaydi,
    DiniDersTakipAlani,
)

from takip.dini_ilerleme_models import (  # noqa: E402,F401
    DiniAlanPlani,
    DiniIlerlemeEsik,
    DiniKonuHedefTarihi,
)

from takip.ogretmen_odeme_models import (  # noqa: E402,F401
    OgretmenOdemeDersKaydi,
    OgretmenOdemeDonemi,
    OgretmenOdemeGunKaydi,
    OgretmenOdemeProfili,
)

from takip.veli_randevu_models import (  # noqa: E402,F401
    RandevuMusaitlik,
    RandevuPersonelAyar,
    VeliRandevu,
)

from takip.mezun_models import (  # noqa: E402,F401
    MezunBasari,
    MezunEtkinlik,
    MezunEtkinlikKatilim,
    MezunGuncellemeGorevKayit,
    MezunGuncellemeGorevi,
    MezunIletisim,
    MezunProfil,
    MezunYolculukOlay,
)

from takip.aidat_models import (  # noqa: E402,F401
    AidatTahsilat,
    AidatTanim,
    TalebeAidatKaydi,
)

from takip.finans_models import (  # noqa: E402,F401
    FinansIndirim,
    FinansIslemLog,
    FinansKampanya,
    FinansTahsilat,
    FinansTaksit,
    FinansUcretPolitikasi,
    TalebeFinansDosyasi,
)

from takip.rehberlik_models import (  # noqa: E402,F401
    GorusmeDosyasi,
    GorusmeGorevi,
    GorusmeTuru,
    OgrenciGorusmesi,
)

from takip.disiplin_models import DisiplinKaydi, DisiplinOlayTuru  # noqa: E402,F401

from takip.disiplin_kurul_models import (  # noqa: E402,F401
    DisiplinKurulAyar,
    DisiplinKurulGundem,
    DisiplinKurulKarar,
    DisiplinKurulKararNot,
    DisiplinKurulKararTakip,
    DisiplinKurulKatilimci,
    DisiplinKurulVarsayilanGundem,
    DisiplinKurulVarsayilanUye,
    DisiplinKurulu,
)

from takip.gunluk_takip_models import GunlukTakipKaydi  # noqa: E402,F401

from takip.pazar_izin_donus_models import (  # noqa: E402,F401
    PazarIzinDonusGunAyar,
    PazarIzinDonusKaydi,
    PazarIzinDonusOturum,
)

from takip.yazili_takip_models import (  # noqa: E402,F401
    YaziliKamp,
    YaziliSinav,
    YaziliSonuc,
)

from takip.vazife_models import PersonelVazife  # noqa: E402,F401
from takip.personel_toplanti_models import (  # noqa: E402,F401
    PersonelToplantiGundemMadde,
    PersonelToplantiKarar,
    PersonelToplantisi,
)

from takip.bildirim_models import Bildirim  # noqa: E402,F401

from takip.yct_models import YctOlay  # noqa: E402,F401

from takip.talebe_panel_models import (  # noqa: E402,F401
    TalebeEvGunu,
    TalebeHesap,
    TalebeKonumKaydi,
)

from takip.ogretmen_not_models import (  # noqa: E402,F401
    OgretmenHaftalikKonu,
    OgretmenSinavNotu,
    OgretmenSinifYoklama,
)

from takip.veli_goruntuleme_models import VeliIcerikGoruntuleme  # noqa: E402,F401

from takip.sohbet_mevzuu_models import HaftalikSohbetMevzuu  # noqa: E402,F401

from takip.cuma_durum_models import CumaDurumMetni  # noqa: E402,F401

from takip.ai_models import AiUretimKaydi  # noqa: E402,F401

from takip.panel_kisayol_models import PanelKisayol, PanelKisayolGorsel  # noqa: E402,F401

from takip.panel_metrik_models import PanelMetrik  # noqa: E402,F401

from takip.konu_destek_models import (  # noqa: E402,F401
    KonuEgitimVideosu,
    KonuKatalogu,
    KonuSorusu,
    KonuTestCevabi,
    KonuTestOturu,
    KonuVideoIzleme,
    TalebeKonuEksigi,
)

from takip.ktt_akilli_models import (  # noqa: E402,F401
    KonuAlias,
    KonuEslestirmeInceleme,
    KttEslestirmeEsik,
    KttEtutMudahale,
)

from takip.olcme_models import (  # noqa: E402,F401
    OlcumCevapAnahtari,
    OlcumIslemGecmisi,
    OlcumKazanim,
    OlcumSablonDers,
    OlcumSablonSoru,
    OlcumSinavDers,
    OlcumSinavSablon,
    OlcumSoru,
    OlcumTalebeCevap,
    OlcumUnite,
)

from takip.dershane_program_models import (  # noqa: E402,F401
    DershaneDersAtamasi,
    DershaneEtutGrubu,
    DershaneGrupDersOgretmen,
    DershaneProgramGun,
    DershaneProgramSablon,
    DershaneProgramSurum,
    DershaneProgrami,
    DershaneSaatBloku,
)

from takip.yemekci_sinif_models import (  # noqa: E402,F401
    YemekciAyar,
    YemekciGunAtama,
    YemekciHavuzKaydi,
    YemekciSinifHavuzu,
)

from takip.sinav_basvuru_models import (  # noqa: E402,F401
    SinavBasvuru,
    SinavBasvuruDurum,
)
from takip.sinav_basvuru_mesaj_models import (  # noqa: E402,F401
    SinavBasvuruMesajLog,
    SinavBasvuruMesajSablon,
)

from takip.ziyaret_arac_models import (  # noqa: E402,F401
    ZiyaretAracAtama,
    ZiyaretAraci,
    ZiyaretPlani,
    ZiyaretPlaniTalebe,
    ZiyaretProgramAdimi,
)

from takip.iletisim_models import (  # noqa: E402,F401
    IletisimEki,
    IletisimKurumAyar,
    IletisimOlay,
    IletisimPaketi,
    IletisimSablon,
)
