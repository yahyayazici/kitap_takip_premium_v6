"""Güvenlik Sprint 1 — cuma_durum_panel XSS düzeltmesi (json_script).

Önceki kod `{{ stuyo_json|safe }}` ile manuel olarak JSON'u script tag'ine
gömüyordu; kullanıcı verisinde (örn. personel görünen adı) `</script>` gibi
bir içerik olsa tarayıcıda script bağlamı kırılabilirdi. Artık Django'nun
güvenli `json_script` filtresi kullanılıyor.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import PersonelProfili


class CumaDurumJsonScriptGuvenlikTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cuma-test", password="Sifre!2026Test")
        PersonelProfili.objects.create(
            user=self.user,
            ad_soyad='</script><script>alert(1)</script>',
        )
        self.client.force_login(self.user)

    def test_json_script_tag_kullaniliyor(self):
        response = self.client.get(reverse("cuma_durum_panel"))
        body = response.content.decode("utf-8")
        self.assertIn(
            '<script id="cd-stuyo-data" type="application/json">',
            body,
        )

    def test_kullanici_verisindeki_script_kapanisi_kacisli(self):
        response = self.client.get(reverse("cuma_durum_panel"))
        body = response.content.decode("utf-8")

        # json_script, "<"/">" karakterlerini \u003C / \u003E olarak
        # kaçışlar (Django: django.utils.html._json_script_escapes) — ham
        # kapanış etiketi script içeriğinde YER ALMAMALI (aksi halde script
        # bağlamı kırılır ve enjekte edilen ikinci <script> çalışabilirdi).
        self.assertNotIn("</script><script>alert(1)</script>", body)
        self.assertIn("\\u003C/script\\u003E", body)

    def test_safe_filtresi_kullanilmiyor(self):
        response = self.client.get(reverse("cuma_durum_panel"))
        body = response.content.decode("utf-8")
        # Eski (güvensiz) yapı tamamen kaldırılmış olmalı.
        self.assertNotIn("stuyo_json", body)
