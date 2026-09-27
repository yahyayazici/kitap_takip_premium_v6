from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils.timezone import localdate

from takip.models import (
    Ders,
    EtutHocasi,
    GunlukSoruDersSatiri,
    GunlukSoruKaydi,
    KttSinav,
    KttSonucu,
    Talebe,
)
from takip.soru_takip_service import (
    kayit_kaydet,
    kayit_satirlari_form_verisi,
    ktt_sonucu_soru_takibe_yansit,
    rapor_ders_ozeti,
    rapor_donemi_coz,
    rapor_kayitlari,
    seed_soru_takip_dersleri,
    soru_takip_dersleri,
)


class SoruTakipRaporDonemiTests(TestCase):
    def test_tarih_araligi_aylik_seciliyken_de_kullanilir(self):
        bas, bit, etiket = rapor_donemi_coz(
            {
                "donem": "aylik",
                "baslangic": "2026-01-10",
                "bitis": "2026-01-20",
            }
        )
        self.assertEqual(bas, date(2026, 1, 10))
        self.assertEqual(bit, date(2026, 1, 20))
        self.assertEqual(etiket, "Özel Dönem Raporu")

    def test_yillik_preset_tarihleri(self):
        bugun = localdate()
        bas, bit, etiket = rapor_donemi_coz(
            {
                "donem": "yillik",
                "baslangic": f"{bugun.year}-01-01",
                "bitis": f"{bugun.year}-12-31",
            }
        )
        self.assertEqual(bas, date(bugun.year, 1, 1))
        self.assertEqual(bit, date(bugun.year, 12, 31))
        self.assertEqual(etiket, "Yıllık Rapor")

    def test_sadece_donem_aylik_bugunun_ayi(self):
        bugun = localdate()
        bas, bit, etiket = rapor_donemi_coz({"donem": "aylik"})
        self.assertEqual(bas, bugun.replace(day=1))
        self.assertEqual(bit.month, bugun.month)
        self.assertEqual(etiket, "Aylık Rapor")


