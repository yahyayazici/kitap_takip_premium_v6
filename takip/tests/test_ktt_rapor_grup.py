from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from takip.ktt_models import KttSinav, KttSonucu
from takip.ktt_service import (
    ktt_hafta_cozulen_soru,
    ktt_rapor_filtrele,
    ktt_rapor_grupla,
    ktt_rapor_istatistik,
)
from takip.models import Ders, EtutHocasi, SinifSube, Talebe


class KttRaporGrupTests(TestCase):
    def setUp(self):
        sinif = SinifSube.objects.create(sinif="5", sube="A")
        self.ders = Ders.objects.create(ad="Türkçe", sira=1, aktif=True)
        user = User.objects.create_user("ktt-rapor-hoca", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Rapor Hoca", user=user)
        self.hoca.sorumlu_sinif_subeler.add(sinif)
        self.talebe_a = Talebe.objects.create(
            ad_soyad="Ayşe Yılmaz",
            sinif_sube=sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.talebe_b = Talebe.objects.create(
            ad_soyad="Mehmet Demir",
            sinif_sube=sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.ktt_a = self._ktt("Workwin Türkçe", 20, date(2026, 9, 26))
        self.ktt_b = self._ktt("Fen Bilimleri", 10, date(2026, 9, 22))
        KttSonucu.objects.create(ktt=self.ktt_a, talebe=self.talebe_a, dogru=12, yanlis=4, bos=4)
        KttSonucu.objects.create(ktt=self.ktt_a, talebe=self.talebe_b, dogru=10, yanlis=5, bos=5)
        KttSonucu.objects.create(ktt=self.ktt_b, talebe=self.talebe_a, dogru=6, yanlis=2, bos=2)

    def _ktt(self, ad, soru, gun):
        return KttSinav.objects.create(
            ad=ad,
            ders=self.ders,
            sinif_seviyesi="5",
            hedef_siniflar="5-A",
            sinav_tarihi=gun,
            soru_sayisi=soru,
            etut_hocasi=self.hoca,
        )

    def test_araliktaki_cozulen_soru_toplami(self):
        istatistik = ktt_rapor_istatistik(KttSonucu.objects.all())
        self.assertEqual(istatistik["toplam_sonuc"], 3)
        self.assertEqual(istatistik["toplam_soru"], 30)

        tek_gun = ktt_rapor_filtrele(
            KttSonucu.objects.all(),
            baslangic="2026-09-22",
            bitis="2026-09-22",
        )
        self.assertEqual(ktt_rapor_istatistik(tek_gun)["toplam_soru"], 10)

    @patch("takip.ktt_service.can", return_value=True)
    def test_bu_hafta_cozulen_soru(self, _can):
        user = User.objects.create_superuser("ktt-rapor-super", password="x")
        self.assertEqual(ktt_hafta_cozulen_soru(user, date(2026, 9, 26)), 30)
        self.assertEqual(ktt_hafta_cozulen_soru(user, date(2026, 10, 5)), 0)

    def test_sonuclar_teste_gore_kapali_gruplanir(self):
        sonuclar = KttSonucu.objects.select_related("ktt").order_by(
            "-ktt__sinav_tarihi", "-puan", "talebe__ad_soyad"
        )
        gruplar = ktt_rapor_grupla(sonuclar)
        self.assertEqual([g["ktt"].pk for g in gruplar], [self.ktt_a.pk, self.ktt_b.pk])
        self.assertEqual(len(gruplar[0]["sonuclar"]), 2)
        self.assertEqual(gruplar[0]["ktt"].soru_sayisi, 20)
        self.assertEqual(len(gruplar[1]["sonuclar"]), 1)
