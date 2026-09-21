"""Akıllı Tahta Dosya Merkezi — madde 13'teki senaryoları kapsayan testler.

Testler modülün aşamaları ilerledikçe bu dosyaya eklenir.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from takip.akilli_tahta_models import AkilliTahtaDosya, AkilliTahtaHedef, AkilliTahtaHesap
from takip.models import EtutHocasi, PersonelProfili


def sahte_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"0" * 64


def sahte_pdf() -> bytes:
    return b"%PDF-1.4\n" + b"0" * 64


def sahte_mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42" + b"0" * 64


class AkilliTahtaYuklemeTests(TestCase):
    """Senaryo 1, 2, 10, 11: yükleme, yetkisiz kullanıcı, hatalı dosya, sahiplik."""

    def setUp(self):
        self.hoca_user = User.objects.create_user("etuthocasi1", password="test12345")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Ayşe Hoca", user=self.hoca_user)

        self.diger_hoca_user = User.objects.create_user("etuthocasi2", password="test12345")
        EtutHocasi.objects.create(ad_soyad="Mehmet Hoca", user=self.diger_hoca_user)

        self.yetkisiz_user = User.objects.create_user("veli1", password="test12345")

    def _yukleme_verisi(self, **ek):
        veri = {
            "baslik": "5. Sınıf Matematik Denemesi",
            "icerik_turu": AkilliTahtaDosya.IcerikTuru.DENEME,
            "tum_siniflar": "",
            "hedef_sinif_seviyeleri": ["5"],
            "yayin_baslangic": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "ust_sirada": "",
            "indirme_izni": "on",
        }
        veri.update(ek)
        return veri

    def test_etut_hocasi_pdf_yukleyebiliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        yanit = self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(yanit.status_code, 302)
        kayit = AkilliTahtaDosya.objects.get(baslik="5. Sınıf Matematik Denemesi")
        self.assertEqual(kayit.dosya_turu, "pdf")
        self.assertEqual(kayit.yukleyen, self.hoca_user)
        self.assertEqual(kayit.durum, AkilliTahtaDosya.Durum.YAYINDA)
        self.assertTrue(kayit.hedefler.filter(sinif_seviyesi="5").exists())

    def test_yetkisiz_kullanici_dosya_yukleyemiyor(self):
        self.client.force_login(self.yetkisiz_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        yanit = self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)
        # Yetki reddi -> dashboard'a yönlendirilir (require_permission deseni)
        self.assertEqual(yanit.status_code, 302)

    def test_anonim_kullanici_yukleme_sayfasina_giremiyor(self):
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        yanit = self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)
        self.assertIn(yanit.status_code, (302, 403))

    def test_yanlis_dosya_turu_reddediliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("virus.exe", b"MZ" + b"0" * 64)
        yanit = self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)
        self.assertEqual(yanit.status_code, 200)

    def test_icerigi_uzantisiyla_uyusmayan_dosya_reddediliyor(self):
        self.client.force_login(self.hoca_user)
        # .pdf uzantılı ama içeriği PNG olan sahte dosya
        dosya = SimpleUploadedFile("sahte.pdf", sahte_png(), content_type="application/pdf")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)

    @override_settings(AKILLI_TAHTA_MAKS_GORSEL_MB=0)
    def test_asiri_buyuk_dosya_reddediliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("buyuk.png", sahte_png(), content_type="image/png")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        self.assertEqual(AkilliTahtaDosya.objects.count(), 0)

    def test_etut_hocasi_kendi_dosyasini_yonetebiliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        kayit = AkilliTahtaDosya.objects.get(baslik="5. Sınıf Matematik Denemesi")

        yanit = self.client.post(reverse("akilli_tahta:arsivle", args=[kayit.pk]))
        self.assertEqual(yanit.status_code, 302)
        kayit.refresh_from_db()
        self.assertEqual(kayit.durum, AkilliTahtaDosya.Durum.ARSIVLENDI)

    def test_baska_hocanin_dosyasini_yonetemiyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, yayimla="1"),
        )
        kayit = AkilliTahtaDosya.objects.get(baslik="5. Sınıf Matematik Denemesi")

        self.client.force_login(self.diger_hoca_user)
        yanit = self.client.post(reverse("akilli_tahta:arsivle", args=[kayit.pk]))
        kayit.refresh_from_db()
        self.assertNotEqual(kayit.durum, AkilliTahtaDosya.Durum.ARSIVLENDI)
        self.assertEqual(yanit.status_code, 302)

    def test_tum_siniflara_gonderilen_dosya_hedeflerde_yok(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("video.mp4", sahte_mp4(), content_type="video/mp4")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(
                baslik="Tüm Sınıf Videosu",
                dosya=dosya,
                tum_siniflar="on",
                hedef_sinif_seviyeleri=[],
                icerik_turu=AkilliTahtaDosya.IcerikTuru.VIDEO,
                yayimla="1",
            ),
        )
        kayit = AkilliTahtaDosya.objects.get(baslik="Tüm Sınıf Videosu")
        self.assertTrue(kayit.tum_siniflar)
        self.assertEqual(kayit.hedefler.count(), 0)
        for seviye in ("5", "6", "7", "8"):
            self.assertTrue(kayit.hedefliyor_mu(seviye))

    def test_taslak_kaydedilebiliyor(self):
        self.client.force_login(self.hoca_user)
        dosya = SimpleUploadedFile("deneme.pdf", sahte_pdf(), content_type="application/pdf")
        self.client.post(
            reverse("akilli_tahta:yukle"),
            data=self._yukleme_verisi(dosya=dosya, taslak="1"),
        )
        kayit = AkilliTahtaDosya.objects.get(baslik="5. Sınıf Matematik Denemesi")
        self.assertEqual(kayit.durum, AkilliTahtaDosya.Durum.TASLAK)


def _dosya_olustur(yukleyen, **ek):
    veri = dict(
        baslik="Test Dosyası",
        dosya=SimpleUploadedFile("t.pdf", sahte_pdf(), content_type="application/pdf"),
        dosya_turu="pdf",
        icerik_turu=AkilliTahtaDosya.IcerikTuru.DENEME,
        yayin_baslangic=timezone.now() - timedelta(hours=1),
        durum=AkilliTahtaDosya.Durum.YAYINDA,
        yukleyen=yukleyen,
        dosya_hash="abc123",
        dosya_boyutu=100,
    )
    veri.update(ek)
    return AkilliTahtaDosya.objects.create(**veri)


class AkilliTahtaHesapVeGirisTests(TestCase):
    """Senaryo 3, 4, 5, 6, 7, 8, 9: hedefleme, yaşam döngüsü, giriş kısıtları."""

    def setUp(self):
        self.hoca_user = User.objects.create_user("hoca_giris", password="test12345")
        EtutHocasi.objects.create(ad_soyad="Test Hoca", user=self.hoca_user)

        self.tahta5_user = User.objects.create_user("tahta5", password="test12345")
        self.tahta5 = AkilliTahtaHesap.objects.create(user=self.tahta5_user, sinif_seviyesi="5")

        self.tahta6_user = User.objects.create_user("tahta6", password="test12345")
        self.tahta6 = AkilliTahtaHesap.objects.create(user=self.tahta6_user, sinif_seviyesi="6")

    def test_giris_yapan_tahta_hesabi_tahta_ekranina_yonlendiriliyor(self):
        yanit = self.client.post(
            reverse("login"),
            {"username": "tahta5", "password": "test12345"},
        )
        self.assertRedirects(yanit, reverse("akilli_tahta_tahta:ekran"))

    def test_5_sinif_dosyasi_5_sinif_tahtasinda_gorunuyor_6da_gorunmuyor(self):
        dosya = _dosya_olustur(self.hoca_user, tum_siniflar=False)
        AkilliTahtaHedef.objects.create(dosya=dosya, sinif_seviyesi="5")

        self.client.force_login(self.tahta5_user)
        yanit = self.client.get(reverse("akilli_tahta_tahta:ekran"))
        self.assertContains(yanit, "Test Dosyası")

        self.client.force_login(self.tahta6_user)
        yanit = self.client.get(reverse("akilli_tahta_tahta:ekran"))
        self.assertNotContains(yanit, "Test Dosyası")

        # 6. sınıf hesabı, doğrudan dosya bağlantısına gitse bile göremez.
        yanit = self.client.get(reverse("akilli_tahta_tahta:goruntule", args=[dosya.pk]))
        self.assertEqual(yanit.status_code, 404)

    def test_tum_siniflara_gonderilen_dosya_dort_hesapta_da_gorunuyor(self):
        _dosya_olustur(self.hoca_user, baslik="Herkese Açık", tum_siniflar=True)

        for seviye, user in (("5", self.tahta5_user), ("6", self.tahta6_user)):
            self.client.force_login(user)
            yanit = self.client.get(reverse("akilli_tahta_tahta:ekran"))
            self.assertContains(yanit, "Herkese Açık")

    def test_taslak_dosya_tahtada_gorunmuyor(self):
        dosya = _dosya_olustur(
            self.hoca_user, baslik="Taslak Dosya", tum_siniflar=True,
            durum=AkilliTahtaDosya.Durum.TASLAK,
        )
        self.client.force_login(self.tahta5_user)
        yanit = self.client.get(reverse("akilli_tahta_tahta:ekran"))
        self.assertNotContains(yanit, "Taslak Dosya")
        self.assertEqual(
            self.client.get(reverse("akilli_tahta_tahta:goruntule", args=[dosya.pk])).status_code,
            404,
        )

    def test_yayin_zamani_gelmeyen_dosya_gorunmuyor(self):
        _dosya_olustur(
            self.hoca_user, baslik="Gelecek Dosya", tum_siniflar=True,
            yayin_baslangic=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.tahta5_user)
        yanit = self.client.get(reverse("akilli_tahta_tahta:ekran"))
        self.assertNotContains(yanit, "Gelecek Dosya")

    def test_suresi_dolmus_dosya_aktif_listede_gorunmuyor(self):
        _dosya_olustur(
            self.hoca_user, baslik="Eski Dosya", tum_siniflar=True,
            yayin_baslangic=timezone.now() - timedelta(days=10),
            yayin_bitis=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.tahta5_user)
        yanit = self.client.get(reverse("akilli_tahta_tahta:ekran"))
        self.assertNotContains(yanit, "Eski Dosya")

    def test_pasif_tahta_hesabi_giris_yapamiyor(self):
        self.tahta5_user.is_active = False
        self.tahta5_user.save()
        self.tahta5.aktif = False
        self.tahta5.save()

        giris_oldu = self.client.login(username="tahta5", password="test12345")
        self.assertFalse(giris_oldu)

    def test_pasif_hesap_mevcut_oturumda_da_engelleniyor(self):
        self.client.force_login(self.tahta5_user)
        self.tahta5.aktif = False
        self.tahta5.save()
        yanit = self.client.get(reverse("akilli_tahta_tahta:ekran"))
        self.assertRedirects(yanit, reverse("dashboard"))

    def test_tahta_hesabi_yukleme_ekranina_giremiyor(self):
        self.client.force_login(self.tahta5_user)
        yanit = self.client.get(reverse("akilli_tahta:yukle"))
        self.assertNotEqual(yanit.status_code, 200)

    def test_tahta_hesabi_panel_listesine_giremiyor(self):
        self.client.force_login(self.tahta5_user)
        yanit = self.client.get(reverse("akilli_tahta:liste"))
        self.assertNotEqual(yanit.status_code, 200)


class AkilliTahtaYoneticiTests(TestCase):
    """Senaryo 12: yönetici bütün dosyaları ve hesapları yönetebiliyor."""

    def setUp(self):
        self.idareci_user = User.objects.create_user("idareci1", password="test12345")
        PersonelProfili.objects.create(
            user=self.idareci_user, ad_soyad="İdareci", ana_rol=PersonelProfili.Rol.IDARECI
        )

        self.hoca_user = User.objects.create_user("hoca_admin_test", password="test12345")
        EtutHocasi.objects.create(ad_soyad="Test Hoca", user=self.hoca_user)

    def test_yonetici_baska_hocanin_dosyasini_arsivleyebiliyor(self):
        dosya = _dosya_olustur(self.hoca_user, tum_siniflar=True)
        self.client.force_login(self.idareci_user)
        yanit = self.client.post(reverse("akilli_tahta:arsivle", args=[dosya.pk]))
        self.assertEqual(yanit.status_code, 302)
        dosya.refresh_from_db()
        self.assertEqual(dosya.durum, AkilliTahtaDosya.Durum.ARSIVLENDI)

    def test_yonetici_liste_ekraninda_tum_dosyalari_gorur(self):
        _dosya_olustur(self.hoca_user, baslik="Hoca Dosyası", tum_siniflar=True)
        self.client.force_login(self.idareci_user)
        yanit = self.client.get(reverse("akilli_tahta:liste"))
        self.assertContains(yanit, "Hoca Dosyası")

    def test_hoca_liste_ekraninda_baskasinin_dosyasini_gormez(self):
        _dosya_olustur(self.hoca_user, baslik="Hoca Dosyası", tum_siniflar=True)
        diger_hoca = User.objects.create_user("baska_hoca", password="test12345")
        EtutHocasi.objects.create(ad_soyad="Başka Hoca", user=diger_hoca)
        self.client.force_login(diger_hoca)
        yanit = self.client.get(reverse("akilli_tahta:liste"))
        self.assertNotContains(yanit, "Hoca Dosyası")

    def test_yonetici_tahta_hesabi_olusturabiliyor(self):
        self.client.force_login(self.idareci_user)
        yanit = self.client.post(
            reverse("akilli_tahta_yonetim:hesap_olustur"),
            {"username": "tahta7", "password": "GucluSifre123!", "sinif_seviyesi": "7", "aktif": "on"},
        )
        self.assertEqual(yanit.status_code, 302)
        hesap = AkilliTahtaHesap.objects.get(sinif_seviyesi="7")
        self.assertEqual(hesap.user.username, "tahta7")
        self.assertTrue(hesap.user.check_password("GucluSifre123!"))

    def test_ayni_seviye_icin_ikinci_hesap_olusturulamiyor(self):
        user = User.objects.create_user("tahta8a", password="test12345")
        AkilliTahtaHesap.objects.create(user=user, sinif_seviyesi="8")

        self.client.force_login(self.idareci_user)
        yanit = self.client.post(
            reverse("akilli_tahta_yonetim:hesap_olustur"),
            {"username": "tahta8b", "password": "GucluSifre123!", "sinif_seviyesi": "8", "aktif": "on"},
        )
        self.assertEqual(yanit.status_code, 200)
        self.assertEqual(AkilliTahtaHesap.objects.filter(sinif_seviyesi="8").count(), 1)

    def test_yonetici_hesabi_pasif_yapinca_oturumlar_kapaniyor(self):
        tahta_user = User.objects.create_user("tahta_pasif", password="test12345")
        hesap = AkilliTahtaHesap.objects.create(user=tahta_user, sinif_seviyesi="6")
        self.client.force_login(tahta_user)
        self.client.get(reverse("akilli_tahta_tahta:ekran"))  # oturumu oluştur

        self.client.force_login(self.idareci_user)
        self.client.post(
            reverse("akilli_tahta_yonetim:hesap_duzenle", args=[hesap.pk]),
            {},  # aktif kutusunu boş bırak -> pasif
        )
        hesap.refresh_from_db()
        self.assertFalse(hesap.aktif)
        self.assertFalse(User.objects.get(pk=tahta_user.pk).is_active)

    def test_etut_hocasi_hesap_yonetimine_giremiyor(self):
        self.client.force_login(self.hoca_user)
        yanit = self.client.get(reverse("akilli_tahta_yonetim:hesap_listesi"))
        self.assertNotEqual(yanit.status_code, 200)


class AkilliTahtaCanliGuncellemeTests(TestCase):
    """Aşama 7: polling ile canlı güncelleme."""

    def setUp(self):
        self.hoca_user = User.objects.create_user("hoca_canli", password="test12345")
        EtutHocasi.objects.create(ad_soyad="Canlı Hoca", user=self.hoca_user)
        self.tahta_user = User.objects.create_user("tahta_canli", password="test12345")
        self.hesap = AkilliTahtaHesap.objects.create(user=self.tahta_user, sinif_seviyesi="5")

    def test_durum_ucu_degisiklik_gosterir(self):
        self.client.force_login(self.tahta_user)
        ilk = self.client.get(reverse("akilli_tahta_tahta:durum")).json()

        _dosya_olustur(self.hoca_user, baslik="Yeni Dosya", tum_siniflar=True)

        ikinci = self.client.get(reverse("akilli_tahta_tahta:durum")).json()
        self.assertNotEqual(ilk["son_guncelleme"], ikinci["son_guncelleme"])

    def test_icerik_ucu_yeni_dosyayi_iceriyor(self):
        _dosya_olustur(self.hoca_user, baslik="Poll Dosyası", tum_siniflar=True)
        self.client.force_login(self.tahta_user)
        yanit = self.client.get(reverse("akilli_tahta_tahta:icerik"))
        self.assertContains(yanit, "Poll Dosyası")

    def test_normal_kullanici_durum_ucuna_giremiyor(self):
        self.client.force_login(self.hoca_user)
        yanit = self.client.get(reverse("akilli_tahta_tahta:durum"))
        self.assertEqual(yanit.status_code, 302)
