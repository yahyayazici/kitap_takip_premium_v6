"""Güvenlik Sprint 1/2 — bootstrap-setup sertleştirme testleri.

Not: /bootstrap-admin/ endpoint'i (anahtarla admin şifresi sıfırlama)
Sprint 2'de tamamen kaldırıldı — girişsiz, GET ile çağrılabilen bir
şifre-sıfırlama uç noktası, anahtarı ele geçiren herkese admin hesabını
devretme riski taşıyordu. Admin şifresi artık yalnızca sunucu erişimi
gerektiren `manage.py reset_admin --password ...` komutuyla değiştirilir.
"""

import os
from unittest import mock

from django.test import TestCase
from django.urls import reverse


class BootstrapSetupVarsayilanKapaliTests(TestCase):
    def test_setup_env_yoksa_403(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADMIN_BOOTSTRAP_KEY", None)
            response = self.client.get(reverse("bootstrap_setup"), {"key": "herhangi"})
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
