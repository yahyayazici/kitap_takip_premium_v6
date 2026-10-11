"""Soru takip paneli: şube değişimi ve boş hesabı."""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import (
    Ders,
    EtutHocasi,
    GunlukSoruDersSatiri,
    GunlukSoruKaydi,
    SinifSube,
    Talebe,
)
from takip.soru_takip_service import kayit_kaydet, seed_soru_takip_dersleri, soru_takip_dersleri


class SoruTakipSubeGecisTests(TestCase):
    def setUp(self):
        seed_soru_takip_dersleri()
        self.user = User.objects.create_superuser("st-panel", password="x")
        self.client.force_login(self.user)
        self.hoca = EtutHocasi.objects.create(ad_soyad="Panel Hoca", user=self.user)
        self.sinif_a = SinifSube.objects.create(sinif="7", sube="A")
        self.sinif_b = SinifSube.objects.create(sinif="7", sube="B")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif_a, self.sinif_b)
        self.talebe_a = self._talebe("Yedi A Talebe", self.sinif_a, "A")
        self.talebe_b = self._talebe("Yedi B Talebe", self.sinif_b, "B")

    def _talebe(self, ad, sinif_sube, sube):
        return Talebe.objects.create(
            ad_soyad=ad,
            sinif=sinif_sube.sinif,
            sube=sube,
            sinif_sube=sinif_sube,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            aktif=True,
        )

    def test_baska_subeye_gecince_onceki_talebe_birakilir(self):
        yanit = self.client.get(
            reverse("soru_takip_panel"),
            {"sinif_sube": self.sinif_b.pk, "talebe": self.talebe_a.pk},
        )
        self.assertEqual(yanit.status_code, 200)
        self.assertContains(yanit, "Yedi B Talebe")
        self.assertNotContains(yanit, "Yedi A Talebe")
        self.assertContains(yanit, "Kayıt girmek için yukarıdan talebe seçin.")
        self.assertContains(yanit, f'value="{self.sinif_b.pk}" selected')

    def test_yalniz_talebe_ile_gelince_sube_ona_hizalanir(self):
        yanit = self.client.get(
            reverse("soru_takip_panel"),
            {"talebe": self.talebe_a.pk},
        )
        self.assertEqual(yanit.status_code, 200)
        self.assertContains(yanit, "Yedi A Talebe")
        self.assertNotContains(yanit, "Yedi B Talebe")
        self.assertContains(yanit, f'value="{self.sinif_a.pk}" selected')
        self.assertContains(yanit, "st-bos")
        self.assertContains(yanit, "soru-takip-panel.js")

    def test_ayni_subedeki_talebe_kalir(self):
        yanit = self.client.get(
            reverse("soru_takip_panel"),
            {"sinif_sube": self.sinif_a.pk, "talebe": self.talebe_a.pk},
        )
        self.assertEqual(yanit.status_code, 200)
        self.assertContains(yanit, "<h2>Yedi A Talebe</h2>")
        self.assertContains(yanit, 'class="st-num-input st-bos" readonly')


class SoruTakipBosHesapTests(TestCase):
    def setUp(self):
        seed_soru_takip_dersleri()
        self.user = User.objects.create_superuser("st-bos", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Bos Hoca", user=self.user)
        self.talebe = Talebe.objects.create(
            ad_soyad="Bos Talebe",
            sinif="7",
            sube="A",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            aktif=True,
        )
        self.turkce = Ders.objects.get(ad="Türkçe")

    def _post(self, **alanlar):
        post = {}
        for ders in soru_takip_dersleri():
            post[f"ders_{ders.id}_toplam"] = "0"
            post[f"ders_{ders.id}_dogru"] = "0"
            post[f"ders_{ders.id}_yanlis"] = "0"
            post[f"ders_{ders.id}_bos"] = "0"
        for anahtar, deger in alanlar.items():
            post[f"ders_{self.turkce.id}_{anahtar}"] = str(deger)
        return post

    def test_bos_toplamdan_kalan_olarak_dolar(self):
        kayit, hatalar = kayit_kaydet(
            self.user,
            self.talebe,
            date(2026, 10, 11),
            soru_takip_dersleri(),
            self._post(toplam=40, dogru=30, yanlis=4, bos=0),
        )
        self.assertEqual(hatalar, [])
        satir = GunlukSoruDersSatiri.objects.get(kayit=kayit, ders=self.turkce)
        self.assertEqual(satir.toplam_soru, 40)
        self.assertEqual(satir.dogru, 30)
        self.assertEqual(satir.yanlis, 4)
        self.assertEqual(satir.bos, 6)

    def test_dogru_ve_yanlis_toplami_asarsa_kayit_yazilmaz(self):
        _kayit, hatalar = kayit_kaydet(
            self.user,
            self.talebe,
            date(2026, 10, 11),
            soru_takip_dersleri(),
            self._post(toplam=40, dogru=30, yanlis=20, bos=0),
        )
        self.assertTrue(hatalar)
        self.assertFalse(
            GunlukSoruDersSatiri.objects.filter(ders=self.turkce).exists()
        )


class SoruTakipSilmeTests(TestCase):
    def setUp(self):
        seed_soru_takip_dersleri()
        self.user = User.objects.create_superuser("st-sil", password="x")
        self.client.force_login(self.user)
        self.hoca = EtutHocasi.objects.create(ad_soyad="Sil Hoca", user=self.user)
        self.talebe = Talebe.objects.create(
            ad_soyad="Sil Talebe",
            sinif="7",
            sube="A",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            aktif=True,
        )
        turkce = Ders.objects.get(ad="Türkçe")
        kayit, hatalar = kayit_kaydet(
            self.user,
            self.talebe,
            date(2026, 10, 11),
            soru_takip_dersleri(),
            {
                f"ders_{turkce.id}_toplam": "10",
                f"ders_{turkce.id}_dogru": "6",
                f"ders_{turkce.id}_yanlis": "1",
                f"ders_{turkce.id}_bos": "3",
            },
        )
        self.assertEqual(hatalar, [])
        self.kayit = kayit

    def test_get_kaydi_silmez(self):
        yanit = self.client.get(reverse("soru_takip_sil", args=[self.kayit.pk]))
        self.assertEqual(yanit.status_code, 302)
        self.assertTrue(GunlukSoruKaydi.objects.filter(pk=self.kayit.pk).exists())

    def test_post_kaydi_siler(self):
        yanit = self.client.post(reverse("soru_takip_sil", args=[self.kayit.pk]))
        self.assertEqual(yanit.status_code, 302)
        self.assertFalse(GunlukSoruKaydi.objects.filter(pk=self.kayit.pk).exists())
