"""Güvenlik Sprint 1 — veli hesap şifre güvenliği regresyon testleri.

Kapsam:
- Yeni veli hesabı artık TC son 4 hane şifre kullanmıyor (secrets ile üretilmiş).
- Mevcut hesap `veli_panel_ensure` ile tekrar "ensure" edildiğinde şifre
  hash'i DEĞİŞMİYOR (önceki bug: her çağrıda TC son 4'e resetleniyordu).
"""

from django.contrib.auth.models import User
from django.test import TestCase

from takip.models import EtutHocasi, SinifSube, Talebe
from takip.tc_util import veli_sifre_tc_son4
from takip.veli_hesap_util import gecici_sifre_uret, veli_panel_ensure


class VeliGeciciSifreUretTests(TestCase):
    def test_uretilen_sifre_yeterli_uzunlukta(self):
        sifre = gecici_sifre_uret()
        self.assertGreaterEqual(len(sifre), 10)

    def test_uretilen_sifreler_tekrarlanmiyor(self):
        sifreler = {gecici_sifre_uret() for _ in range(50)}
        # 50 üretimde çakışma olasılığı ihmal edilebilir düzeyde olmalı.
        self.assertEqual(len(sifreler), 50)

    def test_karisik_karakterler_haric(self):
        sifre = gecici_sifre_uret()
        for karakter in "0O1Il":
            self.assertNotIn(karakter, sifre)


class VeliPanelEnsureYeniHesapTests(TestCase):
    def setUp(self):
        sinif = SinifSube.objects.create(sinif="6", sube="A")
        hoca_user = User.objects.create_user("hoca-veli-test", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Test Hoca", user=hoca_user)
        self.hoca.sorumlu_sinif_subeler.add(sinif)
        self.talebe = Talebe.objects.create(
            ad_soyad="Test Talebe",
            sinif_sube=sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            tc_kimlik="12345678901",
        )

    def test_yeni_hesap_tc_son4_sifre_kullanmiyor(self):
        sonuc = veli_panel_ensure(self.talebe, "12345678901", "Ayşe Test", "0532 000 00 00")

        self.assertTrue(sonuc.basarili)
        self.assertTrue(sonuc.olusturuldu)
        self.assertIsNotNone(sonuc.gecici_sifre)

        tc_son4 = veli_sifre_tc_son4("12345678901")
        self.assertNotEqual(sonuc.gecici_sifre, tc_son4)

        user = User.objects.get(username="12345678901")
        self.assertFalse(user.check_password(tc_son4))
        self.assertTrue(user.check_password(sonuc.gecici_sifre))

    def test_gecici_sifre_yeterince_uzun(self):
        sonuc = veli_panel_ensure(self.talebe, "12345678901", "Ayşe Test")
        self.assertGreaterEqual(len(sonuc.gecici_sifre), 10)


class VeliPanelEnsureMevcutHesapIdempotencyTests(TestCase):
    """Kritik regresyon: mevcut hesabın şifresi ensure() ile resetlenmemeli."""

    def setUp(self):
        sinif = SinifSube.objects.create(sinif="6", sube="A")
        hoca_user = User.objects.create_user("hoca-veli-test2", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Test Hoca", user=hoca_user)
        self.hoca.sorumlu_sinif_subeler.add(sinif)
        self.talebe = Talebe.objects.create(
            ad_soyad="Test Talebe",
            sinif_sube=sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            tc_kimlik="12345678901",
        )
        ilk_sonuc = veli_panel_ensure(self.talebe, "12345678901", "Ayşe Test")
        self.assertTrue(ilk_sonuc.olusturuldu)

        self.user = User.objects.get(username="12345678901")
        # Veli kendi şifresini değiştirmiş gibi simüle ediyoruz.
        self.user.set_password("VelininKendiSifresi!2026")
        self.user.save()
        self.onceki_hash = self.user.password

    def test_tekrar_ensure_edildiginde_sifre_hash_degismiyor(self):
        sonuc = veli_panel_ensure(self.talebe, "12345678901", "Ayşe Test Güncel")

        self.assertTrue(sonuc.basarili)
        self.assertFalse(sonuc.olusturuldu)
        self.assertIsNone(sonuc.gecici_sifre)

        self.user.refresh_from_db()
        self.assertEqual(self.user.password, self.onceki_hash)
        self.assertTrue(self.user.check_password("VelininKendiSifresi!2026"))

    def test_tekrar_ensure_edildiginde_ad_guncellenir(self):
        veli_panel_ensure(self.talebe, "12345678901", "Ayşe Test Güncel")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ayşe Test Güncel")

    def test_coklu_tekrar_ensure_sifreyi_bozmuyor(self):
        # Excel toplu içe aktarımda aynı satır birden çok kez işlenebilir.
        for _ in range(5):
            veli_panel_ensure(self.talebe, "12345678901", "Ayşe Test")
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, self.onceki_hash)
