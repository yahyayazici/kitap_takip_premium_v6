from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils.timezone import localdate

from takip.models import Ders, EtutHocasi, GunlukSoruDersSatiri, Talebe
from takip.ss_deneme_models import (
    SORU_DAGILIMI,
    SozelSayisalBransSonuc,
    SozelSayisalDeneme,
    SozelSayisalSonuc,
    brans_soru_sayisi,
)
from takip.ss_deneme_service import (
    sonuc_toplamlari_guncelle,
    ss_deneme_sonucu_soru_takibe_yansit,
)
from takip.soru_takip_service import seed_soru_takip_dersleri


class SoruDagilimTests(TestCase):
    def test_90_ve_75_toplamlari(self):
        self.assertEqual(sum(SORU_DAGILIMI[90].values()), 90)
        self.assertEqual(sum(SORU_DAGILIMI[75].values()), 75)
        self.assertEqual(SORU_DAGILIMI[90]["turkce"], 20)
        self.assertEqual(SORU_DAGILIMI[75]["turkce"], 15)
        self.assertEqual(SORU_DAGILIMI[90]["sosyal"], 10)
        self.assertEqual(SORU_DAGILIMI[75]["ingilizce"], 10)


class SsDenemeSoruTakipTests(TestCase):
    def setUp(self):
        seed_soru_takip_dersleri()
        self.user = User.objects.create_superuser("ssqa", "ssqa@example.com", "x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Test Hoca", user=self.user)
        self.talebe = Talebe.objects.create(
            ad_soyad="Deneme Talebe",
            sinif="7",
            sube="A",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            aktif=True,
        )
        self.deneme = SozelSayisalDeneme.objects.create(
            ad="7. Deneme",
            sinav_tarihi=localdate(),
            soru_formati=90,
            sinif_seviyesi="7",
            hedef_siniflar="7-A",
            etut_hocasi=self.hoca,
            olusturan=self.user,
        )

    def test_brans_soru_sayisi(self):
        self.assertEqual(brans_soru_sayisi(self.deneme, "turkce"), 20)
        self.assertEqual(brans_soru_sayisi(self.deneme, "din"), 10)
        self.deneme.soru_formati = 75
        self.assertEqual(brans_soru_sayisi(self.deneme, "matematik"), 15)

    def test_net_ve_soru_takip(self):
        sonuc = SozelSayisalSonuc.objects.create(
            deneme=self.deneme, talebe=self.talebe, kaydeden=self.user
        )
        SozelSayisalBransSonuc.objects.create(
            sonuc=sonuc, brans="turkce", dogru=16, yanlis=4, bos=0
        )
        SozelSayisalBransSonuc.objects.create(
            sonuc=sonuc, brans="matematik", dogru=12, yanlis=4, bos=4
        )
        sonuc_toplamlari_guncelle(sonuc)
        sonuc.refresh_from_db()
        self.assertEqual(sonuc.sozel_dogru, 16)
        self.assertEqual(sonuc.sayisal_dogru, 12)
        self.assertEqual(sonuc.toplam_net, Decimal("26.00"))

        ss_deneme_sonucu_soru_takibe_yansit(
            user=self.user,
            deneme=self.deneme,
            talebe=self.talebe,
            yeni_brans={"turkce": (16, 4, 0), "matematik": (12, 4, 4)},
        )
        turkce = Ders.objects.get(ad="Türkçe")
        satir = GunlukSoruDersSatiri.objects.get(
            kayit__talebe=self.talebe, kayit__tarih=self.deneme.sinav_tarihi, ders=turkce
        )
        self.assertEqual(satir.dogru, 16)
        self.assertEqual(satir.yanlis, 4)
        self.assertEqual(satir.toplam_soru, 20)
