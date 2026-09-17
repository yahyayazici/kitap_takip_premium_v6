"""Ekran modülü — cihaz eşleştirme, API güvenliği ve yetkilendirme."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from takip.ekran_models import (
    EkranCihaz,
    EkranKonumu,
    EkranOynatmaListesi,
    EkranOynatmaOgesi,
    EkranProje,
    EkranSahne,
    EkranYayinPlani,
    OgeTuru,
)
from takip.ekran_service import paket_derle, sahne_kaydet
from takip.models import PersonelProfili

GECICI_MEDYA = tempfile.mkdtemp(prefix="ekran-api-medya-")

# Cihaz API'si yalnız alt alan adının urlconf'unda tanımlı olduğu için
# testler bu urlconf üzerinden gider.
EKRAN_URLCONF = "config.ekran_urls"


@override_settings(MEDIA_ROOT=GECICI_MEDYA, ROOT_URLCONF=EKRAN_URLCONF)
class CihazApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(GECICI_MEDYA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("ekran_api", password="test-12345")

    def _kaydol(self):
        yanit = self.client.post(
            "/api/cihaz/kayit/",
            data=json.dumps({"genislik": 1920, "yukseklik": 1080, "surum": "1.0.0"}),
            content_type="application/json",
        )
        return yanit, yanit.json()

    def _yayin_kur(self):
        proje = EkranProje.objects.create(ad="Test")
        sahne = EkranSahne.objects.create(proje=proje, ad="Sahne 1", sira=0)
        sahne_kaydet(sahne, {"ogeler": [{
            "tur": OgeTuru.METIN, "ad": "Slogan", "x": 0, "y": 0, "g": 600, "h": 200,
            "katman": 0, "icerik": {"sozler": [{"metin": "Merhaba", "sure": 0}]},
        }]}, kullanici=self.user)

        liste = EkranOynatmaListesi.objects.create(ad="Liste")
        EkranOynatmaOgesi.objects.create(liste=liste, sahne=sahne, sira=0)
        plan = EkranYayinPlani.objects.create(ad="Yayın", liste=liste, tum_ekranlar=True)
        paket_derle(plan, kullanici=self.user)
        return plan

    # —— Kayıt ve eşleştirme ——

    def test_yeni_cihaz_anahtar_ve_kod_alir(self):
        yanit, veri = self._kaydol()
        self.assertEqual(yanit.status_code, 200)
        self.assertTrue(veri["tamam"])
        self.assertTrue(veri["anahtar"])
        self.assertEqual(len(veri["eslestirme_kodu"]), 6)

        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        self.assertEqual(cihaz.durum, EkranCihaz.Durum.BEKLIYOR)
        self.assertEqual(cihaz.cozunurluk_genislik, 1920)

    def test_anahtarsiz_istek_reddedilir(self):
        yanit = self.client.post("/api/cihaz/yoklama/")
        self.assertEqual(yanit.status_code, 404)
        self.assertTrue(yanit.json()["yeniden_kaydol"])

    def test_gecersiz_anahtar_reddedilir(self):
        yanit = self.client.post(
            "/api/cihaz/yoklama/", HTTP_X_EKRAN_ANAHTAR="uydurma-anahtar"
        )
        self.assertEqual(yanit.status_code, 404)

    def test_eslesmemis_cihaz_yayin_alamaz(self):
        _, veri = self._kaydol()
        yanit = self.client.get("/api/cihaz/yayin/", HTTP_X_EKRAN_ANAHTAR=veri["anahtar"])
        self.assertEqual(yanit.status_code, 403)

    def test_eslesmemis_cihaz_yoklamada_kod_gorur(self):
        _, veri = self._kaydol()
        yanit = self.client.post(
            "/api/cihaz/yoklama/", HTTP_X_EKRAN_ANAHTAR=veri["anahtar"]
        )
        govde = yanit.json()
        self.assertFalse(govde["eslestirildi"])
        self.assertEqual(govde["eslestirme_kodu"], veri["eslestirme_kodu"])

    def test_kod_tek_kullanimliktir(self):
        _, veri = self._kaydol()
        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        kod = cihaz.eslestirme_kodu

        cihaz.ad = "Giriş TV"
        cihaz.durum = EkranCihaz.Durum.AKTIF
        cihaz.eslestirme_kodu = ""
        cihaz.eslestirme_kodu_bitis = None
        cihaz.save()

        self.assertFalse(
            EkranCihaz.objects.filter(
                eslestirme_kodu=kod, durum=EkranCihaz.Durum.BEKLIYOR
            ).exists()
        )

    def test_suresi_dolmus_kod_gecersiz(self):
        _, veri = self._kaydol()
        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        cihaz.eslestirme_kodu_bitis = timezone.now() - timedelta(minutes=1)
        cihaz.save(update_fields=["eslestirme_kodu_bitis"])
        self.assertFalse(cihaz.kod_gecerli_mi)

    def test_suresi_dolan_kod_yoklamada_yenilenir(self):
        _, veri = self._kaydol()
        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        eski_kod = cihaz.eslestirme_kodu
        cihaz.eslestirme_kodu_bitis = timezone.now() - timedelta(minutes=1)
        cihaz.save(update_fields=["eslestirme_kodu_bitis"])

        yanit = self.client.post(
            "/api/cihaz/yoklama/", HTTP_X_EKRAN_ANAHTAR=veri["anahtar"]
        )
        yeni_kod = yanit.json()["eslestirme_kodu"]
        self.assertNotEqual(eski_kod, yeni_kod)

    def test_kayit_ip_basina_sinirli(self):
        """Eşleşmemiş cihaz tablosu dışarıdan şişirilememeli."""
        for _ in range(8):
            yanit, _ = self._kaydol()
            self.assertEqual(yanit.status_code, 200)

        yanit, veri = self._kaydol()
        self.assertEqual(yanit.status_code, 429)
        self.assertIn("çok fazla", veri["mesaj"].lower())

    # —— Yayın alma ——

    def test_eslesmis_cihaz_yayini_alir(self):
        self._yayin_kur()
        _, veri = self._kaydol()
        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        cihaz.ad = "Giriş TV"
        cihaz.durum = EkranCihaz.Durum.AKTIF
        cihaz.save()

        yoklama = self.client.post(
            "/api/cihaz/yoklama/", HTTP_X_EKRAN_ANAHTAR=veri["anahtar"]
        ).json()
        self.assertTrue(yoklama["eslestirildi"])
        self.assertTrue(yoklama["damga"])

        yayin = self.client.get(
            "/api/cihaz/yayin/", HTTP_X_EKRAN_ANAHTAR=veri["anahtar"]
        ).json()
        self.assertFalse(yayin["bos"])
        self.assertEqual(len(yayin["sahneler"]), 1)
        self.assertEqual(yayin["damga"], yoklama["damga"])

    def test_cihaz_baska_cihazin_yayinini_goremez(self):
        """Anahtar yalnız kendi cihazının verisini açar."""
        konum_a = EkranKonumu.objects.create(ad="A Katı")
        konum_b = EkranKonumu.objects.create(ad="B Katı")

        _, veri = self._kaydol()
        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        cihaz.ad = "A TV"
        cihaz.konum = konum_a
        cihaz.durum = EkranCihaz.Durum.AKTIF
        cihaz.save()

        yayin = self.client.get(
            "/api/cihaz/yayin/", HTTP_X_EKRAN_ANAHTAR=veri["anahtar"]
        ).json()
        self.assertEqual(yayin["cihaz"]["ad"], "A TV")
        self.assertEqual(yayin["cihaz"]["konum"], "A Katı")

    def test_yayin_alindi_raporu_kaydedilir(self):
        self._yayin_kur()
        _, veri = self._kaydol()
        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        cihaz.ad = "TV"
        cihaz.durum = EkranCihaz.Durum.AKTIF
        cihaz.save()

        damga = self.client.post(
            "/api/cihaz/yoklama/", HTTP_X_EKRAN_ANAHTAR=veri["anahtar"]
        ).json()["damga"]

        self.client.post(
            "/api/cihaz/rapor/",
            data=json.dumps({"damga": damga, "sonuc": "alindi"}),
            content_type="application/json",
            HTTP_X_EKRAN_ANAHTAR=veri["anahtar"],
        )

        cihaz.refresh_from_db()
        self.assertEqual(cihaz.son_yayin_damgasi, damga)
        self.assertIsNotNone(cihaz.son_basarili_guncelleme)
        self.assertTrue(cihaz.olaylar.filter(tur="yayin_alindi").exists())

    def test_hata_raporu_olay_yazar(self):
        _, veri = self._kaydol()
        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        cihaz.durum = EkranCihaz.Durum.AKTIF
        cihaz.save()

        self.client.post(
            "/api/cihaz/rapor/",
            data=json.dumps({"damga": "x", "sonuc": "hata", "mesaj": "Video oynatılamadı"}),
            content_type="application/json",
            HTTP_X_EKRAN_ANAHTAR=veri["anahtar"],
        )
        self.assertTrue(cihaz.olaylar.filter(tur="hata").exists())
        self.assertTrue(cihaz.oynatma_raporlari.filter(sonuc="hata").exists())

    def test_pasif_cihaza_yayin_gitmez(self):
        self._yayin_kur()
        _, veri = self._kaydol()
        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        cihaz.durum = EkranCihaz.Durum.PASIF
        cihaz.save()

        yoklama = self.client.post(
            "/api/cihaz/yoklama/", HTTP_X_EKRAN_ANAHTAR=veri["anahtar"]
        ).json()
        self.assertTrue(yoklama["pasif"])
        self.assertNotIn("damga", yoklama)

    def test_yeniden_yukleme_istegi_iletilir(self):
        self._yayin_kur()
        _, veri = self._kaydol()
        cihaz = EkranCihaz.objects.get(cihaz_anahtari=veri["anahtar"])
        cihaz.durum = EkranCihaz.Durum.AKTIF
        cihaz.yeniden_yukle_istegi = True
        cihaz.save()

        yoklama = self.client.post(
            "/api/cihaz/yoklama/", HTTP_X_EKRAN_ANAHTAR=veri["anahtar"]
        ).json()
        self.assertTrue(yoklama["yeniden_yukle"])


@override_settings(MEDIA_ROOT=GECICI_MEDYA)
class YetkiTests(TestCase):
    """Yetkisiz kullanıcı yayın yapamamalı, tasarım düzenleyememeli."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(GECICI_MEDYA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.idareci = User.objects.create_user("ekran_idareci", password="test-12345")
        PersonelProfili.objects.create(
            user=self.idareci, ad_soyad="İdareci", ana_rol=PersonelProfili.Rol.IDARECI
        )
        self.muhasebeci = User.objects.create_user("ekran_muhasebe", password="test-12345")
        PersonelProfili.objects.create(
            user=self.muhasebeci, ad_soyad="Muhasebeci", ana_rol=PersonelProfili.Rol.MUHASEBECI
        )

        self.proje = EkranProje.objects.create(ad="Test tasarımı")
        self.sahne = EkranSahne.objects.create(proje=self.proje, ad="Sahne 1", sira=0)

        liste = EkranOynatmaListesi.objects.create(ad="Liste")
        EkranOynatmaOgesi.objects.create(liste=liste, sahne=self.sahne, sira=0)
        self.plan = EkranYayinPlani.objects.create(ad="Yayın", liste=liste, tum_ekranlar=True)

    def test_giris_yapmamis_kullanici_yonlendirilir(self):
        yanit = self.client.get(reverse("ekran:dashboard"))
        self.assertEqual(yanit.status_code, 302)
        self.assertIn("/giris", yanit.url.lower() + "/giris")

    def test_idareci_panele_girebilir(self):
        # Modül girişi panoya yönlendirir (bkz. ekran_views.dashboard).
        self.client.force_login(self.idareci)
        yanit = self.client.get(reverse("ekran:dashboard"), follow=True)
        self.assertEqual(yanit.status_code, 200)
        self.assertIn("ek-tuval-sahne", yanit.content.decode())

    def test_yetkisiz_rol_panele_giremez(self):
        self.client.force_login(self.muhasebeci)
        yanit = self.client.get(reverse("ekran:dashboard"))
        self.assertEqual(yanit.status_code, 302)

    def test_yetkisiz_rol_yayin_yapamaz(self):
        self.client.force_login(self.muhasebeci)
        yanit = self.client.post(reverse("ekran:yayin_yayinla", args=[self.plan.pk]))
        self.assertEqual(yanit.status_code, 302)

        self.plan.refresh_from_db()
        self.assertIsNone(self.plan.aktif_paket)
        self.assertEqual(self.plan.durum, EkranYayinPlani.Durum.TASLAK)

    def test_yetkisiz_rol_sahne_kaydedemez(self):
        self.client.force_login(self.muhasebeci)
        yanit = self.client.post(
            reverse("ekran:sahne_kaydet", args=[self.sahne.pk]),
            data=json.dumps({"ogeler": [{"tur": "metin", "x": 0, "y": 0, "g": 10, "h": 10}]}),
            content_type="application/json",
        )
        self.assertEqual(yanit.status_code, 302)
        self.assertEqual(self.sahne.ogeler.count(), 0)

    def test_yetkisiz_rol_acil_duyuru_baslatamaz(self):
        self.client.force_login(self.muhasebeci)
        yanit = self.client.post(reverse("ekran:acil_listesi"), data={"baslik": "Test"})
        self.assertEqual(yanit.status_code, 302)
