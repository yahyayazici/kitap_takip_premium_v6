"""Pano akışı — tek tıkla ekranlara gönderme.

Kullanıcının bilmesi gereken tek şey pano ve ekranlardır; oynatma listesi
ve yayın planı arka planda kurulur.
"""

from __future__ import annotations

import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from takip.ekran_models import (
    EkranCihaz,
    EkranKonumu,
    EkranOynatmaListesi,
    EkranProje,
    EkranSahne,
    EkranYayinPaketi,
    EkranYayinPlani,
    OgeTuru,
)
from takip.ekran_service import (
    YayinHatasi,
    cihaz_durumu,
    pano_getir,
    pano_yayin_durumu,
    panoyu_ekranlara_gonder,
    sahne_kaydet,
    uygun_planlar,
    yayin_paketi_verisi,
)
from takip.models import PersonelProfili

GECICI_MEDYA = tempfile.mkdtemp(prefix="ekran-pano-medya-")


@override_settings(MEDIA_ROOT=GECICI_MEDYA)
class PanoGondermeTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(GECICI_MEDYA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("ekran_pano", password="test-12345")
        PersonelProfili.objects.create(
            user=self.user, ad_soyad="İdareci", ana_rol=PersonelProfili.Rol.IDARECI
        )
        self.client.force_login(self.user)

        self.kat1 = EkranKonumu.objects.create(ad="Giriş Katı", sira=0)
        self.kat2 = EkranKonumu.objects.create(ad="1. Kat", sira=1)
        self.tv1 = EkranCihaz.objects.create(
            ad="Giriş TV", konum=self.kat1, durum=EkranCihaz.Durum.AKTIF
        )
        self.tv2 = EkranCihaz.objects.create(
            ad="1. Kat TV", konum=self.kat2, durum=EkranCihaz.Durum.AKTIF
        )

        self.proje = pano_getir(kullanici=self.user)
        self.sahne = EkranSahne.objects.filter(proje=self.proje).first()
        self._panoyu_doldur()

    def _panoyu_doldur(self, metin="Merhaba"):
        sahne_kaydet(
            self.sahne,
            {"ogeler": [{
                "tur": OgeTuru.METIN, "ad": "Söz",
                "x": 100, "y": 300, "g": 1200, "h": 300, "katman": 0,
                "icerik": {"sozler": [{"metin": metin, "sure": 0}]},
            }]},
            kullanici=self.user,
        )

    # —— Pano ——

    def test_pano_getir_tek_pano_dondurur(self):
        self.assertEqual(pano_getir(), self.proje)
        self.assertEqual(EkranProje.objects.count(), 1)

    # —— Gönderme ——

    def test_tum_ekranlara_gonder(self):
        paket, hedefler = panoyu_ekranlara_gonder(
            self.proje, tum_ekranlar=True, kullanici=self.user
        )
        self.assertEqual(len(hedefler), 2)
        self.assertEqual(len(paket.veri["sahneler"]), 1)

        for cihaz in (self.tv1, self.tv2):
            self.assertTrue(uygun_planlar(cihaz))
            self.assertFalse(yayin_paketi_verisi(cihaz)["bos"])

    def test_secili_ekrana_gonder(self):
        _, hedefler = panoyu_ekranlara_gonder(
            self.proje, cihazlar=[self.tv2], kullanici=self.user
        )
        self.assertEqual(hedefler, [self.tv2])
        self.assertEqual(uygun_planlar(self.tv1), [])
        self.assertTrue(uygun_planlar(self.tv2))

    def test_kat_secerek_gonder(self):
        _, hedefler = panoyu_ekranlara_gonder(
            self.proje, konumlar=[self.kat1], kullanici=self.user
        )
        self.assertEqual(hedefler, [self.tv1])
        self.assertEqual(uygun_planlar(self.tv2), [])

    def test_hedef_secilmezse_hata(self):
        with self.assertRaises(YayinHatasi) as kapsam:
            panoyu_ekranlara_gonder(self.proje, kullanici=self.user)
        self.assertIn("ekranı seçin", str(kapsam.exception))

    def test_tekrar_gonderince_yeni_plan_birikmez(self):
        """Her gönderimde yeni liste/plan oluşmamalı."""
        for _ in range(3):
            panoyu_ekranlara_gonder(self.proje, tum_ekranlar=True, kullanici=self.user)

        self.assertEqual(EkranOynatmaListesi.objects.count(), 1)
        self.assertEqual(EkranYayinPlani.objects.count(), 1)

    def test_pano_degisince_yeni_paket_cikar(self):
        panoyu_ekranlara_gonder(self.proje, tum_ekranlar=True, kullanici=self.user)
        ilk = cihaz_durumu(self.tv1).damga

        self._panoyu_doldur("Değişti")
        panoyu_ekranlara_gonder(self.proje, tum_ekranlar=True, kullanici=self.user)

        self.assertNotEqual(ilk, cihaz_durumu(self.tv1).damga)
        self.assertEqual(EkranYayinPaketi.objects.count(), 2)

    def test_gonderilmeden_once_ekranlara_gitmez(self):
        self.assertEqual(uygun_planlar(self.tv1), [])
        self.assertTrue(yayin_paketi_verisi(self.tv1)["bos"])

    # —— Durum rozeti ——

    def test_yayin_durumu_gonderimden_sonra_guncel(self):
        panoyu_ekranlara_gonder(self.proje, tum_ekranlar=True, kullanici=self.user)
        self.proje.refresh_from_db()

        durum = pano_yayin_durumu(self.proje)
        self.assertTrue(durum["yayinda"])
        self.assertTrue(durum["guncel"])
        self.assertEqual(len(durum["ekranlar"]), 2)

    def test_gonderdikten_sonra_duzenleyince_eski_uyarisi(self):
        panoyu_ekranlara_gonder(self.proje, tum_ekranlar=True, kullanici=self.user)
        self._panoyu_doldur("Sonradan değişti")
        self.proje.refresh_from_db()

        self.assertFalse(pano_yayin_durumu(self.proje)["guncel"])

    # —— Görünüm ——

    def test_gonder_gorunumu_calisir(self):
        yanit = self.client.post(
            reverse("ekran:pano_gonder", args=[self.proje.pk]), {"hedef": "tum"}
        )
        self.assertEqual(yanit.status_code, 302)
        self.assertTrue(uygun_planlar(self.tv1))

    def test_yetkisiz_kullanici_gonderemez(self):
        baskasi = User.objects.create_user("ekran_yetkisiz", password="test-12345")
        PersonelProfili.objects.create(
            user=baskasi, ad_soyad="Muhasebeci", ana_rol=PersonelProfili.Rol.MUHASEBECI
        )
        self.client.force_login(baskasi)

        yanit = self.client.post(
            reverse("ekran:pano_gonder", args=[self.proje.pk]), {"hedef": "tum"}
        )
        self.assertEqual(yanit.status_code, 302)
        self.assertEqual(uygun_planlar(self.tv1), [])
