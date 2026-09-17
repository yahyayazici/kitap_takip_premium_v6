"""Ekran medyası kendi kalıcı deposunda durmalı.

Canlıda proje varsayılanı Cloudinary olabilir; ekran modülünün videoları
oraya giderse ücretsiz plandaki 100 MB sınırına takılır. Bu yüzden ekran
dosyaları her koşulda dosya sisteminde tutulur.
"""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from takip.ekran_media_service import medya_yukle
from takip.ekran_models import EkranMedya

VARSAYILAN_KOK = tempfile.mkdtemp(prefix="ekran-varsayilan-")
EKRAN_KOK = tempfile.mkdtemp(prefix="ekran-ozel-")


def png_baytlari() -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (60, 40), (21, 66, 127)).save(tampon, format="PNG")
    return tampon.getvalue()


def pdf_baytlari() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    tampon = io.BytesIO()
    cizim = canvas.Canvas(tampon, pagesize=A4)
    cizim.drawString(100, 700, "Sayfa")
    cizim.showPage()
    cizim.save()
    return tampon.getvalue()


@override_settings(MEDIA_ROOT=VARSAYILAN_KOK, EKRAN_MEDIA_ROOT=Path(EKRAN_KOK))
class EkranDepolamaTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(VARSAYILAN_KOK, ignore_errors=True)
        shutil.rmtree(EKRAN_KOK, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("ekran_depo", password="test-12345")

    def test_gorsel_ekran_kokune_yazilir(self):
        medya = medya_yukle(
            SimpleUploadedFile("afis.png", png_baytlari()), kullanici=self.user
        ).medya

        yol = Path(medya.dosya.path)
        self.assertTrue(yol.exists())
        self.assertTrue(
            str(yol).startswith(EKRAN_KOK),
            f"dosya ekran deposunda değil: {yol}",
        )
        self.assertFalse(str(yol).startswith(VARSAYILAN_KOK))

    def test_pdf_sayfalari_da_ekran_kokune_yazilir(self):
        medya = medya_yukle(
            SimpleUploadedFile("sunum.pdf", pdf_baytlari()), kullanici=self.user
        ).medya

        self.assertEqual(medya.sayfa_sayisi, 1)
        for sayfa in medya.sayfalar.all():
            self.assertTrue(str(Path(sayfa.gorsel.path)).startswith(EKRAN_KOK))
        self.assertTrue(str(Path(medya.onizleme.path)).startswith(EKRAN_KOK))

    def test_adres_ekran_medya_onekiyle_baslar(self):
        """Televizyonun indireceği adres, diski servis eden yola işaret etmeli."""
        medya = medya_yukle(
            SimpleUploadedFile("afis2.png", png_baytlari()), kullanici=self.user
        ).medya
        self.assertTrue(
            medya.dosya.url.startswith(settings.EKRAN_MEDIA_URL),
            f"beklenmeyen adres: {medya.dosya.url}",
        )

    def test_adres_http_uzerinden_servis_edilir(self):
        medya = medya_yukle(
            SimpleUploadedFile("afis3.png", png_baytlari()), kullanici=self.user
        ).medya

        yanit = self.client.get(medya.dosya.url)
        self.assertEqual(yanit.status_code, 200, f"{medya.dosya.url} servis edilemedi")

    def test_alt_alan_adinda_da_servis_edilir(self):
        """Televizyon medyayı ekran.<domain> üzerinden indirir."""
        medya = medya_yukle(
            SimpleUploadedFile("afis4.png", png_baytlari()), kullanici=self.user
        ).medya

        with self.settings(ROOT_URLCONF="config.ekran_urls"):
            yanit = self.client.get(medya.dosya.url)
        self.assertEqual(yanit.status_code, 200)


@override_settings(MEDIA_ROOT=VARSAYILAN_KOK, EKRAN_MEDIA_ROOT=Path(EKRAN_KOK))
class EkranMedyaServisiTests(TestCase):
    """Televizyonun dosyaları indirdiği uç.

    Akıllı TV tarayıcılarının çoğu WebKit tabanlıdır ve ``<video>`` için
    byte-range (206) bekler; range yoksa video hiç başlamayabilir.
    """

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(VARSAYILAN_KOK, ignore_errors=True)
        shutil.rmtree(EKRAN_KOK, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("ekran_servis", password="test-12345")
        self.medya = medya_yukle(
            SimpleUploadedFile("afis.png", png_baytlari()), kullanici=self.user
        ).medya
        self.adres = self.medya.dosya.url
        self.boyut = self.medya.boyut

    def test_tam_dosya_servis_edilir(self):
        yanit = self.client.get(self.adres)
        self.assertEqual(yanit.status_code, 200)
        self.assertEqual(yanit["Accept-Ranges"], "bytes")
        self.assertEqual(int(yanit["Content-Length"]), self.boyut)

    def test_range_istegi_206_doner(self):
        yanit = self.client.get(self.adres, HTTP_RANGE="bytes=0-9")
        self.assertEqual(yanit.status_code, 206)
        self.assertEqual(yanit["Content-Range"], f"bytes 0-9/{self.boyut}")
        self.assertEqual(int(yanit["Content-Length"]), 10)
        self.assertEqual(len(b"".join(yanit.streaming_content)), 10)

    def test_acik_uclu_range(self):
        yanit = self.client.get(self.adres, HTTP_RANGE="bytes=5-")
        self.assertEqual(yanit.status_code, 206)
        self.assertEqual(int(yanit["Content-Length"]), self.boyut - 5)

    def test_sondan_range(self):
        yanit = self.client.get(self.adres, HTTP_RANGE="bytes=-20")
        self.assertEqual(yanit.status_code, 206)
        self.assertEqual(int(yanit["Content-Length"]), 20)

    def test_gecersiz_range_416_doner(self):
        yanit = self.client.get(self.adres, HTTP_RANGE=f"bytes={self.boyut + 10}-")
        self.assertEqual(yanit.status_code, 416)
        self.assertEqual(yanit["Content-Range"], f"bytes */{self.boyut}")

    def test_dizin_disina_cikilamaz(self):
        """Yol geçişi (path traversal) engellenmeli."""
        for kotu in ("../../../../etc/passwd", "..%2f..%2fetc%2fpasswd"):
            yanit = self.client.get(f"/ekran-medya/{kotu}")
            self.assertIn(yanit.status_code, (400, 404), f"{kotu} → {yanit.status_code}")

    def test_olmayan_dosya_404(self):
        self.assertEqual(self.client.get("/ekran-medya/yok/olmayan.png").status_code, 404)
