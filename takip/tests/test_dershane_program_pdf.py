"""Dershane programı PDF kapsamları: gün, sınıf, etüt, öğretmen, zip."""

from __future__ import annotations

import zipfile
from datetime import date, time
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from pypdf import PdfReader

from takip.dershane_program_models import (
    DershaneDersAtamasi,
    DershaneEtutGrubu,
    DershaneProgrami,
    DershaneSaatBloku,
)
from takip.dershane_program_service import (
    etut_haftalik_pdf_baglami,
    ogretmen_haftalik_pdf_baglami,
    program_ogretmen_adlari,
    sinif_haftalik_pdf_baglami,
    tum_haftalik_pdf_baglami,
)
from takip.pdf_utils import html_to_pdf


class DershaneProgramPdfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("dpadmin", "dp@example.com", "x")
        self.program = DershaneProgrami.objects.create(
            ad="Test Dershane",
            baslangic_tarihi=date(2026, 9, 1),
            bitis_tarihi=date(2027, 6, 30),
            aktif=True,
            olusturan=self.user,
        )
        self.g5 = DershaneEtutGrubu.objects.create(
            program=self.program,
            etiket="5. Sınıf Etüt-A",
            sinif_seviye="5",
            sira=0,
        )
        self.g6 = DershaneEtutGrubu.objects.create(
            program=self.program,
            etiket="6. Sınıf Etüt-A",
            sinif_seviye="6",
            sira=1,
        )
        self.pzt = DershaneSaatBloku.objects.create(
            program=self.program,
            gun=0,
            baslangic_saati=time(8, 30),
            bitis_saati=time(9, 10),
            tur=DershaneSaatBloku.Tur.DERS,
            aciklama="Ders",
            sira=1,
        )
        self.cmt = DershaneSaatBloku.objects.create(
            program=self.program,
            gun=5,
            baslangic_saati=time(10, 10),
            bitis_saati=time(10, 50),
            tur=DershaneSaatBloku.Tur.DERS,
            aciklama="Ders",
            sira=1,
        )
        DershaneSaatBloku.objects.create(
            program=self.program,
            gun=1,
            baslangic_saati=time(8, 30),
            bitis_saati=time(9, 10),
            tur=DershaneSaatBloku.Tur.DERS,
            aciklama="Ders",
            sira=1,
        )
        DershaneDersAtamasi.objects.create(
            program=self.program,
            saat_bloku=self.pzt,
            etut_grubu=self.g5,
            ders_adi="Matematik",
            ogretmen_adi="Ali Yılmaz",
        )
        DershaneDersAtamasi.objects.create(
            program=self.program,
            saat_bloku=self.cmt,
            etut_grubu=self.g5,
            ders_adi="Fen Bilimleri",
            ogretmen_adi="Veli Demir",
        )
        DershaneDersAtamasi.objects.create(
            program=self.program,
            saat_bloku=self.pzt,
            etut_grubu=self.g6,
            ders_adi="Türkçe",
            ogretmen_adi="Ali Yılmaz",
        )
        self.pdf_url = reverse("dershane_program_pdf")

    def test_tum_pdf_sadece_dersi_olan_gunleri_alir(self):
        ctx = tum_haftalik_pdf_baglami(self.user, program=self.program)
        gunler = [p["gun"] for p in ctx["gun_panelleri"]]
        self.assertEqual(gunler, [0, 5])
        self.assertTrue(ctx["tum_gunler"])

    def test_ogretmen_pdf_sadece_kendi_gun_saatini_alir(self):
        ctx = ogretmen_haftalik_pdf_baglami(self.user, self.program, "Ali Yılmaz")
        self.assertTrue(ctx["bireysel"])
        kartlar = ctx["bolumler"][0]["gun_kartlari"]
        self.assertEqual([g["ad"] for g in kartlar], ["Pazartesi"])
        dersler = [s["ders"] for g in kartlar for s in g["satirlar"]]
        self.assertIn("Matematik", dersler)
        self.assertIn("Türkçe", dersler)
        self.assertNotIn("Fen Bilimleri", dersler)
        self.assertEqual(ctx["rol"], "Matematik Öğretmeni")

        veli = ogretmen_haftalik_pdf_baglami(self.user, self.program, "Veli Demir")
        veli_gun = [g["ad"] for g in veli["bolumler"][0]["gun_kartlari"]]
        self.assertEqual(veli_gun, ["Cumartesi"])
        self.assertIn("bulunmamaktadır", veli["bos_notu"])

    def test_sinif_pdf_yalniz_o_sinifin_etutlerini_alir(self):
        ctx = sinif_haftalik_pdf_baglami(self.user, self.program, "5")
        self.assertEqual([p["baslik"] for p in ctx["bolumler"]], ["5. Sınıf Etüt-A"])
        gunler = [g["ad"] for g in ctx["bolumler"][0]["gun_kartlari"]]
        self.assertEqual(gunler, ["Pazartesi", "Cumartesi"])
        dersler = [s["ders"] for g in ctx["bolumler"][0]["gun_kartlari"] for s in g["satirlar"]]
        self.assertIn("Matematik", dersler)
        self.assertIn("Fen Bilimleri", dersler)
        self.assertNotIn("Türkçe", dersler)

    def test_etut_pdf_yalniz_o_grubun_derslerini_alir(self):
        ctx = etut_haftalik_pdf_baglami(self.user, self.program, self.g5.pk)
        self.assertEqual(ctx["kisi"], "5. Sınıf Etüt-A")
        dersler = [
            s["ders"]
            for g in ctx["bolumler"][0]["gun_kartlari"]
            for s in g["satirlar"]
        ]
        self.assertEqual(sorted(dersler), ["Fen Bilimleri", "Matematik"])

    def test_bireysel_html_giris_karti_duzeninde(self):
        ctx = ogretmen_haftalik_pdf_baglami(self.user, self.program, "Ali Yılmaz")
        html = render_to_string("dershane_program_bireysel_pdf.html", ctx)
        self.assertIn("Kişiye özel belge", html)
        self.assertIn("who-name", html)
        self.assertIn("Ali Yılmaz", html)
        self.assertIn("Pazartesi", html)
        self.assertIn("Matematik", html)
        self.assertIn("5. Sınıf Etüt-A", html)
        self.assertNotIn("Cumartesi", html)
        self.assertNotIn("program-table", html)

    def test_sinif_html_iki_etut_yan_yana(self):
        g5b = DershaneEtutGrubu.objects.create(
            program=self.program,
            etiket="5. Sınıf Etüt-B",
            sinif_seviye="5",
            sira=2,
        )
        DershaneDersAtamasi.objects.create(
            program=self.program,
            saat_bloku=self.pzt,
            etut_grubu=g5b,
            ders_adi="Türkçe",
            ogretmen_adi="Ayşe Kaya",
        )
        ctx = sinif_haftalik_pdf_baglami(self.user, self.program, "5")
        self.assertEqual(len(ctx["bolum_satirlari"]), 1)
        self.assertEqual(len(ctx["bolum_satirlari"][0]), 2)
        html = render_to_string("dershane_program_bireysel_pdf.html", ctx)
        self.assertIn("is-sinif", html)
        self.assertIn("bolum-grid", html)
        self.assertIn("5. Sınıf Etüt-A", html)
        self.assertIn("5. Sınıf Etüt-B", html)

    def test_sinif_pdf_yogun_program_tek_sayfa(self):
        g5b = DershaneEtutGrubu.objects.create(
            program=self.program,
            etiket="5. Sınıf Etüt-B",
            sinif_seviye="5",
            sira=2,
        )
        cuma_saatler = [
            (time(21, 40), time(22, 20)),
            (time(22, 20), time(23, 0)),
            (time(23, 0), time(23, 40)),
            (time(23, 40), time(0, 20)),
        ]
        cmt_saatler = [
            (time(8, 30), time(9, 10)),
            (time(9, 20), time(10, 0)),
            (time(10, 10), time(10, 50)),
            (time(11, 0), time(11, 40)),
            (time(11, 50), time(12, 30)),
        ]
        dersler = [
            ("Türkçe", "Hacı Bayram İnalcığıl"),
            ("Türkçe", "Hacı Bayram İnalcığıl"),
            ("İngilizce", "Yusuf Yılmaz"),
            ("İngilizce", "Yusuf Yılmaz"),
            ("Matematik", "Ahmet Kurnaz Bayte"),
            ("Matematik", "Ahmet Kurnaz Bayte"),
            ("Fen Bilimleri", "Burhan Kocaman"),
            ("Fen Bilimleri", "Burhan Kocaman"),
            ("Sosyal Bilgiler", "Hasan Yaprak"),
        ]
        DershaneDersAtamasi.objects.create(
            program=self.program,
            saat_bloku=self.pzt,
            etut_grubu=g5b,
            ders_adi="Atatürk Okuma",
            ogretmen_adi="Hacı Bayram İnalcığıl",
        )
        for sira, (bas, bit) in enumerate(cuma_saatler, start=2):
            ders, ogretmen = dersler[sira - 2]
            blok = DershaneSaatBloku.objects.create(
                program=self.program,
                gun=4,
                baslangic_saati=bas,
                bitis_saati=bit,
                tur=DershaneSaatBloku.Tur.DERS,
                aciklama="Ders",
                sira=sira,
            )
            for grup in (self.g5, g5b):
                DershaneDersAtamasi.objects.create(
                    program=self.program,
                    saat_bloku=blok,
                    etut_grubu=grup,
                    ders_adi=ders,
                    ogretmen_adi=ogretmen,
                )
        for sira, (bas, bit) in enumerate(cmt_saatler, start=2):
            ders, ogretmen = dersler[sira + 2]
            if (bas, bit) == (time(10, 10), time(10, 50)):
                DershaneDersAtamasi.objects.create(
                    program=self.program,
                    saat_bloku=self.cmt,
                    etut_grubu=g5b,
                    ders_adi=ders,
                    ogretmen_adi=ogretmen,
                )
                continue
            blok = DershaneSaatBloku.objects.create(
                program=self.program,
                gun=5,
                baslangic_saati=bas,
                bitis_saati=bit,
                tur=DershaneSaatBloku.Tur.DERS,
                aciklama="Ders",
                sira=sira,
            )
            for grup in (self.g5, g5b):
                DershaneDersAtamasi.objects.create(
                    program=self.program,
                    saat_bloku=blok,
                    etut_grubu=grup,
                    ders_adi=ders,
                    ogretmen_adi=ogretmen,
                )
        ctx = sinif_haftalik_pdf_baglami(self.user, self.program, "5")
        html = render_to_string("dershane_program_bireysel_pdf.html", ctx)
        pdf = html_to_pdf(html, base_url="file:///tmp/")
        self.assertTrue(pdf)
        sayfa = len(PdfReader(BytesIO(pdf)).pages)
        self.assertEqual(sayfa, 1)

    @patch("takip.dershane_program_views.pdf_engine_status", return_value="weasyprint")
    @patch("takip.dershane_program_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_ogretmen_zip_her_ogretmen_icin_pdf_yazar(self, _pdf, _engine):
        self.client.force_login(self.user)
        res = self.client.get(
            self.pdf_url,
            {"program": self.program.pk, "mod": "ogretmen", "zip": "1"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/zip")
        with zipfile.ZipFile(BytesIO(res.content)) as arsiv:
            adlar = arsiv.namelist()
        self.assertEqual(len(adlar), 2)
        self.assertTrue(any("ali" in a.lower() for a in adlar))
        self.assertTrue(any("veli" in a.lower() for a in adlar))

    @patch("takip.dershane_program_views.pdf_engine_status", return_value="weasyprint")
    @patch("takip.dershane_program_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_sinif_ve_gun_pdf_ayri_dosya_adi(self, _pdf, _engine):
        self.client.force_login(self.user)
        sinif = self.client.get(
            self.pdf_url,
            {"program": self.program.pk, "mod": "sinif", "sinif": "5"},
        )
        self.assertEqual(sinif.status_code, 200)
        self.assertIn("sinif_5", sinif["Content-Disposition"])

        gun = self.client.get(
            self.pdf_url,
            {"program": self.program.pk, "mod": "genel", "gun": "5"},
        )
        self.assertEqual(gun.status_code, 200)
        self.assertIn("gun_5", gun["Content-Disposition"])

    def test_program_ogretmen_adlari(self):
        self.assertEqual(
            program_ogretmen_adlari(self.program),
            ["Ali Yılmaz", "Veli Demir"],
        )
