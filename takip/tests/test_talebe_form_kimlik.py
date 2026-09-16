"""Talebe düzenleme formu — kimlik adı/soyadı ad_soyad’dan dolmalı."""

from django.contrib.auth.models import User
from django.test import TestCase

from takip.models import EtutHocasi, Talebe
from takip.yonetim_forms import TalebeForm, _ad_soyad_parcala


class AdSoyadParcalaTests(TestCase):
    def test_iki_kelime(self):
        self.assertEqual(_ad_soyad_parcala("AHMED ARIF"), ("AHMED", "ARIF"))

    def test_uc_kelime(self):
        self.assertEqual(
            _ad_soyad_parcala("AHMED YASIR KAYMAKÇI"),
            ("AHMED YASIR", "KAYMAKÇI"),
        )

    def test_bos(self):
        self.assertEqual(_ad_soyad_parcala("  "), ("", ""))


class TalebeFormKimlikInitialTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("hoca-kimlik-form", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Test Hoca", user=user)

    def test_bos_kimlik_alanlari_ad_soyaddan_dolar(self):
        talebe = Talebe.objects.create(
            ad_soyad="ABDÜLBARI MİRAÇ ÇİÇEK",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        form = TalebeForm(instance=talebe)
        self.assertEqual(form["kimlik_adi"].value(), "ABDÜLBARI MİRAÇ")
        self.assertEqual(form["kimlik_soyadi"].value(), "ÇİÇEK")

    def test_kayitli_kimlik_alanlari_korunur(self):
        talebe = Talebe.objects.create(
            ad_soyad="AHMED ARIF KÜÇÜK",
            kimlik_adi="Ahmed Arif",
            kimlik_soyadi="Küçük",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        form = TalebeForm(instance=talebe)
        self.assertEqual(form["kimlik_adi"].value(), "Ahmed Arif")
        self.assertEqual(form["kimlik_soyadi"].value(), "Küçük")
