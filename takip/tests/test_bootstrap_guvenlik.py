"""Güvenlik Sprint 1 — bootstrap-admin / bootstrap-setup sertleştirme testleri.

Not: GET metodu, query-string secret kullanımı ve "production'da tamamen
disabled" davranışı bu sprintte KASITLI olarak değiştirilmedi (mevcut
deploy sürecindeki kullanımı doğrulanamadı — bkz. final rapor). Bu testler
sadece güvenli biçimde YAPILAN değişikliği (traceback sızıntısının
kaldırılması) ve zaten var olan default-disabled davranışını doğrular.
"""

import os
from unittest import mock

from django.test import TestCase
from django.urls import reverse


class BootstrapAdminVarsayilanKapaliTests(TestCase):
    def test_env_yoksa_403(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADMIN_BOOTSTRAP_KEY", None)
            os.environ.pop("ADMIN_PASSWORD", None)
            response = self.client.get(reverse("bootstrap_admin"), {"key": "herhangi"})
        self.assertEqual(response.status_code, 403)

    def test_setup_env_yoksa_403(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADMIN_BOOTSTRAP_KEY", None)
            response = self.client.get(reverse("bootstrap_setup"), {"key": "herhangi"})
        self.assertEqual(response.status_code, 403)

    def test_yanlis_key_forbidden(self):
        with mock.patch.dict(
            os.environ,
            {"ADMIN_BOOTSTRAP_KEY": "dogru-anahtar", "ADMIN_PASSWORD": "Gecici!2026Sifre"},
        ):
            response = self.client.get(reverse("bootstrap_admin"), {"key": "yanlis-anahtar"})
        self.assertEqual(response.status_code, 403)


class BootstrapSetupTracebackSizintisiTests(TestCase):
    def test_hata_durumunda_traceback_response_body_donmuyor(self):
        with mock.patch.dict(os.environ, {"ADMIN_BOOTSTRAP_KEY": "dogru-anahtar"}):
            with mock.patch(
                "takip.bootstrap_views.call_command",
                side_effect=RuntimeError("beklenmedik hata: gizli-detay-XYZ"),
            ):
                with self.assertLogs("takip.bootstrap_views", level="ERROR"):
                    response = self.client.get(
                        reverse("bootstrap_setup"), {"key": "dogru-anahtar"}
                    )

        self.assertEqual(response.status_code, 500)
        body = response.content.decode("utf-8")
        self.assertNotIn("Traceback (most recent call last)", body)
        self.assertNotIn("RuntimeError", body)
        self.assertNotIn("gizli-detay-XYZ", body)
        self.assertNotIn("bootstrap_views.py", body)
