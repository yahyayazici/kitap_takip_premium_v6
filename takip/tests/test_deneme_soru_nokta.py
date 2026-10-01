"""Soru karnesi: eksi = yanlış, sınıfta yüzde 33+ aynı soru Deneme Kontrol’de."""

import io
import os
import zipfile
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from openpyxl import Workbook

from takip.deneme_kontrol_service import _nokta_yuzde, sinif_nokta_atisi
from takip.deneme_models import DenemeSinavi, DenemeSoruSonucu
from takip.deneme_soru_karne import (
    _Parca,
    _ders_adi,
    _satir_soru,
    _soru_satirini_birlestir,
    _sutun_sorulari,
    _tr_baslik,
    import_soru_karneleri,
)
from takip.models import EtutHocasi, PersonelProfili, SinifSube, Talebe


class SoruSatirParserTests(SimpleTestCase):
    def test_eksi_ve_harf(self):
        no, konu, sonuc = _satir_soru("5 Paragraf Anlamı Yönü C A -")
        self.assertEqual((no, konu, sonuc), (5, "Paragraf Anlamı Yönü", "yanlis"))
        no, konu, sonuc = _satir_soru("2 Sözcükte Anlam A A +")
        self.assertEqual(sonuc, "dogru")
        self.assertEqual(_satir_soru("4 Konu B C")[2], "yanlis")
        no, konu, sonuc = _satir_soru("10 Paragrafın Anlam Yönü C")
        self.assertEqual((no, konu, sonuc), (10, "Paragrafın Anlam Yönü", "bos"))
        self.assertEqual(_satir_soru("3 Konu B-")[2], "yanlis")
        self.assertIsNone(_satir_soru("2 GÜNAY - 5.SINIF SÜREÇ İZLEME SINAVI -"))

    def test_cevap_sutunu_konuya_yapisir(self):
        segmentler = [
            _Parca("TÜRKÇE", 94, 140, 740),
            _Parca("1 Sözcükte Anlam", 30, 130, 712),
            _Parca("C C +", 174, 210, 711),
            _Parca("3 Paragrafın Anlam Yönü", 30, 150, 694),
            _Parca("B D -", 174, 210, 693),
            _Parca("MATEMATİK", 272, 340, 703),
            _Parca("3 Açılar", 220, 280, 694),
            _Parca("D C -", 363, 400, 693),
            _Parca("10 Paragrafın Anlam Yönü", 29, 92, 632),
            _Parca("C", 174, 178, 632),
            _Parca("10 Hello", 406, 426, 632),
            _Parca("B", 551, 554, 632),
            _Parca("İNGİLİZCE", 466, 520, 740),
        ]
        satirlar = _sutun_sorulari(_soru_satirini_birlestir(segmentler), 595)
        bulunan = {(s.ders, s.soru_no, s.sonuc) for s in satirlar}
        self.assertEqual(
            bulunan,
            {
                ("Türkçe", 1, "dogru"),
                ("Türkçe", 3, "yanlis"),
                ("Türkçe", 10, "bos"),
                ("Matematik", 3, "yanlis"),
                ("İngilizce", 10, "bos"),
            },
        )

    def test_ders_basligi(self):
        self.assertEqual(_ders_adi("TÜRKÇE"), "Türkçe")
        self.assertEqual(_ders_adi("FEN BİLGİSİ"), "Fen Bilgisi")
        self.assertEqual(_ders_adi("İNGİLİZCE"), "İngilizce")
        self.assertEqual(_ders_adi("SOSYAL BİLGİLER"), "Sosyal Bilgiler")
        self.assertEqual(_tr_baslik("GEOMETRİ"), "Geometri")

    def test_yuzde_esigi(self):
        self.assertEqual(_nokta_yuzde(1, 3), 33)
        self.assertIsNone(_nokta_yuzde(1, 4))
        self.assertIsNone(_nokta_yuzde(326, 1000))
        self.assertEqual(_nokta_yuzde(334, 1000), 33)
        self.assertEqual(_nokta_yuzde(335, 1000), 34)
        self.assertEqual(_nokta_yuzde(3, 4), 75)


