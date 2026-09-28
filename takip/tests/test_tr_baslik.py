from django.test import SimpleTestCase

from takip.templatetags.filter_tags import tr_baslik


class TrBaslikTests(SimpleTestCase):
    def test_buyuk_turkce_ad_kelime_basi_buyuk_kalir(self):
        self.assertEqual(tr_baslik("ABDULLAH HİLMİ KARA"), "Abdullah Hilmi Kara")
        self.assertEqual(tr_baslik("AHMET ARİF DEMİRCİ"), "Ahmet Arif Demirci")
        self.assertEqual(tr_baslik("İSMAİL"), "İsmail")
        self.assertEqual(tr_baslik("IŞIK"), "Işık")

    def test_zaten_baslik_olan_ad_bozulmaz(self):
        self.assertEqual(tr_baslik("Ahmet Arif"), "Ahmet Arif")
        self.assertEqual(tr_baslik(""), "")
