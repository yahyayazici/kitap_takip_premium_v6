"""Kurum denemesi — puan aktarımı, silme, PDF paket, etüt kapsamı."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from takip.deneme_excel import deneme_excel_onizle, deneme_sonuclari_aktar
from takip.deneme_models import DenemeBransSonucu, DenemeSinavi, DenemeSonucu
from takip.deneme_service import eksik_deneme_puanlarini_doldur
from takip.models import EtutHocasi, PersonelProfili, SinifSube, Talebe


def _xlsx(satirlar: list[list]) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    for satir in satirlar:
        ws.append(satir)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class DenemePuanAktarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("deneme-admin", "a@b.com", "x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Hoca", user=self.user)
        self.sinif = SinifSube.objects.create(sinif="8", sube="A")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.talebe = Talebe.objects.create(
            ad_soyad="Mehmet Murat Gölbaşı",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.deneme = DenemeSinavi.objects.create(
            ad="Startfen-Start Sayısı",
            sinav_tarihi=date(2026, 9, 15),
            sinif_seviyesi="8",
            olusturan=self.user,
        )

    def test_okyanus_ust_satirdaki_puan_kolonu_cekilir(self):
        dosya = _xlsx(
            [
                ["", "Türkçe", "", "", "", "Puan"],
                ["Ad Soyad", "Doğru", "Yanlış", "Boş", "Net", ""],
                ["Mehmet Murat Gölbaşı", 18, 2, 0, 17.5, 412.25],
            ]
        )
        onizleme = deneme_excel_onizle(dosya)
        self.assertEqual(onizleme.format, "okyanus")
        self.assertEqual(len(onizleme.satirlar), 1)
        self.assertEqual(onizleme.satirlar[0].puan, "412.25")
        sayi, hatalar = deneme_sonuclari_aktar(self.deneme, onizleme, self.user)
        self.assertEqual(hatalar, [])
        self.assertEqual(sayi, 1)
        sonuc = DenemeSonucu.objects.get(deneme=self.deneme)
        self.assertEqual(sonuc.puan, Decimal("412.25"))

    def test_okyanus_puani_basligi(self):
        dosya = _xlsx(
            [
                ["", "Matematik", "", "", ""],
                ["Ad Soyad", "Doğru", "Yanlış", "Boş", "Puanı"],
                ["Mehmet Murat Gölbaşı", 16, 0, 4, 388],
            ]
        )
        onizleme = deneme_excel_onizle(dosya)
        self.assertEqual(onizleme.satirlar[0].puan, "388")

    def test_ders_puani_degil_genel_puan_alinir(self):
        dosya = _xlsx(
            [
                [
                    "",
                    "Türkçe",
                    "",
                    "",
                    "",
                    "",
                    "Matematik",
                    "",
                    "",
                    "",
                    "",
                    "Puanlar / Sıralamalar",
                    "",
                ],
                [
                    "Ad Soyad",
                    "Doğru",
                    "Yanlış",
                    "Boş",
                    "Net",
                    "Puanı",
                    "Doğru",
                    "Yanlış",
                    "Boş",
                    "Net",
                    "Puanı",
                    "Puan",
                    "Sıra",
                ],
                [
                    "Mehmet Murat Gölbaşı",
                    18,
                    2,
                    0,
                    17.5,
                    72.5,
                    16,
                    0,
                    4,
                    16,
                    80,
                    412.25,
                    5,
                ],
            ]
        )
        onizleme = deneme_excel_onizle(dosya)
        self.assertEqual(onizleme.satirlar[0].puan, "412.25")
        self.assertEqual(onizleme.satirlar[0].branslar["turkce"]["net"], "17.50")
        self.assertEqual(onizleme.satirlar[0].branslar["matematik"]["net"], "16.00")

    def test_ham_puan_yerine_yerlestirme_puani(self):
        dosya = _xlsx(
            [
                ["Ad Soyad", "Türkçe Doğru", "Türkçe Net", "Ham Puan", "Puan"],
                ["Mehmet Murat Gölbaşı", 18, 17.5, 188.4, 412.25],
            ]
        )
        onizleme = deneme_excel_onizle(dosya)
        self.assertEqual(onizleme.satirlar[0].puan, "412.25")

    def test_duz_baslikta_ders_puani_atlanir(self):
        dosya = _xlsx(
            [
                [
                    "Ad Soyad",
                    "Türkçe Doğru",
                    "Türkçe Net",
                    "Türkçe Puan",
                    "Matematik Doğru",
                    "Matematik Net",
                    "Puan",
                ],
                ["Mehmet Murat Gölbaşı", 18, 17.5, 72, 16, 16, 401.5],
            ]
        )
        onizleme = deneme_excel_onizle(dosya)
        self.assertEqual(onizleme.satirlar[0].puan, "401.5")

    def test_puan_yoksa_sifir_kalir(self):
        dosya = _xlsx(
            [
                ["", "Türkçe", "", "", ""],
                ["Ad Soyad", "Doğru", "Yanlış", "Boş", "Net"],
                ["Mehmet Murat Gölbaşı", 20, 0, 0, 20],
            ]
        )
        onizleme = deneme_excel_onizle(dosya)
        deneme_sonuclari_aktar(self.deneme, onizleme, self.user)
        sonuc = DenemeSonucu.objects.get(deneme=self.deneme)
        self.assertEqual(sonuc.puan, Decimal("0.00"))

    def test_kayitli_sifir_puan_sonradan_dolar(self):
        sonuc = DenemeSonucu.objects.create(
            deneme=self.deneme,
            talebe=self.talebe,
            toplam_dogru=20,
            toplam_net=Decimal("20.00"),
            puan=Decimal("0.00"),
        )
        DenemeBransSonucu.objects.create(
            sonuc=sonuc,
            brans="turkce",
            dogru=20,
            yanlis=0,
            bos=0,
            net=Decimal("20.00"),
        )
        doldurulan = eksik_deneme_puanlarini_doldur(
            DenemeSonucu.objects.filter(pk=sonuc.pk).prefetch_related(
                "brans_satirlari"
            ).select_related("deneme")
        )
        self.assertEqual(doldurulan[0].puan, Decimal("500.00"))
        sonuc.refresh_from_db()
        self.assertEqual(sonuc.puan, Decimal("500.00"))

    def test_okyanus_toplam_dyb_grubu_cekilir(self):
        dosya = _xlsx(
            [
                ["", "Türkçe", "", "", "", "Toplam", "", "", "", "Puan"],
                [
                    "Ad Soyad",
                    "Doğru",
                    "Yanlış",
                    "Boş",
                    "Net",
                    "Doğru",
                    "Yanlış",
                    "Boş",
                    "Net",
                    "",
                ],
                [
                    "Mehmet Murat Gölbaşı",
                    18,
                    2,
                    0,
                    17.5,
                    87,
                    3,
                    0,
                    86.01,
                    486.20,
                ],
            ]
        )
        onizleme = deneme_excel_onizle(dosya)
        self.assertEqual(onizleme.satirlar[0].toplam["dogru"], 87)
        self.assertEqual(onizleme.satirlar[0].toplam["yanlis"], 3)
        self.assertEqual(onizleme.satirlar[0].toplam["bos"], 0)
        self.assertEqual(onizleme.satirlar[0].toplam["net"], "86.01")
        deneme_sonuclari_aktar(self.deneme, onizleme, self.user)
        sonuc = DenemeSonucu.objects.get(deneme=self.deneme)
        self.assertEqual(sonuc.toplam_dogru, 87)
        self.assertEqual(sonuc.toplam_yanlis, 3)
        self.assertEqual(sonuc.puan, Decimal("486.20"))

    def test_yabanci_dil_ingilizce_olarak_okunur(self):
        dosya = _xlsx(
            [
                ["", "Yabancı Dil", "", "", ""],
                ["Ad Soyad", "Doğru", "Yanlış", "Boş", "Net"],
                ["Mehmet Murat Gölbaşı", 9, 1, 0, 8.75],
            ]
        )
        onizleme = deneme_excel_onizle(dosya)
        self.assertIn("ingilizce", onizleme.satirlar[0].branslar)

    def test_yonetim_deneme_ekle_formu_hizali(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("yonetim:deneme_ekle"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="yonetim-form-grid"')
        self.assertContains(resp, 'name="ad"')
        self.assertContains(resp, 'name="sinav_tarihi"')
        self.assertContains(resp, 'name="sinif_seviyesi"')
        self.assertContains(resp, 'name="aciklama"')
        self.assertContains(resp, 'class="primary-btn"')
        html = resp.content.decode()
        self.assertIn("deneme-form-page", html)
        self.assertNotIn("{{ form.as_p }}", html)


class DenemeSilVePdfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("deneme-sil-admin", "a@b.com", "x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Hoca", user=self.user)
        self.sinif = SinifSube.objects.create(sinif="8", sube="A")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.talebe = Talebe.objects.create(
            ad_soyad="Ahmet Hakan Coşkun",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.deneme = DenemeSinavi.objects.create(
            ad="Startfen",
            sinav_tarihi=date(2026, 9, 15),
            sinif_seviyesi="8",
            durum=DenemeSinavi.Durum.AKTIF,
            olusturan=self.user,
        )
        sonuc = DenemeSonucu.objects.create(
            deneme=self.deneme,
            talebe=self.talebe,
            toplam_dogru=10,
            toplam_yanlis=1,
            toplam_bos=0,
            toplam_net=Decimal("9.75"),
            puan=Decimal("350.00"),
        )
        DenemeBransSonucu.objects.create(
            sonuc=sonuc, brans="turkce", dogru=10, yanlis=1, bos=0, net=Decimal("9.75")
        )
        self.client.force_login(self.user)

    def test_admin_denemeyi_siler(self):
        resp = self.client.post(reverse("deneme_sil", args=[self.deneme.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(DenemeSinavi.objects.filter(pk=self.deneme.pk).exists())

    def test_detay_tablosunda_din_kulturu_var(self):
        from takip.deneme_service import DENEME_DETAY_BRANSLAR, deneme_detay_satirlari

        self.assertIn("din", DENEME_DETAY_BRANSLAR)
        satirlar = deneme_detay_satirlari(
            DenemeSonucu.objects.filter(deneme=self.deneme).prefetch_related(
                "brans_satirlari"
            )
        )
        kodlar = [b["kod"] for b in satirlar[0]["branslar"]]
        self.assertEqual(kodlar, list(DENEME_DETAY_BRANSLAR))
        self.assertEqual(satirlar[0]["branslar"][kodlar.index("din")]["etiket"], "Din Kültürü")

    @patch("takip.deneme_views.html_to_pdf", return_value=b"%PDF-1.4 fake")
    def test_pdf_tek_dosyada_sadece_genel_siralama(self, mock_pdf):
        sonuc = DenemeSonucu.objects.get(deneme=self.deneme)
        DenemeBransSonucu.objects.create(
            sonuc=sonuc, brans="din", dogru=8, yanlis=1, bos=1, net=Decimal("7.75")
        )
        resp = self.client.get(reverse("deneme_detay_pdf", args=[self.deneme.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn(".pdf", resp["Content-Disposition"])
        self.assertNotIn(".zip", resp["Content-Disposition"].lower())
        self.assertEqual(mock_pdf.call_count, 1)
        html = mock_pdf.call_args[0][0]
        self.assertIn("Genel Sıralama", html)
        self.assertNotIn("Din Kültürü", html)


class DenemeEtutKapsamTests(TestCase):
    def setUp(self):
        self.sinif = SinifSube.objects.create(sinif="8", sube="A")
        self.diger_sinif = SinifSube.objects.create(sinif="8", sube="B")
        self.admin = User.objects.create_superuser("deneme-kapsam-admin", "a@b.com", "x")

        self.etut_user = User.objects.create_user("etut-deneme", password="x")
        self.etut_hoca = EtutHocasi.objects.create(
            ad_soyad="Etüt Hoca", user=self.etut_user, aktif=True
        )
        self.etut_hoca.sorumlu_sinif_subeler.add(self.sinif)
        PersonelProfili.objects.create(
            user=self.etut_user,
            ad_soyad="Etüt Hoca",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=self.etut_hoca,
        )

        self.diger_user = User.objects.create_user("diger-etut", password="x")
        self.diger_hoca = EtutHocasi.objects.create(
            ad_soyad="Diğer Hoca", user=self.diger_user, aktif=True
        )
        self.diger_hoca.sorumlu_sinif_subeler.add(self.diger_sinif)

        self.kendi = Talebe.objects.create(
            ad_soyad="Kendi Talebe",
            sinif_sube=self.sinif,
            etut_hocasi=self.etut_hoca,
            dini_ders_hocasi=self.etut_hoca,
        )
        self.baska = Talebe.objects.create(
            ad_soyad="Başka Talebe",
            sinif_sube=self.diger_sinif,
            etut_hocasi=self.diger_hoca,
            dini_ders_hocasi=self.diger_hoca,
        )
        self.deneme = DenemeSinavi.objects.create(
            ad="Kapsam Deneme",
            sinav_tarihi=date(2026, 9, 15),
            sinif_seviyesi="8",
            durum=DenemeSinavi.Durum.AKTIF,
        )
        for t, net in ((self.kendi, "80.00"), (self.baska, "70.00")):
            DenemeSonucu.objects.create(
                deneme=self.deneme,
                talebe=t,
                toplam_net=Decimal(net),
                puan=Decimal("400.00"),
            )

    def test_admin_herkesi_gorur(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("deneme_detay", args=[self.deneme.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kendi Talebe")
        self.assertContains(resp, "Başka Talebe")

    def test_etut_hocasi_sadece_kendi_talebesini_gorur(self):
        self.client.force_login(self.etut_user)
        resp = self.client.get(reverse("deneme_detay", args=[self.deneme.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kendi Talebe")
        self.assertNotContains(resp, "Başka Talebe")

    def test_etut_listede_sadece_kendi_sonuc_sayisi(self):
        self.client.force_login(self.etut_user)
        resp = self.client.get(reverse("deneme_listesi"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "1 öğrenci")
        self.assertNotContains(resp, "2 öğrenci")
