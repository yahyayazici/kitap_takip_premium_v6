from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from takip.models import (
    EtutHocasi,
    Talebe,
    TemizlikAlani,
    TemizlikGorevlisi,
    TemizlikKatSorumlusu,
    TemizlikKati,
    TemizlikListesi,
)
from takip.temizlik_service import sabit_temizlik_katlari, sabit_temizlik_satirlari


class SabitTemizlikListesiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("tzadmin", "tz@example.com", "x")
        self.hoca_user = User.objects.create_user("tzhoca", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Kat Temizlikçisi", user=self.hoca_user)
        self.liste = TemizlikListesi.objects.create(
            ad="Sabit Temizlik",
            baslangic_tarihi=date(2020, 1, 1),
            bitis_tarihi=date(2030, 12, 31),
            aktif=True,
        )
        self.kat_a = TemizlikKati.objects.create(liste=self.liste, ad="1. KAT", sira=1)
        self.kat_b = TemizlikKati.objects.create(liste=self.liste, ad="2. KAT", sira=2)
        self.mahal_a = TemizlikAlani.objects.create(ad="KORİDOR", kat=self.kat_a, sira=1)
        self.mahal_b = TemizlikAlani.objects.create(ad="WC", kat=self.kat_b, sira=1)
        self.liste.alanlar.add(self.mahal_a, self.mahal_b)
        TemizlikKatSorumlusu.objects.create(kat=self.kat_a, personel=self.hoca_user)
        self.talebe = Talebe.objects.create(
            ad_soyad="Görevli Talebe",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        TemizlikGorevlisi.objects.create(
            liste=self.liste, alan=self.mahal_a, talebe=self.talebe
        )

    def test_kat_temizlikcisi_sadece_kendi_katini_gorur(self):
        kartlar = sabit_temizlik_katlari(self.hoca_user)
        self.assertEqual([k["kat"].ad for k in kartlar], ["1. KAT"])
        satirlar = sabit_temizlik_satirlari(self.hoca_user)
        self.assertEqual(len(satirlar), 1)
        self.assertEqual(satirlar[0]["alan"].ad, "KORİDOR")

    def test_admin_tum_katlari_gorur(self):
        kartlar = sabit_temizlik_katlari(self.admin)
        self.assertEqual([k["kat"].ad for k in kartlar], ["1. KAT", "2. KAT"])

    def test_temizlikci_gorevli_veya_kat_sorumlusu(self):
        satirlar = sabit_temizlik_satirlari(self.hoca_user)
        self.assertEqual(satirlar[0]["temizlikciler"], ["Görevli Talebe"])
        bos_kat = sabit_temizlik_satirlari(self.admin)
        ikinci = next(s for s in bos_kat if s["alan"].ad == "WC")
        self.assertEqual(ikinci["temizlikciler"], [])