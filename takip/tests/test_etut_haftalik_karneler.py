"""Etüt hocası — haftalık karne listesi ve toplu PDF."""

from __future__ import annotations

import zipfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import EtutHocasi, PersonelProfili, SinifSube, Talebe
from takip.ogretmen_service import aktif_hafta_baslangic


class EtutHaftalikKarnelerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("etutkarneler", password="x")
        self.hoca = EtutHocasi.objects.create(
            ad_soyad="Etüt Hoca", user=self.user, aktif=True
        )
        PersonelProfili.objects.create(
            user=self.user,
            ad_soyad="Etüt Hoca",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=self.hoca,
        )
        self.sinif = SinifSube.objects.create(sinif="7", sube="A")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.t1 = Talebe.objects.create(
            ad_soyad="Abdullah Bedestenci",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.t2 = Talebe.objects.create(
            ad_soyad="Ahmet Arif Kara",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.client.force_login(self.user)

    def test_liste_tum_pdf_linki_gosterir(self):
        resp = self.client.get(reverse("etut_haftalik_karneler"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Tüm PDF")
        self.assertContains(resp, reverse("etut_haftalik_karneler_pdf"))

    @patch("takip.etut_karne_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_tum_pdf_zip_her_talebe_ayri_dosya(self, _pdf):
        hafta = aktif_hafta_baslangic()
        resp = self.client.get(
            reverse("etut_haftalik_karneler_pdf"),
            {"hafta": hafta.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/zip")
        self.assertIn(
            f"haftalik-egitim-karneleri-{hafta:%Y-%m-%d}.zip",
            resp["Content-Disposition"],
        )
        with zipfile.ZipFile(BytesIO(resp.content)) as arsiv:
            adlar = arsiv.namelist()
        self.assertEqual(len(adlar), 2)
        self.assertTrue(all(ad.endswith(".pdf") for ad in adlar))
        self.assertTrue(any("Abdullah" in ad or "Bedestenci" in ad for ad in adlar))
        self.assertTrue(any("Ahmet" in ad or "Kara" in ad for ad in adlar))
        self.assertEqual(_pdf.call_count, 2)

    @patch("takip.etut_karne_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_baska_hocanin_talebesi_zip_disinda(self, _pdf):
        diger_user = User.objects.create_user("digerhoca", password="x")
        diger_hoca = EtutHocasi.objects.create(
            ad_soyad="Diğer Hoca", user=diger_user, aktif=True
        )
        diger_sinif = SinifSube.objects.create(sinif="7", sube="B")
        diger_hoca.sorumlu_sinif_subeler.add(diger_sinif)
        Talebe.objects.create(
            ad_soyad="Yabancı Talebe",
            sinif_sube=diger_sinif,
            etut_hocasi=diger_hoca,
            dini_ders_hocasi=diger_hoca,
        )
        resp = self.client.get(reverse("etut_haftalik_karneler_pdf"))
        self.assertEqual(resp.status_code, 200)
        with zipfile.ZipFile(BytesIO(resp.content)) as arsiv:
            adlar = arsiv.namelist()
        self.assertEqual(len(adlar), 2)
        self.assertFalse(any("Yabanc" in ad for ad in adlar))
