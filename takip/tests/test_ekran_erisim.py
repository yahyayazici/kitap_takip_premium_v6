"""Ekran modülüne ana panelden ulaşılabildiğini doğrular.

Modül kodu doğru çalışsa bile kullanıcı ona ulaşamıyorsa yok sayılır:
menüde giriş olmalı ve korumalı adrese tıklayan biri girişten sonra
oraya dönmeli.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import PersonelProfili
from takip.panel_permissions import panel_nav_items


class EkranMenuErisimTests(TestCase):
    def setUp(self):
        self.sifre = "test-erisim-12345"
        self.idareci = User.objects.create_user("ekran_nav_idareci", password=self.sifre)
        PersonelProfili.objects.create(
            user=self.idareci, ad_soyad="İdareci", ana_rol=PersonelProfili.Rol.IDARECI
        )
        self.muhasebeci = User.objects.create_user("ekran_nav_muhasebe", password=self.sifre)
        PersonelProfili.objects.create(
            user=self.muhasebeci, ad_soyad="Muhasebeci", ana_rol=PersonelProfili.Rol.MUHASEBECI
        )

    def test_menude_ekran_girisi_var(self):
        anahtarlar = [item.key for item in panel_nav_items(self.idareci)]
        self.assertIn("ekran", anahtarlar)

    def test_yetkisiz_rolde_menu_girisi_yok(self):
        anahtarlar = [item.key for item in panel_nav_items(self.muhasebeci)]
        self.assertNotIn("ekran", anahtarlar)

    def test_ana_panelde_ekran_baglantisi_goruluyor(self):
        self.client.force_login(self.idareci)
        yanit = self.client.get(reverse("dashboard"))
        self.assertEqual(yanit.status_code, 200)
        self.assertIn(reverse("ekran:dashboard"), yanit.content.decode())

    def test_girisden_sonra_tiklanan_adrese_donulur(self):
        """/ekran/ bağlantısına tıklayıp giriş yapan kişi normal panelde
        kalmamalı — yoksa modül bulunamaz."""
        hedef = reverse("ekran:dashboard")

        yanit = self.client.get(hedef)
        self.assertEqual(yanit.status_code, 302)
        self.assertIn(f"next={hedef}", yanit.url)

        giris = self.client.post(
            yanit.url,
            {"username": self.idareci.username, "password": self.sifre},
        )
        self.assertEqual(giris.status_code, 302)
        self.assertEqual(giris.url, hedef)

    def test_next_yoksa_rol_panosuna_gidilir(self):
        """Mevcut davranış korunmalı: next yoksa eskisi gibi çalışır."""
        giris = self.client.post(
            reverse("login"),
            {"username": self.idareci.username, "password": self.sifre},
        )
        self.assertEqual(giris.status_code, 302)
        self.assertEqual(giris.url, reverse("dashboard"))

    def test_dis_adrese_yonlendirilmez(self):
        """Açık yönlendirme (open redirect) açığı oluşmamalı."""
        giris = self.client.post(
            reverse("login") + "?next=https://kotu-site.example/calindi",
            {"username": self.idareci.username, "password": self.sifre},
        )
        self.assertEqual(giris.status_code, 302)
        self.assertEqual(giris.url, reverse("dashboard"))
