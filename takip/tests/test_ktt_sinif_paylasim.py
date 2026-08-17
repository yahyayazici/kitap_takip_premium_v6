from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from takip.ktt_models import KttSinav
from takip.ktt_service import ktt_duzenleyebilir, ktt_sonuc_girebilir, yetkili_ktt_sinavlari
from takip.models import Ders, EtutHocasi, SinifSube
from takip.ss_deneme_models import SozelSayisalDeneme
from takip.ss_deneme_service import ss_sonuc_girebilir, yetkili_ss_denemeler


def _can_ktt(user, modul, islem):
    return modul == "ktt" and islem in {"view", "create", "edit"}


class KttSinifPaylasimTests(TestCase):
    def setUp(self):
        self.sinif = SinifSube.objects.create(sinif="8", sube="A")
        self.ders = Ders.objects.create(ad="Matematik", sira=1, aktif=True)
        self.user_a = User.objects.create_user("hoca8a", password="x")
        self.user_b = User.objects.create_user("hoca8b", password="x")
        self.hoca_a = EtutHocasi.objects.create(ad_soyad="Hoca A", user=self.user_a)
        self.hoca_b = EtutHocasi.objects.create(ad_soyad="Hoca B", user=self.user_b)
        self.hoca_a.sorumlu_sinif_subeler.add(self.sinif)
        self.hoca_b.sorumlu_sinif_subeler.add(self.sinif)
        self.ktt = KttSinav.objects.create(
            ad="8. Sınıf KTT",
            ders=self.ders,
            sinif_seviyesi="8",
            hedef_siniflar="8-A",
            sinav_tarihi=date(2026, 8, 17),
            soru_sayisi=20,
            etut_hocasi=self.hoca_a,
            olusturan=self.user_a,
        )

    @patch("takip.ktt_service.can", side_effect=_can_ktt)
    def test_diger_8_hocasi_mevcut_ktt_yi_gorur(self, _can):
        ids = set(yetkili_ktt_sinavlari(self.user_b).values_list("pk", flat=True))
        self.assertIn(self.ktt.pk, ids)
        self.assertTrue(ktt_sonuc_girebilir(self.user_b, self.ktt))
        self.assertFalse(ktt_duzenleyebilir(self.user_b, self.ktt))

    @patch("takip.ktt_service.can", side_effect=_can_ktt)
    def test_ayni_seviye_farkli_sube_hocasi_gorur(self, _can):
        user_8b = User.objects.create_user("hoca8bsube", password="x")
        hoca_8b = EtutHocasi.objects.create(ad_soyad="Hoca 8B", user=user_8b)
        sinif_8b = SinifSube.objects.create(sinif="8", sube="B")
        hoca_8b.sorumlu_sinif_subeler.add(sinif_8b)
        ids = set(yetkili_ktt_sinavlari(user_8b).values_list("pk", flat=True))
        self.assertIn(self.ktt.pk, ids)

    @patch("takip.ktt_service.can", side_effect=_can_ktt)
    def test_hedef_sinifsiz_eski_ktt_de_paylasilir(self, _can):
        eski = KttSinav.objects.create(
            ad="Eski 8 KTT",
            ders=self.ders,
            sinif_seviyesi="8",
            hedef_siniflar="",
            sinav_tarihi=date(2026, 3, 1),
            soru_sayisi=15,
            etut_hocasi=self.hoca_a,
            olusturan=self.user_a,
        )
        ids = set(yetkili_ktt_sinavlari(self.user_b).values_list("pk", flat=True))
        self.assertIn(eski.pk, ids)

    @patch("takip.ktt_service.can", side_effect=_can_ktt)
    def test_farkli_seviye_hocasi_gormez(self, _can):
        user_7 = User.objects.create_user("hoca7", password="x")
        hoca_7 = EtutHocasi.objects.create(ad_soyad="Hoca 7", user=user_7)
        sinif_7 = SinifSube.objects.create(sinif="7", sube="A")
        hoca_7.sorumlu_sinif_subeler.add(sinif_7)
        ids = set(yetkili_ktt_sinavlari(user_7).values_list("pk", flat=True))
        self.assertNotIn(self.ktt.pk, ids)


class SsDenemeSinifPaylasimTests(TestCase):
    def setUp(self):
        self.sinif = SinifSube.objects.create(sinif="8", sube="A")
        self.user_a = User.objects.create_user("ss8a", password="x")
        self.user_b = User.objects.create_user("ss8b", password="x")
        self.hoca_a = EtutHocasi.objects.create(ad_soyad="SS A", user=self.user_a)
        self.hoca_b = EtutHocasi.objects.create(ad_soyad="SS B", user=self.user_b)
        self.hoca_a.sorumlu_sinif_subeler.add(self.sinif)
        self.hoca_b.sorumlu_sinif_subeler.add(self.sinif)
        self.deneme = SozelSayisalDeneme.objects.create(
            ad="8. Sözel Sayısal",
            sinav_tarihi=date(2026, 8, 17),
            soru_formati=90,
            sinif_seviyesi="8",
            hedef_siniflar="8-A",
            etut_hocasi=self.hoca_a,
            olusturan=self.user_a,
        )

    @patch("takip.ss_deneme_service.can", side_effect=_can_ktt)
    @patch("takip.ktt_service.can", side_effect=_can_ktt)
    def test_diger_8_hocasi_ss_denemeyi_gorur(self, _c1, _c2):
        ids = set(yetkili_ss_denemeler(self.user_b).values_list("pk", flat=True))
        self.assertIn(self.deneme.pk, ids)
        self.assertTrue(ss_sonuc_girebilir(self.user_b, self.deneme))
