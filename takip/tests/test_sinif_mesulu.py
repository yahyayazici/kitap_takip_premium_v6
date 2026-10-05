"""7-A ve 7-B listelerinde seviye mesulünün adı durur."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.etut_zimmet_service import (
    etut_mesul_sinif_zimmet_senkronize,
    sinif_liste_hocasi,
    sinif_mesulunu_kaydet,
)
from takip.models import EtutHocasi, PersonelProfili, SinifSeviyeMesulu, SinifSube, Talebe


class SinifMesuluTests(TestCase):
    def setUp(self):
        self.emirhan = self._hoca("emirhan", "Emirhan Hoca")
        self.recep = self._hoca("recep", "Recep Hoca")
        self.sinif_a = SinifSube.objects.create(sinif="7", sube="A")
        self.sinif_b = SinifSube.objects.create(sinif="7", sube="B")
        self.sinif_8 = SinifSube.objects.create(sinif="8", sube="A")
        for hoca in (self.emirhan, self.recep):
            hoca.sorumlu_sinif_subeler.add(self.sinif_a, self.sinif_b)
        self.emirhan.sorumlu_sinif_subeler.add(self.sinif_8)
        self.ali = self._talebe("Ali Yedi", self.sinif_a, self.emirhan)
        self.veli = self._talebe("Veli Yedi", self.sinif_b, self.emirhan)
        self.ayse = self._talebe("Ayse Sekiz", self.sinif_8, self.emirhan)
        self.admin = User.objects.create_superuser("mesul-admin", "a@b.com", "x")

    def _hoca(self, username, ad):
        user = User.objects.create_user(username, password="x")
        hoca = EtutHocasi.objects.create(user=user, ad_soyad=ad, aktif=True)
        PersonelProfili.objects.create(
            user=user,
            ad_soyad=ad,
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=hoca,
        )
        return hoca

    def _talebe(self, ad, sinif, hoca):
        return Talebe.objects.create(
            ad_soyad=ad,
            sinif_sube=sinif,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
        )

    def _adlar(self):
        return {
            talebe.ad_soyad: talebe.etut_hocasi.ad_soyad
            for talebe in Talebe.objects.select_related("etut_hocasi")
        }

    def test_mesul_yokken_son_zimmet_yazan_listede_gorunur(self):
        etut_mesul_sinif_zimmet_senkronize(self.recep)
        adlar = self._adlar()
        self.assertEqual(adlar["Ali Yedi"], "Recep Hoca")
        self.assertEqual(adlar["Veli Yedi"], "Recep Hoca")
        self.assertEqual(adlar["Ayse Sekiz"], "Emirhan Hoca")

    def test_seviye_mesulu_iki_subede_de_listede_kalir(self):
        sinif_mesulunu_kaydet("7", self.recep)
        self.assertEqual(sinif_liste_hocasi(self.sinif_a).ad_soyad, "Recep Hoca")
        self.assertEqual(sinif_liste_hocasi(self.sinif_b).ad_soyad, "Recep Hoca")
        etut_mesul_sinif_zimmet_senkronize(self.emirhan)
        adlar = self._adlar()
        self.assertEqual(adlar["Ali Yedi"], "Recep Hoca")
        self.assertEqual(adlar["Veli Yedi"], "Recep Hoca")
        self.assertEqual(adlar["Ayse Sekiz"], "Emirhan Hoca")

    def test_yonetim_mesulu_kaydedince_liste_adi_degisir(self):
        self.client.force_login(self.admin)
        sayfa = self.client.get(reverse("yonetim:sinif_listesi"))
        self.assertContains(sayfa, "Sınıf mesulü")
        self.assertContains(sayfa, "7. Sınıf")
        self.assertContains(sayfa, "7-A")
        self.assertContains(sayfa, "7-B")

        kayit = self.client.post(
            reverse("yonetim:sinif_mesulu_kaydet"),
            {"sinif": "7", "hoca": str(self.recep.pk)},
        )
        self.assertRedirects(kayit, reverse("yonetim:sinif_listesi"))
        self.assertEqual(SinifSeviyeMesulu.objects.get(sinif="7").hoca, self.recep)
        adlar = self._adlar()
        self.assertEqual(adlar["Ali Yedi"], "Recep Hoca")
        self.assertEqual(adlar["Veli Yedi"], "Recep Hoca")
        self.assertEqual(adlar["Ayse Sekiz"], "Emirhan Hoca")

        self.client.post(reverse("yonetim:sinif_mesulu_kaydet"), {"sinif": "7", "hoca": ""})
        self.assertFalse(SinifSeviyeMesulu.objects.filter(sinif="7").exists())
