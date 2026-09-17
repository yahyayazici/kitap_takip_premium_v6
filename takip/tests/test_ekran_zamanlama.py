"""Ekran modülü — yayın çözümleme, öncelik, hedefleme ve acil duyuru."""

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
    EkranOynatmaListesi,
    EkranOynatmaOgesi,
    EkranProje,
    EkranSahne,
    EkranYayinHedefi,
    EkranYayinPlani,
    OgeTuru,
)
from takip.ekran_service import (
    aktif_acil_duyuru,
    cihaz_durumu,
    nabiz_isle,
    paket_derle,
    sahne_kaydet,
    uygun_planlar,
    yayin_paketi_verisi,
)

GECICI_MEDYA = tempfile.mkdtemp(prefix="ekran-zaman-medya-")


def png_baytlari() -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (100, 100), (21, 66, 127)).save(tampon, format="PNG")
    return tampon.getvalue()


@override_settings(MEDIA_ROOT=GECICI_MEDYA)
class ZamanlamaTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(GECICI_MEDYA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("ekran_zaman", password="test-12345")
        self.giris_kat = EkranKonumu.objects.create(ad="Giriş Katı", sira=0)
        self.birinci_kat = EkranKonumu.objects.create(ad="1. Kat", sira=1)

        self.giris_ekrani = EkranCihaz.objects.create(
            ad="Giriş TV", konum=self.giris_kat, durum=EkranCihaz.Durum.AKTIF
        )
        self.kat_ekrani = EkranCihaz.objects.create(
            ad="1. Kat TV", konum=self.birinci_kat, durum=EkranCihaz.Durum.AKTIF
        )

    def _liste_olustur(self, ad="Liste"):
        proje = EkranProje.objects.create(ad=f"{ad} tasarımı")
        sahne = EkranSahne.objects.create(proje=proje, ad="Sahne 1", sira=0)
        sahne_kaydet(sahne, {"ogeler": [{
            "tur": OgeTuru.METIN, "ad": "Slogan",
            "x": 0, "y": 0, "g": 600, "h": 200, "katman": 0,
            "icerik": {"sozler": [{"metin": ad, "sure": 0}]},
        }]}, kullanici=self.user)

        liste = EkranOynatmaListesi.objects.create(ad=ad)
        EkranOynatmaOgesi.objects.create(liste=liste, sahne=sahne, sira=0)
        return liste

    def _plan(self, ad, *, yayinla=True, **ayarlar):
        liste = ayarlar.pop("liste", None) or self._liste_olustur(ad)
        ayarlar.setdefault("tum_ekranlar", True)
        plan = EkranYayinPlani.objects.create(ad=ad, liste=liste, **ayarlar)
        if yayinla:
            paket_derle(plan, kullanici=self.user)
            plan.refresh_from_db()
        return plan

    # —— Hedefleme ——

    def test_tum_ekranlara_yayin(self):
        plan = self._plan("Tüm ekranlar", tum_ekranlar=True)
        self.assertEqual([p.pk for p in uygun_planlar(self.giris_ekrani)], [plan.pk])
        self.assertEqual([p.pk for p in uygun_planlar(self.kat_ekrani)], [plan.pk])

    def test_kat_bazli_yayin(self):
        plan = self._plan("Giriş katı", tum_ekranlar=False)
        EkranYayinHedefi.objects.create(plan=plan, konum=self.giris_kat)

        self.assertEqual([p.pk for p in uygun_planlar(self.giris_ekrani)], [plan.pk])
        self.assertEqual(uygun_planlar(self.kat_ekrani), [])

    def test_tek_cihaza_yayin(self):
        plan = self._plan("Tek ekran", tum_ekranlar=False)
        EkranYayinHedefi.objects.create(plan=plan, cihaz=self.kat_ekrani)

        self.assertEqual(uygun_planlar(self.giris_ekrani), [])
        self.assertEqual([p.pk for p in uygun_planlar(self.kat_ekrani)], [plan.pk])

    def test_yayinlanmamis_plan_ekrana_gitmez(self):
        self._plan("Taslak", yayinla=False)
        self.assertEqual(uygun_planlar(self.giris_ekrani), [])

    def test_durdurulmus_plan_ekrana_gitmez(self):
        plan = self._plan("Durdurulacak")
        plan.durum = EkranYayinPlani.Durum.DURDURULDU
        plan.save(update_fields=["durum"])
        self.assertEqual(uygun_planlar(self.giris_ekrani), [])

    # —— Zaman ——

    def test_tarih_araligi_disindaki_plan_calismaz(self):
        dun = timezone.localdate() - timedelta(days=1)
        self._plan("Geçmiş", bitis_tarih=dun)
        self.assertEqual(uygun_planlar(self.giris_ekrani), [])

    def test_gun_secimi_uygulanir(self):
        an = timezone.localtime()
        yarin_gunu = (an.weekday() + 1) % 7
        self._plan("Yarın", gunler=[yarin_gunu])
        self.assertEqual(uygun_planlar(self.giris_ekrani, an), [])

        bugun_plan = self._plan("Bugün", gunler=[an.weekday()])
        self.assertEqual([p.pk for p in uygun_planlar(self.giris_ekrani, an)], [bugun_plan.pk])

    def test_saat_araligi_uygulanir(self):
        an = timezone.localtime().replace(hour=14, minute=0, second=0, microsecond=0)
        self._plan("Sabah", baslangic_saat=time(6, 0), bitis_saat=time(9, 0))
        ogleden_sonra = self._plan(
            "Öğleden sonra", baslangic_saat=time(13, 0), bitis_saat=time(18, 0)
        )
        self.assertEqual(
            [p.pk for p in uygun_planlar(self.giris_ekrani, an)], [ogleden_sonra.pk]
        )

    def test_gece_yarisini_asan_aralik(self):
        gece = timezone.localtime().replace(hour=23, minute=30, second=0, microsecond=0)
        sabah = timezone.localtime().replace(hour=2, minute=0, second=0, microsecond=0)
        plan = self._plan("Gece", baslangic_saat=time(22, 0), bitis_saat=time(6, 0))

        self.assertEqual([p.pk for p in uygun_planlar(self.giris_ekrani, gece)], [plan.pk])
        self.assertEqual([p.pk for p in uygun_planlar(self.giris_ekrani, sabah)], [plan.pk])

    # —— Öncelik ——

    def test_yuksek_oncelikli_plan_kazanir(self):
        dusuk = self._plan("Normal gün", oncelik=10)
        yuksek = self._plan("Sınav haftası", oncelik=50)

        planlar = uygun_planlar(self.giris_ekrani)
        self.assertEqual(planlar[0].pk, yuksek.pk)
        self.assertEqual(planlar[1].pk, dusuk.pk)

    def test_cakisan_planlar_listelenir(self):
        self._plan("A", oncelik=10)
        self._plan("B", oncelik=20)
        self.assertEqual(len(uygun_planlar(self.giris_ekrani)), 2)

    # —— Cihaz durumu / damga ——

    def test_damga_yayin_degisince_degisir(self):
        plan = self._plan("Yayın")
        ilk = cihaz_durumu(self.giris_ekrani).damga

        sahne = plan.liste.ogeler.first().sahne
        sahne_kaydet(sahne, {"ogeler": [{
            "tur": OgeTuru.METIN, "ad": "Yeni", "x": 0, "y": 0, "g": 600, "h": 200,
            "katman": 0, "icerik": {"sozler": [{"metin": "Değişti", "sure": 0}]},
        }]}, kullanici=self.user)
        paket_derle(plan, kullanici=self.user)

        self.assertNotEqual(ilk, cihaz_durumu(self.giris_ekrani).damga)

    def test_yayin_yoksa_bos_paket_doner(self):
        paket = yayin_paketi_verisi(self.giris_ekrani)
        self.assertTrue(paket["bos"])
        self.assertEqual(paket["sahneler"], [])
        self.assertIn("mesaj", paket)

    def test_paket_cihaz_bilgisi_tasir(self):
        self._plan("Yayın")
        paket = yayin_paketi_verisi(self.giris_ekrani)
        self.assertFalse(paket["bos"])
        self.assertEqual(paket["cihaz"]["ad"], "Giriş TV")
        self.assertEqual(paket["cihaz"]["konum"], "Giriş Katı")

    # —— Acil duyuru ——

    def test_acil_duyuru_tum_ekranlara_gider(self):
        duyuru = EkranAcilDuyuru.objects.create(
            baslik="Tahliye tatbikatı", tum_ekranlar=True, baslatan=self.user
        )
        self.assertEqual(aktif_acil_duyuru(self.giris_ekrani).pk, duyuru.pk)
        self.assertEqual(aktif_acil_duyuru(self.kat_ekrani).pk, duyuru.pk)

    def test_acil_duyuru_kat_bazli_hedeflenir(self):
        duyuru = EkranAcilDuyuru.objects.create(
            baslik="Giriş katı duyurusu", tum_ekranlar=False, baslatan=self.user
        )
        duyuru.konumlar.add(self.giris_kat)

        self.assertEqual(aktif_acil_duyuru(self.giris_ekrani).pk, duyuru.pk)
        self.assertIsNone(aktif_acil_duyuru(self.kat_ekrani))

    def test_acil_duyuru_damgayi_degistirir(self):
        self._plan("Yayın")
        normal_damga = cihaz_durumu(self.giris_ekrani).damga

        EkranAcilDuyuru.objects.create(baslik="Acil", tum_ekranlar=True, baslatan=self.user)
        acil_damga = cihaz_durumu(self.giris_ekrani).damga
        self.assertNotEqual(normal_damga, acil_damga)

    def test_acil_duyuru_kapaninca_normal_yayina_donulur(self):
        self._plan("Yayın")
        normal_damga = cihaz_durumu(self.giris_ekrani).damga

        duyuru = EkranAcilDuyuru.objects.create(
            baslik="Acil", tum_ekranlar=True, baslatan=self.user
        )
        self.assertIsNotNone(cihaz_durumu(self.giris_ekrani).acil)

        duyuru.aktif = False
        duyuru.save(update_fields=["aktif"])

        durum = cihaz_durumu(self.giris_ekrani)
        self.assertIsNone(durum.acil)
        self.assertEqual(durum.damga, normal_damga)

    def test_suresi_gecmis_acil_duyuru_gosterilmez(self):
        EkranAcilDuyuru.objects.create(
            baslik="Bitmiş",
            tum_ekranlar=True,
            baslangic=timezone.now() - timedelta(hours=2),
            bitis=timezone.now() - timedelta(hours=1),
            baslatan=self.user,
        )
        self.assertIsNone(aktif_acil_duyuru(self.giris_ekrani))

    # —— Nabız ——

    def test_nabiz_cevrimici_yapar(self):
        cihaz = self.giris_ekrani
        self.assertFalse(cihaz.cevrimici_mi)
        nabiz_isle(cihaz, ip="10.0.0.5", tarayici="TestTV/1.0", surum="1.0.0")
        cihaz.refresh_from_db()
        self.assertTrue(cihaz.cevrimici_mi)
        self.assertEqual(cihaz.son_ip, "10.0.0.5")
        self.assertEqual(cihaz.olaylar.filter(tur="cevrimici").count(), 1)

    def test_sik_nabiz_veritabanina_her_seferinde_yazmaz(self):
        """256 MB'lık veritabanında 10 saniyelik yazma yükü istemiyoruz."""
        cihaz = self.giris_ekrani
        nabiz_isle(cihaz)
        cihaz.refresh_from_db()
        ilk_zaman = cihaz.son_baglanti

        nabiz_isle(cihaz)
        cihaz.refresh_from_db()
        self.assertEqual(cihaz.son_baglanti, ilk_zaman)

    def test_cozunurluk_yonelimi_belirler(self):
        cihaz = self.giris_ekrani
        nabiz_isle(cihaz, cozunurluk=(1080, 1920))
        cihaz.refresh_from_db()
        self.assertEqual(cihaz.yonelim, EkranCihaz.Yonelim.DIKEY)
