import io
import zipfile
from datetime import date
from unittest.mock import patch
from urllib.parse import quote

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.ktt_models import KttSinav, KttSonucu
from takip.ktt_service import (
    ktt_hafta_cozulen_soru,
    ktt_hafta_ders_sorulari,
    ktt_hafta_sinif_ozeti,
    ktt_rapor_filtrele,
    ktt_rapor_grupla,
    ktt_rapor_istatistik,
    ktt_rapor_pdf_adi,
    ktt_rapor_talebe_satirlari,
    ktt_rapor_zip_adi,
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
        self.assertEqual(istatistik["toplam_soru"], 50)
        self.assertEqual(istatistik["toplam_dogru"], 28)
        self.assertEqual(istatistik["toplam_yanlis"], 11)
        self.assertEqual(istatistik["toplam_bos"], 11)
        self.assertEqual(istatistik["toplam_net"], "25,25")
        self.assertEqual(istatistik["basari"], "56")

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

    @patch("takip.ktt_service.can", return_value=True)
    def test_bu_hafta_ders_ders_soru(self, _can):
        user = User.objects.create_superuser("ktt-rapor-super-ders", password="x")
        paragraf = Ders.objects.create(ad="Paragraf", sira=2, aktif=True)
        matematik = Ders.objects.create(ad="Matematik", sira=3, aktif=True)
        fen = Ders.objects.create(ad="Fen Bilimleri", sira=4, aktif=True)
        ingilizce = Ders.objects.create(ad="İngilizce", sira=5, aktif=True)
        din = Ders.objects.create(ad="Din Kültürü", sira=6, aktif=True)
        geometri = Ders.objects.create(ad="Geometri", sira=7, aktif=True)
        gun = date(2026, 9, 26)
        ktt_paragraf = KttSinav.objects.create(
            ad="Paragraf KTT",
            ders=paragraf,
            sinif_seviyesi="5",
            hedef_siniflar="5-A",
            sinav_tarihi=date(2026, 9, 23),
            soru_sayisi=45,
            etut_hocasi=self.hoca,
        )
        KttSonucu.objects.create(ktt=ktt_paragraf, talebe=self.talebe_a, dogru=30, yanlis=10, bos=5)
        KttSonucu.objects.create(ktt=ktt_paragraf, talebe=self.talebe_b, dogru=20, yanlis=15, bos=10)
        for ad, ders, soru, tarih in (
            ("Mat KTT", matematik, 12, date(2026, 9, 24)),
            ("Fen KTT", fen, 8, date(2026, 9, 25)),
            ("İng KTT", ingilizce, 6, date(2026, 9, 21)),
            ("Din KTT", din, 4, date(2026, 9, 27)),
            ("Geo KTT", geometri, 3, date(2026, 9, 22)),
        ):
            sinav = KttSinav.objects.create(
                ad=ad,
                ders=ders,
                sinif_seviyesi="5",
                hedef_siniflar="5-A",
                sinav_tarihi=tarih,
                soru_sayisi=soru,
                etut_hocasi=self.hoca,
            )
            KttSonucu.objects.create(
                ktt=sinav,
                talebe=self.talebe_a,
                dogru=soru,
                yanlis=0,
                bos=0,
            )

        satirlar = ktt_hafta_ders_sorulari(user, gun)
        sayilar = {satir["etiket"]: satir["soru"] for satir in satirlar}
        self.assertEqual(
            [satir["etiket"] for satir in satirlar[:7]],
            ["Türkçe", "Paragraf", "Matematik", "Fen", "Sosyal", "Din", "İngilizce"],
        )
        self.assertEqual(sayilar["Türkçe"], 30)
        self.assertEqual(sayilar["Paragraf"], 45)
        self.assertEqual(sayilar["Matematik"], 12)
        self.assertEqual(sayilar["Fen"], 8)
        self.assertEqual(sayilar["Sosyal"], 0)
        self.assertEqual(sayilar["Din"], 4)
        self.assertEqual(sayilar["İngilizce"], 6)
        self.assertEqual(sayilar["Geometri"], 3)
        self.assertEqual(sum(satir["soru"] for satir in satirlar), ktt_hafta_cozulen_soru(user, gun))
        self.assertEqual(ktt_hafta_cozulen_soru(user, gun), 108)

        bos_hafta = ktt_hafta_ders_sorulari(user, date(2026, 10, 5))
        self.assertEqual([satir["soru"] for satir in bos_hafta], [0, 0, 0, 0, 0, 0, 0])

    @patch("takip.ktt_service.can", return_value=True)
    def test_hafta_pdf_sinif_cumlesi(self, _can):
        user = User.objects.create_superuser("ktt-hafta-pdf", password="x")
        matematik = Ders.objects.create(ad="Matematik", sira=3, aktif=True)
        fen = Ders.objects.create(ad="Fen Bilimleri", sira=4, aktif=True)
        gun = date(2026, 9, 26)
        for ad, ders, soru in (
            ("7 Türkçe", self.ders, 30),
            ("7 Matematik", matematik, 62),
            ("7 Fen", fen, 71),
        ):
            sinav = KttSinav.objects.create(
                ad=ad,
                ders=ders,
                sinif_seviyesi="7",
                hedef_siniflar="7-A",
                sinav_tarihi=gun,
                soru_sayisi=soru,
                etut_hocasi=self.hoca,
            )
            KttSonucu.objects.create(
                ktt=sinav, talebe=self.talebe_a, dogru=soru, yanlis=0, bos=0
            )

        ozet = ktt_hafta_sinif_ozeti(user, gun)
        self.assertEqual(ozet["baslangic"], date(2026, 9, 21))
        self.assertEqual(ozet["bitis"], date(2026, 9, 27))
        self.assertEqual(ozet["toplam"], ktt_hafta_cozulen_soru(user, gun))
        yedi = next(sinif for sinif in ozet["siniflar"] if sinif["seviye"] == "7")
        bes = next(sinif for sinif in ozet["siniflar"] if sinif["seviye"] == "5")
        self.assertEqual(yedi["baslik"], "7. sınıflar")
        self.assertEqual(yedi["toplam"], 163)
        self.assertEqual(
            yedi["cumle"],
            "7. sınıflar bu hafta Türkçe dersinden 30, Matematik dersinden 62 ve Fen dersinden 71 soru çözdü.",
        )
        self.assertNotIn("Sosyal", yedi["cumle"])
        self.assertEqual(bes["toplam"], 30)
        self.assertEqual(bes["cumle"], "5. sınıflar bu hafta Türkçe dersinden 30 soru çözdü.")
        duz = {satir["etiket"]: satir["soru"] for satir in ktt_hafta_ders_sorulari(user, gun)}
        self.assertEqual(duz["Türkçe"], 60)
        self.assertEqual(duz["Matematik"], 62)
        self.assertEqual(duz["Fen"], 71)

        self.client.force_login(user)
        # PDF ucu gün vermez; bu haftayı localdate() ile alır. Fikstür haftası 21–27 Eylül.
        with (
            patch("takip.ktt_views.html_to_pdf", return_value=b"%PDF-1.4 fake") as mock_pdf,
            patch("takip.ktt_service.localdate", return_value=gun),
        ):
            resp = self.client.get(reverse("ktt_hafta_pdf"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ktt-hafta-2026-09-21.pdf", resp["Content-Disposition"])
        html = mock_pdf.call_args[0][0]
        cumle = "7. sınıflar bu hafta Türkçe dersinden 30, Matematik dersinden 62 ve Fen dersinden 71 soru çözdü."
        self.assertIn(cumle, html)
        blok = html[html.index(cumle):]
        cizgi = blok.index('<div class="apple-cizgi-bar">')
        self.assertLess(blok.index("ders-serit"), cizgi)
        self.assertLess(blok.index("Matematik"), cizgi)
        sayfa = self.client.get(reverse("ktt_listesi"))
        self.assertContains(sayfa, reverse("ktt_hafta_pdf"))

        self.client.force_login(user)
        sayfa = self.client.get(reverse("ktt_listesi"))
        self.assertEqual(sayfa.status_code, 200)
        html = sayfa.content.decode()
        cizgi = html.find("ktt-hafta-cizgi")
        dikkat = html.find("Bugün dikkat gerektirenler")
        self.assertIn("ktt-hafta-dersler", html)
        self.assertGreater(cizgi, html.find("ktt-hafta-dersler"))
        self.assertIn("Paragraf", html)
        self.assertIn("İngilizce", html)
        if dikkat != -1:
            self.assertLess(cizgi, dikkat)

    def test_sonuclar_teste_gore_kapali_gruplanir(self):
        sonuclar = KttSonucu.objects.select_related("ktt").order_by(
            "-ktt__sinav_tarihi", "-puan", "talebe__ad_soyad"
        )
        gruplar = ktt_rapor_grupla(sonuclar)
        self.assertEqual([g["ktt"].pk for g in gruplar], [self.ktt_a.pk, self.ktt_b.pk])
        self.assertEqual(len(gruplar[0]["sonuclar"]), 2)
        self.assertEqual(gruplar[0]["ktt"].soru_sayisi, 20)
        self.assertEqual(len(gruplar[1]["sonuclar"]), 1)

    def test_talebe_satirlari_ada_gore_toplar(self):
        sonuclar = list(
            KttSonucu.objects.select_related("ktt", "ktt__ders", "talebe").order_by(
                "-ktt__sinav_tarihi", "-puan", "talebe__ad_soyad"
            )
        )
        satirlar = ktt_rapor_talebe_satirlari(sonuclar)
        self.assertEqual(
            [s["talebe"].ad_soyad for s in satirlar],
            ["Ayşe Yılmaz", "Mehmet Demir"],
        )
        ayse = satirlar[0]
        self.assertEqual(ayse["test"], 2)
        self.assertEqual(ayse["soru"], 30)
        self.assertEqual(ayse["dogru"], 18)
        self.assertEqual(ayse["yanlis"], 6)
        self.assertEqual(ayse["bos"], 6)
        self.assertEqual(ayse["net"], "16,5")
        self.assertEqual(ayse["ozet"], "2 test · 30 soru · 18 doğru · 6 yanlış · 6 boş")
        self.assertEqual(ayse["basari"], "60")
        self.assertEqual(ayse["testler"][0]["ktt_id"], self.ktt_a.pk)
        mehmet = satirlar[1]
        self.assertEqual(mehmet["soru"], 20)
        self.assertEqual(mehmet["dogru"], 10)
        self.assertEqual(mehmet["yanlis"], 5)
        self.assertEqual(mehmet["bos"], 5)
        self.assertEqual(mehmet["test"], 1)

    def test_ders_filtresi_yalnizca_secilen_dersi_sayar(self):
        fen = Ders.objects.create(ad="Fen", sira=2, aktif=True)
        self.ktt_b.ders = fen
        self.ktt_b.save(update_fields=["ders"])
        qs = ktt_rapor_filtrele(KttSonucu.objects.all(), ders_ids=[fen.id])
        istatistik = ktt_rapor_istatistik(qs)
        self.assertEqual(istatistik["toplam_soru"], 10)
        self.assertEqual(istatistik["toplam_dogru"], 6)
        satirlar = ktt_rapor_talebe_satirlari(list(qs.select_related("ktt", "ktt__ders", "talebe")))
        self.assertEqual(len(satirlar), 1)
        self.assertEqual(satirlar[0]["talebe"].pk, self.talebe_a.pk)
        self.assertEqual(satirlar[0]["ozet"], "1 test · 10 soru · 6 doğru · 2 yanlış · 2 boş")

    def test_pdf_adi_talebe_ve_tarih_araligini_icerir(self):
        self.assertEqual(
            ktt_rapor_pdf_adi("Ayşe Yılmaz", "2026-09-21", "2026-09-27"),
            "Ayşe Yılmaz_2026-09-21_2026-09-27.pdf",
        )
        self.assertEqual(ktt_rapor_pdf_adi("Ayşe Yılmaz", "", ""), "Ayşe Yılmaz_tum-aralik.pdf")
        self.assertEqual(
            ktt_rapor_zip_adi("2026-09-21", "2026-09-27"),
            "ktt-talebe-raporlari_2026-09-21_2026-09-27.zip",
        )

    @patch("takip.ktt_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_talebe_pdf_ve_zip(self, _pdf):
        user = User.objects.create_superuser("ktt-rapor-super-indirme", password="x")
        self.client.force_login(user)
        sorgu = {"baslangic": "2026-09-21", "bitis": "2026-09-27"}

        pdf = self.client.get(
            reverse("ktt_rapor_talebe_pdf", args=[self.talebe_a.pk]),
            sorgu,
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        beklenen = quote("Ayşe Yılmaz_2026-09-21_2026-09-27.pdf")
        self.assertIn(beklenen, pdf["Content-Disposition"])
        html = _pdf.call_args.args[0]
        self.assertIn("2 test · 30 soru · 18 doğru · 6 yanlış · 6 boş", html)
        self.assertIn("box-shadow: none", html)

        bos = self.client.get(
            reverse("ktt_rapor_talebe_pdf", args=[self.talebe_b.pk]),
            {"baslangic": "2026-09-22", "bitis": "2026-09-22"},
        )
        self.assertEqual(bos.status_code, 302)

        paket = self.client.get(reverse("ktt_rapor_zip"), sorgu)
        self.assertEqual(paket.status_code, 200)
        self.assertEqual(paket["Content-Type"], "application/zip")
        self.assertIn(
            "ktt-talebe-raporlari_2026-09-21_2026-09-27.zip",
            paket["Content-Disposition"],
        )
        with zipfile.ZipFile(io.BytesIO(paket.content)) as arsiv:
            adlar = arsiv.namelist()
        self.assertEqual(
            adlar,
            [
                "Ayşe Yılmaz_2026-09-21_2026-09-27.pdf",
                "Mehmet Demir_2026-09-21_2026-09-27.pdf",
            ],
        )

    def test_rapor_sayfasi_talebe_ozetini_gosterir(self):
        user = User.objects.create_superuser("ktt-rapor-super-sayfa", password="x")
        self.client.force_login(user)
        yanit = self.client.get(reverse("ktt_rapor"))
        self.assertContains(yanit, "2 test · 30 soru · 18 doğru · 6 yanlış · 6 boş")
        self.assertContains(yanit, "1 test · 20 soru · 10 doğru · 5 yanlış · 5 boş")
        self.assertContains(yanit, "Toplam net")
        self.assertContains(yanit, "25,25")

        fen = Ders.objects.create(ad="Fen", sira=2, aktif=True)
        self.ktt_b.ders = fen
        self.ktt_b.save(update_fields=["ders"])
        dar = self.client.get(reverse("ktt_rapor"), {"ders": fen.id})
        self.assertContains(dar, "1 test · 10 soru · 6 doğru · 2 yanlış · 2 boş")
        self.assertNotContains(dar, "Mehmet Demir</strong>")
