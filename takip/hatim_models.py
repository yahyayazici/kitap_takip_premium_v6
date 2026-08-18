"""Hatim Takip Merkezi — program, dönem ve cüz atama modelleri."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class HatimProgrami(models.Model):
    class Tur(models.TextChoices):
        PERSONEL = "personel", "Personel Hatmi"
        TALEBE = "talebe", "Talebe Hatmi"
        SINIF = "sinif", "Sınıf Hatmi"
        VELI = "veli", "Veli Hatmi"

    class Tekrar(models.TextChoices):
        BIR_KEZ = "once", "Sadece bir kez"
        GUNLUK = "daily", "Her gün"
        IKI_GUN = "every_2", "2 günde bir"
        UC_GUN = "every_3", "3 günde bir"
        HAFTALIK = "weekly", "Haftalık"
        OZEL = "custom", "Özel gün aralığı"

    class CuzStrateji(models.TextChoices):
        AYNI = "same", "Aynı cüzler tekrar okunacak"
        DON = "rotate", "Cüzler her dönemde sırayla döndürülecek"
        YENIDEN = "redistribute", "Cüzler her dönemde yeniden dağıtılacak"

    class DagitimYontemi(models.TextChoices):
        OTOMATIK = "auto", "Otomatik sırayla"
        MANUEL = "manual", "Manuel dağıtım"

    class Durum(models.TextChoices):
        TASLAK = "draft", "Taslak"
        AKTIF = "active", "Aktif"
        DURAKLATILDI = "paused", "Duraklatıldı"
        TAMAMLANDI = "completed", "Tamamlandı"
        DURDURULDU = "stopped", "Durduruldu"

    ad = models.CharField(max_length=200, verbose_name="Hatim adı")
    tur = models.CharField(
        max_length=20,
        choices=Tur.choices,
        default=Tur.PERSONEL,
        verbose_name="Hatim türü",
    )
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    baslangic_tarihi = models.DateField(verbose_name="Başlangıç tarihi")
    program_bitis_tarihi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Program bitiş tarihi",
        help_text="Boş bırakılırsa yetkili durdurana kadar devam eder.",
    )
    son_tamamlama_saati = models.TimeField(
        default="20:00",
        verbose_name="Son tamamlama saati",
    )
    kisi_basina_cuz = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Kişi başına cüz sayısı",
    )
    cuz_dagitim_yontemi = models.CharField(
        max_length=10,
        choices=DagitimYontemi.choices,
        default=DagitimYontemi.OTOMATIK,
        verbose_name="Cüz dağıtım yöntemi",
    )
    tekrar_turu = models.CharField(
        max_length=20,
        choices=Tekrar.choices,
        default=Tekrar.IKI_GUN,
        verbose_name="Tekrarlama",
    )
    tekrar_gun_araligi = models.PositiveSmallIntegerField(
        default=2,
        verbose_name="Özel gün aralığı",
        help_text="“Her N günde bir” için N değeri.",
    )
    cuz_donem_stratejisi = models.CharField(
        max_length=20,
        choices=CuzStrateji.choices,
        default=CuzStrateji.AYNI,
        verbose_name="Dönemler arası cüz stratejisi",
    )
    hafta_sonu_dahil = models.BooleanField(
        default=True,
        verbose_name="Hafta sonlarını dahil et",
    )
    yeni_donem_otomatik = models.BooleanField(
        default=True,
        verbose_name="Yeni dönem otomatik başlasın",
    )
    eksik_aktar = models.BooleanField(
        default=False,
        verbose_name="Eksik okumayı sonraki döneme aktar",
    )
    gecikmis_sakla = models.BooleanField(
        default=True,
        verbose_name="Yeni dönemde önceki eksikleri gecikmiş olarak sakla",
    )
    yarim_son_donem = models.BooleanField(
        default=True,
        verbose_name="Bitiş tarihinde yarım kalan son dönemi oluştur",
    )
    durum = models.CharField(
        max_length=20,
        choices=Durum.choices,
        default=Durum.TASLAK,
        verbose_name="Durum",
    )
    dua_yapildi = models.BooleanField(default=False, verbose_name="Dua yapıldı")
    tamamlanma_zamani = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Tamamlanma zamanı",
    )
    hatirlatma_program_baslangic = models.BooleanField(default=True)
    hatirlatma_yeni_donem = models.BooleanField(default=True)
    hatirlatma_bitis_12h = models.BooleanField(default=True)
    hatirlatma_bitis_2h = models.BooleanField(default=True)
    hatirlatma_sure_gecti = models.BooleanField(default=True)
    hatirlatma_program_tamamlandi = models.BooleanField(default=True)
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_hatimler",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Hatim programı"
        verbose_name_plural = "Hatim programları"
        ordering = ["-baslangic_tarihi", "-id"]

    def __str__(self) -> str:
        return self.ad

    def tekrar_gun_sayisi(self) -> int | None:
        if self.tekrar_turu == self.Tekrar.BIR_KEZ:
            return None
        if self.tekrar_turu == self.Tekrar.GUNLUK:
            return 1
        if self.tekrar_turu == self.Tekrar.IKI_GUN:
            return 2
        if self.tekrar_turu == self.Tekrar.UC_GUN:
            return 3
        if self.tekrar_turu == self.Tekrar.HAFTALIK:
            return 7
        return max(int(self.tekrar_gun_araligi or 1), 1)

    def tekrar_etiketi(self) -> str:
        gun = self.tekrar_gun_sayisi()
        if self.tekrar_turu == self.Tekrar.BIR_KEZ:
            return "Tek seferlik"
        if gun == 1:
            return "Her gün"
        if self.tekrar_turu == self.Tekrar.HAFTALIK:
            return "Haftalık"
        return f"Her {gun} günde bir"

    def clean(self) -> None:
        if (
            self.program_bitis_tarihi
            and self.program_bitis_tarihi < self.baslangic_tarihi
        ):
            raise ValidationError(
                {"program_bitis_tarihi": "Program bitişi başlangıçtan önce olamaz."}
            )
        if self.kisi_basina_cuz < 1 or self.kisi_basina_cuz > 30:
            raise ValidationError(
                {"kisi_basina_cuz": "Kişi başına cüz sayısı 1–30 arasında olmalıdır."}
            )

    @property
    def aktif_mi(self) -> bool:
        return self.durum == self.Durum.AKTIF


class HatimDonemi(models.Model):
    class Durum(models.TextChoices):
        BEKLEMEDE = "pending", "Onay bekliyor"
        AKTIF = "active", "Aktif"
        TAMAMLANDI = "completed", "Tamamlandı"
        ATLANDI = "skipped", "Atlandı"

    program = models.ForeignKey(
        HatimProgrami,
        on_delete=models.CASCADE,
        related_name="donemler",
        verbose_name="Program",
    )
    sira = models.PositiveIntegerField(verbose_name="Dönem sırası")
    baslangic = models.DateTimeField(verbose_name="Başlangıç")
    bitis = models.DateTimeField(verbose_name="Bitiş")
    durum = models.CharField(
        max_length=20,
        choices=Durum.choices,
        default=Durum.AKTIF,
        verbose_name="Durum",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Hatim dönemi"
        verbose_name_plural = "Hatim dönemleri"
        ordering = ["program_id", "sira"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "sira"],
                name="benzersiz_hatim_donem_sira",
            )
        ]

    def __str__(self) -> str:
        return f"{self.program.ad} · Dönem {self.sira}"


class HatimKatilimcisi(models.Model):
    program = models.ForeignKey(
        HatimProgrami,
        on_delete=models.CASCADE,
        related_name="katilimcilar",
        verbose_name="Program",
    )
    personel = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hatim_katilimlari",
        verbose_name="Personel",
    )
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hatim_katilimlari",
        verbose_name="Talebe",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hatim_katilimlari",
        verbose_name="Kullanıcı",
    )
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    varsayilan_cuz_bas = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Varsayılan cüz başlangıç",
    )
    varsayilan_cuz_bit = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Varsayılan cüz bitiş",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Hatim katılımcısı"
        verbose_name_plural = "Hatim katılımcıları"
        ordering = ["sira", "id"]

    def __str__(self) -> str:
        return self.gorunen_ad

    @property
    def gorunen_ad(self) -> str:
        if self.personel_id:
            return self.personel.ad_soyad
        if self.talebe_id:
            return self.talebe.ad_soyad
        if self.user_id:
            return self.user.get_full_name() or self.user.username
        return f"Katılımcı #{self.pk}"


class CuzAtamasi(models.Model):
    class Durum(models.TextChoices):
        BASLANMADI = "baslanmadi", "Başlanmadı"
        OKUNUYOR = "okunuyor", "Okunuyor"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"
        GECIKMIS = "gecikmis", "Gecikmiş"
        MUAF = "muaf", "Muaf"
        DEVREDILDI = "devredildi", "Devredildi"

    donem = models.ForeignKey(
        HatimDonemi,
        on_delete=models.CASCADE,
        related_name="cuz_atamalari",
        verbose_name="Dönem",
    )
    katilimci = models.ForeignKey(
        HatimKatilimcisi,
        on_delete=models.CASCADE,
        related_name="cuz_atamalari",
        verbose_name="Katılımcı",
    )
    cuz_baslangic = models.PositiveSmallIntegerField(verbose_name="Cüz başlangıç")
    cuz_bitis = models.PositiveSmallIntegerField(verbose_name="Cüz bitiş")
    durum = models.CharField(
        max_length=20,
        choices=Durum.choices,
        default=Durum.BASLANMADI,
        verbose_name="Durum",
    )
    baslama_zamani = models.DateTimeField(null=True, blank=True)
    tamamlama_zamani = models.DateTimeField(null=True, blank=True)
    devredilen_katilimci = models.ForeignKey(
        HatimKatilimcisi,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devralinan_cuzler",
        verbose_name="Devredilen katılımcı",
    )
    notlar = models.TextField(blank=True, verbose_name="Notlar")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cüz ataması"
        verbose_name_plural = "Cüz atamaları"
        ordering = ["donem_id", "katilimci__sira", "cuz_baslangic"]

    def __str__(self) -> str:
        return f"{self.katilimci.gorunen_ad}: {self.cuz_etiketi}"

    @property
    def cuz_etiketi(self) -> str:
        if self.cuz_baslangic == self.cuz_bitis:
            return f"{self.cuz_baslangic}. cüz"
        return f"{self.cuz_baslangic}–{self.cuz_bitis}. cüz"

    def cuz_numaralari(self) -> list[int]:
        return list(range(self.cuz_baslangic, self.cuz_bitis + 1))

    def clean(self) -> None:
        if self.cuz_baslangic < 1 or self.cuz_bitis > 30:
            raise ValidationError("Cüz numarası 1–30 arasında olmalıdır.")
        if self.cuz_baslangic > self.cuz_bitis:
            raise ValidationError("Cüz aralığı geçersiz.")


class DonemTamamlamaKaydi(models.Model):
    class Islem(models.TextChoices):
        BASLADI = "basladi", "Okumaya başladı"
        TAMAMLADI = "tamamladi", "Dönemi tamamladı"
        GERI_ALINDI = "geri_alindi", "Geri alındı"
        MUAF = "muaf", "Muaf"
        DEVREDILDI = "devredildi", "Devredildi"
        GECIKMIS = "gecikmis", "Gecikmiş işaretlendi"

    atama = models.ForeignKey(
        CuzAtamasi,
        on_delete=models.CASCADE,
        related_name="kayitlar",
        verbose_name="Atama",
    )
    islem = models.CharField(max_length=20, choices=Islem.choices, verbose_name="İşlem")
    yapan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hatim_kayitlari",
        verbose_name="Yapan",
    )
    zaman = models.DateTimeField(default=timezone.now, verbose_name="Zaman")
    not_metni = models.TextField(blank=True, verbose_name="Not")

    class Meta:
        verbose_name = "Dönem tamamlama kaydı"
        verbose_name_plural = "Dönem tamamlama kayıtları"
        ordering = ["-zaman", "-id"]


class HatimHatirlatmasi(models.Model):
    class Tetik(models.TextChoices):
        PROGRAM_BASLANGIC = "program_baslangic", "Program başladığında"
        YENI_DONEM = "yeni_donem", "Yeni dönem başladığında"
        BITIS_12H = "bitis_12h", "Dönem bitimine 12 saat kala"
        BITIS_2H = "bitis_2h", "Dönem bitimine 2 saat kala"
        SURE_GECTI = "sure_gecti", "Süre geçtiğinde"
        PROGRAM_TAMAMLANDI = "program_tamamlandi", "Hatim tamamlandığında"

    program = models.ForeignKey(
        HatimProgrami,
        on_delete=models.CASCADE,
        related_name="hatirlatmalar",
        verbose_name="Program",
    )
    tetik = models.CharField(max_length=30, choices=Tetik.choices, verbose_name="Tetik")
    donem = models.ForeignKey(
        HatimDonemi,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hatirlatmalar",
        verbose_name="Dönem",
    )
    alici = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hatim_hatirlatmalari",
        verbose_name="Alıcı",
    )
    gonderim_zamani = models.DateTimeField(auto_now_add=True)
    bildirim = models.ForeignKey(
        "Bildirim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hatim_hatirlatmalari",
    )

    class Meta:
        verbose_name = "Hatim hatırlatması"
        verbose_name_plural = "Hatim hatırlatmaları"
        ordering = ["-gonderim_zamani", "-id"]
