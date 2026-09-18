"""Televizyon sayfası hem alt alan adında hem ana sitenin /tv/ yolunda çalışmalı.

Alt alan adı isteğe bağlıdır: DNS ve sertifika işiyle uğraşmak istemeyen
kurum, televizyonda <domain>/tv/ adresini açar. Adresler sabit yazılırsa
ikinci durumda cihaz hiç bağlanamaz — bu testler onu korur.
"""

from __future__ import annotations

import json

from django.test import TestCase, override_settings


class TvYoluTests(TestCase):
    """Ana site: <domain>/tv/"""

    def test_televizyon_sayfasi_acilir(self):
        yanit = self.client.get("/tv/")
        self.assertEqual(yanit.status_code, 200)
        self.assertIn("ek-sahne-katmani", yanit.content.decode())

    def test_sayfa_dogru_kokü_bildirir(self):
        govde = self.client.get("/tv/").content.decode()
        self.assertIn('window.EKRAN_TEMEL = "/tv/"', govde)

    def test_cihaz_api_tv_altinda_calisir(self):
        yanit = self.client.post(
            "/tv/api/cihaz/kayit/",
            data=json.dumps({"genislik": 1920, "yukseklik": 1080}),
            content_type="application/json",
        )
        self.assertEqual(yanit.status_code, 200)
        self.assertTrue(yanit.json()["anahtar"])

    def test_service_worker_tv_kapsaminda(self):
        yanit = self.client.get("/tv/sw.js")
        self.assertEqual(yanit.status_code, 200)
        self.assertEqual(yanit["Service-Worker-Allowed"], "/tv/")

        govde = yanit.content.decode()
        self.assertIn("self.EKRAN_TEMEL = '/tv/';", govde)
        self.assertIn("'/tv/',", govde)

    def test_service_worker_kabugu_sayfayla_ayni_adresleri_kullanir(self):
        import re

        sw = self.client.get("/tv/sw.js").content.decode()
        sayfa = self.client.get("/tv/").content.decode()
        for varlik in ("ekran/css/viewer.css", "ekran/js/engine.js", "ekran/js/viewer.js"):
            desen = re.escape(varlik) + r"\?v=[^'\"]+"
            self.assertEqual(
                re.search(desen, sw).group(0),
                re.search(desen, sayfa).group(0),
                f"{varlik} adresleri örtüşmüyor",
            )

    def test_cevrimdisi_sayfasi_acilir(self):
        self.assertEqual(self.client.get("/tv/offline/").status_code, 200)


@override_settings(ROOT_URLCONF="config.ekran_urls")
class AltAlanAdiYoluTests(TestCase):
    """Alt alan adı: ekran.<domain>/ — eski davranış bozulmamalı."""

    def test_kok_televizyon_sayfasi(self):
        yanit = self.client.get("/")
        self.assertEqual(yanit.status_code, 200)
        self.assertIn('window.EKRAN_TEMEL = "/"', yanit.content.decode())

    def test_cihaz_api_kokte_calisir(self):
        yanit = self.client.post(
            "/api/cihaz/kayit/",
            data=json.dumps({"genislik": 1920, "yukseklik": 1080}),
            content_type="application/json",
        )
        self.assertEqual(yanit.status_code, 200)

    def test_service_worker_kok_kapsaminda(self):
        yanit = self.client.get("/sw.js")
        self.assertEqual(yanit["Service-Worker-Allowed"], "/")
        self.assertIn("self.EKRAN_TEMEL = '/';", yanit.content.decode())


class EskiTarayiciUyumuTests(TestCase):
    """Akıllı televizyon tarayıcıları çok eski olabiliyor.

    Konsollarına erişilemediği için bir çökme ekranda sessiz mavi bir
    hiçlik olarak görünür. Bu testler, sayfanın eski tarayıcıda da
    ayakta kalmasını sağlayan mekanizmaları korur.
    """

    def test_tani_sayfasi_acilir(self):
        yanit = self.client.get("/tv/tani/")
        self.assertEqual(yanit.status_code, 200)
        govde = yanit.content.decode()

        # Teşhis sayfasının KENDİ stilleri modern CSS'e dayanmamalı; sayfa
        # en eski tarayıcıda da okunabilmeli. (Metin içinde geçen "var(--x)"
        # bir destek sınaması, stil değil — bu yüzden yalnız <style> bloğuna
        # bakılıyor.)
        import re

        stil = govde[govde.index("<style>"):govde.index("</style>")]
        stil = re.sub(r"/\*.*?\*/", "", stil, flags=re.S)  # yorumlar sayılmaz
        for modern in ("var(--", "inset:", "aspect-ratio", "place-items", "gap:"):
            self.assertNotIn(modern, stil, f"teşhis sayfasında modern CSS: {modern}")
        for beklenen in ("fetch()", "localStorage", "MP4 oynatma", "JavaScript ÇALIŞMIYOR"):
            self.assertIn(beklenen, govde)

    def test_televizyon_sayfasi_hata_kancasi_tasir(self):
        """JavaScript çökerse ekranda okunur bir mesaj çıkmalı."""
        govde = self.client.get("/tv/").content.decode()
        self.assertIn("window.onerror", govde)
        self.assertIn("Ekran başlatılamadı", govde)
        self.assertIn("tani/", govde)

    def test_viewer_js_fetch_yoksa_yedek_kullanir(self):
        from pathlib import Path

        from django.conf import settings

        kaynak = (Path(settings.BASE_DIR) / "static/ekran/js/viewer.js").read_text("utf-8")
        self.assertIn("XMLHttpRequest", kaynak, "fetch yedeği yok")
        self.assertIn("typeof window.fetch === 'function'", kaynak)
        self.assertIn("BasitSoz", kaynak, "Promise yedeği yok")

        # Eski tarayıcıların anlamadığı sözdizimi sızmamalı.
        for yasak in ("=>", "`", "const ", "let "):
            self.assertNotIn(yasak, kaynak, f"eski tarayıcıda çalışmaz: {yasak!r}")

    def test_viewer_css_ozel_degisken_icin_yedek_renk_tasir(self):
        """var() desteklemeyen tarayıcıda renkler kaybolmamalı."""
        import re
        from pathlib import Path

        from django.conf import settings

        kaynak = (Path(settings.BASE_DIR) / "static/ekran/css/viewer.css").read_text("utf-8")
        govde = kaynak[kaynak.index("}", kaynak.index(":root")):]  # :root bloğunu atla

        for eslesme in re.finditer(r"^(\s*)([a-z-]+): var\((--[a-z-]+)\);$", govde, re.M):
            bosluk, ozellik = eslesme.group(1), eslesme.group(2)
            oncesi = govde[:eslesme.start()].rstrip().split("\n")[-1].strip()
            self.assertTrue(
                oncesi.startswith(ozellik + ":"),
                f"{ozellik}: var(...) için düz değer yedeği yok",
            )
