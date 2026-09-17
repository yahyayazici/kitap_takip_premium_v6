"""Dijital Duyuru Ekranı — veri modeli.

Kurumun katlarındaki televizyonlarda yayın yapan modül. Tasarım stüdyosunda
hazırlanan sahneler, oynatma listelerinde toplanır; yayın planları bu
listeleri belirli cihaz/kat/tarih hedeflerine gönderir.

Koordinat sistemi
-----------------
Öğe konum ve ölçüleri **tasarım uzayında** (varsayılan 1920×1080) float
olarak saklanır. Televizyon tarafı bu uzayı kendi çözünürlüğüne
``transform: scale()`` ile oranlar; böylece 1366×768, 1920×1080 ve 4K aynı
veriyle bozulmadan çalışır. Tuval ölçüsü proje bazında tutulduğu için
ileride dikey (1080×1920) ekran desteği veri modelini değiştirmeden eklenir.

JSON kullanımı
--------------
Yalnız *sunuma ait* serbest biçimli ayarlar (stil, animasyon, tipografi)
JSON alanlarda tutulur. İlişkisel olarak sorgulanması gereken her şey —
hangi tasarım hangi medyayı kullanıyor, hangi plan hangi cihaza gidiyor —
gerçek ForeignKey'dir.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from takip.ekran_storage import ekran_depolama

# Tasarım uzayı varsayılanı — tüm koordinatlar bu referansa göredir.
TUVAL_GENISLIK = 1920
TUVAL_YUKSEKLIK = 1080

# Cihaz eşleştirme kodunun geçerlilik süresi.
ESLESTIRME_KODU_DAKIKA = 15

# Karıştırılması kolay karakterler (0/O, 1/I) dışarıda bırakıldı.
_KOD_ALFABESI = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def eslestirme_kodu_uret(uzunluk: int = 6) -> str:
    return "".join(secrets.choice(_KOD_ALFABESI) for _ in range(uzunluk))


def cihaz_anahtari_uret() -> str:
    return secrets.token_urlsafe(32)


class EkranZamanDamgali(models.Model):
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_olusturdu",
        verbose_name="Oluşturan",
    )
    son_duzenleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_duzenledi",
        verbose_name="Son düzenleyen",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Konum ve cihaz
# ---------------------------------------------------------------------------


class EkranKonumu(models.Model):
    """Kat / ortak alan. Yayınlar kat bazında hedeflenebilsin diye ayrı model."""

    ad = models.CharField(max_length=120, verbose_name="Konum adı")
    aciklama = models.CharField(max_length=255, blank=True, verbose_name="Açıklama")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Ekran konumu"
        verbose_name_plural = "Ekran konumları"
        ordering = ["sira", "ad"]
        constraints = [
            models.UniqueConstraint(fields=["ad"], name="benzersiz_ekran_konumu"),
        ]

    def __str__(self) -> str:
        return self.ad


class EkranCihaz(models.Model):
    """Bir televizyon / görüntüleyici.

    Cihaz ilk açıldığında kendini kaydeder: sunucu gizli bir ``cihaz_anahtari``
    ve kısa ömürlü bir ``eslestirme_kodu`` üretir. Yönetici kodu panele
    girince cihaz kuruma bağlanır. Anahtar cihazın tarayıcısında saklanır ve
    her istekte kimlik olarak kullanılır; kod tek kullanımlıktır.
    """

    class Yonelim(models.TextChoices):
        YATAY = "yatay", "Yatay"
        DIKEY = "dikey", "Dikey"

    class Durum(models.TextChoices):
        BEKLIYOR = "bekliyor", "Eşleştirme bekliyor"
        AKTIF = "aktif", "Aktif"
        PASIF = "pasif", "Pasif"

    ad = models.CharField(max_length=120, blank=True, verbose_name="Ekran adı")
    konum = models.ForeignKey(
        EkranKonumu,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cihazlar",
        verbose_name="Konum / kat",
    )
    cihaz_anahtari = models.CharField(
        max_length=64,
        unique=True,
        default=cihaz_anahtari_uret,
        editable=False,
        verbose_name="Cihaz anahtarı",
    )
    eslestirme_kodu = models.CharField(
        max_length=12,
        blank=True,
        db_index=True,
        verbose_name="Eşleştirme kodu",
    )
    eslestirme_kodu_bitis = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Kod geçerlilik bitişi",
    )
    durum = models.CharField(
        max_length=12,
        choices=Durum.choices,
        default=Durum.BEKLIYOR,
        db_index=True,
        verbose_name="Durum",
    )
    eslestiren = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eslestirdigi_ekranlar",
        verbose_name="Eşleştiren",
    )
    eslestirme_zamani = models.DateTimeField(null=True, blank=True, verbose_name="Eşleştirme zamanı")

    cozunurluk_genislik = models.PositiveIntegerField(default=0, verbose_name="Çözünürlük (genişlik)")
    cozunurluk_yukseklik = models.PositiveIntegerField(default=0, verbose_name="Çözünürlük (yükseklik)")
    yonelim = models.CharField(
        max_length=10,
        choices=Yonelim.choices,
        default=Yonelim.YATAY,
        verbose_name="Yönelim",
    )

    son_baglanti = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Son bağlantı")
    son_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="Son IP")
    tarayici = models.CharField(max_length=255, blank=True, verbose_name="Tarayıcı")
    uygulama_surumu = models.CharField(max_length=40, blank=True, verbose_name="Uygulama sürümü")

    aktif_sahne = models.ForeignKey(
        "EkranSahne",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="oynatan_cihazlar",
        verbose_name="Yayındaki sahne",
    )
    son_yayin_damgasi = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Son alınan yayın damgası",
    )
    son_basarili_guncelleme = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Son başarılı içerik güncellemesi",
    )
    yeniden_yukle_istegi = models.BooleanField(
        default=False,
        verbose_name="Yeniden yükleme istendi",
    )

    notlar = models.TextField(blank=True, verbose_name="Notlar")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    # Bu süre boyunca haber alınamazsa cihaz çevrim dışı sayılır.
    CEVRIMDISI_ESIK_SANIYE = 90

    class Meta:
        verbose_name = "Ekran cihazı"
        verbose_name_plural = "Ekran cihazları"
        ordering = ["konum__sira", "konum__ad", "ad"]
        indexes = [
            models.Index(fields=["durum", "son_baglanti"], name="ekran_cihaz_durum_idx"),
        ]

    def __str__(self) -> str:
        return self.ad or f"Eşleşmemiş ekran #{self.pk}"

    @property
    def gorunen_ad(self) -> str:
        if self.ad:
            return self.ad
        return f"Eşleşmemiş ekran #{self.pk}"

    @property
    def cevrimici_mi(self) -> bool:
        if not self.son_baglanti:
            return False
        gecen = (timezone.now() - self.son_baglanti).total_seconds()
        return gecen <= self.CEVRIMDISI_ESIK_SANIYE

    @property
    def kod_gecerli_mi(self) -> bool:
        if not self.eslestirme_kodu or not self.eslestirme_kodu_bitis:
            return False
        return timezone.now() < self.eslestirme_kodu_bitis

    def yeni_eslestirme_kodu(self, kaydet: bool = True) -> str:
        """Çakışmayan, süreli ve tek kullanımlık kod üretir."""
        for _ in range(40):
            kod = eslestirme_kodu_uret()
            cakisma = (
                EkranCihaz.objects.filter(
                    eslestirme_kodu=kod,
                    eslestirme_kodu_bitis__gt=timezone.now(),
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if not cakisma:
                break
        else:  # pragma: no cover — 32^6 alanda pratikte ulaşılmaz
            kod = eslestirme_kodu_uret(8)

        self.eslestirme_kodu = kod
        self.eslestirme_kodu_bitis = timezone.now() + timedelta(minutes=ESLESTIRME_KODU_DAKIKA)
        if kaydet:
            self.save(update_fields=["eslestirme_kodu", "eslestirme_kodu_bitis", "guncellenme"])
        return kod


class EkranCihazOlayi(models.Model):
    """Cihaz durum *değişikliklerini* kaydeder.

    Nabız her 10 saniyede bir gelir; her nabzı satır olarak yazmak 256 MB'lık
    veritabanını kısa sürede doldururdu. Bu yüzden düzenli nabız yalnız
    ``EkranCihaz.son_baglanti`` alanını günceller (tek UPDATE), buraya ise
    sadece anlamlı olaylar yazılır: çevrim içi/dışı geçişi, yeni yayın alımı,
    oynatma hatası.
    """

    class Tur(models.TextChoices):
        CEVRIMICI = "cevrimici", "Çevrim içi oldu"
        CEVRIMDISI = "cevrimdisi", "Çevrim dışı kaldı"
        YAYIN_ALINDI = "yayin_alindi", "Yayın alındı"
        HATA = "hata", "Hata"
        ESLESTIRILDI = "eslestirildi", "Eşleştirildi"
        YENIDEN_YUKLENDI = "yeniden_yuklendi", "Yeniden yüklendi"

    cihaz = models.ForeignKey(
        EkranCihaz,
        on_delete=models.CASCADE,
        related_name="olaylar",
        verbose_name="Cihaz",
    )
    tur = models.CharField(max_length=20, choices=Tur.choices, verbose_name="Olay")
    mesaj = models.CharField(max_length=400, blank=True, verbose_name="Mesaj")
    yayin_damgasi = models.CharField(max_length=64, blank=True, verbose_name="Yayın damgası")
    zaman = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Ekran cihaz olayı"
        verbose_name_plural = "Ekran cihaz olayları"
        ordering = ["-zaman"]
        indexes = [
            models.Index(fields=["cihaz", "-zaman"], name="ekran_olay_cihaz_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.cihaz} — {self.get_tur_display()}"


# ---------------------------------------------------------------------------
# Medya kütüphanesi
# ---------------------------------------------------------------------------


class EkranMedyaKlasoru(models.Model):
    ad = models.CharField(max_length=120, verbose_name="Klasör adı")
    ust = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alt_klasorler",
        verbose_name="Üst klasör",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ekran_medya_klasorleri",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ekran medya klasörü"
        verbose_name_plural = "Ekran medya klasörleri"
        ordering = ["sira", "ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["ust", "ad"],
                name="benzersiz_ekran_medya_klasoru",
            ),
        ]

    def __str__(self) -> str:
        return self.ad

    @property
    def tam_yol(self) -> str:
        parcalar = [self.ad]
        ust = self.ust
        derinlik = 0
        while ust is not None and derinlik < 10:
            parcalar.append(ust.ad)
            ust = ust.ust
            derinlik += 1
        return " / ".join(reversed(parcalar))


class EkranMedya(models.Model):
    """Yüklenen PDF, görsel ve videolar.

    ``sha256`` benzersizdir: aynı dosya ikinci kez yüklenmek istendiğinde
    servis katmanı mevcut kaydı döndürür, disk ikinci kopyayı tutmaz.
    """

    class Tur(models.TextChoices):
        GORSEL = "gorsel", "Görsel"
        PDF = "pdf", "PDF"
        VIDEO = "video", "Video"

    class IslemDurumu(models.TextChoices):
        HAZIR = "hazir", "Hazır"
        ISLENIYOR = "isleniyor", "İşleniyor"
        HATA = "hata", "Hata"

    ad = models.CharField(max_length=200, verbose_name="Ad")
    orijinal_ad = models.CharField(max_length=255, blank=True, verbose_name="Orijinal dosya adı")
    tur = models.CharField(max_length=10, choices=Tur.choices, db_index=True, verbose_name="Tür")
    dosya = models.FileField(
        upload_to="ekran/medya/%Y/%m/",
        storage=ekran_depolama,
        verbose_name="Dosya",
    )
    onizleme = models.ImageField(
        upload_to="ekran/onizleme/%Y/%m/",
        storage=ekran_depolama,
        blank=True,
        null=True,
        verbose_name="Küçük ön izleme",
    )
    klasor = models.ForeignKey(
        EkranMedyaKlasoru,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medyalar",
        verbose_name="Klasör",
    )

    sha256 = models.CharField(max_length=64, unique=True, editable=False, verbose_name="İçerik özeti")
    boyut = models.BigIntegerField(default=0, verbose_name="Boyut (bayt)")
    mime = models.CharField(max_length=120, blank=True, verbose_name="MIME türü")
    genislik = models.PositiveIntegerField(default=0, verbose_name="Genişlik")
    yukseklik = models.PositiveIntegerField(default=0, verbose_name="Yükseklik")
    sure_sn = models.FloatField(default=0, verbose_name="Süre (sn)")
    sayfa_sayisi = models.PositiveIntegerField(default=0, verbose_name="Sayfa sayısı")

    islem_durumu = models.CharField(
        max_length=12,
        choices=IslemDurumu.choices,
        default=IslemDurumu.HAZIR,
        verbose_name="İşlem durumu",
    )
    islem_notu = models.CharField(max_length=400, blank=True, verbose_name="İşlem notu")

    yukleyen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="yukledigi_ekran_medyalari",
        verbose_name="Yükleyen",
    )
    olusturulma = models.DateTimeField(auto_now_add=True, db_index=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ekran medyası"
        verbose_name_plural = "Ekran medyaları"
        ordering = ["-olusturulma"]
        indexes = [
            models.Index(fields=["tur", "-olusturulma"], name="ekran_medya_tur_idx"),
        ]

    def __str__(self) -> str:
        return self.ad

    @property
    def boyut_okunabilir(self) -> str:
        boyut = float(self.boyut or 0)
        for birim in ("B", "KB", "MB", "GB"):
            if boyut < 1024 or birim == "GB":
                if birim == "B":
                    return f"{int(boyut)} B"
                return f"{boyut:.1f} {birim}"
            boyut /= 1024
        return f"{boyut:.1f} GB"

    @property
    def onizleme_url(self) -> str:
        if self.onizleme:
            return self.onizleme.url
        if self.tur == self.Tur.GORSEL and self.dosya:
            return self.dosya.url
        return ""

    def kullanim_sayisi(self) -> int:
        """Kaç tasarım öğesinde kullanıldığı — silme korumasının dayanağı."""
        return self.ogeler.count() + self.oge_kaynaklari.count()


class EkranMedyaSayfasi(models.Model):
    """PDF'in sunucuda görselleştirilmiş tek sayfası.

    Televizyonun PDF motoru çalıştırması gerekmez: sayfalar hazır PNG olarak
    servis edilir. Bu hem uzun süreli kararlılık hem de çevrim dışı önbellek
    için gereklidir.
    """

    medya = models.ForeignKey(
        EkranMedya,
        on_delete=models.CASCADE,
        related_name="sayfalar",
        verbose_name="PDF",
    )
    sira = models.PositiveIntegerField(default=0, verbose_name="Sayfa no")
    gorsel = models.ImageField(
        upload_to="ekran/pdf/%Y/%m/",
        storage=ekran_depolama,
        verbose_name="Sayfa görseli",
    )
    genislik = models.PositiveIntegerField(default=0)
    yukseklik = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "PDF sayfası"
        verbose_name_plural = "PDF sayfaları"
        ordering = ["medya_id", "sira"]
        constraints = [
            models.UniqueConstraint(fields=["medya", "sira"], name="benzersiz_ekran_pdf_sayfasi"),
        ]

    def __str__(self) -> str:
        return f"{self.medya.ad} — sayfa {self.sira + 1}"


# ---------------------------------------------------------------------------
# Tasarım: proje → sahne → öğe
# ---------------------------------------------------------------------------


class OgeTuru(models.TextChoices):
    """Tuvale eklenebilen öğe türleri.

    Yeni tür eklemek için: buraya bir satır, ``ekran_oge_katalogu`` içine bir
    tanım ve render motoruna (``static/ekran/js/engine.js``) bir çizici.
    Veri modeli değişmez.
    """

    PDF = "pdf", "PDF"
    GORSEL = "gorsel", "Görsel / afiş"
    VIDEO = "video", "Video"
    METIN = "metin", "Metin / slogan"
    GERI_SAYIM = "geri_sayim", "Geri sayım"
    SAAT = "saat", "Saat ve tarih"
    KAYAN_BANT = "kayan_bant", "Kayan duyuru bandı"
    LOGO = "logo", "Kurum logosu"
    QR = "qr", "QR kod"
    SEKIL = "sekil", "Şekil / renk bloğu"
    CIZGI = "cizgi", "Çizgi / ayırıcı"
    GUNLUK_PROGRAM = "gunluk_program", "Günlük program"
    YEMEK_LISTESI = "yemek_listesi", "Yemek listesi"
    SINAV_DUYURUSU = "sinav_duyurusu", "Sınav duyurusu"
    NAMAZ_VAKITLERI = "namaz_vakitleri", "Namaz vakitleri"
    BILGI_KUTUSU = "bilgi_kutusu", "Bilgi kutusu"


class EkranProje(EkranZamanDamgali):
    """Bir ekran tasarımı. Bir veya daha çok sahne içerir."""

    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        YAYINDA = "yayinda", "Yayında"
        ARSIV = "arsiv", "Arşiv"

    ad = models.CharField(max_length=160, verbose_name="Tasarım adı")
    aciklama = models.CharField(max_length=400, blank=True, verbose_name="Açıklama")
    tuval_genislik = models.PositiveIntegerField(default=TUVAL_GENISLIK, verbose_name="Tuval genişliği")
    tuval_yukseklik = models.PositiveIntegerField(default=TUVAL_YUKSEKLIK, verbose_name="Tuval yüksekliği")
    durum = models.CharField(
        max_length=10,
        choices=Durum.choices,
        default=Durum.TASLAK,
        db_index=True,
        verbose_name="Durum",
    )
    yayindaki_surum = models.ForeignKey(
        "EkranProjeSurumu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="yayinda_oldugu_projeler",
        verbose_name="Yayındaki sürüm",
    )
    kaydedilmemis_degisiklik = models.BooleanField(
        default=False,
        verbose_name="Yayınlanmamış değişiklik var",
    )

    class Meta:
        verbose_name = "Ekran tasarımı"
        verbose_name_plural = "Ekran tasarımları"
        ordering = ["-guncellenme"]

    def __str__(self) -> str:
        return self.ad

    @property
    def en_boy_orani(self) -> float:
        if not self.tuval_yukseklik:
            return 16 / 9
        return self.tuval_genislik / self.tuval_yukseklik


class EkranProjeSurumu(models.Model):
    """Tasarımın dondurulmuş anlık görüntüsü.

    Düzenlenebilir hâl ilişkisel tablolardadır (sahne + öğe). Kaydet/Yayınla
    ayrımı burada gerçekleşir: her yayınlamada mevcut hâlin tam JSON kopyası
    bu tabloya yazılır ve televizyonlara *bu kopya* gider. Böylece taslakta
    yapılan düzenleme yayındaki ekranı bozmaz, eski sürüm geri yüklenebilir.
    """

    proje = models.ForeignKey(
        EkranProje,
        on_delete=models.CASCADE,
        related_name="surumler",
        verbose_name="Tasarım",
    )
    surum_no = models.PositiveIntegerField(default=1, verbose_name="Sürüm no")
    veri = models.JSONField(default=dict, verbose_name="Anlık görüntü")
    not_metni = models.CharField(max_length=300, blank=True, verbose_name="Not")
    yayinlandi_mi = models.BooleanField(default=False, verbose_name="Yayınlandı")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ekran_surumleri",
        verbose_name="Oluşturan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ekran tasarım sürümü"
        verbose_name_plural = "Ekran tasarım sürümleri"
        ordering = ["-surum_no"]
        constraints = [
            models.UniqueConstraint(fields=["proje", "surum_no"], name="benzersiz_ekran_surumu"),
        ]

    def __str__(self) -> str:
        return f"{self.proje.ad} — v{self.surum_no}"


class EkranSahne(models.Model):
    """Tasarımın tek bir ekran görünümü."""

    class SureTipi(models.TextChoices):
        SANIYE = "saniye", "Belirli süre"
        VIDEO_BITENE = "video_bitene", "Video bitene kadar"
        PDF_BITENE = "pdf_bitene", "PDF sayfaları bitene kadar"
        SURESIZ = "suresiz", "Süresiz"

    class Gecis(models.TextChoices):
        YOK = "yok", "Geçiş yok"
        SOLDUR = "soldur", "Yumuşak geçiş"
        KAYDIR = "kaydir", "Kaydır"
        YAKINLASTIR = "yakinlastir", "Yakınlaştır"

    proje = models.ForeignKey(
        EkranProje,
        on_delete=models.CASCADE,
        related_name="sahneler",
        verbose_name="Tasarım",
    )
    ad = models.CharField(max_length=160, verbose_name="Sahne adı")
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    sure_tipi = models.CharField(
        max_length=14,
        choices=SureTipi.choices,
        default=SureTipi.SANIYE,
        verbose_name="Süre tipi",
    )
    sure_sn = models.PositiveIntegerField(default=20, verbose_name="Süre (saniye)")
    gecis = models.CharField(max_length=14, choices=Gecis.choices, default=Gecis.SOLDUR, verbose_name="Geçiş efekti")
    arka_plan_rengi = models.CharField(max_length=24, default="#0f203c", verbose_name="Arka plan rengi")
    arka_plan_medya = models.ForeignKey(
        EkranMedya,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="arka_plan_sahneleri",
        verbose_name="Arka plan görseli",
    )
    onizleme = models.ImageField(
        upload_to="ekran/sahne/%Y/%m/",
        storage=ekran_depolama,
        blank=True,
        null=True,
        verbose_name="Ön izleme görseli",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ekran sahnesi"
        verbose_name_plural = "Ekran sahneleri"
        ordering = ["proje_id", "sira"]
        indexes = [
            models.Index(fields=["proje", "sira"], name="ekran_sahne_sira_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.proje.ad} — {self.ad}"


class EkranOgeGrubu(models.Model):
    """Katman panelindeki klasör (ör. "Sağ afişler")."""

    sahne = models.ForeignKey(
        EkranSahne,
        on_delete=models.CASCADE,
        related_name="gruplar",
        verbose_name="Sahne",
    )
    ad = models.CharField(max_length=120, verbose_name="Grup adı")
    sira = models.IntegerField(default=0, verbose_name="Sıra")
    kilitli = models.BooleanField(default=False, verbose_name="Kilitli")
    gorunur = models.BooleanField(default=True, verbose_name="Görünür")

    class Meta:
        verbose_name = "Ekran öğe grubu"
        verbose_name_plural = "Ekran öğe grupları"
        ordering = ["sahne_id", "sira"]

    def __str__(self) -> str:
        return self.ad


class EkranOge(models.Model):
    """Tuvaldeki tek bir öğe.

    Konum/ölçü alanları tasarım uzayındadır (bkz. modül başlığı). Türden
    bağımsız yerleşim bilgisi sütunlarda, türe özgü sunum ayarları JSON
    alanlardadır.
    """

    sahne = models.ForeignKey(
        EkranSahne,
        on_delete=models.CASCADE,
        related_name="ogeler",
        verbose_name="Sahne",
    )
    grup = models.ForeignKey(
        EkranOgeGrubu,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ogeler",
        verbose_name="Grup",
    )
    tur = models.CharField(max_length=20, choices=OgeTuru.choices, db_index=True, verbose_name="Tür")
    ad = models.CharField(max_length=120, blank=True, verbose_name="Öğe adı")

    x = models.FloatField(default=0, verbose_name="X")
    y = models.FloatField(default=0, verbose_name="Y")
    genislik = models.FloatField(default=400, verbose_name="Genişlik")
    yukseklik = models.FloatField(default=300, verbose_name="Yükseklik")
    donus = models.FloatField(default=0, verbose_name="Döndürme (derece)")
    katman = models.IntegerField(default=0, verbose_name="Katman sırası")
    opaklik = models.FloatField(default=1.0, verbose_name="Opaklık")

    kilitli = models.BooleanField(default=False, verbose_name="Kilitli")
    gorunur = models.BooleanField(default=True, verbose_name="Görünür")

    medya = models.ForeignKey(
        EkranMedya,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ogeler",
        verbose_name="Medya",
        help_text="Tek kaynaklı öğeler için. PROTECT: kullanımdaki dosya silinemez.",
    )

    stil = models.JSONField(default=dict, blank=True, verbose_name="Stil ayarları")
    icerik = models.JSONField(default=dict, blank=True, verbose_name="İçerik ayarları")
    zamanlama = models.JSONField(default=dict, blank=True, verbose_name="Zamanlama")
    animasyon = models.JSONField(default=dict, blank=True, verbose_name="Animasyon")

    olusturulma = models.DateTimeField(auto_now_add=True)
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ekran öğesi"
        verbose_name_plural = "Ekran öğeleri"
        ordering = ["sahne_id", "katman", "id"]
        indexes = [
            models.Index(fields=["sahne", "katman"], name="ekran_oge_katman_idx"),
        ]

    def __str__(self) -> str:
        return self.ad or self.get_tur_display()


class EkranOgeKaynagi(models.Model):
    """Çok kaynaklı öğelerin (görsel slaytı) sıralı medya listesi."""

    oge = models.ForeignKey(
        EkranOge,
        on_delete=models.CASCADE,
        related_name="kaynaklar",
        verbose_name="Öğe",
    )
    medya = models.ForeignKey(
        EkranMedya,
        on_delete=models.PROTECT,
        related_name="oge_kaynaklari",
        verbose_name="Medya",
    )
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    sure_sn = models.FloatField(default=8, verbose_name="Gösterim süresi (sn)")
    gorunur = models.BooleanField(default=True, verbose_name="Gösterimde")

    class Meta:
        verbose_name = "Ekran öğe kaynağı"
        verbose_name_plural = "Ekran öğe kaynakları"
        ordering = ["oge_id", "sira"]

    def __str__(self) -> str:
        return f"{self.oge} — {self.medya.ad}"


class EkranSablon(models.Model):
    """Hazır ekran düzeni. Seçildiğinde sahneye kopyalanır; hiçbir alanı kilitli değildir."""

    ad = models.CharField(max_length=160, verbose_name="Şablon adı")
    aciklama = models.CharField(max_length=400, blank=True, verbose_name="Açıklama")
    kategori = models.CharField(max_length=60, blank=True, verbose_name="Kategori")
    anahtar = models.SlugField(max_length=80, unique=True, verbose_name="Anahtar")
    veri = models.JSONField(default=dict, verbose_name="Sahne verisi")
    onizleme = models.ImageField(
        upload_to="ekran/sablon/",
        storage=ekran_depolama,
        blank=True,
        null=True,
        verbose_name="Ön izleme",
    )
    yerlesik_mi = models.BooleanField(
        default=False,
        verbose_name="Yerleşik şablon",
        help_text="Sistemle gelen şablon — silinemez, güncellemede yenilenir.",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ekran_sablonlari",
    )
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ekran şablonu"
        verbose_name_plural = "Ekran şablonları"
        ordering = ["sira", "ad"]

    def __str__(self) -> str:
        return self.ad


# ---------------------------------------------------------------------------
# Oynatma listesi ve yayın planı
# ---------------------------------------------------------------------------


class EkranOynatmaListesi(EkranZamanDamgali):
    ad = models.CharField(max_length=160, verbose_name="Liste adı")
    aciklama = models.CharField(max_length=400, blank=True, verbose_name="Açıklama")
    donguye_al = models.BooleanField(default=True, verbose_name="Bitince başa dön")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Oynatma listesi"
        verbose_name_plural = "Oynatma listeleri"
        ordering = ["ad"]

    def __str__(self) -> str:
        return self.ad


class EkranOynatmaOgesi(models.Model):
    liste = models.ForeignKey(
        EkranOynatmaListesi,
        on_delete=models.CASCADE,
        related_name="ogeler",
        verbose_name="Liste",
    )
    sahne = models.ForeignKey(
        EkranSahne,
        on_delete=models.CASCADE,
        related_name="oynatma_ogeleri",
        verbose_name="Sahne",
    )
    sira = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    sure_sn = models.PositiveIntegerField(
        default=0,
        verbose_name="Süre (sn)",
        help_text="0 ise sahnenin kendi süresi kullanılır.",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        verbose_name = "Oynatma listesi öğesi"
        verbose_name_plural = "Oynatma listesi öğeleri"
        ordering = ["liste_id", "sira"]
        indexes = [
            models.Index(fields=["liste", "sira"], name="ekran_liste_sira_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.liste.ad} — {self.sahne.ad}"


class EkranYayinPlani(EkranZamanDamgali):
    """Bir oynatma listesinin ne zaman, nerede yayınlanacağı."""

    class Durum(models.TextChoices):
        TASLAK = "taslak", "Taslak"
        YAYINDA = "yayinda", "Yayında"
        DURDURULDU = "durduruldu", "Durduruldu"

    GUN_ADLARI = (
        (0, "Pazartesi"),
        (1, "Salı"),
        (2, "Çarşamba"),
        (3, "Perşembe"),
        (4, "Cuma"),
        (5, "Cumartesi"),
        (6, "Pazar"),
    )

    ad = models.CharField(max_length=160, verbose_name="Yayın adı")
    liste = models.ForeignKey(
        EkranOynatmaListesi,
        on_delete=models.PROTECT,
        related_name="yayin_planlari",
        verbose_name="Oynatma listesi",
    )
    durum = models.CharField(
        max_length=12,
        choices=Durum.choices,
        default=Durum.TASLAK,
        db_index=True,
        verbose_name="Durum",
    )
    baslangic_tarih = models.DateField(null=True, blank=True, verbose_name="Başlangıç tarihi")
    bitis_tarih = models.DateField(null=True, blank=True, verbose_name="Bitiş tarihi")
    baslangic_saat = models.TimeField(null=True, blank=True, verbose_name="Başlangıç saati")
    bitis_saat = models.TimeField(null=True, blank=True, verbose_name="Bitiş saati")
    gunler = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Haftanın günleri",
        help_text="0=Pazartesi … 6=Pazar. Boş bırakılırsa her gün.",
    )
    oncelik = models.PositiveSmallIntegerField(
        default=10,
        db_index=True,
        verbose_name="Öncelik",
        help_text="Aynı saate denk gelen yayınlarda yüksek olan kazanır.",
    )
    tum_ekranlar = models.BooleanField(default=False, verbose_name="Tüm ekranlarda yayınla")
    aktif_paket = models.ForeignKey(
        "EkranYayinPaketi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aktif_oldugu_planlar",
        verbose_name="Yayındaki paket",
    )

    class Meta:
        verbose_name = "Yayın planı"
        verbose_name_plural = "Yayın planları"
        ordering = ["-oncelik", "ad"]
        indexes = [
            models.Index(fields=["durum", "oncelik"], name="ekran_plan_durum_idx"),
        ]

    def __str__(self) -> str:
        return self.ad

    @property
    def gun_etiketleri(self) -> str:
        if not self.gunler:
            return "Her gün"
        adlar = dict(self.GUN_ADLARI)
        return ", ".join(adlar.get(int(g), "?") for g in sorted(self.gunler))


class EkranYayinHedefi(models.Model):
    """Planın gideceği yer: tek cihaz ya da bir kat.

    ``EkranYayinPlani.tum_ekranlar`` işaretliyse hedef satırına gerek yoktur.
    """

    plan = models.ForeignKey(
        EkranYayinPlani,
        on_delete=models.CASCADE,
        related_name="hedefler",
        verbose_name="Plan",
    )
    konum = models.ForeignKey(
        EkranKonumu,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="yayin_hedefleri",
        verbose_name="Kat / konum",
    )
    cihaz = models.ForeignKey(
        EkranCihaz,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="yayin_hedefleri",
        verbose_name="Cihaz",
    )

    class Meta:
        verbose_name = "Yayın hedefi"
        verbose_name_plural = "Yayın hedefleri"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(konum__isnull=False, cihaz__isnull=True)
                    | models.Q(konum__isnull=True, cihaz__isnull=False)
                ),
                name="ekran_hedef_tek_tip",
            ),
            models.UniqueConstraint(
                fields=["plan", "konum"],
                condition=models.Q(konum__isnull=False),
                name="benzersiz_plan_konum_hedefi",
            ),
            models.UniqueConstraint(
                fields=["plan", "cihaz"],
                condition=models.Q(cihaz__isnull=False),
                name="benzersiz_plan_cihaz_hedefi",
            ),
        ]

    def __str__(self) -> str:
        return str(self.cihaz or self.konum)


class EkranYayinPaketi(models.Model):
    """Yayınlama anında derlenmiş, televizyona birebir gidecek JSON paket.

    Yayınla'ya basıldığında sahneler, öğeler ve medya adresleri tek bir
    yapıya derlenir ve içeriğinin SHA-256 özeti ``damga`` olarak saklanır.
    Televizyon 10 saniyede bir yalnız bu damgayı sorar; damga değişmedikçe
    hiçbir içerik yeniden indirilmez. Eksik medya varsa derleme aşamasında
    yakalanır, yayın hiç çıkmaz.
    """

    plan = models.ForeignKey(
        EkranYayinPlani,
        on_delete=models.CASCADE,
        related_name="paketler",
        verbose_name="Plan",
    )
    damga = models.CharField(max_length=64, db_index=True, verbose_name="İçerik damgası")
    veri = models.JSONField(default=dict, verbose_name="Derlenmiş yayın")
    varlik_sayisi = models.PositiveIntegerField(default=0, verbose_name="Medya sayısı")
    toplam_boyut = models.BigIntegerField(default=0, verbose_name="Toplam medya boyutu")
    yayinlayan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ekran_yayinlari",
        verbose_name="Yayınlayan",
    )
    olusturulma = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Yayın paketi"
        verbose_name_plural = "Yayın paketleri"
        ordering = ["-olusturulma"]

    def __str__(self) -> str:
        return f"{self.plan.ad} — {self.damga[:8]}"


# ---------------------------------------------------------------------------
# Acil duyuru
# ---------------------------------------------------------------------------


class EkranAcilDuyuru(models.Model):
    """Tüm yayınların üzerine çıkan duyuru."""

    class Ton(models.TextChoices):
        KIRMIZI = "kirmizi", "Acil (kırmızı)"
        LACIVERT = "lacivert", "Kurumsal (lacivert)"
        AMBER = "amber", "Uyarı (amber)"

    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    mesaj = models.TextField(blank=True, max_length=2000, verbose_name="Açıklama")
    ton = models.CharField(max_length=12, choices=Ton.choices, default=Ton.KIRMIZI, verbose_name="Görünüm")
    arka_plan_rengi = models.CharField(max_length=24, blank=True, verbose_name="Özel arka plan rengi")
    gorsel = models.ForeignKey(
        EkranMedya,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acil_gorselleri",
        verbose_name="Görsel",
    )
    video = models.ForeignKey(
        EkranMedya,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acil_videolari",
        verbose_name="Video",
    )
    sesli_uyari = models.BooleanField(default=False, verbose_name="Sesli uyarı")

    tum_ekranlar = models.BooleanField(default=True, verbose_name="Tüm ekranlarda")
    konumlar = models.ManyToManyField(
        EkranKonumu,
        blank=True,
        related_name="acil_duyurular",
        verbose_name="Katlar",
    )
    cihazlar = models.ManyToManyField(
        EkranCihaz,
        blank=True,
        related_name="acil_duyurular",
        verbose_name="Cihazlar",
    )

    baslangic = models.DateTimeField(default=timezone.now, verbose_name="Başlangıç")
    bitis = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Bitiş",
        help_text="Boş bırakılırsa elle kapatılana kadar yayında kalır.",
    )
    aktif = models.BooleanField(default=True, db_index=True, verbose_name="Aktif")

    baslatan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="baslattigi_acil_duyurular",
        verbose_name="Başlatan",
    )
    kapatan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kapattigi_acil_duyurular",
        verbose_name="Kapatan",
    )
    kapatma_zamani = models.DateTimeField(null=True, blank=True, verbose_name="Kapatma zamanı")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Acil duyuru"
        verbose_name_plural = "Acil duyurular"
        ordering = ["-baslangic"]
        indexes = [
            models.Index(fields=["aktif", "baslangic"], name="ekran_acil_aktif_idx"),
        ]

    def __str__(self) -> str:
        return self.baslik

    @property
    def yayinda_mi(self) -> bool:
        if not self.aktif:
            return False
        simdi = timezone.now()
        if self.baslangic and simdi < self.baslangic:
            return False
        if self.bitis and simdi > self.bitis:
            return False
        return True


# ---------------------------------------------------------------------------
# Raporlama
# ---------------------------------------------------------------------------


class EkranOynatmaRaporu(models.Model):
    """Cihazın yayını alıp alamadığının kaydı.

    Yalnız *durum değişiminde* yazılır (yeni paket alındı / alınamadı),
    her nabızda değil.
    """

    class Sonuc(models.TextChoices):
        ALINDI = "alindi", "Yayın alındı"
        HATA = "hata", "Hata"
        EKSIK_MEDYA = "eksik_medya", "Medya yüklenemedi"

    cihaz = models.ForeignKey(
        EkranCihaz,
        on_delete=models.CASCADE,
        related_name="oynatma_raporlari",
        verbose_name="Cihaz",
    )
    paket = models.ForeignKey(
        EkranYayinPaketi,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="raporlar",
        verbose_name="Paket",
    )
    sonuc = models.CharField(max_length=14, choices=Sonuc.choices, verbose_name="Sonuç")
    mesaj = models.CharField(max_length=400, blank=True, verbose_name="Mesaj")
    zaman = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Oynatma raporu"
        verbose_name_plural = "Oynatma raporları"
        ordering = ["-zaman"]
        indexes = [
            models.Index(fields=["cihaz", "-zaman"], name="ekran_rapor_cihaz_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.cihaz} — {self.get_sonuc_display()}"


class EkranIslemKaydi(models.Model):
    """Kim ne yaptı — tasarım, yayın, medya ve acil duyuru işlemleri."""

    class Eylem(models.TextChoices):
        TASARIM_OLUSTUR = "tasarim_olustur", "Tasarım oluşturdu"
        TASARIM_DUZENLE = "tasarim_duzenle", "Tasarım düzenledi"
        TASARIM_SIL = "tasarim_sil", "Tasarım sildi"
        SURUM_GERI_YUKLE = "surum_geri_yukle", "Sürüm geri yükledi"
        YAYINLA = "yayinla", "Yayına aldı"
        YAYIN_DURDUR = "yayin_durdur", "Yayını durdurdu"
        MEDYA_YUKLE = "medya_yukle", "Medya yükledi"
        MEDYA_SIL = "medya_sil", "Medya sildi"
        ACIL_BASLAT = "acil_baslat", "Acil duyuru başlattı"
        ACIL_KAPAT = "acil_kapat", "Acil duyuruyu kapattı"
        CIHAZ_ESLESTIR = "cihaz_eslestir", "Cihaz eşleştirdi"
        CIHAZ_SIL = "cihaz_sil", "Cihaz kaydını sildi"

    kullanici = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ekran_islem_kayitlari",
        verbose_name="Kullanıcı",
    )
    eylem = models.CharField(max_length=24, choices=Eylem.choices, db_index=True, verbose_name="Eylem")
    nesne_tipi = models.CharField(max_length=40, blank=True, verbose_name="Nesne tipi")
    nesne_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="Nesne no")
    aciklama = models.CharField(max_length=500, blank=True, verbose_name="Açıklama")
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    zaman = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Ekran işlem kaydı"
        verbose_name_plural = "Ekran işlem kayıtları"
        ordering = ["-zaman"]

    def __str__(self) -> str:
        return f"{self.kullanici} — {self.get_eylem_display()}"
