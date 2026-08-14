"""Ölçme Merkezi — sonuç ve analiz testleri."""

from django.contrib.auth.models import User
from django.test import TestCase

from takip.konu_destek_models import KonuKatalogu
from takip.models import Ders, EtutHocasi, KttSinav, KttSonucu, Talebe
from takip.olcme_models import OlcumCevapAnahtari
from takip.olcme_service import (
    olcme_sonuc_sonrasi_konu_eksikleri,
    optik_satirlar_parcala,
    sablondan_sinav_olustur,
    satir_cevap_parcala,
    sinav_kazanim_analizi,
    sinav_konu_analizi,
    sinav_sablon_kaydet,
    sinav_sonuc_ozet,
    sorulari_olustur,
    talebe_cevaplari_kaydet,
    talebe_kimlik_eslestir,
    toplu_optik_kaydet,
    sinav_durum_guncelle,
    yayinlanabilir_mi,
    zayif_konulari_etut_planina_aktar,
)


class OlcumSonucTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("olcme_sonuc", password="test")
        self.ders = Ders.objects.create(ad="Matematik", sira=1, aktif=True)
        self.hoca = EtutHocasi.objects.create(user=self.user, ad_soyad="Hoca", aktif=True)
        self.konu = KonuKatalogu.objects.create(
            sinif_seviyesi="7",
            brans="matematik",
            konu_ad="Kesirler",
        )
        self.sinav = KttSinav.objects.create(
            ad="Sonuç Test",
            ders=self.ders,
            sinif_seviyesi="7",
            hedef_siniflar="7-A",
            sinav_tarihi="2026-08-14",
            soru_sayisi=3,
            etut_hocasi=self.hoca,
            olusturan=self.user,
        )
        self.talebe = Talebe.objects.create(
            ad_soyad="Ali Veli",
            sinif="7-A",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            aktif=True,
        )
        sorulari_olustur(self.sinav, varsayilan_ders=self.ders)
        for soru in self.sinav.olcme_sorulari.all():
            OlcumCevapAnahtari.objects.update_or_create(
                soru=soru,
                kitapcik="A",
                defaults={"dogru_secenek": "A"},
            )
            soru.konu = self.konu
            soru.zimmet_tamam = True
            soru.save(update_fields=["konu", "zimmet_tamam"])

    def test_satir_cevap_parcala(self):
        out = satir_cevap_parcala("A B C", 3)
        self.assertEqual(out, {1: "A", 2: "B", 3: "C"})

    def test_talebe_cevaplari_net(self):
        cevaplar = {1: "A", 2: "B", 3: "BOS"}
        sonuc = talebe_cevaplari_kaydet(
            self.sinav,
            self.talebe,
            cevaplar,
            kullanici=self.user,
        )
        self.assertIsNotNone(sonuc)
        self.assertEqual(sonuc.dogru, 1)
        self.assertEqual(sonuc.yanlis, 1)
        self.assertEqual(sonuc.bos, 1)

    def test_konu_analizi(self):
        talebe_cevaplari_kaydet(
            self.sinav,
            self.talebe,
            {1: "A", 2: "B", 3: "BOS"},
            kullanici=self.user,
        )
        analiz = sinav_konu_analizi(self.sinav)
        self.assertEqual(len(analiz), 1)
        self.assertEqual(analiz[0]["konu_ad"], "Kesirler")
        self.assertEqual(analiz[0]["dogru"], 1)

    def test_sablon_kaydet(self):
        sablon = sinav_sablon_kaydet(self.sinav, "Mat 3 soru", self.user)
        self.assertEqual(sablon.ad, "Mat 3 soru")
        self.assertEqual(sablon.sorular.count(), 3)

    def test_sablondan_sinav_olustur(self):
        sablon = sinav_sablon_kaydet(self.sinav, "Şablon Kopya", self.user)
        yeni = sablondan_sinav_olustur(
            sablon,
            ad="Yeni Mat",
            sinav_tarihi="2026-08-15",
            ders=self.ders,
            sinif_etiketleri=["7-A"],
            kullanici=self.user,
            etut_hocasi=self.hoca,
        )
        self.assertEqual(yeni.soru_sayisi, 3)
        self.assertEqual(yeni.olcme_sorulari.filter(konu=self.konu).count(), 3)

    def test_optik_satirlar_parcala(self):
        satirlar = optik_satirlar_parcala("101|ABC\nAli Veli A B C", 3)
        self.assertEqual(len(satirlar), 2)
        self.assertEqual(satirlar[0][0], "101")
        self.assertEqual(satirlar[0][1][1], "A")

    def test_talebe_kimlik_eslestir(self):
        self.talebe.talebe_no = "101"
        self.talebe.save(update_fields=["talebe_no"])
        bulunan = talebe_kimlik_eslestir([self.talebe], "101")
        self.assertEqual(bulunan.pk, self.talebe.pk)

    def test_toplu_optik_kaydet(self):
        self.talebe.talebe_no = "777"
        self.talebe.save(update_fields=["talebe_no"])
        for soru in self.sinav.olcme_sorulari.all():
            OlcumCevapAnahtari.objects.update_or_create(
                soru=soru, kitapcik="A", defaults={"dogru_secenek": "A"},
            )
        satirlar = optik_satirlar_parcala("777|AAA", 3)
        sonuc = toplu_optik_kaydet(
            self.sinav,
            [self.talebe],
            satirlar,
            kullanici=self.user,
        )
        self.assertEqual(sonuc["kaydedilen"], 1)
        self.assertTrue(KttSonucu.objects.filter(ktt=self.sinav, talebe=self.talebe).exists())

    def test_konu_eksigi_aktarimi(self):
        from takip.konu_destek_models import TalebeKonuEksigi

        self.talebe.talebe_no = "888"
        self.talebe.save(update_fields=["talebe_no"])
        for soru in self.sinav.olcme_sorulari.all():
            OlcumCevapAnahtari.objects.update_or_create(
                soru=soru, kitapcik="A", defaults={"dogru_secenek": "A"},
            )
        sonuc = talebe_cevaplari_kaydet(
            self.sinav,
            self.talebe,
            {1: "B", 2: "B", 3: "B"},
            kullanici=self.user,
        )
        self.assertIsNotNone(sonuc)
        adet = olcme_sonuc_sonrasi_konu_eksikleri(sonuc)
        self.assertGreaterEqual(adet, 1)
        self.assertTrue(
            TalebeKonuEksigi.objects.filter(
                talebe=self.talebe,
                konu=self.konu,
                kaynak=TalebeKonuEksigi.Kaynak.KTT,
            ).exists()
        )

    def test_zayif_konular_etut_planina(self):
        from takip.etut_plan_models import EtutPlanFaaliyet
        from takip.etut_plan_service import saat_bloklari_otomatik_olustur

        saat_bloklari_otomatik_olustur(self.hoca)
        talebe_cevaplari_kaydet(
            self.sinav,
            self.talebe,
            {1: "B", 2: "B", 3: "B"},
            kullanici=self.user,
        )
        sonuc = zayif_konulari_etut_planina_aktar(self.user, self.sinav)
        self.assertIsNone(sonuc.get("hata"))
        self.assertGreaterEqual(sonuc["atanan"], 1)
        self.assertTrue(
            EtutPlanFaaliyet.objects.filter(
                plan__etut_hocasi=self.hoca,
                baslik__startswith="Konu Tekrarı:",
            ).exists()
        )

    def test_yayin_veli_goster(self):
        talebe_cevaplari_kaydet(
            self.sinav,
            self.talebe,
            {1: "A", 2: "A", 3: "A"},
            kullanici=self.user,
        )
        self.sinav.veliye_goster = False
        self.sinav.save(update_fields=["veliye_goster"])
        sinav_durum_guncelle(
            self.sinav,
            KttSinav.SinavDurum.YAYINLANDI,
            self.user,
        )
        self.sinav.refresh_from_db()
        self.assertEqual(self.sinav.durum, KttSinav.SinavDurum.YAYINLANDI)
        self.assertTrue(self.sinav.veliye_goster)

    def test_yayin_sonuc_gerektirir(self):
        ok, mesajlar = yayinlanabilir_mi(self.sinav)
        self.assertFalse(ok)
        self.assertTrue(any("sonucu" in m.lower() for m in mesajlar))