def _xlsx(rows, name="karne.xlsx"):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(name, buf.getvalue())


def _deneme(ad, gun, *, durum=DenemeSinavi.Durum.AKTIF, tur=DenemeSinavi.Tur.GRUP):
    return DenemeSinavi.objects.create(
        ad=ad,
        sinav_tarihi=date(2026, 9, gun),
        sinif_seviyesi="8",
        durum=durum,
        tur=tur,
    )


class DenemeSoruNoktaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("nokta-etut", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Nokta Hoca", user=self.user, aktif=True)
        PersonelProfili.objects.create(
            user=self.user,
            ad_soyad="Nokta Hoca",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=self.hoca,
        )
        self.sinif = SinifSube.objects.create(sinif="8", sube="A")
        self.sinif5 = SinifSube.objects.create(sinif="5", sube="A")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif, self.sinif5)
        self.ali = self._talebe("Ali Veli", self.sinif)
        self.ayse = self._talebe("Ayse Demir", self.sinif)
        self.veli = self._talebe("Veli Kaya", self.sinif)
        self.can = self._talebe("Can Oz", self.sinif)
        self.ahmed = self._talebe("Ahmed Arif Küçük", self.sinif5)

    def _talebe(self, ad, sinif):
        return Talebe.objects.create(
            ad_soyad=ad,
            sinif_sube=sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )

    def _soru(self, deneme, talebe, ders, no, sonuc, konu="", sira=0):
        return DenemeSoruSonucu.objects.create(
            deneme=deneme,
            talebe=talebe,
            ders_ad=ders,
            ders_key=ders.lower().replace(" ", ""),
            soru_no=no,
            konu_ad=konu,
            sonuc=sonuc,
            sira=sira,
        )

    def test_duz_excel_turkce_isim_ve_sinif(self):
        deneme = _deneme("Günay", 30)
        dosya = _xlsx(
            [
                ["GÜNAY 5. SINIF"],
                ["Sınıf", "Ad Soyad", "Türkçe 5", "Fen Bilgisi 12", "Matematik 1"],
                ["5-A", "AHMED ARİF KÜÇÜK", "-", "+", "B"],
                ["8-A", "Ali Veli", "+", "-", "+"],
            ]
        )
        stats = import_soru_karneleri(dosya, deneme=deneme)
        self.assertEqual(stats.eslesen_talebe, 2)
        ahmed = DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ahmed, soru_no=5)
        self.assertEqual(ahmed.ders_ad, "Türkçe")
        self.assertEqual(ahmed.sonuc, "yanlis")
        fen = DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ahmed, soru_no=12)
        self.assertEqual(fen.ders_ad, "Fen Bilgisi")
        self.assertEqual(fen.sonuc, "dogru")
        bos = DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ahmed, ders_key="matematik")
        self.assertEqual(bos.sonuc, "bos")
        self.assertEqual(
            DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ali, soru_no=12).sonuc,
            "yanlis",
        )

    def test_matris_ve_uzun_excel(self):
        deneme = _deneme("Matris", 28)
        matris = _xlsx(
            [
                ["Sınıf", "Ad Soyad", "Türkçe", "Türkçe", "Matematik"],
                ["", "", 1, 5, 3],
                ["", "", "Sözcük", "Paragraf", "Açılar"],
                ["8-A", "Ali Veli", "+", "-", "+"],
            ]
        )
        import_soru_karneleri(matris, deneme=deneme)
        bes = DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ali, soru_no=5)
        self.assertEqual(bes.ders_ad, "Türkçe")
        self.assertEqual(bes.sonuc, "yanlis")
        self.assertEqual(bes.konu_ad, "Paragraf")
        self.assertEqual(
            DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ali, soru_no=3).ders_ad,
            "Matematik",
        )

        uzun = _xlsx(
            [
                ["Sınıf", "Ad Soyad", "Ders", "Soru No", "Konu", "Sonuç"],
                ["8-A", "Ayse Demir", "İngilizce", 4, "Hello", "-"],
            ],
            name="uzun.xlsx",
        )
        import_soru_karneleri(uzun, deneme=deneme)
        self.assertTrue(
            DenemeSoruSonucu.objects.filter(
                deneme=deneme, talebe=self.ali, ders_ad="Türkçe", soru_no=5
            ).exists()
        )
        ing = DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ayse, soru_no=4)
        self.assertEqual(ing.ders_ad, "İngilizce")
        self.assertEqual(ing.sonuc, "yanlis")

    def test_yeniden_yukleme_yalnizca_o_talebeyi_degistirir(self):
        deneme = _deneme("Tekrar", 27)
        import_soru_karneleri(
            _xlsx(
                [
                    ["Sınıf", "Ad Soyad", "Türkçe 5", "Türkçe 2"],
                    ["8-A", "Ali Veli", "-", "+"],
                    ["8-A", "Ayse Demir", "-", "-"],
                ]
            ),
            deneme=deneme,
        )
        import_soru_karneleri(
            _xlsx(
                [
                    ["Sınıf", "Ad Soyad", "Türkçe 5"],
                    ["8-A", "Ali Veli", "+"],
                ]
            ),
            deneme=deneme,
        )
        self.assertEqual(
            DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ali, soru_no=5).sonuc,
            "dogru",
        )
        self.assertFalse(
            DenemeSoruSonucu.objects.filter(deneme=deneme, talebe=self.ali, soru_no=2).exists()
        )
        self.assertEqual(
            DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ayse, soru_no=2).sonuc,
            "yanlis",
        )

    def test_eslesmeyen_isim_var_olani_silmez(self):
        deneme = _deneme("Koruma", 26)
        import_soru_karneleri(
            _xlsx(
                [
                    ["Sınıf", "Ad Soyad", "Türkçe 5"],
                    ["8-A", "Ali Veli", "-"],
                ]
            ),
            deneme=deneme,
        )
        with self.assertRaises(ValueError):
            import_soru_karneleri(
                _xlsx(
                    [
                        ["Sınıf", "Ad Soyad", "Türkçe 1"],
                        ["8-A", "Kimse Yok", "-"],
                    ]
                ),
                deneme=deneme,
            )
        self.assertEqual(DenemeSoruSonucu.objects.filter(deneme=deneme).count(), 1)

    def test_zip_excel(self):
        deneme = _deneme("Zip", 25)
        ic = _xlsx(
            [
                ["Sınıf", "Ad Soyad", "Türkçe 5"],
                ["8-A", "Ali Veli", "-"],
            ]
        ).read()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as paket:
            paket.writestr("ali.xlsx", ic)
        stats = import_soru_karneleri(
            SimpleUploadedFile("karneler.zip", buf.getvalue()),
            deneme=deneme,
        )
        self.assertEqual(stats.soru_yazilan, 1)
        self.assertEqual(
            DenemeSoruSonucu.objects.get(deneme=deneme, talebe=self.ali).sonuc,
            "yanlis",
        )

    def test_nokta_cumlesi_ve_arsiv(self):
        eski = _deneme("Eski", 1)
        yeni = _deneme("Yeni", 10)
        arsiv = _deneme("Arşiv", 20, durum=DenemeSinavi.Durum.ARSIV)
        for talebe, sonuc in (
            (self.ali, "yanlis"),
            (self.ayse, "yanlis"),
            (self.veli, "yanlis"),
            (self.can, "dogru"),
        ):
            self._soru(yeni, talebe, "Türkçe", 5, sonuc, konu="Paragraf", sira=1)
        self._soru(yeni, self.ali, "Türkçe", 2, "yanlis", sira=2)
        for talebe in (self.ayse, self.veli, self.can):
            self._soru(yeni, talebe, "Türkçe", 2, "dogru", sira=2)
        self._soru(yeni, self.ali, "Matematik", 1, "yanlis", sira=3)
        self._soru(yeni, self.ayse, "Matematik", 1, "yanlis", sira=3)
        self._soru(yeni, self.veli, "Matematik", 1, "dogru", sira=3)
        self._soru(yeni, self.can, "Matematik", 1, "dogru", sira=3)
        self._soru(yeni, self.ali, "Fen Bilgisi", 4, "yanlis", sira=4)
        self._soru(yeni, self.ayse, "Fen Bilgisi", 4, "dogru", sira=4)
        self._soru(yeni, self.veli, "Fen Bilgisi", 4, "dogru", sira=4)
        for talebe in (self.ali, self.ayse, self.veli, self.can):
            self._soru(eski, talebe, "Türkçe", 9, "yanlis", sira=1)
            self._soru(arsiv, talebe, "Fen Bilgisi", 1, "yanlis", sira=1)

        self.assertEqual(
            DenemeSoruSonucu.objects.filter(deneme=yeni, ders_ad="Fen Bilgisi", soru_no=4).count(),
            3,
        )

        nokta = sinif_nokta_atisi([self.ali.id, self.ayse.id, self.veli.id, self.can.id])
        self.assertEqual(nokta["deneme"].id, yeni.id)
        self.assertEqual(nokta["karne_sayisi"], 4)
        cumleler = [s["cumle"] for s in nokta["satirlar"]]
        self.assertIn("Türkçe 5. soru %75 yanlış yapmış", cumleler)
        self.assertIn("Matematik 1. soru %50 yanlış yapmış", cumleler)
        self.assertIn("Fen Bilgisi 4. soru %33 yanlış yapmış", cumleler)
        self.assertFalse(any("Türkçe 2" in c for c in cumleler))
        self.assertFalse(any("Türkçe 9" in c for c in cumleler))
        self.assertFalse(any("Fen Bilgisi 1" in c for c in cumleler))
        turkce = next(s for s in nokta["satirlar"] if s["soru_no"] == 5)
        self.assertEqual(turkce["konu"], "Paragraf")

    def test_yalniz_arsiv_gorunmez(self):
        arsiv = _deneme("Sadece arşiv", 21, durum=DenemeSinavi.Durum.ARSIV)
        self._soru(arsiv, self.ali, "Fen Bilgisi", 1, "yanlis")
        nokta = sinif_nokta_atisi([self.ali.id])
        self.assertIsNone(nokta["deneme"])
        self.assertEqual(nokta["satirlar"], [])

    def test_sayfa_nokta_atisi(self):
        deneme = _deneme("Ekran", 12)
        for talebe, sonuc in (
            (self.ali, "yanlis"),
            (self.ayse, "yanlis"),
            (self.veli, "yanlis"),
            (self.can, "dogru"),
        ):
            self._soru(deneme, talebe, "Türkçe", 5, sonuc, konu="Paragraf")
        self._soru(deneme, self.ali, "Türkçe", 2, "yanlis")
        for talebe in (self.ayse, self.veli, self.can):
            self._soru(deneme, talebe, "Türkçe", 2, "dogru")
        self.client.force_login(self.user)
        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[self.sinif.id]))
        self.assertContains(sayfa, "Nokta atışı")
        self.assertContains(sayfa, "Türkçe 5. soru %75 yanlış yapmış")
        self.assertContains(sayfa, "Paragraf")
        self.assertNotContains(sayfa, "Türkçe 2. soru")

    def test_karne_yoksa_ornek_cumle(self):
        self.client.force_login(self.user)
        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[self.sinif.id]))
        self.assertContains(sayfa, "Türkçe 5. soru %40 yanlış yapmış")

    def test_esik_altinda_bos_durum(self):
        deneme = _deneme("Temiz", 11)
        for talebe in (self.ali, self.ayse, self.veli, self.can):
            self._soru(deneme, talebe, "Türkçe", 5, "dogru")
        self.client.force_login(self.user)
        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[self.sinif.id]))
        self.assertContains(sayfa, "ortak yanlış yok")

    def test_yonetim_yukle(self):
        admin = User.objects.create_superuser("nokta-admin", "a@b.c", "x")
        deneme = _deneme("Yükleme", 15)
        self.client.force_login(admin)
        detay = self.client.get(reverse("yonetim:deneme_detay", args=[deneme.pk]))
        self.assertContains(detay, "soru_karne")
        dosya = _xlsx(
            [
                ["Sınıf", "Ad Soyad", "Türkçe 5"],
                ["8-A", "Ali Veli", "-"],
            ]
        )
        cevap = self.client.post(
            reverse("yonetim:deneme_soru_yukle", args=[deneme.pk]),
            {"soru_karne": dosya},
            follow=True,
        )
        self.assertContains(cevap, "Soru karnesi yüklendi")
        self.assertEqual(DenemeSoruSonucu.objects.filter(deneme=deneme).count(), 1)

        taslak = _deneme("Taslak", 16, durum=DenemeSinavi.Durum.TASLAK)
        ret = self.client.post(
            reverse("yonetim:deneme_soru_yukle", args=[taslak.pk]),
            {"soru_karne": dosya},
            follow=True,
        )
        self.assertContains(ret, "yalnızca aktif")
        self.assertFalse(DenemeSoruSonucu.objects.filter(deneme=taslak).exists())

    def test_pdf_iki_sutun(self):
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        if not os.path.exists(font):
            self.skipTest("DejaVu yok")
        try:
            import pypdfium2  # noqa: F401
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("pdf kütüphanesi yok")

        pdfmetrics.registerFont(TTFont("DejaVu", font))
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.setFont("DejaVu", 11)
        c.drawString(40, 800, "Ali Veli")
        c.drawString(40, 782, "8-A")
        c.drawString(40, 740, "DERS ANALİZİ")
        c.drawString(40, 700, "TÜRKÇE")
        c.drawString(40, 680, "15 12 3 0")
        c.showPage()
        c.setFont("DejaVu", 11)
        c.drawString(40, 740, "TÜRKÇE")
        c.drawString(40, 720, "5 Paragraf Anlamı C A -")
        c.drawString(40, 700, "2 Sözcükte Anlam A A +")
        c.drawString(40, 660, "SOSYAL BİLGİLER")
        c.drawString(40, 640, "1 Yerleşme B B +")
        c.drawString(320, 740, "MATEMATİK")
        c.drawString(320, 720, "3 Açılar B C -")
        c.drawString(320, 660, "İNGİLİZCE")
        c.drawString(320, 640, "4 Hello A B -")
        c.save()

        deneme = _deneme("PDF", 18)
        stats = import_soru_karneleri(
            SimpleUploadedFile("ali.pdf", buf.getvalue()),
            deneme=deneme,
        )
        satirlar = list(
            DenemeSoruSonucu.objects.filter(deneme=deneme, talebe=self.ali).values_list(
                "ders_ad", "soru_no", "sonuc"
            )
        )
        self.assertGreaterEqual(stats.eslesen_talebe, 1, satirlar)
        self.assertIn(("Türkçe", 5, "yanlis"), satirlar)
        self.assertIn(("Türkçe", 2, "dogru"), satirlar)
        self.assertIn(("Sosyal Bilgiler", 1, "dogru"), satirlar)
        self.assertIn(("Matematik", 3, "yanlis"), satirlar)
        self.assertIn(("İngilizce", 4, "yanlis"), satirlar)
        self.assertFalse(any(ders == "Türkçe" and no == 3 for ders, no, _s in satirlar))
        self.assertFalse(any(no == 15 for _d, no, _s in satirlar))