class SoruTakipRaporIcerikTests(TestCase):
    def setUp(self):
        seed_soru_takip_dersleri()
        self.user = User.objects.create_superuser("stqa", "stqa@example.com", "x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Test Hoca", user=self.user)
        self.talebe = Talebe.objects.create(
            ad_soyad="Rapor Talebe",
            sinif="7",
            sube="A",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            aktif=True,
        )
        self.turkce = Ders.objects.get(ad="Türkçe")
        self.mat = Ders.objects.get(ad="Matematik")

    def _satir(self, tarih, ders, dogru, yanlis, bos):
        kayit, _ = GunlukSoruKaydi.objects.get_or_create(
            talebe=self.talebe, tarih=tarih, defaults={"kaydeden": self.user}
        )
        GunlukSoruDersSatiri.objects.update_or_create(
            kayit=kayit,
            ders=ders,
            defaults={
                "toplam_soru": dogru + yanlis + bos,
                "dogru": dogru,
                "yanlis": yanlis,
                "bos": bos,
            },
        )

    def test_ders_ozeti_araliktaki_d_y_b(self):
        self._satir(date(2026, 1, 5), self.turkce, 10, 2, 1)
        self._satir(date(2026, 1, 15), self.turkce, 8, 1, 0)
        self._satir(date(2026, 2, 1), self.mat, 20, 0, 0)

        kayitlar, *_ = rapor_kayitlari(
            self.user,
            {
                "donem": "ozel",
                "baslangic": "2026-01-01",
                "bitis": "2026-01-31",
            },
        )
        ozet = {s["ders"]: s for s in rapor_ders_ozeti(kayitlar)}
        self.assertIn("Türkçe", ozet)
        self.assertNotIn("Matematik", ozet)
        self.assertEqual(ozet["Türkçe"]["toplam_soru"], 22)
        self.assertEqual(ozet["Türkçe"]["dogru"], 18)
        self.assertEqual(ozet["Türkçe"]["yanlis"], 3)
        self.assertEqual(ozet["Türkçe"]["bos"], 1)

    def test_ktt_yansitma_mevcut_kaydi_silmez(self):
        gun = localdate()
        self._satir(gun, self.turkce, 5, 1, 0)

        class FakeKtt:
            ders = self.turkce
            sinav_tarihi = gun
            ad = "Haftalık KTT"

        ktt_sonucu_soru_takibe_yansit(
            user=self.user,
            ktt=FakeKtt(),
            talebe=self.talebe,
            dogru=10,
            yanlis=2,
            bos=0,
        )
        satir = GunlukSoruDersSatiri.objects.get(
            kayit__talebe=self.talebe, kayit__tarih=gun, ders=self.turkce
        )
        self.assertEqual(satir.dogru, 15)
        self.assertEqual(satir.yanlis, 3)
        self.assertEqual(satir.toplam_soru, 18)

    def test_ktt_sonrasi_form_yalnizca_elle_payi_ister(self):
        gun = date(2026, 9, 27)
        ktt = KttSinav.objects.create(
            ad="Matematik KTT",
            ders=self.mat,
            sinif_seviyesi="7",
            sinav_tarihi=gun,
            soru_sayisi=15,
            etut_hocasi=self.hoca,
            olusturan=self.user,
        )
        KttSonucu.objects.create(
            ktt=ktt,
            talebe=self.talebe,
            dogru=12,
            yanlis=2,
            bos=1,
            kaydeden=self.user,
        )
        ktt_sonucu_soru_takibe_yansit(
            user=self.user,
            ktt=ktt,
            talebe=self.talebe,
            dogru=12,
            yanlis=2,
            bos=1,
        )

        kayit = GunlukSoruKaydi.objects.get(talebe=self.talebe, tarih=gun)
        mat_form = next(
            s
            for s in kayit_satirlari_form_verisi(kayit, soru_takip_dersleri())
            if s["ders"].id == self.mat.id
        )
        self.assertEqual(mat_form["elle_toplam"], 0)
        self.assertEqual(mat_form["elle_dogru"], 0)
        self.assertEqual(mat_form["olcum_soru"], 15)
        self.assertTrue(mat_form["olcum_ayri"])
        self.assertEqual(mat_form["toplam_soru"], 15)

        post = {}
        for ders in soru_takip_dersleri():
            post[f"ders_{ders.id}_toplam"] = "0"
            post[f"ders_{ders.id}_dogru"] = "0"
            post[f"ders_{ders.id}_yanlis"] = "0"
            post[f"ders_{ders.id}_bos"] = "0"
        post[f"ders_{self.mat.id}_toplam"] = "10"
        post[f"ders_{self.mat.id}_dogru"] = "8"
        post[f"ders_{self.mat.id}_yanlis"] = "2"
        post[f"ders_{self.mat.id}_bos"] = "0"

        kayit_kaydet(
            self.user,
            self.talebe,
            gun,
            soru_takip_dersleri(),
            post,
        )
        satir = GunlukSoruDersSatiri.objects.get(
            kayit__talebe=self.talebe, kayit__tarih=gun, ders=self.mat
        )
        self.assertEqual(satir.dogru, 20)
        self.assertEqual(satir.yanlis, 4)
        self.assertEqual(satir.bos, 1)
        self.assertEqual(satir.toplam_soru, 25)

        kayit = GunlukSoruKaydi.objects.get(talebe=self.talebe, tarih=gun)
        mat_form = next(
            s
            for s in kayit_satirlari_form_verisi(kayit, soru_takip_dersleri())
            if s["ders"].id == self.mat.id
        )
        self.assertEqual(mat_form["elle_dogru"], 8)
        self.assertEqual(mat_form["elle_yanlis"], 2)
        self.assertEqual(mat_form["elle_toplam"], 10)

        kayit_kaydet(
            self.user,
            self.talebe,
            gun,
            soru_takip_dersleri(),
            post,
        )
        satir.refresh_from_db()
        self.assertEqual(satir.toplam_soru, 25)
        self.assertEqual(satir.dogru, 20)

    def test_bos_kayit_ktt_payini_silmez(self):
        gun = date(2026, 9, 28)
        ktt = KttSinav.objects.create(
            ad="Fen KTT",
            ders=self.turkce,
            sinif_seviyesi="7",
            sinav_tarihi=gun,
            soru_sayisi=10,
            etut_hocasi=self.hoca,
            olusturan=self.user,
        )
        KttSonucu.objects.create(
            ktt=ktt,
            talebe=self.talebe,
            dogru=7,
            yanlis=2,
            bos=1,
            kaydeden=self.user,
        )
        ktt_sonucu_soru_takibe_yansit(
            user=self.user,
            ktt=ktt,
            talebe=self.talebe,
            dogru=7,
            yanlis=2,
            bos=1,
        )
        post = {}
        for ders in soru_takip_dersleri():
            post[f"ders_{ders.id}_toplam"] = "0"
            post[f"ders_{ders.id}_dogru"] = "0"
            post[f"ders_{ders.id}_yanlis"] = "0"
            post[f"ders_{ders.id}_bos"] = "0"
        kayit_kaydet(
            self.user, self.talebe, gun, soru_takip_dersleri(), post
        )
        satir = GunlukSoruDersSatiri.objects.get(
            kayit__talebe=self.talebe, kayit__tarih=gun, ders=self.turkce
        )
        self.assertEqual(satir.toplam_soru, 10)
        self.assertEqual(satir.dogru, 7)
