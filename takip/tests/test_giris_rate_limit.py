"""Güvenlik Sprint 1 — /giris/ rate limiting + rol bazlı login regresyonu.

Kapsam:
- Normal (doğru şifreli) giriş bozulmadı.
- N başarısız denemeden sonra kısa süreli cooldown devreye giriyor.
- Başarılı girişten sonra kullanıcı kilitli KALMIYOR (DoS'a açık kalıcı
  kilitleme yok).
- Aynı IP'deki FARKLI kullanıcılar birbirini kilitlemiyor (paylaşımlı okul
  ağı senaryosu).
- CSRF koruması hâlâ aktif.
- Mevcut rollerin (veli/talebe/öğretmen/personel) girişi bozulmadı.
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from takip.models import EtutHocasi, SinifSube, Talebe, TalebeHesap
from takip.rate_limit import MAX_DENEME
from takip.veli_hesap_util import veli_panel_ensure

LOGIN_URL = reverse("login")


class GirisRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("ratelimit-test", password="DogruSifre!2026")

    def tearDown(self):
        cache.clear()

    def test_dogru_bilgilerle_giris_calisiyor(self):
        response = self.client.post(
            LOGIN_URL,
            {"username": "ratelimit-test", "password": "DogruSifre!2026"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.client.session.get("_auth_user_id") is not None
            or "_auth_user_id" in self.client.session
        )

    def test_yanlis_sifre_form_hatasi_donuyor(self):
        response = self.client.post(
            LOGIN_URL,
            {"username": "ratelimit-test", "password": "yanlis"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_limit_asilinca_dogru_sifreyle_de_giris_engellenir(self):
        for _ in range(MAX_DENEME):
            self.client.post(
                LOGIN_URL,
                {"username": "ratelimit-test", "password": "yanlis-sifre"},
            )

        response = self.client.post(
            LOGIN_URL,
            {"username": "ratelimit-test", "password": "DogruSifre!2026"},
        )
        # Not: login.html şablonu her form hatasında sabit/genel bir mesaj
        # gösteriyor (bkz. templates/registration/login.html) — bu sprintte
        # tasarıma dokunulmadığından mesaj metni değil, asıl güvenlik
        # özelliği (doğru şifreyle bile giriş yapılamaması) doğrulanıyor.
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_basarili_giris_sonrasi_sayac_sifirlanir_kalici_kilit_yok(self):
        for _ in range(MAX_DENEME - 1):
            self.client.post(
                LOGIN_URL,
                {"username": "ratelimit-test", "password": "yanlis-sifre"},
            )

        basarili = self.client.post(
            LOGIN_URL,
            {"username": "ratelimit-test", "password": "DogruSifre!2026"},
        )
        self.assertEqual(basarili.status_code, 302)

        self.client.logout()
        tekrar = self.client.post(
            LOGIN_URL,
            {"username": "ratelimit-test", "password": "DogruSifre!2026"},
        )
        self.assertEqual(tekrar.status_code, 302, "Başarılı giriş sonrası kalıcı kilitlenme olmamalı")

    def test_farkli_kullanicilar_ayni_istemci_ip_birbirini_kilitlemiyor(self):
        User.objects.create_user("baska-kullanici", password="BaskaSifre!2026")

        for _ in range(MAX_DENEME):
            self.client.post(
                LOGIN_URL,
                {"username": "ratelimit-test", "password": "yanlis-sifre"},
            )

        response = self.client.post(
            LOGIN_URL,
            {"username": "baska-kullanici", "password": "BaskaSifre!2026"},
        )
        self.assertEqual(response.status_code, 302)

    def test_csrf_korumasi_hala_aktif(self):
        # Not: Proje CSRF_FAILURE_VIEW olarak takip.pwa_views.csrf_failure
        # kullanıyor (PWA/mobil geri yükleme senaryosu için, mevcut/sprint
        # kapsamı dışı davranış) — ham 403 yerine "?csrf=1" ile girişe geri
        # yönlendiriyor. Asıl doğrulanan: CSRF token'sız POST kullanıcıyı
        # OTURUM AÇMIŞ hale getirmiyor ve panele değil girişe dönüyor.
        sicil_client = Client(enforce_csrf_checks=True)
        response = sicil_client.post(
            LOGIN_URL,
            {"username": "ratelimit-test", "password": "DogruSifre!2026"},
        )
        self.assertNotIn("_auth_user_id", sicil_client.session)
        if response.status_code == 302:
            self.assertIn("csrf=1", response.url)
        else:
            self.assertEqual(response.status_code, 403)


class RolBazliGirisRegresyonTests(TestCase):
    """Rate limit / password validator değişiklikleri mevcut rollerin
    girişini bozmamalı (mevcut şifreler doğrulanmaz, geriye dönük çalışır).
    """

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_personel_yonetim_girisi(self):
        User.objects.create_superuser("idareci-test", "idareci@example.com", "EskiZayifSifre1")
        response = self.client.post(
            LOGIN_URL,
            {"username": "idareci-test", "password": "EskiZayifSifre1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

    def test_ogretmen_girisi(self):
        user = User.objects.create_user("hoca-test", password="EskiZayifSifre1")
        EtutHocasi.objects.create(ad_soyad="Test Hoca", user=user, aktif=True)

        response = self.client.post(
            LOGIN_URL,
            {"username": "hoca-test", "password": "EskiZayifSifre1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ogretmen_not_girisi"))

    def test_talebe_girisi(self):
        sinif = SinifSube.objects.create(sinif="7", sube="B")
        hoca_user = User.objects.create_user("hoca-talebe-girisi-test", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Test Hoca", user=hoca_user)
        hoca.sorumlu_sinif_subeler.add(sinif)
        talebe = Talebe.objects.create(
            ad_soyad="Talebe Test",
            sinif_sube=sinif,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
        )
        user = User.objects.create_user("talebe-test", password="EskiZayifSifre1")
        TalebeHesap.objects.create(user=user, talebe=talebe, aktif=True)

        response = self.client.post(
            LOGIN_URL,
            {"username": "talebe-test", "password": "EskiZayifSifre1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("talebe_dashboard"))

    def test_veli_girisi(self):
        sinif = SinifSube.objects.create(sinif="7", sube="C")
        hoca_user = User.objects.create_user("hoca-veli-girisi-test", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Test Hoca", user=hoca_user)
        hoca.sorumlu_sinif_subeler.add(sinif)
        talebe = Talebe.objects.create(
            ad_soyad="Veli Talebe Test",
            sinif_sube=sinif,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
            tc_kimlik="98765432109",
        )
        sonuc = veli_panel_ensure(talebe, "98765432109", "Veli Test")
        self.assertTrue(sonuc.basarili and sonuc.olusturuldu)

        response = self.client.post(
            LOGIN_URL,
            {"username": "98765432109", "password": sonuc.gecici_sifre},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("veli_dashboard"))
