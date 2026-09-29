"""Deneme bireysel karne — ders analizi, genel ortalama, sıralama."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.deneme_models import DenemeBransSonucu, DenemeSinavi, DenemeSonucu
from takip.deneme_service import deneme_bireysel_karne, deneme_karne_ortalamalari
from takip.models import EtutHocasi, PersonelProfili, SinifSube, Talebe


class DenemeBireyselKarneTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("karne-admin", "a@b.com", "x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Hoca", user=self.user)
        self.sinif = SinifSube.objects.create(sinif="6", sube="A")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.talha = Talebe.objects.create(
            ad_soyad="Talha Şahin",
            talebe_no="1237",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.diger_sinif = SinifSube.objects.create(sinif="6", sube="B")
        diger_user = User.objects.create_user("karne-diger", password="x")
        self.diger_hoca = EtutHocasi.objects.create(ad_soyad="Diğer", user=diger_user)
        self.diger_hoca.sorumlu_sinif_subeler.add(self.diger_sinif)
        self.diger = Talebe.objects.create(
            ad_soyad="Ayşe Yılmaz",
            sinif_sube=self.diger_sinif,
            etut_hocasi=self.diger_hoca,
            dini_ders_hocasi=self.diger_hoca,
        )
        self.deneme = DenemeSinavi.objects.create(
            ad="HIZ - 6.SINIF TG GELİŞİM DEĞERLENDİRME SINAVI - 3",
            sinav_tarihi=date(2024, 12, 19),
            sinif_seviyesi="6",
            durum=DenemeSinavi.Durum.AKTIF,
            olusturan=self.user,
        )
        self.talha_sonuc = self._sonuc(
            self.talha,
            turkce=("11", "4", "0", "9.67"),
            net="38.33",
            dogru=47,
            yanlis=26,
            bos=2,
            puan="341.60",
            sinif_sira=3,
            sinif_toplam=27,
            kurum_sira=12,
            kurum_toplam=80,
            harici="Türkiye Geneli: 260 / 556 · Şube Sıralaması: 40 / 120",
        )
        self._sonuc(
            self.diger,
            turkce=("8", "4", "0", "7.00"),
            net="30.00",
            dogru=40,
            yanlis=20,
            bos=5,
            puan="300.00",
            sinif_sira=1,
            sinif_toplam=20,
            kurum_sira=20,
            kurum_toplam=80,
        )
        self.client.force_login(self.user)

    def _sonuc(
        self,
        talebe,
        *,
        turkce,
        net,
        dogru,
        yanlis,
        bos,
        puan,
        sinif_sira,
        sinif_toplam,
        kurum_sira,
        kurum_toplam,
        harici="",
    ):
        sonuc = DenemeSonucu.objects.create(
            deneme=self.deneme,
            talebe=talebe,
            toplam_dogru=dogru,
            toplam_yanlis=yanlis,
            toplam_bos=bos,
            toplam_net=Decimal(net),
            puan=Decimal(puan),
            sinif_sirasi=sinif_sira,
            sinif_toplam=sinif_toplam,
            kurum_sirasi=kurum_sira,
            kurum_toplam=kurum_toplam,
            dis_siralama_metni=harici,
        )
        d, y, b, n = turkce
        DenemeBransSonucu.objects.create(
            sonuc=sonuc,
            brans="turkce",
            dogru=int(d),
            yanlis=int(y),
            bos=int(b),
            net=Decimal(n),
        )
        return sonuc

    def test_karne_ders_net_ortalama_ve_siralama(self):
        sonuc = (
            DenemeSonucu.objects.filter(pk=self.talha_sonuc.pk)
            .select_related("talebe", "talebe__sinif_sube", "deneme")
            .prefetch_related("brans_satirlari")
            .get()
        )
        karne = deneme_bireysel_karne(
            self.deneme, sonuc, deneme_karne_ortalamalari(self.deneme)
        )
        self.assertEqual(karne["ad_soyad"], "TALHA ŞAHİN")
        self.assertEqual(karne["okul_no"], "1237")
        self.assertEqual(karne["sinif_etiket"], "6-A")
        self.assertEqual(karne["sinif_rozet"], "6.SINIF")
        turkce = karne["dersler"][0]
        self.assertEqual(turkce["ad"], "TÜRKÇE")
        self.assertEqual(turkce["soru"], 15)
        self.assertEqual(turkce["dogru"], 11)
        self.assertEqual(turkce["net"], "9,67")
        self.assertEqual(turkce["ort"], "8,34")
        matematik = next(d for d in karne["dersler"] if d["ad"] == "MATEMATİK")
        self.assertEqual(matematik["soru"], "—")
        self.assertEqual(karne["toplam"]["soru"], 75)
        self.assertEqual(karne["toplam"]["net"], "38,33")
        self.assertEqual(karne["toplam"]["ort"], "34,17")
        self.assertEqual(karne["puan"], "341,60")
        siralar = {s["ad"]: s for s in karne["siralama"]}
        self.assertEqual(siralar["GENEL"], {"ad": "GENEL", "giren": "556", "sira": "260"})
        self.assertEqual(siralar["KURUM"], {"ad": "KURUM", "giren": "80", "sira": "12"})
        self.assertEqual(siralar["ŞUBE"], {"ad": "ŞUBE", "giren": "120", "sira": "40"})
        self.assertEqual(siralar["SINIF"], {"ad": "SINIF", "giren": "27", "sira": "3"})

    def test_detayda_karne_baglantisi_var(self):
        resp = self.client.get(reverse("deneme_detay", args=[self.deneme.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bireysel Karneler")
        self.assertContains(
            resp, reverse("deneme_bireysel_pdf", args=[self.deneme.pk, self.talha.pk])
        )

    @patch("takip.deneme_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_bireysel_pdf_ders_analizini_basar(self, mock_pdf):
        resp = self.client.get(
            reverse("deneme_bireysel_pdf", args=[self.deneme.pk, self.talha.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("Talha", resp["Content-Disposition"])
        html = mock_pdf.call_args[0][0]
        self.assertIn("Ders Analizi", html)
        self.assertIn("TALHA ŞAHİN", html)
        self.assertIn("TÜRKÇE", html)
        self.assertIn("9,67", html)
        self.assertIn("8,34", html)
        self.assertIn("LGS", html)
        self.assertIn("341,60", html)
        self.assertIn("6-A", html)
        self.assertIn("A4 portrait", html)
        self.assertLess(html.find("<style>"), html.find("@font-face"))
        self.assertNotIn("SIRANIZ", html)
        self.assertNotIn("SINAVA GİREN", html)
        self.assertIn("box-shadow: none", html)
        self.assertIn("border-bottom: 1px solid #d5deea", html)
        self.assertIn(".pdf-karne.deneme-bireysel .meta-panel", html)

    @patch("takip.deneme_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_zip_her_talebe_icin_karne_icerir(self, mock_pdf):
        resp = self.client.get(reverse("deneme_karne_zip", args=[self.deneme.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/zip")
        self.assertEqual(mock_pdf.call_count, 2)
        arsiv = zipfile.ZipFile(io.BytesIO(resp.content))
        adlar = arsiv.namelist()
        self.assertEqual(len(adlar), 2)
        self.assertTrue(any("Talha" in ad for ad in adlar))
        self.assertTrue(any("Ay" in ad for ad in adlar))

    @patch("takip.deneme_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_etut_baska_talebenin_karnesini_alamaz(self, _mock_pdf):
        etut_user = User.objects.create_user("etut-karne", password="x")
        etut = EtutHocasi.objects.create(ad_soyad="Etüt", user=etut_user, aktif=True)
        etut.sorumlu_sinif_subeler.add(self.sinif)
        PersonelProfili.objects.create(
            user=etut_user,
            ad_soyad="Etüt",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=etut,
        )
        self.talha.etut_hocasi = etut
        self.talha.dini_ders_hocasi = etut
        self.talha.save(update_fields=["etut_hocasi", "dini_ders_hocasi"])
        self.client.force_login(etut_user)
        kendi = self.client.get(
            reverse("deneme_bireysel_pdf", args=[self.deneme.pk, self.talha.pk])
        )
        baska = self.client.get(
            reverse("deneme_bireysel_pdf", args=[self.deneme.pk, self.diger.pk])
        )
        self.assertEqual(kendi.status_code, 200)
        self.assertEqual(baska.status_code, 404)
        html = _mock_pdf.call_args_list[0][0][0]
        self.assertIn("8,34", html)
