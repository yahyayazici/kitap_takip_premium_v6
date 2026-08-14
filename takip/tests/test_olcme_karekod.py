"""Ölçme optik karekod testleri."""

from django.test import SimpleTestCase

from takip.olcme_qr import (
    optik_foto_deep_link,
    optik_karekod_metni,
    optik_karekod_parse,
    optik_karekod_png_data_uri,
    optik_karekod_svg,
)


class OlcumKarekodTests(SimpleTestCase):
    def test_metin_ve_parse(self):
        class Talebe:
            pk = 12
            talebe_no = 56

        metin = optik_karekod_metni(5, Talebe(), "A")
        self.assertEqual(metin, "OLCME;S5;T12;N56;KA")
        parsed = optik_karekod_parse(metin)
        self.assertEqual(parsed["sinav_id"], 5)
        self.assertEqual(parsed["talebe_id"], 12)
        self.assertEqual(parsed["kitapcik"], "A")

    def test_png_ve_svg(self):
        metin = "OLCME;S1;T2;N3;KA"
        png = optik_karekod_png_data_uri(metin)
        self.assertTrue(png.startswith("data:image/png;base64,"))
        svg = optik_karekod_svg(metin)
        self.assertIn("<svg", svg)

    def test_url_parse(self):
        url = "http://127.0.0.1:8000/olcme/sinav/7/optik-foto/?talebe=67&kitapcik=A"
        parsed = optik_karekod_parse(url)
        self.assertEqual(parsed["sinav_id"], 7)
        self.assertEqual(parsed["talebe_id"], 67)
        self.assertEqual(parsed["kitapcik"], "A")

    def test_deep_link_qr(self):
        link = optik_foto_deep_link(
            "http://127.0.0.1:8000/olcme/sinav/7/optik-foto/",
            67,
            "A",
        )
        self.assertIn("talebe=67", link)
        self.assertIn("kitapcik=A", link)
