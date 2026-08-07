"""Haftalık etüt planı modelleri — Kurum Akış Programından ayrı."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class EtutHaftaPlani(models.Model):
    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        AKTIF = "aktif", "Aktif"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"

    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.CASCADE,
        related_name="haftalik_planlar",
        verbose_name="Etüt hocası",
    )
    hafta_baslangic = models.DateField(verbose_name="Hafta başlangıcı")
    hafta_bitis = models.DateField(verbose_name="Hafta bitişi")
    durum = models.CharField(
        max_length=12,
        choices=Durum.choices,
        default=Durum.AKTIF,
        verbose_name="Durum",
    )
    notlar = models.TextField(blank=True, verbose_name="Haftalık not")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_etut_planlari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Etüt hafta planı"
        verbose_name_plural = "Etüt hafta planları"
        ordering = ["-hafta_baslangic", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["etut_hocasi", "hafta_baslangic"],
                name="etut_hoca_hafta_tek_plan",
            )
        ]

    def __str__(self):
        return f"{self.etut_hocasi.ad_soyad} · {self.hafta_baslangic:%d.%m.%Y}"

    @property
    def hafta_goster(self) -> str:
        return f"{self.hafta_baslangic:%d.%m.%Y} – {self.hafta_bitis:%d.%m.%Y}"

    @property
    def tamamlanan_sayisi(self) -> int:
        return self.faaliyetler.filter(
            uygulama_durumu=EtutPlanFaaliyet.UygulamaDurumu.TAMAMLANDI
        ).count()

    @property
    def toplam_faaliyet(self) -> int:
        return self.faaliyetler.count()


class EtutPlanFaaliyet(models.Model):
    class Gun(models.IntegerChoices):
        PAZARTESI = 0, "Pazartesi"
        SALI = 1, "Salı"
        CARSAMBA = 2, "Çarşamba"
        PERSEMBE = 3, "Perşembe"
        CUMA = 4, "Cuma"
        CUMARTESI = 5, "Cumartesi"
        PAZAR = 6, "Pazar"

    class FaaliyetTuru(models.TextChoices):
        ETUT = "etut", "Etüt çalışması"
        BRANS_DENEME = "brans_deneme", "Branş denemesi"
        KTT = "ktt", "KTT uygulaması"
        KTT_ANALIZ = "ktt_analiz", "KTT analizi"
        DENEME_ANALIZ = "deneme_analiz", "Deneme analizi"
        KITAP_OKUMA = "kitap_okuma", "Kitap okuma"
        KONU_TEKRAR = "konu_tekrar", "Konu tekrarı"
        SORU_COZUM = "soru_cozum", "Soru çözümü"
        AKADEMIK = "akademik", "Akademik müdahale"
        VIDEO = "video", "Video destekli çalışma"

    class UygulamaDurumu(models.TextChoices):
        BEKLIYOR = "bekliyor", "Bekliyor"
        DEVAM = "devam", "Devam ediyor"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"
        YAPILAMADI = "yapilamadi", "Yapılamadı"

    plan = models.ForeignKey(
        EtutHaftaPlani,
        on_delete=models.CASCADE,
        related_name="faaliyetler",
        verbose_name="Plan",
    )
    saat_bloku = models.ForeignKey(
        "EtutGrupSaatBloku",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="plan_faaliyetleri",
        verbose_name="Saat bloğu",
    )
    havuz = models.ForeignKey(
        "EtutFaaliyetHavuzu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_atamalari",
        verbose_name="Havuz kartı",
    )
    gun = models.PositiveSmallIntegerField(
        choices=Gun.choices,
        verbose_name="Gün",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    faaliyet_turu = models.CharField(
        max_length=20,
        choices=FaaliyetTuru.choices,
        default=FaaliyetTuru.ETUT,
        verbose_name="Faaliyet türü",
    )
    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    hedef = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Hedef",
        help_text="Örn. 40 soru, 20 sayfa",
    )
    renk = models.CharField(max_length=20, blank=True, default="#eff6ff", verbose_name="Renk")
    uygulama_durumu = models.CharField(
        max_length=12,
        choices=UygulamaDurumu.choices,
        default=UygulamaDurumu.BEKLIYOR,
        verbose_name="Uygulama durumu",
    )
    tamamlanma_notu = models.TextField(blank=True, verbose_name="Tamamlanma notu")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Etüt plan faaliyeti"
        verbose_name_plural = "Etüt plan faaliyetleri"
        ordering = ["gun", "sira", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "saat_bloku"],
                condition=models.Q(saat_bloku__isnull=False),
                name="etut_plan_saat_tek_faaliyet",
            )
        ]

    def __str__(self):
        return f"{self.get_gun_display()} · {self.baslik}"


class EtutGrupSaatBloku(models.Model):
    """Admin tarafından tanımlanan etüt saat blokları — hocası değiştiremez."""

    class Durum(models.TextChoices):
        AKTIF = "aktif", "Aktif"
        PASIF = "pasif", "Pasif"
        IZINLI = "izinli", "İzinli"

    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.CASCADE,
        related_name="etut_saat_bloklari",
        verbose_name="Etüt hocası / grup",
    )
    gun = models.PositiveSmallIntegerField(
        choices=EtutPlanFaaliyet.Gun.choices,
        verbose_name="Gün",
    )
    baslangic_saati = models.TimeField(verbose_name="Başlangıç")
    bitis_saati = models.TimeField(verbose_name="Bitiş")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    durum = models.CharField(
        max_length=8,
        choices=Durum.choices,
        default=Durum.AKTIF,
        verbose_name="Durum",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Etüt saat bloğu"
        verbose_name_plural = "Etüt saat blokları"
        ordering = ["etut_hocasi", "gun", "sira", "baslangic_saati"]
        constraints = [
            models.UniqueConstraint(
                fields=["etut_hocasi", "gun", "baslangic_saati"],
                name="etut_saat_blok_tek",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.etut_hocasi.ad_soyad} · {self.get_gun_display()} "
            f"{self.baslangic_saati:%H:%M}-{self.bitis_saati:%H:%M}"
        )

    @property
    def saat_goster(self) -> str:
        return f"{self.baslangic_saati:%H:%M} – {self.bitis_saati:%H:%M}"


class EtutFaaliyetHavuzu(models.Model):
    """Hazır etkinlik kartları — admin havuzu + hocanın özel kartları."""

    baslik = models.CharField(max_length=120, verbose_name="Başlık")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    varsayilan_hedef = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Varsayılan hedef",
    )
    renk = models.CharField(max_length=20, default="#eff6ff", verbose_name="Renk")
    ikon = models.CharField(max_length=8, blank=True, verbose_name="İkon")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    ozel = models.BooleanField(
        default=False,
        verbose_name="Hocaya özel",
        help_text="True ise yalnızca ilgili hocanın havuzunda görünür.",
    )
    etut_hocasi = models.ForeignKey(
        "EtutHocasi",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ozel_faaliyet_havuzu",
        verbose_name="Etüt hocası",
    )
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_etut_havuz_kartlari",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Etüt faaliyet havuzu"
        verbose_name_plural = "Etüt faaliyet havuzu"
        ordering = ["sira", "baslik"]

    def __str__(self) -> str:
        return self.baslik
