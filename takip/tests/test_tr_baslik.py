from django.test import SimpleTestCase

from takip.templatetags.filter_tags import harf_avatar, tr_baslik


class TrBaslikTests(SimpleTestCase):
    def test_buyuk_turkce_ad_kelime_basi_buyuk_kalir(self):
        self.assertEqual(tr_baslik("ABDULLAH HİLMİ KARA"), "Abdullah Hilmi Kara")
        self.assertEqual(tr_baslik("AHMET ARİF DEMİRCİ"), "Ahmet Arif Demirci")
        self.assertEqual(tr_baslik("İSMAİL"), "İsmail")
        self.assertEqual(tr_baslik("IŞIK"), "Işık")

    def test_zaten_baslik_olan_ad_bozulmaz(self):
        self.assertEqual(tr_baslik("Ahmet Arif"), "Ahmet Arif")
        self.assertEqual(tr_baslik(""), "")

    def test_harf_avatar_ilk_ve_son_kelime(self):
        self.assertEqual(harf_avatar("AHMED YASİR KAYMAKÇI"), "AK")
        self.assertEqual(harf_avatar("ÖMER KEREM SUCU"), "ÖS")
        self.assertEqual(harf_avatar("İSMAİL"), "İ")
        self.assertEqual(harf_avatar(""), "")
