"""Anlık kabuk: panel sayfaları içerik kökünü ve süre başlığını taşır."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class CsKabukTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "kabuk-idareci", "kabuk@example.com", "Sifre!2026x"
        )
        self.client.force_login(self.user)

    def test_panel_kabugu_ve_sunucu_suresi(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-cs-shell="panel"')
        self.assertContains(response, 'id="cs-page"')
        self.assertContains(response, 'id="cs-messages"')
        self.assertContains(response, 'id="cs-page-boot"')
        self.assertContains(response, "cs-instant.js")
        self.assertIn("Server-Timing", response)
        self.assertIn("app;dur=", response["Server-Timing"])

    def test_yonetim_kabugu(self):
        response = self.client.get(reverse("yonetim:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-cs-shell="yonetim"')
        self.assertContains(response, 'id="cs-page"')
        self.assertContains(response, "cs-instant.js")
