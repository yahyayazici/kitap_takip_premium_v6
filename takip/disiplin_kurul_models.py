"""Disiplin Kurulu — kurul oturumu, katılımcı, gündem, karar ve takip modelleri."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class DisiplinKurulu(models.Model):
    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        ACILDI = "acildi", "Kurul Açıldı"
        TOPLANTI = "toplanti", "Toplantı Yapıldı"
        KARARLAR = "kararlar", "Kararlar Belirlendi"
        UYGULAMA = "uygulama", "Uygulama Süreci"
        KONTROL = "kontrol", "Kontrol Toplantısı"
        SONUCLANDI = "sonuclandi", "Sonuçlandırıldı"

    class KurulTuru(models.TextChoices):
        ISTISARE_DISIPLIN = "istisare_disiplin", "İstişare ve Disiplin Kurulu"
        DISIPLIN = "disiplin", "Disiplin Kurulu"
        DEGERLENDIRME = "degerlendirme", "Değerlendirme Kurulu"
        AKADEMIK = "akademik", "Akademik Kurul"
        REHBERLIK = "rehberlik", "Rehberlik Kurulu"

    KURUL_ADI = "İstişare ve Disiplin Kurulu"

    kurul_no = models.CharField(max_length=32, unique=True, verbose_name="Kurul no")
    talebe = models.ForeignKey(
        "Talebe",
        on_delete=models.PROTECT,
        related_name="disiplin_kurullari",
        verbose_name="Talebe",
    )
    kurul_turu = models.CharField(
        max_length=24,
        choices=KurulTuru.choices,
        default=KurulTuru.ISTISARE_DISIPLIN,
        verbose_name="Kurul türü",
    )
    durum = models.CharField(
        max_length=16,
        choices=Durum.choices,
        default=Durum.TASLAK,
        verbose_name="Durum",
    )
    toplanti_tarihi = models.DateField(null=True, blank=True, verbose_name="Toplantı tarihi")
    toplanti_saati = models.TimeField(null=True, blank=True, verbose_name="Toplantı saati")
    toplanti_yeri = models.CharField(max_length=200, blank=True, verbose_name="Toplantı yeri")
    oturum_baskani = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="baskanlik_ettigi_kurullar",
        verbose_name="Oturum başkanı",
    )
    raportor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="raportorluk_ettigi_kurullar",
        verbose_name="Raportör",
    )
    genel_aciklama = models.TextField(blank=True, verbose_name="Genel açıklama")
    genel_degerlendirme = models.TextField(blank=True, verbose_name="Genel değerlendirme")
    sonuc_metni = models.TextField(blank=True, verbose_name="Sonuç")
    sonraki_kontrol_tarihi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Sonraki kontrol tarihi",
    )
    tutanak_pdf = models.FileField(
        upload_to="disiplin_kurul/tutanaklar/",
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
        related_name="olusturdugu_disiplin_kurullari",
        verbose_name="Oluşturan",
    )
    son_duzenleyen = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duzenledigi_disiplin_kurullari",
        verbose_name="Son düzenleyen",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Disiplin kurulu"
        verbose_name_plural = "Disiplin kurulları"
        ordering = ["-toplanti_tarihi", "-id"]

    def __str__(self) -> str:
        return f"{self.kurul_no} — {self.talebe.ad_soyad}"

    @property
    def aktif_mi(self) -> bool:
        return self.durum not in {
            self.Durum.SONUCLANDI,
            self.Durum.TASLAK,
        } and not self.arsivlandi

    @property
    def karar_sayisi(self) -> int:
        return self.kararlar.filter(arsivlandi=False).count()


class DisiplinKurulKatilimci(models.Model):
    class KurulGorevi(models.TextChoices):
        BASKAN = "baskan", "Kurul Başkanı"
        RAPORTOR = "raportor", "Raportör"
        UYE = "uye", "Kurul Üyesi"
        DANISMAN = "danisman", "Danışman"
        GOZLEMCI = "gozlemci", "Gözlemci"

    kurul = models.ForeignKey(
        DisiplinKurulu,
        on_delete=models.CASCADE,
        related_name="katilimcilar",
        verbose_name="Kurul",
    )
    personel = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.PROTECT,
        related_name="disiplin_kurul_katilimlari",
        verbose_name="Personel",
    )
    kurum_gorevi = models.CharField(max_length=120, blank=True, verbose_name="Kurumdaki görevi")
    kurul_gorevi = models.CharField(
        max_length=16,
        choices=KurulGorevi.choices,
        default=KurulGorevi.UYE,
        verbose_name="Kuruldaki görevi",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        verbose_name = "Kurul katılımcısı"
        verbose_name_plural = "Kurul katılımcıları"
        ordering = ["sira", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["kurul", "personel"],
                name="disiplin_kurul_katilimci_tek",
            )
        ]

    def __str__(self) -> str:
        return f"{self.personel.ad_soyad} ({self.get_kurul_gorevi_display()})"


class DisiplinKurulGundem(models.Model):
    class MaddeDurum(models.TextChoices):
        BEKLIYOR = "bekliyor", "Bekliyor"
        GORULDU = "goruldu", "Görüşüldü"

    kurul = models.ForeignKey(
        DisiplinKurulu,
        on_delete=models.CASCADE,
        related_name="gundem_maddeleri",
        verbose_name="Kurul",
    )
    sira = models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")
    baslik = models.CharField(max_length=240, verbose_name="Madde")
    durum = models.CharField(
        max_length=12,
        choices=MaddeDurum.choices,
        default=MaddeDurum.BEKLIYOR,
        verbose_name="Durum",
    )

    class Meta:
        verbose_name = "Gündem maddesi"
        verbose_name_plural = "Gündem maddeleri"
        ordering = ["sira", "id"]

    def __str__(self) -> str:
        return f"{self.sira:02d} {self.baslik}"


class DisiplinKurulKarar(models.Model):
    class Kategori(models.TextChoices):
        AKADEMIK = "akademik", "Akademik"
        DAVRANIS = "davranis", "Davranış"
        DINI = "dini", "Dini Eğitim"
        REHBERLIK = "rehberlik", "Rehberlik"
        DISIPLIN = "disiplin", "Disiplin"
        YOKLAMA = "yoklama", "Yoklama"
        VELI = "veli", "Veli Görüşmesi"

    class Durum(models.TextChoices):
        BEKLIYOR = "bekliyor", "Bekliyor"
        UYGULANIYOR = "uygulaniyor", "Uygulanıyor"
        KONTROL = "kontrol", "Kontrol Bekliyor"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"
        GECIKTI = "gecikti", "Gecikti"

    class IliskiliModul(models.TextChoices):
        YOK = "yok", "Bağlantı Yok"
        AKADEMIK = "akademik_takip", "Akademik Takip"
        REHBERLIK = "rehberlik", "Rehberlik"
        DINI = "dini_ders", "Dini Ders"
        YOKLAMA = "yoklama", "Yoklama"
        GOREV = "gorevler", "Görevler"

    karar_no = models.CharField(max_length=40, unique=True, verbose_name="Karar no")
    kurul = models.ForeignKey(
        DisiplinKurulu,
        on_delete=models.CASCADE,
        related_name="kararlar",
        verbose_name="Kurul",
    )
    metin = models.TextField(verbose_name="Karar metni")
    kategori = models.CharField(
        max_length=16,
        choices=Kategori.choices,
        default=Kategori.DISIPLIN,
        verbose_name="Kategori",
    )
    sorumlu = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sorumlu_oldugu_kurul_kararlari",
        verbose_name="Sorumlu personel",
    )
    baslangic_tarihi = models.DateField(null=True, blank=True, verbose_name="Başlangıç")
    kontrol_tarihi = models.DateField(null=True, blank=True, verbose_name="Kontrol tarihi")
    durum = models.CharField(
        max_length=16,
        choices=Durum.choices,
        default=Durum.BEKLIYOR,
        verbose_name="Durum",
    )
    iliskili_modul = models.CharField(
        max_length=20,
        choices=IliskiliModul.choices,
        default=IliskiliModul.YOK,
        verbose_name="İlişkili modül",
    )
    iliskili_kayit_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="İlişkili kayıt ID",
    )
    notlar = models.TextField(blank=True, verbose_name="Notlar")
    arsivlandi = models.BooleanField(default=False, verbose_name="Arşivlendi")
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olusturdugu_kurul_kararlari",
        verbose_name="Oluşturan",
    )
    son_duzenleyen = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duzenledigi_kurul_kararlari",
        verbose_name="Son düzenleyen",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Kurul kararı"
        verbose_name_plural = "Kurul kararları"
        ordering = ["karar_no"]

    def __str__(self) -> str:
        return self.karar_no

    def clean(self):
        super().clean()
        if self.kontrol_tarihi and self.baslangic_tarihi:
            if self.kontrol_tarihi < self.baslangic_tarihi:
                raise ValidationError(
                    {"kontrol_tarihi": "Kontrol tarihi başlangıçtan önce olamaz."}
                )

    @property
    def gecikti_mi(self) -> bool:
        if self.durum in {self.Durum.TAMAMLANDI, self.Durum.GECIKTI}:
            return self.durum == self.Durum.GECIKTI
        if not self.kontrol_tarihi:
            return False
        return self.kontrol_tarihi < timezone.localdate() and self.durum != self.Durum.TAMAMLANDI

    @property
    def uyari_gerekli_mi(self) -> bool:
        if not self.kontrol_tarihi or self.durum == self.Durum.TAMAMLANDI:
            return False
        kalan = (self.kontrol_tarihi - timezone.localdate()).days
        return 0 <= kalan <= 2


class DisiplinKurulKararNot(models.Model):
    karar = models.ForeignKey(
        DisiplinKurulKarar,
        on_delete=models.CASCADE,
        related_name="takip_notlari",
        verbose_name="Karar",
    )
    yazar = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kurul_karar_notlari",
        verbose_name="Yazar",
    )
    metin = models.TextField(verbose_name="Not")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Karar takip notu"
        verbose_name_plural = "Karar takip notları"
        ordering = ["-olusturulma"]


class DisiplinKurulKararTakip(models.Model):
    class Adim(models.TextChoices):
        OLUSTURULDU = "olusturuldu", "Karar oluşturuldu"
        PERSONEL = "personel", "Personel atandı"
        NOT = "not", "Not eklendi"
        KONTROL = "kontrol", "Kontrol edildi"
        TAMAMLANDI = "tamamlandi", "Tamamlandı"

    karar = models.ForeignKey(
        DisiplinKurulKarar,
        on_delete=models.CASCADE,
        related_name="takip_adimlari",
        verbose_name="Karar",
    )
    adim = models.CharField(max_length=16, choices=Adim.choices, verbose_name="Adım")
    aciklama = models.CharField(max_length=240, blank=True, verbose_name="Açıklama")
    kullanici = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kurul_karar_takip_adimlari",
        verbose_name="Kullanıcı",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Karar takip adımı"
        verbose_name_plural = "Karar takip adımları"
        ordering = ["olusturulma", "id"]


class DisiplinKurulAyar(models.Model):
    """Kurum geneli İstişare ve Disiplin Kurulu ayarları."""

    kurul_adi = models.CharField(
        max_length=160,
        default=DisiplinKurulu.KURUL_ADI,
        verbose_name="Kurul adı",
    )
    varsayilan_toplanti_yeri = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Varsayılan toplantı yeri",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Kurul ayarı"
        verbose_name_plural = "Kurul ayarları"

    def __str__(self) -> str:
        return self.kurul_adi

    @classmethod
    def aktif(cls) -> DisiplinKurulAyar:
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={"kurul_adi": DisiplinKurulu.KURUL_ADI},
        )
        return obj


class DisiplinKurulVarsayilanUye(models.Model):
    """Admin tarafından tanımlanan varsayılan kurul üyeleri."""

    personel = models.ForeignKey(
        "PersonelProfili",
        on_delete=models.CASCADE,
        related_name="varsayilan_kurul_uyelikleri",
        verbose_name="Personel",
    )
    kurul_gorevi = models.CharField(
        max_length=16,
        choices=DisiplinKurulKatilimci.KurulGorevi.choices,
        default=DisiplinKurulKatilimci.KurulGorevi.UYE,
        verbose_name="Kuruldaki görevi",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Varsayılan kurul üyesi"
        verbose_name_plural = "Varsayılan kurul üyeleri"
        ordering = ["sira", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["personel"],
                name="disiplin_kurul_varsayilan_uye_tek",
            )
        ]

    def __str__(self) -> str:
        return f"{self.personel.ad_soyad} · {self.get_kurul_gorevi_display()}"


class DisiplinKurulVarsayilanGundem(models.Model):
    """Admin tarafından tanımlanan varsayılan gündem maddeleri."""

    baslik = models.CharField(max_length=240, verbose_name="Madde")
    sira = models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Varsayılan gündem maddesi"
        verbose_name_plural = "Varsayılan gündem maddeleri"
        ordering = ["sira", "id"]

    def __str__(self) -> str:
        return self.baslik
