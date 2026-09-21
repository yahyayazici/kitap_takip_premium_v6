"""Akıllı Tahta Dosya Merkezi — madde 13'teki senaryoları kapsayan testler.

Testler modülün aşamaları ilerledikçe bu dosyaya eklenir.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from takip.akilli_tahta_models import AkilliTahtaDosya
from takip.models import EtutHocasi


def sahte_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"0" * 64


def sahte_pdf() -> bytes:
    return b"%PDF-1.4\n" + b"0" * 64


def sahte_mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42" + b"0" * 64


class AkilliTahtaYuklemeTests(TestCase):
    """Senaryo 1, 2, 10, 11: yükleme, yetkisiz kullanıcı, hatalı dosya, sahiplik."""

    def setUp(self):
        self.hoca_user = User.objects.create_user("etuthocasi1", password="test12345")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Ayşe Hoca", user=self.hoca_user)

        self.diger_hoca_user = User.objects.create_user("etuthocasi2", password="test12345")
        EtutHocasi.objects.create(ad_soyad="Mehmet Hoca", user=self.diger_hoca_user)

        self.yetkisiz_user = User.objects.create_user("veli1", password="test12345")

    def _yukleme_verisi(self, **ek):
        veri = {
            "baslik": "5. Sınıf Matematik Denemesi",
            "icerik_turu": AkilliTahtaDosya.IcerikTuru.DENEME,
            "tum_siniflar": "",
            "hedef_sinif_seviyeleri": ["5"],
            "yayin_baslangic": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "ust_sirada": "",
            "indirme_izni": "on",
        }
        veri.update(ek)
        return veri

    def test_etut_hocasi_pdf_yukleyebiliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        yanit = self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(yanit.status_code, 302)
        kayit = AkilliTahtaDosya.objects.get(baslik="5. Sınıf Matematik Denemesi")
        self.assertEqual(kayit.dosya_turu, "pdf")
        self.assertEqual(kayit.yukleyen, self.hoca_user)
        self.assertEqual(kayit.durum, AkilliTahtaDosya.Durum.YAYINDA)
        self.assertTrue(kayit.hedefler.filter(sinif_seviyesi="5").exists())

    def test_yetkisiz_kullanici_dosya_yukleyemiyor(self):
        self.client.force_login(self.yetkisiz_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        yanit = self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)
        # Yetki reddi -> dashboard'a yönlendirilir (require_permission deseni)
        self.assertEqual(yanit.status_code, 302)

    def test_anonim_kullanici_yukleme_sayfasina_giremiyor(self):
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        yanit = self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)
        self.assertIn(yanit.status_code, (302, 403))

    def test_yanlis_dosya_turu_reddediliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("virus.exe", b"MZ" + b"0" * 64)
        yanit = self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)
        self.assertEqual(yanit.status_code, 200)

    def test_icerigi_uzantisiyla_uyusmayan_dosya_reddediliyor(self):
        self.client.force_login(self.hoca_user)
        # .pdf uzantılı ama içeriği PNG olan sahte dosya
        dosya = SimpleUploadedFile("sahte.pdf", sahte_png(), content_type="application/pdf")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)

    @override_settings(AKILLI_TAHTA_MAKS_GORSEL_MB=0)
    def test_asiri_buyuk_dosya_reddediliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("buyuk.png", sahte_png(), content_type="image/png")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)

    def test_etut_hocasi_kendi_dosyasini_yonetebiliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        kayit = AkilliTahtaDosya.objects.get(baslik="5. Sınıf Matematik Denemesi")

        yanit = self.client.post(reverse("akilli_tahta:arsivle", args=[kayit.pk]))
        self.assertEqual(yanit.status_code, 302)
        kayit.refresh_from_db()
        self.assertEqual(kayit.durum, AkilliTahtaDosya.Durum.ARSIVLENDI)

    def test_baska_hocanin_dosyasini_yonetemiyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        kayit = AkilliTahtaDosya.objects.get(baslik="5. Sınıf Matematik Denemesi")

        self.client.force_login(self.diger_hoca_user)
        yanit = self.client.post(reverse("akilli_tahta:arsivle", args=[kayit.pk]))
        kayit.refresh_from_db()
        self.assertNotEqual(kayit.durum, AkilliTahtaDosya.Durum.ARSIVLENDI)
        self.assertEqual(yanit.status_code, 302)

    def test_tum_siniflara_gonderilen_dosya_hedeflerde_yok(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("video.mp4", sahte_mp4(), content_type="video/mp4")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(
                baslik="Tüm Sınıf Videosu",
                dosya=dosya,
                tum_siniflar="on",
                hedef_sinif_seviyeleri=[],
                icerik_turu=AkilliTahtaDosya.IcerikTuru.VIDEO,
                yayimla="1",
            ),
        )
        kayit = AkilliTahtaDosya.objects.get(baslik="Tüm Sınıf Videosu")
        self.assertTrue(kayit.tum_siniflar)
        self.assertEqual(kayit.hedefler.count(), 0)
        for seviye in ("5", "6", "7", "8"):
            self.assertTrue(kayit.hedefliyor_mu(seviye))

    def test_taslak_kaydedilebiliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, taslak="1"),
        )
        kayit = AkilliTahtaDosya.objects.get(baslik="5. Sınıf Matematik Denemesi")
        self.assertEqual(kayit.durum, AkilliTahtaDosya.Durum.TASLAK)
