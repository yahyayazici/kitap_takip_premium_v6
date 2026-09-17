"""Ekran modülü — her sayfanın açıldığını ve doğru şablonu kullandığını doğrular.

Amaç kapsamlı iş mantığı değil, "hiçbir sayfa 500 vermiyor" güvencesi:
şablon adı hatası, eksik ``{% url %}``, yanlış bağlam anahtarı gibi
hataları erkenden yakalar.
"""

from __future__ import annotations

import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from takip.ekran_models import (
    EkranAcilDuyuru,
    EkranCihaz,
    EkranKonumu,
    EkranMedyaKlasoru,
    EkranOynatmaListesi,
    EkranOynatmaOgesi,
    EkranProje,
    EkranProjeSurumu,
    EkranSablon,
    EkranSahne,
    EkranYayinPlani,
)
from takip.ekran_service import surum_olustur
from takip.models import PersonelProfili

GECICI_MEDYA = tempfile.mkdtemp(prefix="ekran-sayfa-medya-")


@override_settings(MEDIA_ROOT=GECICI_MEDYA)
class PanelSayfalariTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(GECICI_MEDYA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("ekran_sayfa", password="test-12345")
        PersonelProfili.objects.create(
            user=self.user, ad_soyad="İdareci", ana_rol=PersonelProfili.Rol.IDARECI
        )
        self.client.force_login(self.user)

        self.konum = EkranKonumu.objects.create(ad="Giriş Katı")
        self.cihaz = EkranCihaz.objects.create(
            ad="Giriş TV", konum=self.konum, durum=EkranCihaz.Durum.AKTIF
        )
        self.proje = EkranProje.objects.create(ad="Tasarım", olusturan=self.user)
        self.sahne = EkranSahne.objects.create(proje=self.proje, ad="Sahne 1", sira=0)
        self.surum = surum_olustur(self.proje, kullanici=self.user)

        self.liste = EkranOynatmaListesi.objects.create(ad="Liste")
        EkranOynatmaOgesi.objects.create(liste=self.liste, sahne=self.sahne, sira=0)
        self.plan = EkranYayinPlani.objects.create(
            ad="Yayın", liste=self.liste, tum_ekranlar=True
        )
        EkranMedyaKlasoru.objects.create(ad="Afişler", olusturan=self.user)
        EkranAcilDuyuru.objects.create(
            baslik="Geçmiş duyuru", tum_ekranlar=True, aktif=False, baslatan=self.user
        )
        EkranSablon.objects.create(
            ad="Tam ekran PDF", anahtar="test-tam-ekran-pdf", veri={"ogeler": []}, yerlesik_mi=True
        )

    def test_tum_panel_sayfalari_acilir(self):
        adresler = [
            reverse("ekran:pano", args=[self.proje.pk]),
            reverse("ekran:ozet"),
            reverse("ekran:tasarim_listesi"),
            reverse("ekran:studyo", args=[self.proje.pk]),
            reverse("ekran:tasarim_onizleme", args=[self.proje.pk]),
            reverse("ekran:surum_listesi", args=[self.proje.pk]),
            reverse("ekran:sablon_listesi"),
            reverse("ekran:medya_kutuphanesi"),
            reverse("ekran:medya_liste"),
            reverse("ekran:cihaz_listesi"),
            reverse("ekran:cihaz_detay", args=[self.cihaz.pk]),
            reverse("ekran:cihaz_durum_api"),
            reverse("ekran:konum_listesi"),
            reverse("ekran:liste_listesi"),
            reverse("ekran:liste_detay", args=[self.liste.pk]),
            reverse("ekran:yayin_listesi"),
            reverse("ekran:yayin_detay", args=[self.plan.pk]),
            reverse("ekran:acil_listesi"),
            reverse("ekran:gecmis"),
            reverse("ekran:gecmis") + "?sekme=rapor",
            reverse("ekran:gecmis") + "?sekme=olay",
            reverse("ekran:gecmis") + "?sekme=paket",
        ]
        for adres in adresler:
            with self.subTest(adres=adres):
                yanit = self.client.get(adres)
                self.assertEqual(yanit.status_code, 200, f"{adres} → {yanit.status_code}")

    def test_modul_girisi_dogrudan_panoyu_acar(self):
        """Kullanıcı panele girdiğinde liste/özet değil, çalışma alanını görmeli."""
        yanit = self.client.get(reverse("ekran:dashboard"))
        self.assertEqual(yanit.status_code, 302)

        pano = self.client.get(yanit.url)
        self.assertEqual(pano.status_code, 200)
        govde = pano.content.decode()
        self.assertIn("ek-tuval-sahne", govde)
        self.assertIn("Ekranlara gönder", govde)

    def test_pano_yoksa_kendiliginden_olusur(self):
        """Hiç pano yokken modüle girilince boş bir tahta açılmalı."""
        EkranSahne.objects.all().delete()
        EkranProje.objects.all().delete()

        yanit = self.client.get(reverse("ekran:dashboard"))
        self.assertEqual(yanit.status_code, 302)
        self.assertEqual(self.client.get(yanit.url).status_code, 200)
        self.assertEqual(EkranProje.objects.count(), 1)
        self.assertEqual(EkranSahne.objects.count(), 1)

    def test_menude_yalnizca_sade_basliklar_var(self):
        """Günlük kullanımda liste/yayın/medya/geçmiş sekmeleri görünmemeli."""
        govde = self.client.get(
            reverse("ekran:pano", args=[self.proje.pk])
        ).content.decode()
        menu = govde[govde.index('class="ekp-nav"'):govde.index("</nav>")]

        self.assertIn("Pano", menu)
        self.assertIn("Ekranlar", menu)
        for olmamali in ("Oynatma Listeleri", "Yayınlar", "Medya", "Geçmiş", "Tasarımlar"):
            self.assertNotIn(olmamali, menu, f"“{olmamali}” menüden kaldırılmalıydı")

    def test_studyo_baslangic_verisi_gomulur(self):
        yanit = self.client.get(reverse("ekran:studyo", args=[self.proje.pk]))
        govde = yanit.content.decode()
        self.assertIn('id="ek-baslangic"', govde)
        self.assertIn("ek-tuval-sahne", govde)
        # Varlık sürümü şablona ulaşmalı; aksi hâlde service worker'ın
        # ön belleğe aldığı adreslerle sayfanınkiler eşleşmez.
        self.assertIn("ekran/js/studyo.js", govde)
        self.assertNotIn("?v=\"", govde)


@override_settings(MEDIA_ROOT=GECICI_MEDYA, ROOT_URLCONF="config.ekran_urls")
class AltAlanAdiSayfalariTests(TestCase):
    """``ekran.<domain>`` yüzeyi: televizyon sayfası, giriş ve service worker."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(GECICI_MEDYA, ignore_errors=True)
        super().tearDownClass()

    def test_televizyon_sayfasi_acilir(self):
        yanit = self.client.get("/")
        self.assertEqual(yanit.status_code, 200)
        govde = yanit.content.decode()
        for beklenen in ("ek-sahne-katmani", "ek-acil-katmani", "ekran/js/viewer.js"):
            self.assertIn(beklenen, govde)

    def test_giris_sayfasi_acilir(self):
        yanit = self.client.get("/giris/")
        self.assertEqual(yanit.status_code, 200)
        self.assertIn("ekran/css/panel.css", yanit.content.decode())

    def test_cevrimdisi_sayfasi_acilir(self):
        self.assertEqual(self.client.get("/offline/").status_code, 200)

    def test_service_worker_kok_kapsamda_servis_edilir(self):
        yanit = self.client.get("/sw.js")
        self.assertEqual(yanit.status_code, 200)
        self.assertEqual(yanit["Service-Worker-Allowed"], "/")
        self.assertIn("application/javascript", yanit["Content-Type"])

    def test_service_worker_kabugu_sayfanin_adresleriyle_ayni(self):
        """Cache API anahtarı sorgu dizesini de içerir; iki taraf birebir
        eşleşmezse ön yükleme boşa gider."""
        sw = self.client.get("/sw.js").content.decode()
        sayfa = self.client.get("/").content.decode()

        for varlik in ("ekran/css/viewer.css", "ekran/js/engine.js", "ekran/js/viewer.js"):
            import re

            desen = re.escape(varlik) + r"\?v=[^'\"]+"
            sw_adres = re.search(desen, sw)
            sayfa_adres = re.search(desen, sayfa)
            self.assertIsNotNone(sw_adres, f"{varlik} service worker'da yok")
            self.assertIsNotNone(sayfa_adres, f"{varlik} sayfada yok")
            self.assertEqual(sw_adres.group(0), sayfa_adres.group(0))

    def test_ana_panel_adresleri_alt_alan_adinda_yok(self):
        """İki yüzey birbirine karışmamalı."""
        self.assertEqual(self.client.get("/panel/").status_code, 404)

    def test_qr_kodu_svg_doner(self):
        yanit = self.client.get("/ekran-qr/?veri=https://cinilisarayproje.com")
        self.assertEqual(yanit.status_code, 200)
        self.assertIn("image/svg+xml", yanit["Content-Type"])
        self.assertIn("<svg", yanit.content.decode())
