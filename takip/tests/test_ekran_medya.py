"""Ekran medya kütüphanesi — doğrulama, tekilleştirme, PDF sayfalama."""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from takip.ekran_media_service import (
    MedyaHatasi,
    medya_silinebilir_mi,
    medya_yukle,
)
from takip.ekran_models import (
    EkranMedya,
    EkranOge,
    EkranProje,
    EkranSahne,
    OgeTuru,
)

GECICI_MEDYA = tempfile.mkdtemp(prefix="ekran-test-medya-")


def png_baytlari(genislik: int = 120, yukseklik: int = 80) -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (genislik, yukseklik), (21, 66, 127)).save(tampon, format="PNG")
    return tampon.getvalue()


def pdf_baytlari(sayfa_sayisi: int = 3) -> bytes:
    """reportlab projede zaten var; testin dış dosyaya bağımlılığı olmasın."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    tampon = io.BytesIO()
    cizim = canvas.Canvas(tampon, pagesize=A4)
    for sayfa in range(sayfa_sayisi):
        cizim.drawString(100, 700, f"Sayfa {sayfa + 1}")
        cizim.showPage()
    cizim.save()
    return tampon.getvalue()


@override_settings(MEDIA_ROOT=GECICI_MEDYA)
class EkranMedyaTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(GECICI_MEDYA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("ekran_medya", password="test-12345")

    # —— Doğrulama ——

    def test_desteklenmeyen_uzanti_reddedilir(self):
        with self.assertRaises(MedyaHatasi) as kapsam:
            medya_yukle(SimpleUploadedFile("kotu.svg", b"<svg/>"), kullanici=self.user)
        self.assertIn("desteklenmiyor", str(kapsam.exception))

    def test_uzanti_ile_icerik_uyusmazsa_reddedilir(self):
        """.png adıyla gelen HTML/SVG içerik medya adresinden servis edilirse
        tarayıcıda script çalıştırabilirdi — magic number kontrolü bunu keser."""
        sahte = SimpleUploadedFile("resim.png", b"<svg onload=alert(1)></svg>")
        with self.assertRaises(MedyaHatasi) as kapsam:
            medya_yukle(sahte, kullanici=self.user)
        self.assertIn("uyuşmuyor", str(kapsam.exception))

    def test_uzantisiz_dosya_reddedilir(self):
        with self.assertRaises(MedyaHatasi):
            medya_yukle(SimpleUploadedFile("dosya", png_baytlari()), kullanici=self.user)

    # —— Görsel ——

    def test_gorsel_yuklenir_ve_olculeri_okunur(self):
        sonuc = medya_yukle(
            SimpleUploadedFile("afis.png", png_baytlari(300, 500)),
            kullanici=self.user,
            ad="Dikey afiş",
        )
        medya = sonuc.medya
        self.assertTrue(sonuc.yeni_mi)
        self.assertEqual(medya.tur, EkranMedya.Tur.GORSEL)
        self.assertEqual((medya.genislik, medya.yukseklik), (300, 500))
        self.assertTrue(medya.onizleme)
        self.assertEqual(medya.yukleyen, self.user)

    def test_ayni_dosya_ikinci_kez_yuklenmez(self):
        ham = png_baytlari()
        ilk = medya_yukle(SimpleUploadedFile("a.png", ham), kullanici=self.user)
        ikinci = medya_yukle(SimpleUploadedFile("b.png", ham), kullanici=self.user)

        self.assertTrue(ilk.yeni_mi)
        self.assertFalse(ikinci.yeni_mi)
        self.assertEqual(ilk.medya.pk, ikinci.medya.pk)
        self.assertEqual(EkranMedya.objects.count(), 1)

    # —— PDF ——

    def test_pdf_sayfalari_gorsele_cevrilir(self):
        sonuc = medya_yukle(
            SimpleUploadedFile("program.pdf", pdf_baytlari(3)),
            kullanici=self.user,
        )
        medya = sonuc.medya
        self.assertEqual(medya.tur, EkranMedya.Tur.PDF)
        self.assertEqual(medya.islem_durumu, EkranMedya.IslemDurumu.HAZIR)
        self.assertEqual(medya.sayfa_sayisi, 3)
        self.assertEqual(medya.sayfalar.count(), 3)

        sayfalar = list(medya.sayfalar.order_by("sira"))
        self.assertEqual([s.sira for s in sayfalar], [0, 1, 2])
        for sayfa in sayfalar:
            self.assertTrue(sayfa.gorsel.name)
            self.assertGreater(sayfa.genislik, 0)
            self.assertGreater(sayfa.yukseklik, 0)
        self.assertTrue(medya.onizleme)

    def test_bozuk_pdf_hata_durumuna_dusurulur(self):
        """Yükleme çökmemeli; kullanıcı anlaşılır bir not görmeli."""
        bozuk = b"%PDF-1.4\nbu gecerli bir pdf degil"
        sonuc = medya_yukle(SimpleUploadedFile("bozuk.pdf", bozuk), kullanici=self.user)
        medya = sonuc.medya
        self.assertEqual(medya.sayfa_sayisi, 0)
        self.assertEqual(medya.islem_durumu, EkranMedya.IslemDurumu.HATA)
        self.assertTrue(medya.islem_notu)

    # —— Silme koruması ——

    def test_kullanimdaki_medya_silinemez(self):
        medya = medya_yukle(
            SimpleUploadedFile("kullanilan.png", png_baytlari()),
            kullanici=self.user,
        ).medya

        proje = EkranProje.objects.create(ad="Giriş Kat Yayını")
        sahne = EkranSahne.objects.create(proje=proje, ad="Sahne 1", sira=0)
        EkranOge.objects.create(
            sahne=sahne, tur=OgeTuru.GORSEL, ad="Afiş",
            x=0, y=0, genislik=400, yukseklik=600, katman=0, medya=medya,
        )

        silinebilir, sebep = medya_silinebilir_mi(medya)
        self.assertFalse(silinebilir)
        self.assertIn("Giriş Kat Yayını", sebep)

    def test_kullanilmayan_medya_silinebilir(self):
        medya = medya_yukle(
            SimpleUploadedFile("bos.png", png_baytlari()),
            kullanici=self.user,
        ).medya
        silinebilir, sebep = medya_silinebilir_mi(medya)
        self.assertTrue(silinebilir)
        self.assertEqual(sebep, "")

    def test_pdf_yeniden_islenince_eski_sayfalar_diskten_silinir(self):
        """PDF yeniden işlendiğinde eski sayfa görselleri sahipsiz kalmamalı.

        ``queryset.delete()`` yalnız satırları kaldırır; dosyalar diskte
        birikirse her yeniden işlemede depo bir kat daha dolar.
        """
        from pathlib import Path

        from takip.ekran_media_service import pdf_sayfalarini_uret

        medya = medya_yukle(
            SimpleUploadedFile("tekrar.pdf", pdf_baytlari(2)),
            kullanici=self.user,
        ).medya

        eski_yollar = [Path(s.gorsel.path) for s in medya.sayfalar.all()]
        self.assertEqual(len(eski_yollar), 2)
        self.assertTrue(all(y.exists() for y in eski_yollar))

        pdf_sayfalarini_uret(medya)

        for yol in eski_yollar:
            self.assertFalse(yol.exists(), f"sahipsiz dosya kaldı: {yol.name}")

        medya.refresh_from_db()
        self.assertEqual(medya.sayfalar.count(), 2)
        for sayfa in medya.sayfalar.all():
            self.assertTrue(Path(sayfa.gorsel.path).exists())


class VideoBoyutSiniriTests(TestCase):
    """Video boyut sınırı sunucu kapasitesiyle uyumlu kalmalı.

    Sunucu yalnızca 4 eşzamanlı isteğe bakabiliyor (gunicorn 2 worker × 2
    thread — bkz. start.sh). Django, dosyayı view çalışmadan önce tamamen
    okur; çok büyük bir video yavaş bir bağlantıdan yüklenirken worker'ı
    dakikalarca işgal eder ve site aynı anda gelen diğer isteklere cevap
    veremez hâle gelir (2026-09-18'de yaşandı). Bu test, sınırın ileride
    fark edilmeden tekrar yükseltilmesini engeller.
    """

    def test_video_siniri_makul_kaliyor(self):
        from takip.ekran_media_service import MAKS_VIDEO_BAYT

        self.assertLessEqual(
            MAKS_VIDEO_BAYT,
            150 * 1024 * 1024,
            "video sınırı yükseltildi — sunucu kapasitesini (gunicorn "
            "2 worker × 2 thread) tekrar kontrol etmeden büyütme",
        )
