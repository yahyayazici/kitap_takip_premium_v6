import io
import zipfile
from datetime import date
from unittest.mock import patch
from urllib.parse import quote

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
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
    rapor_talebe_satirlari,
    seed_soru_takip_dersleri,
    soru_takip_dersleri,
    soru_takip_pdf_adi,
    soru_takip_zip_adi,
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

    def test_talebe_satiri_ders_dokumu_ve_ozet(self):
        self._satir(date(2026, 1, 5), self.turkce, 8, 1, 1)
        self._satir(date(2026, 1, 5), self.mat, 6, 2, 2)
        self._satir(date(2026, 1, 6), self.turkce, 4, 0, 0)
        kayitlar, *_ = rapor_kayitlari(
            self.user,
            {"donem": "ozel", "baslangic": "2026-01-01", "bitis": "2026-01-31"},
        )
        satir = rapor_talebe_satirlari(kayitlar)[0]
        self.assertEqual(satir["gun_sayisi"], 2)
        self.assertEqual(
            satir["ozet"],
            "2 kayıt günü · 24 soru · 18 doğru · 3 yanlış · 3 boş",
        )
        self.assertEqual([d["ders"] for d in satir["dersler"]], ["Türkçe", "Matematik"])

    def test_pdf_ve_zip_adlari(self):
        bas, bit = date(2026, 1, 1), date(2026, 1, 31)
        self.assertEqual(
            soru_takip_pdf_adi("Ayşe Yılmaz", bas, bit),
            "Ayşe Yılmaz_2026-01-01_2026-01-31.pdf",
        )
        self.assertEqual(
            soru_takip_zip_adi(bas, bit),
            "soru-takip-talebe-raporlari_2026-01-01_2026-01-31.zip",
        )

    @patch("takip.soru_takip_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_talebe_pdf_ve_zip(self, _pdf):
        user = User.objects.create_superuser("st-zip", password="x")
        self.client.force_login(user)
        diger = Talebe.objects.create(
            ad_soyad="Mehmet Demir",
            sinif="7",
            sube="A",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            aktif=True,
        )
        self._satir(date(2026, 1, 5), self.turkce, 8, 1, 1)
        kayit, _ = GunlukSoruKaydi.objects.get_or_create(
            talebe=diger, tarih=date(2026, 1, 6), defaults={"kaydeden": self.user}
        )
        GunlukSoruDersSatiri.objects.update_or_create(
            kayit=kayit,
            ders=self.mat,
            defaults={"toplam_soru": 10, "dogru": 6, "yanlis": 2, "bos": 2},
        )
        sorgu = {"donem": "ozel", "baslangic": "2026-01-01", "bitis": "2026-01-31"}

        pdf = self.client.get(
            reverse("soru_takip_talebe_pdf", args=[self.talebe.pk]),
            sorgu,
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertIn(
            quote("Rapor Talebe_2026-01-01_2026-01-31.pdf"),
            pdf["Content-Disposition"],
        )
        self.assertIn("1 kayıt günü · 10 soru · 8 doğru · 1 yanlış · 1 boş", _pdf.call_args.args[0])
        self.assertIn("A4 portrait", _pdf.call_args.args[0])

        bos = self.client.get(
            reverse("soru_takip_talebe_pdf", args=[diger.pk]),
            {"donem": "ozel", "baslangic": "2026-02-01", "bitis": "2026-02-02"},
        )
        self.assertEqual(bos.status_code, 302)

        paket = self.client.get(reverse("soru_takip_rapor_zip"), sorgu)
        self.assertEqual(paket.status_code, 200)
        self.assertEqual(paket["Content-Type"], "application/zip")
        self.assertIn(
            "soru-takip-talebe-raporlari_2026-01-01_2026-01-31.zip",
            paket["Content-Disposition"],
        )
        with zipfile.ZipFile(io.BytesIO(paket.content)) as arsiv:
            self.assertEqual(
                arsiv.namelist(),
                [
                    "Mehmet Demir_2026-01-01_2026-01-31.pdf",
                    "Rapor Talebe_2026-01-01_2026-01-31.pdf",
                ],
            )

        sayfa = self.client.get(reverse("soru_takip_rapor"), sorgu)
        self.assertContains(sayfa, "Talebe Raporu")
        self.assertContains(sayfa, "Talebe ZIP")
        self.assertContains(sayfa, "1 kayıt günü · 10 soru · 8 doğru · 1 yanlış · 1 boş")
