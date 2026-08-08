"""Personel toplantıları — tutanak, karar, yapılacak ve takip."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class PersonelToplantisi(models.Model):
    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"

    toplanti_no = models.CharField(max_length=32, unique=True, verbose_name="Toplantı no")
    baslik = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Alt başlık",
        help_text="İsteğe bağlı; raporda Personel Toplantısı altında görünür.",
    )
    tarih = models.DateField(verbose_name="Tarih")
    saat = models.TimeField(null=True, blank=True, verbose_name="Saat")
    yer = models.CharField(max_length=200, blank=True, verbose_name="Yer")
    katilimcilar_metin = models.TextField(
        blank=True,
        verbose_name="Katılımcılar (eski)",
        help_text="Kullanımdan kalktı; katılımcı seçimi kullanın.",
    )
    katilimci_personeller = models.ManyToManyField(
        "PersonelProfili",
        blank=True,
        related_name="katildigi_personel_toplantilari",
        verbose_name="Katılımcılar",
    )
    gundem_ozet = models.TextField(blank=True, verbose_name="Gündem özeti")
    gizli_notlar = models.TextField(
        blank=True,
        verbose_name="Sekreter / gizli notlar",
        help_text="Yalnızca yönetim ekranında görünür; PDF'e dahil edilmez.",
    )
    genel_degerlendirme = models.TextField(blank=True, verbose_name="Genel değerlendirme")
    durum = models.CharField(
        max_length=16,
        choices=Durum.choices,
        default=Durum.TASLAK,
        verbose_name="Durum",
    )
    baskan = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="baskanlik_ettigi_toplantilar",
        verbose_name="Toplantı başkanı",
    )
    sekreter = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sekreterlik_ettigi_toplantilar",
        verbose_name="Sekreter",
    )
    tutanak_pdf = models.FileField(
        upload_to="personel_toplanti/tutanaklar/",
        blank=True,
        null=True,
        verbose_name="Tutanak PDF",
    )
    arsivlandi = models.BooleanField(default=False, verbose_name="Arşivlendi")
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_personel_toplantilari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Personel toplantısı"
        verbose_name_plural = "Personel toplantıları"
        ordering = ["-tarih", "-id"]

    def __str__(self) -> str:
        ad = (self.baslik or "").strip() or "Personel Toplantısı"
        return f"{self.toplanti_no} — {ad}"


class PersonelToplantiGundemMadde(models.Model):
    """Toplantıda madde madde görüşülen gündem kayıtları."""

    toplanti = models.ForeignKey(
        PersonelToplantisi,
        on_delete=models.CASCADE,
        related_name="gundem_maddeleri",
        verbose_name="Toplantı",
    )
    sira = models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")
    madde = models.CharField(max_length=300, verbose_name="Gündem maddesi")
    gorusulen = models.TextField(
        blank=True,
        verbose_name="Görüşülen / konuşulanlar",
        help_text="Toplantıda bu madde hakkında konuşulanlar.",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Gündem maddesi"
        verbose_name_plural = "Gündem maddeleri"
        ordering = ["sira", "id"]

    def __str__(self) -> str:
        return f"{self.toplanti.toplanti_no} · {self.madde[:40]}"


class PersonelToplantiKarar(models.Model):
    class Tur(models.TextChoices):
        KARAR = "karar", "Karar"
        YAPILACAK = "yapilacak", "Yapılacak"
        TAKIP = "takip", "Takip edilecek"

    class Durum(models.TextChoices):
        BEKLIYOR = "bekliyor", "Bekliyor"
        DEVAM = "devam", "Devam ediyor"
        TAMAM = "tamam", "Tamamlandı"
        IPTAL = "iptal", "İptal"

    toplanti = models.ForeignKey(
        PersonelToplantisi,
        on_delete=models.CASCADE,
        related_name="kararlar",
        verbose_name="Toplantı",
    )
    sira = models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")
    tur = models.CharField(
        max_length=12,
        choices=Tur.choices,
        default=Tur.KARAR,
        verbose_name="Tür",
    )
    metin = models.TextField(verbose_name="Metin")
    sorumlu = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="toplanti_kararlari",
        verbose_name="Sorumlu personel",
    )
    kontrol_tarihi = models.DateField(null=True, blank=True, verbose_name="Takip / son tarih")
    durum = models.CharField(
        max_length=12,
        choices=Durum.choices,
        default=Durum.BEKLIYOR,
        verbose_name="Durum",
    )
    vazife = models.ForeignKey(
        "PersonelVazife",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="toplanti_kaynaklari",
        verbose_name="Oluşan vazife",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Toplantı kararı"
        verbose_name_plural = "Toplantı kararları"
        ordering = ["sira", "id"]

    def __str__(self) -> str:
        return f"{self.toplanti.toplanti_no} · {self.get_tur_display()}"

    @property
    def vazife_gerekli_mi(self) -> bool:
        return (
            self.sorumlu_id is not None
            and self.tur in {self.Tur.YAPILACAK, self.Tur.TAKIP}
            and self.durum not in {self.Durum.IPTAL, self.Durum.TAMAM}
        )
