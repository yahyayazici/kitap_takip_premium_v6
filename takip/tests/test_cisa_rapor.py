"""ÇİSA — seçilen denemelerin ortalaması, konu dökümü ve PDF."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.cisa_service import cisa_deneme_listesi, cisa_rapor
from takip.deneme_models import (
    DenemeBransSonucu,
    DenemeSinavi,
    DenemeSonucu,
    DenemeSoruSonucu,
)
from takip.models import EtutHocasi, PersonelProfili, SinifSube, Talebe


class CisaRaporTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("cisa-admin", "a@b.com", "x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Cisa Hoca", user=self.admin, aktif=True)
        self.sinif = SinifSube.objects.create(sinif="8", sube="A")
        self.diger_sinif = SinifSube.objects.create(sinif="8", sube="B")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.ali = Talebe.objects.create(
            ad_soyad="Ali Çisa",
            talebe_no="81",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.ayse = Talebe.objects.create(
            ad_soyad="Ayşe Çisa",
            talebe_no="82",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )

        self.etut_user = User.objects.create_user("cisa-etut", password="x")
        self.etut_hoca = EtutHocasi.objects.create(
            ad_soyad="Etüt Çisa", user=self.etut_user, aktif=True
        )
        self.etut_hoca.sorumlu_sinif_subeler.add(self.sinif)
        PersonelProfili.objects.create(
            user=self.etut_user,
            ad_soyad="Etüt Çisa",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=self.etut_hoca,
        )
        self.baska_user = User.objects.create_user("cisa-baska", password="x")
        self.baska_hoca = EtutHocasi.objects.create(
            ad_soyad="Başka Hoca", user=self.baska_user, aktif=True
        )
        self.baska_hoca.sorumlu_sinif_subeler.add(self.diger_sinif)
        self.baska = Talebe.objects.create(
            ad_soyad="Başka Talebe",
            talebe_no="83",
            sinif_sube=self.diger_sinif,
            etut_hocasi=self.baska_hoca,
            dini_ders_hocasi=self.baska_hoca,
        )

        self.ocak = self._deneme("Ocak Deneme", date(2026, 1, 10), DenemeSinavi.Durum.AKTIF)
        self.subat = self._deneme("Şubat Deneme", date(2026, 2, 10), DenemeSinavi.Durum.AKTIF)
        self.silinen = self._deneme("Silinen Deneme", date(2026, 4, 1), DenemeSinavi.Durum.ARSIV)
        self.mart = self._deneme("Mart Deneme", date(2026, 3, 10), DenemeSinavi.Durum.AKTIF)
        self.taslak = self._deneme("Taslak Deneme", date(2026, 4, 10), DenemeSinavi.Durum.TASLAK)
        self.yabanci = self._deneme("Yabancı Deneme", date(2026, 1, 20), DenemeSinavi.Durum.AKTIF)

        self.ali_ocak = self._sonuc(self.ocak, self.ali, "80.00", "10.00", 8, 4, 0)
        self.ali_subat = self._sonuc(self.subat, self.ali, "60.00", "6.00", 6, 0, 2)
        self._sonuc(self.mart, self.ali, "100.00", "20.00", 20, 0, 0)
        self._sonuc(self.taslak, self.ali, "50.00", "5.00", 5, 0, 0)
        self._sonuc(self.silinen, self.ali, "30.00", "3.00", 3, 0, 0)
        self._sonuc(self.ocak, self.ayse, "40.00", "4.00", 4, 0, 0)
        self._sonuc(self.subat, self.ayse, "70.00", "8.00", 8, 0, 0)
        self._sonuc(self.yabanci, self.baska, "90.00", "15.00", 15, 0, 0)

        self._soru(self.ocak, self.ali, 1, "dogru")
        self._soru(self.ocak, self.ali, 2, "yanlis")
        self._soru(self.ocak, self.ali, 3, "yanlis")
        self._soru(self.ocak, self.ali, 4, "bos")
        self._soru(self.ocak, self.ali, 5, "dogru", konu="Sözcükte anlam")
        self._soru(self.ocak, self.ali, 6, "dogru", konu="Sözcükte anlam")
        for no, sonuc in ((1, "dogru"), (2, "dogru"), (3, "dogru"), (4, "yanlis")):
            self._soru(self.ocak, self.ayse, no, sonuc)

    def _deneme(self, ad, tarih, durum):
        return DenemeSinavi.objects.create(
            ad=ad,
            sinav_tarihi=tarih,
            sinif_seviyesi="8",
            durum=durum,
        )

    def _sonuc(self, deneme, talebe, toplam, turkce_net, dogru, yanlis, bos):
        sonuc = DenemeSonucu.objects.create(
            deneme=deneme,
            talebe=talebe,
            toplam_net=Decimal(toplam),
            puan=Decimal("400.00"),
        )
        DenemeBransSonucu.objects.create(
            sonuc=sonuc,
            brans="turkce",
            dogru=dogru,
            yanlis=yanlis,
            bos=bos,
            net=Decimal(turkce_net),
        )
        return sonuc

    def _soru(self, deneme, talebe, no, sonuc, konu="Paragraf"):
        DenemeSoruSonucu.objects.create(
            deneme=deneme,
            talebe=talebe,
            ders_ad="Türkçe",
            ders_key="turkce",
            soru_no=no,
            konu_ad=konu,
            sonuc=sonuc,
        )

    def test_secilen_denemelerin_ortalamasi_ve_konusu(self):
        rapor = cisa_rapor(
            self.ali, [self.ocak.id, self.subat.id, self.yabanci.id, self.silinen.id]
        )
        self.assertEqual(rapor["ortalama_net"], "70,00")
        self.assertEqual([d["ad"] for d in rapor["denemeler"]], ["Ocak Deneme", "Şubat Deneme"])
        self.assertEqual(rapor["denemeler"][0]["soru_karnesi"], True)
        self.assertEqual(rapor["denemeler"][1]["soru_karnesi"], False)
        turkce = rapor["dersler"][0]
        self.assertEqual(turkce["ad"], "Türkçe")
        self.assertEqual(turkce["net"], "8,00")
        self.assertEqual(turkce["sinif_net"], "7,00")
        self.assertEqual(turkce["durum"], "iyi")
        self.assertEqual(turkce["fark"], "1,00")
        self.assertEqual(turkce["fark_yazi"], "üstünde")
        self.assertEqual(turkce["dogru"], 14)
        self.assertEqual(turkce["yanlis"], 4)
        self.assertEqual(turkce["bos"], 2)
        self.assertEqual(turkce["dogru_yuzde"], 70)

        self.assertEqual(len(rapor["konular"]), 1)
        paragraf = rapor["konular"][0]["satirlar"][0]
        self.assertEqual(paragraf["konu"], "Paragraf")
        self.assertEqual(paragraf["soru"], 4)
        self.assertEqual(paragraf["dogru"], 1)
        self.assertEqual(paragraf["yanlis"], 2)
        self.assertEqual(paragraf["bos"], 1)
        self.assertEqual(paragraf["yuzde"], 25)
        self.assertEqual(paragraf["sinif_yuzde"], 50)
        self.assertEqual(rapor["kayiplar"][0]["konu"], "Paragraf")
        self.assertEqual(rapor["kayiplar"][0]["kaynak"], "yanlıştan")
        self.assertNotIn("Sözcükte anlam", [k["konu"] for k in rapor["kayiplar"]])

    def test_secilmeyen_ve_taslak_girmez(self):
        liste = cisa_deneme_listesi(self.ali)
        adlar = [d["ad"] for d in liste]
        self.assertEqual(adlar, ["Mart Deneme", "Şubat Deneme", "Ocak Deneme"])
        self.assertNotIn("Taslak Deneme", adlar)
        self.assertNotIn("Silinen Deneme", adlar)
        self.assertIsNone(cisa_rapor(self.ali, [self.silinen.id]))
        yalniz = cisa_rapor(self.ali, [self.subat.id])
        self.assertEqual(yalniz["konular"], [])
        self.assertEqual(yalniz["ortalama_net"], "60,00")
        self.assertIsNone(cisa_rapor(self.ali, [self.taslak.id, self.yabanci.id]))

    def test_sayfa_ve_pdf(self):
        self.client.force_login(self.admin)
        profil = self.client.get(reverse("talebe_detay", args=[self.ali.id]))
        self.assertContains(profil, reverse("cisa_sec", args=[self.ali.id]))
        sayfa = self.client.get(reverse("cisa_sec", args=[self.ali.id]))
        self.assertEqual(sayfa.status_code, 200)
        self.assertContains(sayfa, "Hangi denemelerin raporunu alalım?")
        self.assertContains(sayfa, "Ocak Deneme")
        self.assertContains(sayfa, "Şubat Deneme")
        self.assertContains(sayfa, "Soru karnesi var")
        self.assertContains(sayfa, "Yalnız net")
        self.assertNotContains(sayfa, "Taslak Deneme")
        self.assertNotContains(sayfa, "Silinen Deneme")

        with patch("takip.cisa_views.html_to_pdf", return_value=b"%PDF-1.4 fake") as mock_pdf:
            resp = self.client.post(
                reverse("cisa_pdf", args=[self.ali.id]),
                {"deneme": [self.ocak.id, self.subat.id, self.silinen.id]},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("Ali", resp["Content-Disposition"])
        html = mock_pdf.call_args[0][0]
        self.assertIn("Ali Çisa", html)
        self.assertIn("70,00", html)
        self.assertIn("Paragraf", html)
        self.assertIn("yanlıştan", html)
        self.assertIn("cisa-logo.png", html)
        self.assertIn('class="kayip"', html)
        self.assertIn("sayfa-denemeler", html)
        self.assertIn("sayfa-kazanim", html)
        self.assertIn("Kazanım alınan denemeler", html)
        self.assertIn("Ocak Deneme", html)
        kazanim = html.index("sayfa-kazanim")
        self.assertLess(html.index("sayfa-denemeler"), kazanim)
        self.assertLess(html.index("Kazanım alınan denemeler"), kazanim)
        self.assertIn("Paragraf", html[kazanim:])
        self.assertNotIn("ders-sayfa", html)
        self.assertNotIn("Şubat Deneme", html)
        self.assertIn("dyb", html)
        self.assertRegex(html, r"td\.kim\s*\{[^}]*text-align:\s*left")
        self.assertRegex(html, r"td\.net\s*\{[^}]*text-align:\s*right")
        self.assertLess(html.index('class="kim"'), html.index('class="net"'))
        self.assertLess(html.index('class="net"'), html.index('class="cizgi"'))
        self.assertIn('class="dogru"', html)
        self.assertIn('class="yanlis"', html)
        self.assertIn("td.dogru b { color: #0f7a4a; }", html)
        self.assertIn("td.yanlis b { color: #c62828; }", html)
        self.assertRegex(html, r"\.ders\s*\{[^}]*text-align:\s*left")
        self.assertRegex(html, r"\.kart-net\s*\{[^}]*text-align:\s*left")
        self.assertIn("%70 doğruluk", html)
        self.assertIn("1,00 net üstünde", html)
        self.assertIn('class="cubuk"', html)
        self.assertNotIn("Mart Deneme", html)
        self.assertNotIn("Silinen Deneme", html)

        bos = self.client.post(reverse("cisa_pdf", args=[self.ali.id]), {})
        self.assertRedirects(bos, reverse("cisa_sec", args=[self.ali.id]))

    def test_yetkisiz_talebe_404(self):
        self.client.force_login(self.etut_user)
        kendi = self.client.get(reverse("cisa_sec", args=[self.ali.id]))
        self.assertEqual(kendi.status_code, 200)
        yabanci = self.client.get(reverse("cisa_sec", args=[self.baska.id]))
        self.assertEqual(yabanci.status_code, 404)

    def test_denemeler_sirala_yaninda_cisa(self):
        self.client.force_login(self.admin)
        sayfa = self.client.get(reverse("deneme_listesi"))
        self.assertEqual(sayfa.status_code, 200)
        html = sayfa.content.decode()
        self.assertLess(html.index("ÇİSA"), html.index("Sırala"))
        self.assertIn(reverse("cisa_denemeler"), html)
        giris = self.client.get(reverse("cisa_denemeler"))
        self.assertContains(giris, "Deneme raporları")
        self.assertContains(giris, "Ali Çisa")
        self.assertContains(giris, "Ocak Deneme")
        self.assertContains(giris, "Sınıf PDF")
        self.assertNotContains(giris, "Silinen Deneme")

    def test_etut_kendi_sinifinda_pdf_ve_toplu_paket(self):
        self.client.force_login(self.etut_user)
        sayfa = self.client.get(reverse("cisa_denemeler"))
        html = sayfa.content.decode()
        self.assertIn("Ali Çisa", html)
        self.assertIn("Ayşe Çisa", html)
        self.assertNotIn("Başka Talebe", html)
        self.assertIn("Ocak Deneme", html)
        self.assertIn("Sınıf PDF", html)
        self.assertIn(f'name="talebe" value="{self.ali.id}"', html)
        self.assertNotIn("Silinen Deneme", html)
        self.assertNotIn("Taslak Deneme", html)
        self.assertNotIn("Yabancı Deneme", html)

        with patch("takip.cisa_views.html_to_pdf", return_value=b"%PDF-1.4 fake"):
            tek = self.client.post(
                reverse("cisa_denemeler"),
                {"deneme": [self.ocak.id], "talebe": self.ali.id},
            )
            paket = self.client.post(
                reverse("cisa_denemeler"),
                {"deneme": [self.ocak.id], "toplu": "1"},
            )
            yabanci = self.client.post(
                reverse("cisa_denemeler"),
                {"deneme": [self.yabanci.id], "talebe": self.baska.id},
            )
        self.assertEqual(tek.status_code, 200)
        self.assertEqual(tek["Content-Type"], "application/pdf")
        self.assertIn("Ali", tek["Content-Disposition"])
        self.assertEqual(paket.status_code, 200)
        self.assertEqual(paket["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(paket.content)) as arsiv:
            self.assertEqual(len(arsiv.namelist()), 2)
        self.assertEqual(yabanci.status_code, 302)
        detay = self.client.get(
            reverse(
                "ogretmen_deneme_kontrol_ogrenci_detay",
                args=[self.sinif.id, self.ali.id],
            )
        )
        self.assertNotContains(detay, reverse("cisa_sec", args=[self.ali.id]))
        masa = self.client.get(
            reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[self.sinif.id])
            + "?ekran=cisa"
        )
        self.assertContains(masa, "cisa-logo.png")
        self.assertContains(masa, f'name="talebe" value="{self.ali.id}"')
        self.assertNotContains(masa, "ÇİSA →")

    def test_tum_sinifta_grup_ve_tum_sinif_paketi(self):
        user = User.objects.create_user("cisa-grup", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Grup Çisa", user=user, aktif=True)
        PersonelProfili.objects.create(
            user=user,
            ad_soyad="Grup Çisa",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=hoca,
        )
        hoca.sorumlu_sinif_subeler.add(self.sinif, self.diger_sinif)
        self.client.force_login(user)
        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi") + "?ekran=cisa")
        html = sayfa.content.decode()
        self.assertContains(sayfa, "A grubu raporunu indir")
        self.assertContains(sayfa, "B grubu raporunu indir")
        self.assertContains(sayfa, "Tüm sınıf raporunu indir")
        self.assertIn(f'name="sinif" value="{self.sinif.id}"', html)
        self.assertIn(f'name="sinif" value="{self.diger_sinif.id}"', html)
        self.assertIn(
            f'name="sinif" value="{self.sinif.id},{self.diger_sinif.id}"',
            html,
        )
        self.assertIn(f'name="talebe" value="{self.ali.id}"', html)
        self.assertIn(f'name="talebe" value="{self.baska.id}"', html)
        self.assertNotIn(reverse("cisa_sec", args=[self.ali.id]), html)

        with patch("takip.cisa_views.html_to_pdf", return_value=b"%PDF-1.4 fake"):
            a_grubu = self.client.post(
                reverse("cisa_denemeler"),
                {"deneme": [self.ocak.id], "sinif": str(self.sinif.id)},
            )
            tum = self.client.post(
                reverse("cisa_denemeler"),
                {
                    "deneme": [self.ocak.id, self.yabanci.id],
                    "sinif": f"{self.sinif.id},{self.diger_sinif.id}",
                },
            )
            yabanci_karisik = self.client.post(
                reverse("cisa_denemeler"),
                {
                    "deneme": [self.yabanci.id],
                    "sinif": f"{self.diger_sinif.id},999999",
                },
            )
        self.assertEqual(a_grubu.status_code, 200)
        self.assertEqual(a_grubu["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(a_grubu.content)) as arsiv:
            self.assertEqual(len(arsiv.namelist()), 2)
            self.assertTrue(any("Ali" in ad for ad in arsiv.namelist()))
            self.assertFalse(any("Başka" in ad for ad in arsiv.namelist()))
        self.assertEqual(tum.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(tum.content)) as arsiv:
            adlar = arsiv.namelist()
            self.assertEqual(len(adlar), 3)
            self.assertTrue(any("Başka" in ad for ad in adlar))
        self.assertEqual(yabanci_karisik.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(yabanci_karisik.content)) as arsiv:
            self.assertEqual(len(arsiv.namelist()), 1)
            self.assertIn("Başka", arsiv.namelist()[0])
