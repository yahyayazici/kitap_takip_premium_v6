"""Yazılı Öncesi Seviye Tespit Sınavı — public başvuru formu.

Kapsam:
- Sayfa yeni başlık ve metinlerle açılıyor; eski 4A metinleri ve "Önemli" rozeti yok.
- Sınıf ve okul adı zorunlu.
- Geçerli başvuru kaydediliyor; sınıf, okul ve sınav adı doğru tutuluyor.
"""

from django.test import TestCase
from django.urls import reverse

from config.branding import SINAV_BASVURU_BASLIK
from takip.models import SinavBasvuru

FORM_URL = reverse("sinav_basvuru_form")


def gecerli_veri(**degisiklik):
    veri = {
        "ad_soyad": "Ahmet Yılmaz",
        "sinif": "6",
        "okul_adi": "Başakşehir Ortaokulu",
        "baba_adi": "Mehmet",
        "baba_telefon": "0532 111 22 33",
        "anne_adi": "Ayşe",
        "anne_telefon": "0533 444 55 66",
        "il": "İstanbul",
        "ilce": "Başakşehir",
        "dogum_tarihi": "2014-05-10",
        "bilgilendirme_onay": "on",
    }
    veri.update(degisiklik)
    return veri


class SinavBasvuruFormTests(TestCase):
    def test_sayfa_yeni_metinlerle_acilir(self):
        yanit = self.client.get(FORM_URL)
        self.assertEqual(yanit.status_code, 200)
        icerik = yanit.content.decode()
        self.assertIn("Öğrenci ad soyad", icerik)
        self.assertIn("Okul adı", icerik)
        self.assertIn("24 Ekim 2026", icerik)
        self.assertIn("2 örnek yazılı", icerik)
        self.assertNotIn("4A Proje", icerik)
        self.assertNotIn("Önemli", icerik)

    def test_sinif_ve_okul_zorunlu(self):
        yanit = self.client.post(FORM_URL, gecerli_veri(sinif="", okul_adi="  "))
        self.assertEqual(yanit.status_code, 200)
        self.assertEqual(SinavBasvuru.objects.count(), 0)
        form = yanit.context["form"]
        self.assertIn("sinif", form.errors)
        self.assertIn("okul_adi", form.errors)

    def test_gecersiz_sinif_reddedilir(self):
        yanit = self.client.post(FORM_URL, gecerli_veri(sinif="9"))
        self.assertEqual(yanit.status_code, 200)
        self.assertEqual(SinavBasvuru.objects.count(), 0)

    def test_gecerli_basvuru_kaydedilir(self):
        yanit = self.client.post(FORM_URL, gecerli_veri())
        self.assertEqual(yanit.status_code, 302)
        self.assertTrue(yanit["Location"].startswith(reverse("sinav_basvuru_tesekkur") + "?t="))
        basvuru = SinavBasvuru.objects.get()
        self.assertEqual(basvuru.sinif, "6")
        self.assertEqual(basvuru.okul_adi, "Başakşehir Ortaokulu")
        self.assertEqual(basvuru.sinav_adi, SINAV_BASVURU_BASLIK)
