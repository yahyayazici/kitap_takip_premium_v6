"""Güvenlik Sprint 1 — AUTH_PASSWORD_VALIDATORS regresyon testleri.

Kapsam:
- Zayıf şifreler YENİ şifre belirleme formlarında reddediliyor.
- Düzenlemede boş şifre (değiştirilmiyor) validator'ı tetiklemiyor.
- Mevcut (validator öncesi oluşturulmuş, zayıf) şifreli kullanıcılar hâlâ
  giriş yapabiliyor — validator'lar login akışını ETKİLEMİYOR.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.admin import EtutHocasiAdminForm
from takip.forms import TalebeHesapForm, VeliHesapForm
from takip.models import EtutHocasi, Talebe
from takip.wave0_models import VeliHesap
from takip.yonetim_forms import PersonelProfiliForm


def _test_hocasi(username):
    user = User.objects.create_user(username, password="x")
    return EtutHocasi.objects.create(ad_soyad="Test Hoca", user=user)


class VeliHesapFormSifreValidatorTests(TestCase):
    def setUp(self):
        hoca = _test_hocasi("hoca-veli-form-test")
        self.talebe = Talebe.objects.create(
            ad_soyad="Form Test Talebe",
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
        )

    def _veri(self, password):
        return {
            "username": "veli-form-test",
            "password": password,
            "ad_soyad": "Test Veli",
            "telefon": "",
            "yakinlik": "veli",
            "talebeler": [self.talebe.pk],
            "aktif": True,
        }

    def test_zayif_sifre_reddedilir(self):
        form = VeliHesapForm(data=self._veri("1234"))
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_guclu_sifre_kabul_edilir(self):
        form = VeliHesapForm(data=self._veri("Guclu-Bir-Sifre-2026xyz"))
        self.assertNotIn("password", form.errors)

    def test_duzenlemede_bos_sifre_validator_tetiklemiyor(self):
        # duzenleme=True + instance + boş şifre → "şifre değişmiyor"
        # anlamına gelir (bkz. VeliHesapForm.__init__), validate_password()
        # hiç çağrılmamalı ve alan zorunlu olmaktan çıkar.
        duzenlenecek_user = User.objects.create_user("veli-duzenleme-test", password="x")
        hesap = VeliHesap.objects.create(
            user=duzenlenecek_user,
            ad_soyad="Düzenlenecek Veli",
            aktif=True,
        )
        veri = self._veri("")
        form = VeliHesapForm(data=veri, instance=hesap, duzenleme=True)
        form.is_valid()
        self.assertNotIn("password", form.errors)


class TalebeHesapFormSifreValidatorTests(TestCase):
    def setUp(self):
        hoca = _test_hocasi("hoca-talebe-form-test")
        self.talebe = Talebe.objects.create(
            ad_soyad="Form Test Talebe 2",
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
        )

    def test_zayif_sifre_reddedilir(self):
        form = TalebeHesapForm(
            data={
                "username": "talebe-form-test",
                "password": "12345678",
                "talebe": self.talebe.pk,
                "aktif": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_guclu_sifre_kabul_edilir(self):
        form = TalebeHesapForm(
            data={
                "username": "talebe-form-test",
                "password": "Guclu-Bir-Sifre-2026xyz",
                "talebe": self.talebe.pk,
                "aktif": True,
            }
        )
        self.assertNotIn("password", form.errors)


class PersonelProfiliFormSifreValidatorTests(TestCase):
    def test_zayif_sifre_reddedilir(self):
        form = PersonelProfiliForm(
            data={
                "kullanici_adi": "personel-form-test",
                "sifre": "password",
                "ad_soyad": "Test Personel",
                "ana_rol": "etut_mesul",
                "aktif": True,
            }
        )
        form.is_valid()
        self.assertIn("sifre", form.errors)

    def test_guclu_sifre_kabul_edilir(self):
        form = PersonelProfiliForm(
            data={
                "kullanici_adi": "personel-form-test",
                "sifre": "Guclu-Bir-Sifre-2026xyz",
                "ad_soyad": "Test Personel",
                "ana_rol": "etut_mesul",
                "aktif": True,
            }
        )
        form.is_valid()
        self.assertNotIn("sifre", form.errors)


class EtutHocasiAdminFormSifreValidatorTests(TestCase):
    def test_zayif_sifre_reddedilir(self):
        form = EtutHocasiAdminForm(
            data={
                "ad_soyad": "Test Hoca",
                "kullanici_adi": "hoca-form-test",
                "sifre": "abcdefgh",
                "aktif": True,
            }
        )
        form.is_valid()
        self.assertIn("sifre", form.errors)

    def test_guclu_sifre_kabul_edilir(self):
        form = EtutHocasiAdminForm(
            data={
                "ad_soyad": "Test Hoca",
                "kullanici_adi": "hoca-form-test",
                "sifre": "Guclu-Bir-Sifre-2026xyz",
                "aktif": True,
            }
        )
        form.is_valid()
        self.assertNotIn("sifre", form.errors)


class MevcutZayifSifreliKullaniciGirisiTests(TestCase):
    """En kritik regresyon: validator'lar eklenmeden önce oluşturulmuş
    zayıf şifreli hesaplar giriş yapabilmeye devam etmeli."""

    def test_cok_zayif_mevcut_sifreyle_giris_calisir(self):
        user = User.objects.create_user("eski-hesap-test", password="12345678")
        # set_password() hiçbir zaman validate_password() çağırmaz — bu,
        # gerçek "validator öncesi" bir hesabı doğru şekilde simüle eder.
        response = self.client.post(
            reverse("login"),
            {"username": "eski-hesap-test", "password": "12345678"},
        )
        self.assertEqual(response.status_code, 302)
