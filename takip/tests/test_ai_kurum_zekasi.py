"""Kurum zekası — kural tabanlı fallback (OpenAI yokken 500 olmamalı)."""

from django.contrib.auth.models import User
from django.test import TestCase

from takip.ai_context import kurum_baglam
from takip.ai_service import kurum_zekasi_ozet


class KurumZekasiFallbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "qa_ai_bot", "qa_ai@example.com", "test-pass"
        )

    def test_kurum_baglam_toplam_soru_alani(self):
        baglam = kurum_baglam(self.user)
        self.assertIn("bu_ay_soru_toplam", baglam)
        self.assertIsInstance(baglam["bu_ay_soru_toplam"], int)

    def test_kurum_zekasi_ozet_openai_olmadan(self):
        sonuc = kurum_zekasi_ozet(self.user, yenile=True)
        self.assertTrue(sonuc.bolumler)
        self.assertFalse(sonuc.yapay_zeka)
        self.assertEqual(sonuc.tur, "kurum_zekasi")

    def test_baglam_json_decimal(self):
        from decimal import Decimal
        from takip.ai_context import baglam_json

        raw = baglam_json({"toplam_net": Decimal("12.50")})
        self.assertIn("12.5", raw)


class DuyuruGorselFallbackTests(TestCase):
    def test_missing_file_is_not_gorsel_var(self):
        from django.core.files.base import ContentFile
        from django.utils.timezone import localdate
        from takip.models import Duyuru

        duyuru = Duyuru(
            baslik="QA missing",
            ozet="test",
            baslangic=localdate(),
            aktif=True,
        )
        duyuru.gorsel.name = "duyurular/does-not-exist-qa.png"
        self.assertFalse(duyuru.gorsel_var_mi)

    def test_saved_file_is_gorsel_var(self):
        from django.core.files.base import ContentFile
        from django.utils.timezone import localdate
        from takip.models import Duyuru

        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        duyuru = Duyuru(
            baslik="QA file",
            ozet="test",
            baslangic=localdate(),
            aktif=True,
        )
        duyuru.gorsel.save("qa_sprint5.png", ContentFile(png), save=False)
        duyuru.save()
        self.assertTrue(duyuru.gorsel_var_mi)

