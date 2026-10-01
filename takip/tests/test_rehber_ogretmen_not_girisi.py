"""Rehber öğretmen panelinde not girişi yoktur; branş öğretmeninde vardır."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import EtutHocasi
from takip.wave0_models import KullaniciRol, Rol


class RehberOgretmenNotGirisiTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.create(
            slug="rehber_ogretmeni",
            ad="Rehber Öğretmeni",
            aktif=True,
        )

    def _hoca(self, username, *, rehber=False):
        user = User.objects.create_user(username, password="x")
        EtutHocasi.objects.create(ad_soyad=username, user=user, aktif=True)
        if rehber:
            KullaniciRol.objects.create(user=user, rol=self.rol, birincil=False)
        return user

    def test_rehber_panelinde_not_girisi_yok(self):
        user = self._hoca("rehber-hoca", rehber=True)
        self.client.force_login(user)

        panel = self.client.get(reverse("ogretmen_dashboard"))
        self.assertEqual(panel.status_code, 200)
        self.assertNotContains(panel, "Not Girişi")
        self.assertContains(panel, "Rehberlik")
        self.assertContains(panel, "Öğretmen · Rehber")

        giris = self.client.get(reverse("ogretmen_not_girisi"))
        self.assertRedirects(giris, reverse("ogretmen_dashboard"))

    def test_brans_ogretmeninde_not_girisi_durur(self):
        user = self._hoca("brans-hoca")
        self.client.force_login(user)

        panel = self.client.get(reverse("ogretmen_dashboard"))
        self.assertEqual(panel.status_code, 200)
        self.assertContains(panel, "Not Girişi")

        giris = self.client.get(reverse("ogretmen_not_girisi"))
        self.assertEqual(giris.status_code, 200)
