from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from takip.gunluk_takip_models import GunlukTakipKaydi
from takip.gunluk_takip_service import etut_sinif_secenekleri, etut_yoklama_kaydet, etut_yoklama_satirlari
from takip.models import EtutHocasi, SinifSube, Talebe


class EtutYoklamaKursDevamTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("gtqa", "gtqa@example.com", "x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Test Hoca", user=self.user)
        self.sinif_a = SinifSube.objects.create(sinif="5", sube="A")
        self.sinif_b = SinifSube.objects.create(sinif="5", sube="B")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif_a, self.sinif_b)
        self.gelmeyen = Talebe.objects.create(
            ad_soyad="Ahmet Gelmedi",
            sinif_sube=self.sinif_a,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.gelen = Talebe.objects.create(
            ad_soyad="Mehmet Geldi",
            sinif_sube=self.sinif_b,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.gec = Talebe.objects.create(
            ad_soyad="Ali Gec",
            sinif_sube=self.sinif_a,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.tarih = date(2026, 8, 17)

    def test_devamsiz_kursa_gelmedi_olarak_islenir(self):
        GunlukTakipKaydi.objects.create(
            talebe=self.gec,
            tarih=self.tarih,
            devam=GunlukTakipKaydi.DevamDurumu.GEC,
            etut_katilim=True,
        )
        etut_yoklama_kaydet(self.user, self.tarih, {self.gelmeyen.pk})

        gelmeyen = GunlukTakipKaydi.objects.get(talebe=self.gelmeyen, tarih=self.tarih)
        gelen = GunlukTakipKaydi.objects.get(talebe=self.gelen, tarih=self.tarih)
        gec = GunlukTakipKaydi.objects.get(talebe=self.gec, tarih=self.tarih)

        self.assertEqual(gelmeyen.devam, GunlukTakipKaydi.DevamDurumu.GELMEDI)
        self.assertFalse(gelmeyen.etut_katilim)
        self.assertEqual(gelen.devam, GunlukTakipKaydi.DevamDurumu.GELDI)
        self.assertTrue(gelen.etut_katilim)
        self.assertEqual(gec.devam, GunlukTakipKaydi.DevamDurumu.GEC)
        self.assertTrue(gec.etut_katilim)

    def test_sinif_secenekleri(self):
        satirlar = etut_yoklama_satirlari(self.user, self.tarih)
        secenekler = etut_sinif_secenekleri(satirlar)
        self.assertEqual(
            [(c["key"], c["label"]) for c in secenekler],
            [("5-A", "5/A"), ("5-B", "5/B")],
        )
