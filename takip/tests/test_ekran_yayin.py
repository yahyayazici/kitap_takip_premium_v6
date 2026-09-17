"""Ekran modülü — sahne kaydı, sürümleme, yayın derleme ve zamanlama."""

from __future__ import annotations

import io
import shutil
import tempfile
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from takip.ekran_media_service import medya_yukle
from takip.ekran_models import (
    EkranAcilDuyuru,
    EkranCihaz,
    EkranKonumu,
    EkranMedya,
    EkranOynatmaListesi,
    EkranOynatmaOgesi,
    EkranProje,
    EkranProjeSurumu,
    EkranSahne,
    EkranYayinHedefi,
    EkranYayinPlani,
    OgeTuru,
)
from takip.ekran_service import (
    YayinHatasi,
    cihaz_durumu,
    paket_derle,
    proje_verisi,
    sahne_getir,
    sahne_kaydet,
    sahne_verisi,
    surum_geri_yukle,
    surum_olustur,
    uygun_planlar,
    yayin_paketi_verisi,
)

GECICI_MEDYA = tempfile.mkdtemp(prefix="ekran-yayin-medya-")


def png_baytlari(g=200, y=300) -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (g, y), (21, 66, 127)).save(tampon, format="PNG")
    return tampon.getvalue()


@override_settings(MEDIA_ROOT=GECICI_MEDYA)
class EkranYayinTestTemeli(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(GECICI_MEDYA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("ekran_yayin", password="test-12345")
        self.proje = EkranProje.objects.create(ad="Giriş Kat Yayını", olusturan=self.user)
        self.sahne = EkranSahne.objects.create(proje=self.proje, ad="Sahne 1", sira=0)
        self.gorsel = medya_yukle(
            SimpleUploadedFile("afis.png", png_baytlari()), kullanici=self.user
        ).medya

    def _metin_ogesi(self, metin="Merhaba", **ek):
        temel = {
            "tur": OgeTuru.METIN,
            "ad": "Slogan",
            "x": 100, "y": 200, "g": 800, "h": 300,
            "katman": 0,
            "stil": {"punto": 64, "renk": "#ffffff"},
            "icerik": {"sozler": [{"metin": metin, "sure": 0}]},
        }
        temel.update(ek)
        return temel

    def _gorsel_ogesi(self):
        return {
            "tur": OgeTuru.GORSEL,
            "ad": "Afiş",
            "x": 1200, "y": 60, "g": 500, "h": 900,
            "katman": 1,
            "medya_id": self.gorsel.pk,
            "icerik": {"sigdir": "doldur"},
        }

    def _sahneyi_doldur(self):
        sahne_kaydet(
            self.sahne,
            {
                "ad": "Sahne 1",
                "sure_tipi": "saniye",
                "sure_sn": 25,
                "arka_plan": {"renk": "#0f203c"},
                "ogeler": [self._metin_ogesi(), self._gorsel_ogesi()],
            },
            kullanici=self.user,
        )
        self.sahne.refresh_from_db()

    def _yayin_kur(self, **plan_ayarlari):
        self._sahneyi_doldur()
        liste = EkranOynatmaListesi.objects.create(ad="Normal Gün")
        EkranOynatmaOgesi.objects.create(liste=liste, sahne=self.sahne, sira=0)
        ayarlar = {"ad": "Normal Gün Yayını", "liste": liste, "tum_ekranlar": True}
        ayarlar.update(plan_ayarlari)
        plan = EkranYayinPlani.objects.create(**ayarlar)
        return liste, plan


class SahneKaydiTests(EkranYayinTestTemeli):
    def test_sahne_kaydedilip_ayni_sekilde_geri_okunur(self):
        """Kabul ölçütü: tasarımı kaydedip yeniden açınca aynı görünüm."""
        self._sahneyi_doldur()
        veri = sahne_verisi(sahne_getir(self.sahne.pk))

        self.assertEqual(veri["ad"], "Sahne 1")
        self.assertEqual(veri["sure_sn"], 25)
        self.assertEqual(len(veri["ogeler"]), 2)

        metin, gorsel = veri["ogeler"][0], veri["ogeler"][1]
        self.assertEqual(metin["tur"], OgeTuru.METIN)
        self.assertEqual((metin["x"], metin["y"], metin["g"], metin["h"]), (100, 200, 800, 300))
        self.assertEqual(metin["icerik"]["sozler"][0]["metin"], "Merhaba")
        self.assertEqual(metin["stil"]["punto"], 64)

        self.assertEqual(gorsel["tur"], OgeTuru.GORSEL)
        self.assertEqual(gorsel["kaynak"]["id"], self.gorsel.pk)
        self.assertTrue(gorsel["kaynak"]["url"])

    def test_katman_sirasi_korunur(self):
        sahne_kaydet(self.sahne, {"ogeler": [
            self._metin_ogesi("Arka", katman=5),
            self._metin_ogesi("Ön", katman=1),
        ]}, kullanici=self.user)

        veri = sahne_verisi(sahne_getir(self.sahne.pk))
        # Serileştirme katman sırasına göre gelir: önce küçük katman.
        self.assertEqual(veri["ogeler"][0]["icerik"]["sozler"][0]["metin"], "Ön")
        self.assertEqual(veri["ogeler"][1]["icerik"]["sozler"][0]["metin"], "Arka")

    def test_gecersiz_tur_yok_sayilir(self):
        sahne_kaydet(self.sahne, {"ogeler": [
            {"tur": "zararli_tur", "x": 0, "y": 0, "g": 10, "h": 10},
            self._metin_ogesi(),
        ]}, kullanici=self.user)
        self.assertEqual(self.sahne.ogeler.count(), 1)

    def test_bozuk_sayilar_varsayilana_duser(self):
        sahne_kaydet(self.sahne, {"ogeler": [
            self._metin_ogesi(x="abc", y=None, g=0, h=-40),
        ]}, kullanici=self.user)
        oge = self.sahne.ogeler.get()
        self.assertEqual(oge.x, 0)
        self.assertEqual(oge.y, 0)
        self.assertGreaterEqual(oge.genislik, 1)
        self.assertGreaterEqual(oge.yukseklik, 1)

    def test_kayit_sonrasi_proje_kirli_isaretlenir(self):
        self._sahneyi_doldur()
        self.proje.refresh_from_db()
        self.assertTrue(self.proje.kaydedilmemis_degisiklik)
        self.assertEqual(self.proje.son_duzenleyen, self.user)


class SurumTests(EkranYayinTestTemeli):
    def test_surum_olustur_ve_geri_yukle(self):
        self._sahneyi_doldur()
        surum = surum_olustur(self.proje, kullanici=self.user, not_metni="ilk")
        self.assertEqual(surum.surum_no, 1)
        self.assertEqual(len(surum.veri["sahneler"]), 1)

        # Taslağı boşalt
        sahne_kaydet(self.sahne, {"ogeler": []}, kullanici=self.user)
        self.assertEqual(self.sahne.ogeler.count(), 0)

        surum_geri_yukle(surum, kullanici=self.user)
        self.proje.refresh_from_db()
        yeni_sahne = EkranSahne.objects.filter(proje=self.proje).first()
        self.assertEqual(yeni_sahne.ogeler.count(), 2)

    def test_surum_numaralari_artar(self):
        self._sahneyi_doldur()
        surum_olustur(self.proje, kullanici=self.user)
        ikinci = surum_olustur(self.proje, kullanici=self.user)
        self.assertEqual(ikinci.surum_no, 2)


class PaketDerlemeTests(EkranYayinTestTemeli):
    def test_bos_liste_yayinlanamaz(self):
        liste = EkranOynatmaListesi.objects.create(ad="Boş liste")
        plan = EkranYayinPlani.objects.create(ad="Boş yayın", liste=liste, tum_ekranlar=True)
        with self.assertRaises(YayinHatasi) as kapsam:
            paket_derle(plan, kullanici=self.user)
        self.assertIn("sahne yok", str(kapsam.exception))

    def test_bos_sahne_yayinlanamaz(self):
        liste = EkranOynatmaListesi.objects.create(ad="Liste")
        EkranOynatmaOgesi.objects.create(liste=liste, sahne=self.sahne, sira=0)
        plan = EkranYayinPlani.objects.create(ad="Yayın", liste=liste, tum_ekranlar=True)

        with self.assertRaises(YayinHatasi) as kapsam:
            paket_derle(plan, kullanici=self.user)
        self.assertIn("boş", str(kapsam.exception))

    def test_dosyasiz_medya_ogesi_yayini_engeller(self):
        """“Yayın sırasında eksik dosya oluşmaması” gereği."""
        sahne_kaydet(self.sahne, {"ogeler": [
            {"tur": OgeTuru.GORSEL, "ad": "Afiş", "x": 0, "y": 0, "g": 400, "h": 600, "katman": 0},
        ]}, kullanici=self.user)

        liste = EkranOynatmaListesi.objects.create(ad="Liste")
        EkranOynatmaOgesi.objects.create(liste=liste, sahne=self.sahne, sira=0)
        plan = EkranYayinPlani.objects.create(ad="Yayın", liste=liste, tum_ekranlar=True)

        with self.assertRaises(YayinHatasi) as kapsam:
            paket_derle(plan, kullanici=self.user)
        self.assertIn("dosya seçilmemiş", str(kapsam.exception))

    def test_paket_derlenir_ve_damgalanir(self):
        _, plan = self._yayin_kur()
        paket = paket_derle(plan, kullanici=self.user)

        self.assertEqual(len(paket.damga), 64)
        self.assertEqual(len(paket.veri["sahneler"]), 1)
        self.assertIn(self.gorsel.dosya.url, paket.veri["varliklar"])
        self.assertEqual(paket.varlik_sayisi, 1)

        plan.refresh_from_db()
        self.assertEqual(plan.aktif_paket_id, paket.pk)
        self.assertEqual(plan.durum, EkranYayinPlani.Durum.YAYINDA)

    def test_ayni_icerik_ayni_damgayi_uretir(self):
        _, plan = self._yayin_kur()
        ilk = paket_derle(plan, kullanici=self.user)
        ikinci = paket_derle(plan, kullanici=self.user)
        self.assertEqual(ilk.pk, ikinci.pk)
        self.assertEqual(ilk.damga, ikinci.damga)

    def test_icerik_degisince_damga_degisir(self):
        _, plan = self._yayin_kur()
        ilk = paket_derle(plan, kullanici=self.user)

        sahne_kaydet(self.sahne, {
            "ogeler": [self._metin_ogesi("Yeni slogan"), self._gorsel_ogesi()],
        }, kullanici=self.user)
        ikinci = paket_derle(plan, kullanici=self.user)

        self.assertNotEqual(ilk.damga, ikinci.damga)

    def test_yayinlama_surum_olusturur(self):
        _, plan = self._yayin_kur()
        paket_derle(plan, kullanici=self.user)

        self.proje.refresh_from_db()
        self.assertEqual(self.proje.durum, EkranProje.Durum.YAYINDA)
        self.assertFalse(self.proje.kaydedilmemis_degisiklik)
        self.assertIsNotNone(self.proje.yayindaki_surum)
        self.assertTrue(self.proje.yayindaki_surum.yayinlandi_mi)

    def test_taslak_duzenlemesi_yayindaki_paketi_degistirmez(self):
        """Yayınlanmış tasarımın yeni sürümü hazırlanırken mevcut yayın sürer."""
        _, plan = self._yayin_kur()
        paket = paket_derle(plan, kullanici=self.user)
        ilk_damga = paket.damga

        sahne_kaydet(self.sahne, {
            "ogeler": [self._metin_ogesi("Taslakta değişti"), self._gorsel_ogesi()],
        }, kullanici=self.user)

        plan.refresh_from_db()
        self.assertEqual(plan.aktif_paket.damga, ilk_damga)
        gonderilen = plan.aktif_paket.veri["sahneler"][0]["ogeler"][0]
        self.assertEqual(gonderilen["icerik"]["sozler"][0]["metin"], "Merhaba")

    def test_liste_suresi_sahne_suresini_ezer(self):
        liste, plan = self._yayin_kur()
        liste.ogeler.update(sure_sn=99)
        paket = paket_derle(plan, kullanici=self.user)
        self.assertEqual(paket.veri["sahneler"][0]["sure_sn"], 99)
