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
        self.assertIn("Deneme Sonuç Tablosu", html)
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
        self.assertContains(resp, "1 talebe")
        self.assertNotContains(resp, "2 talebe")


class DenemeEtutSiraTests(TestCase):
    """Kurum sırası durur; etüt kendi denemelerini 1'den görür."""

    def setUp(self):
        from takip.models import EgitimYili

        self.yil = EgitimYili.objects.create(
            ad="2026-2027 sira",
            baslangic=date(2026, 9, 1),
            bitis=date(2027, 6, 30),
        )
        self.sinif = SinifSube.objects.create(sinif="5", sube="A")
        self.diger_sinif = SinifSube.objects.create(sinif="5", sube="B")
        self.admin = User.objects.create_superuser("sira-admin", "a@b.com", "x")

        self.etut_user = User.objects.create_user("sira-etut", password="x")
        self.etut_hoca = EtutHocasi.objects.create(
            ad_soyad="Recep Bebek", user=self.etut_user, aktif=True
        )
        self.etut_hoca.sorumlu_sinif_subeler.add(self.sinif)
        PersonelProfili.objects.create(
            user=self.etut_user,
            ad_soyad="Recep Bebek",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=self.etut_hoca,
        )

        self.diger_user = User.objects.create_user("sira-diger", password="x")
        self.diger_hoca = EtutHocasi.objects.create(
            ad_soyad="Diğer Hoca", user=self.diger_user, aktif=True
        )
        self.diger_hoca.sorumlu_sinif_subeler.add(self.diger_sinif)

        self.talebe = Talebe.objects.create(
            ad_soyad="Etüt Talebesi",
            sinif_sube=self.sinif,
            etut_hocasi=self.etut_hoca,
            dini_ders_hocasi=self.etut_hoca,
        )
        self.baska = Talebe.objects.create(
            ad_soyad="Başka Sınıf",
            sinif_sube=self.diger_sinif,
            etut_hocasi=self.diger_hoca,
            dini_ders_hocasi=self.diger_hoca,
        )
        self.d1 = self._deneme("Kurum 1", date(2026, 9, 1), 1)
        self.d2 = self._deneme("Kurum 2", date(2026, 9, 10), 2)
        self.d3 = self._deneme("Ankara", date(2026, 9, 22), 3)
        DenemeSonucu.objects.create(
            deneme=self.d1, talebe=self.baska, puan=Decimal("300.00")
        )
        DenemeSonucu.objects.create(
            deneme=self.d2, talebe=self.baska, puan=Decimal("320.00")
        )
        DenemeSonucu.objects.create(
            deneme=self.d3, talebe=self.talebe, puan=Decimal("409.00")
        )
        DenemeSonucu.objects.create(
            deneme=self.d3, talebe=self.baska, puan=Decimal("400.00")
        )

    def _deneme(self, ad, tarih, sira, seviye="5"):
        return DenemeSinavi.objects.create(
            ad=ad,
            sinav_tarihi=tarih,
            sinif_seviyesi=seviye,
            egitim_yili=self.yil,
            sira_no=sira,
            yayin=ad,
            durum=DenemeSinavi.Durum.AKTIF,
            tur=DenemeSinavi.Tur.GRUP,
        )

    def test_etut_kendi_ilk_denemesini_bir_gorur(self):
        self.client.force_login(self.etut_user)
        resp = self.client.get(reverse("deneme_listesi"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "1. Deneme")
        self.assertNotContains(resp, "3. Deneme")
        detay = self.client.get(reverse("deneme_detay", args=[self.d3.pk]))
        self.assertEqual(detay.status_code, 200)
        self.assertContains(detay, "1. Deneme")
        self.assertNotContains(detay, "3. Deneme")
        self.d3.refresh_from_db()
        self.assertEqual(self.d3.sira_no, 3)

    def test_idare_kurum_sirasini_gorur(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("deneme_listesi"))
        self.assertContains(resp, "1. Deneme")
        self.assertContains(resp, "3. Deneme")
        detay = self.client.get(reverse("deneme_detay", args=[self.d3.pk]))
        self.assertContains(detay, "3. Deneme — Ankara")

    def test_filtre_sonraki_numarayi_kaydirmaz(self):
        d4 = self._deneme("İkinci", date(2026, 10, 1), 4)
        DenemeSonucu.objects.create(
            deneme=d4, talebe=self.talebe, puan=Decimal("420.00")
        )
        self.client.force_login(self.etut_user)
        resp = self.client.get(
            reverse("deneme_listesi"), {"baslangic": "2026-09-25"}
        )
        self.assertContains(resp, "2. Deneme")
        self.assertNotContains(resp, "1. Deneme")
        self.assertNotContains(resp, "4. Deneme")

    def test_arsiv_ve_baska_seviye_sayaci_bozmaz(self):
        from takip.deneme_service import deneme_sira_haritasi_talebeler

        arsiv = self._deneme("Eski", date(2026, 8, 1), 9)
        arsiv.durum = DenemeSinavi.Durum.ARSIV
        arsiv.save(update_fields=["durum"])
        DenemeSonucu.objects.create(
            deneme=arsiv, talebe=self.talebe, puan=Decimal("10.00")
        )
        bireysel = DenemeSinavi.objects.create(
            ad="Bireysel",
            sinav_tarihi=date(2026, 8, 15),
            sinif_seviyesi="5",
            egitim_yili=self.yil,
            durum=DenemeSinavi.Durum.AKTIF,
            tur=DenemeSinavi.Tur.BIREYSEL,
        )
        DenemeSonucu.objects.create(
            deneme=bireysel, talebe=self.talebe, puan=Decimal("50.00")
        )
        alti = self._deneme("Altı", date(2026, 9, 5), 1, seviye="6")
        DenemeSonucu.objects.create(
            deneme=alti, talebe=self.talebe, puan=Decimal("100.00")
        )
        harita = deneme_sira_haritasi_talebeler([self.talebe.id])
        self.assertEqual(harita[self.d3.pk], 1)
        self.assertEqual(harita[alti.pk], 1)
        self.assertNotIn(arsiv.pk, harita)
        self.assertNotIn(bireysel.pk, harita)

    def test_etut_kontrol_etiketi_etut_sirasidir(self):
        from takip.etut_kontrol_service import (
            etut_deneme_kutulari,
            etut_dikkat,
            talebe_deneme_kutulari,
        )
        from takip.deneme_models import DenemeKazanimSonucu

        DenemeKazanimSonucu.objects.create(
            deneme=self.d3,
            talebe=self.talebe,
            ders_ad="Matematik",
            konu_ad="Kesirler",
            ders_key="matematik",
            konu_key="kesirler",
            yuzde=Decimal("80.00"),
        )
        kutular = etut_deneme_kutulari(self.etut_hoca)
        self.assertEqual(len(kutular), 1)
        self.assertEqual(kutular[0]["deneme"].goster_sira, 1)
        self.assertEqual(kutular[0]["deneme"].sira_no, 3)
        dikkat = etut_dikkat(self.etut_hoca)
        self.assertEqual(dikkat["deneme"].goster_sira, 1)
        talebe_kutu = talebe_deneme_kutulari(self.talebe)
        self.assertEqual(talebe_kutu[0]["deneme"].goster_sira, 1)


class DenemeDersNetOrtalamaTests(TestCase):
    def test_sinif_ders_neti_ayri_ve_toplu(self):
        from takip.deneme_service import deneme_ders_net_ozeti, deneme_detay_satirlari

        user = User.objects.create_user("net-ort", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Net Hoca", user=user, aktif=True)
        a = SinifSube.objects.create(sinif="8", sube="A")
        b = SinifSube.objects.create(sinif="8", sube="B")
        hoca.sorumlu_sinif_subeler.add(a, b)
        ali = Talebe.objects.create(
            ad_soyad="Ali Net", sinif_sube=a, etut_hocasi=hoca, dini_ders_hocasi=hoca
        )
        ayse = Talebe.objects.create(
            ad_soyad="Ayse Net", sinif_sube=b, etut_hocasi=hoca, dini_ders_hocasi=hoca
        )
        deneme = DenemeSinavi.objects.create(
            ad="Net Deneme",
            sinav_tarihi=date(2026, 4, 1),
            sinif_seviyesi="8",
            durum=DenemeSinavi.Durum.AKTIF,
        )
        s1 = DenemeSonucu.objects.create(
            deneme=deneme, talebe=ali, toplam_net=Decimal("10.00"), puan=Decimal("400")
        )
        s2 = DenemeSonucu.objects.create(
            deneme=deneme, talebe=ayse, toplam_net=Decimal("5.00"), puan=Decimal("300")
        )
        DenemeBransSonucu.objects.create(
            sonuc=s1, brans="turkce", dogru=10, yanlis=0, bos=0, net=Decimal("10.00")
        )
        DenemeBransSonucu.objects.create(
            sonuc=s2, brans="turkce", dogru=6, yanlis=4, bos=2, net=Decimal("5.00")
        )
        satirlar = deneme_detay_satirlari(
            DenemeSonucu.objects.filter(deneme=deneme)
            .select_related("talebe__sinif_sube")
            .prefetch_related("brans_satirlari")
            .order_by("talebe__ad_soyad")
        )
        ozet = deneme_ders_net_ozeti(satirlar)
        turkce = next(item for item in ozet["genel"] if item["kod"] == "turkce")
        self.assertEqual(turkce["net"], "7,50")
        self.assertEqual(turkce["dogru"], "8,0")
        self.assertEqual(turkce["yanlis"], "2,0")
        self.assertEqual(turkce["bos"], "1,0")
        matematik = next(item for item in ozet["genel"] if item["kod"] == "matematik")
        self.assertEqual(matematik["net"], "—")
        self.assertEqual([s["etiket"] for s in ozet["siniflar"]], ["8-A", "8-B"])
        a_net = next(item for item in ozet["siniflar"][0]["branslar"] if item["kod"] == "turkce")
        self.assertEqual(a_net["net"], "10,00")

        admin = User.objects.create_superuser("net-admin", "a@b.com", "x")
        self.client.force_login(admin)
        sayfa = self.client.get(reverse("deneme_detay", args=[deneme.pk]))
        self.assertContains(sayfa, "7,50")
        self.assertContains(sayfa, "Sınıf ortalaması")
        self.assertContains(sayfa, "8-A")
        with patch("takip.deneme_views.html_to_pdf", return_value=b"%PDF-1.4 fake") as mock_pdf:
            resp = self.client.get(reverse("deneme_detayli_pdf", args=[deneme.pk]))
        self.assertEqual(resp.status_code, 200)
        html = mock_pdf.call_args[0][0]
        self.assertIn("7,50", html)
        self.assertIn("Sınıf neti", html)
        self.assertIn("apple-cizgi-bar", html)
        self.assertLess(html.index("apple-cizgi-bar"), html.index("Sınıf neti"))
        self.assertNotIn("8-A net", html)
        self.assertNotIn("8-B net", html)
        self.assertIn('colspan="3"', html)
        self.assertIn("8,0 D", html)
