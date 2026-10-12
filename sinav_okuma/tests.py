"""Sınav okuma: optik .dat, ayrı host, ana siteye yazmama."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from sinav_okuma.anahtar_excel import anahtar_excel_oku
from sinav_okuma.models import OptikForm, Sinav, SinavSatiri, SinavSoru
from sinav_okuma.okuma import (
    ORNEK_FORM_AD,
    FormHaritasi,
    OptikHata,
    anahtar_temizle,
    dagilim_coz,
    form_alanlarini_coz,
    harita_from_form,
    kazanim_listesi,
    kazanim_metni,
    optik_oku,
    ornek_dat_oku,
    satirlari_puanla,
)
from takip.deneme_models import DenemeSinavi, DenemeSonucu

HOST = "sinav.localhost"
SIFRE = "Sinav-Test-Sifre-42"
ORNEK_DAT = "/home/ubuntu/.cursor/projects/workspace/uploads/G_nay-2024_51b9.dat"
ORNEK_ANAHTAR = (
    "/home/ubuntu/.cursor/projects/workspace/uploads/"
    "Optik-Okutma_Kazanim-Tablosu_Cevap-Anahtarli_9fb1.xlsx"
)

SULEYMAN = (
    "0                   00021A   SÜLEYMAN MERT DURAK  "
    "CDBACCCCB BBB D     CDBADACBABABACBCABDCACBD CCAB CAD DADCABB BDC     "
    "CDB  ABBCADADBB               "
)
KARAKAYA = (
    "0                   00014A5A ÖMER KARAKAYA        "
    "CBBACCADBCBBABD     CDBADACBAB BBCB A*DCACBDDCC BBCACDABDCABBBBDC     "
    "CDDBBAB CBDACBA               "
)


def _anahtar_xlsx(satirlar, baslik="Deneme", sinif="7.Sınıf"):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ÇS", None, baslik])
    ws.append([None, None, sinif])
    ws.append(["Kitapçık", "Test", "Ders", "A Soru", "B Soru", "Cevap", "Kazanım Kodu", "Kazanım-1", "Kazanım-2"])
    for satir in satirlar:
        ws.append(list(satir))
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        "anahtar.xlsx",
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _kayit(
    *,
    no: str = "00021",
    ad: str = "ALI VELI",
    cevaplar: str,
    sinif: str = "",
    sube: str = "",
    kitap: str = "A",
    tasma: str = "",
) -> str:
    satir = [" "] * 150
    satir[0] = "0"
    for i, ch in enumerate(no.rjust(5)[:5]):
        satir[20 + i] = ch
    satir[25] = kitap or " "
    if sinif:
        satir[26] = sinif[0]
    if sube:
        satir[27] = sube[0]
    ad_alan = ad[:21].ljust(21)
    for i, ch in enumerate(ad_alan):
        satir[29 + i] = ch
    if len(cevaplar) != 75:
        raise AssertionError(len(cevaplar))
    konumlar = list(range(50, 65)) + list(range(70, 115)) + list(range(120, 135))
    for i, ch in enumerate(cevaplar):
        satir[konumlar[i]] = ch
    if tasma:
        for i, ch in enumerate(tasma):
            satir[12 + i] = ch
    return "".join(satir)


class OrnekDatOkumaTests(TestCase):
    def test_ornek_satir_numara_ad_ve_75_sik(self):
        self.assertEqual(len(SULEYMAN), 150)
        self.assertEqual(len(KARAKAYA), 150)
        dosya = ornek_dat_oku((SULEYMAN + "\r\n" + KARAKAYA + "\r\n").encode("cp1254"))
        self.assertEqual(dosya.cevap_sayisi, 75)
        ilk = dosya.kayitlar[0]
        self.assertEqual(ilk.ogrenci_no, "00021")
        self.assertTrue(ilk.numara_guvenilir)
        self.assertEqual(ilk.ad_soyad, "SÜLEYMAN MERT DURAK")
        self.assertEqual(ilk.kitapcik, "A")
        self.assertEqual(len(ilk.cevaplar), 75)
        self.assertTrue(ilk.cevaplar.startswith("CDBACCCCB BBB D"))
        ikinci = dosya.kayitlar[1]
        self.assertEqual(ikinci.ogrenci_no, "00014")
        self.assertEqual(ikinci.sinif, "5")
        self.assertEqual(ikinci.sube, "A")
        self.assertIn("*", ikinci.cevaplar)
        self.assertTrue(any("çift işaret" in u for u in ikinci.uyarilar))

    def test_tasan_numara_guvenilmez(self):
        satir = _kayit(no="00002", ad="MIRAÇ ÇİÇEK", cevaplar="A" * 75, tasma="335373082")
        kayit = ornek_dat_oku(satir.encode("cp1254")).kayitlar[0]
        self.assertFalse(kayit.numara_guvenilir)
        self.assertEqual(kayit.ogrenci_no, "")
        self.assertEqual(kayit.ad_soyad, "MIRAÇ ÇİÇEK")
        self.assertTrue(any("kaymış" in u for u in kayit.uyarilar))

    def test_kisa_satir_atilir_dosya_bos_kalirsa_hata(self):
        with self.assertRaises(OptikHata):
            ornek_dat_oku(b"kisa satir\n")

    def test_ornek_form_kayitta(self):
        form = OptikForm.objects.get(ad=ORNEK_FORM_AD)
        self.assertNotIn("Günay", form.ad)
        self.assertEqual(
            harita_from_form(form).sik_sayisi,
            ornek_dat_oku((SULEYMAN + "\n").encode("cp1254")).cevap_sayisi,
        )

    def test_cakisan_kolon_kaydedilmez(self):
        with self.assertRaises(OptikHata):
            form_alanlarini_coz("sik 1 5\nsik 5 8", 20)

    def test_dagilim_toplami_optik_sayisina_esit_olmali(self):
        self.assertEqual(
            dagilim_coz("turkce 15\nmatematik 60", 75),
            [("turkce", 15), ("matematik", 60)],
        )
        with self.assertRaises(OptikHata):
            dagilim_coz("turkce 10", 75)
        with self.assertRaises(OptikHata):
            anahtar_temizle("ABCD", 75, kitapcik="A")

    def test_kazanim_son_bos_satir_kaybolmaz(self):
        metin = kazanim_metni(["Fiil"] + [""] * 74)
        satirlar = kazanim_listesi(metin, 75)
        self.assertEqual(len(satirlar), 75)
        self.assertEqual(satirlar[0], "Fiil")
        self.assertEqual(satirlar[-1], "")

    def test_on_dogru_dort_yanlis_bir_cift_altmis_bos(self):
        cevaplar = ("A" * 10) + ("B" * 4) + "*" + (" " * 60)
        dosya = ornek_dat_oku(_kayit(cevaplar=cevaplar).encode("cp1254"))
        satir = satirlari_puanla(
            dosya,
            dagilim_coz("Türkçe 75", 75),
            anahtar_temizle("A" * 75, 75, kitapcik="A"),
            "",
            kazanim_listesi("Fiil\n" + ("\n" * 74), 75),
        )[0]
        self.assertEqual(satir.dogru, 10)
        self.assertEqual(satir.yanlis, 5)
        self.assertEqual(satir.bos, 60)
        self.assertEqual(satir.net, "8.75")
        self.assertEqual(satir.puan, "11.67")
        self.assertEqual(satir.sorular[0]["sonuc"], "dogru")
        self.assertEqual(satir.sorular[0]["konu_ad"], "Fiil")
        self.assertEqual(satir.sorular[10]["sonuc"], "yanlis")
        self.assertEqual(satir.sorular[14]["sonuc"], "yanlis")
        self.assertEqual(satir.sorular[15]["sonuc"], "bos")

    def test_kisa_form_ayri_kolonlardan_okunur(self):
        alanlar = form_alanlarini_coz("numara 1 2\nsik 4 6", 10)
        self.assertEqual(alanlar[0].tur, "numara")
        dosya = optik_oku(
            "21 ABC    ".encode(),
            FormHaritasi(satir_uzunluk=10, kodlama="utf-8", alanlar=alanlar),
        )
        self.assertEqual(dosya.kayitlar[0].ogrenci_no, "21")
        self.assertEqual(dosya.kayitlar[0].cevaplar, "ABC")


class AnahtarExcelTests(TestCase):
    def test_b_sorusu_anahtari_ve_kazanimi_yer_degistirir(self):
        ham = _anahtar_xlsx(
            [
                ["A", "Sözel (TÜR)", "Türkçe", 1, 2, "C", "", "Fiil"],
                ["A", "Sözel (TÜR)", "Türkçe", 2, 1, "A", "T.O.7.7", "Ana düşünce", "Yardımcı düşünce"],
                ["A", "Sayısal (MAT)", "Matematik", 1, 1, "D", "MAT.7.1.1", "Rasyonel sayılar"],
            ],
            baslik="7.SINIF KURUMSAL DENEME 1",
        ).read()
        belge = anahtar_excel_oku(ham)
        self.assertEqual(belge.ad, "7.SINIF KURUMSAL DENEME 1")
        self.assertEqual(belge.sinif, "7.Sınıf")
        self.assertEqual(belge.dagilim, [("turkce", 2), ("matematik", 1)])
        self.assertEqual(belge.anahtar("A"), "CAD")
        self.assertEqual(belge.anahtar("B"), "ACD")
        self.assertEqual(belge.kazanimlar("A")[0], "Fiil")
        self.assertEqual(belge.kazanimlar("B")[0], "T.O.7.7 · Ana düşünce · Yardımcı düşünce")
        self.assertEqual(belge.kazanimlar("A")[2], "MAT.7.1.1 · Rasyonel sayılar")

    def test_din_adi_ve_gercek_dosya(self):
        if not os.path.exists(ORNEK_ANAHTAR):
            self.skipTest("örnek anahtar exceli bu ortamda yok")
        belge = anahtar_excel_oku(open(ORNEK_ANAHTAR, "rb").read())
        self.assertEqual(belge.soru_sayisi, 90)
        self.assertIn("KURUMSAL DENEME", belge.ad)
        self.assertEqual(belge.sinif, "7.Sınıf")
        self.assertEqual(
            belge.dagilim,
            [
                ("turkce", 20),
                ("sosyal", 10),
                ("din", 10),
                ("ingilizce", 10),
                ("matematik", 20),
                ("fen", 20),
            ],
        )
        self.assertEqual(belge.anahtar("A")[0], "C")
        self.assertEqual(belge.anahtar("B")[0], "A")
        self.assertEqual(belge.kazanimlar("A")[0], "Sözcükte anlam: çok anlamlılık")
        self.assertTrue(belge.b_var)
        self.assertEqual(len(belge.anahtar("A")), 90)
        self.assertEqual(len(belge.anahtar("B")), 90)


class OrnekDosyaTests(TestCase):
    def test_yuklenen_ornek_yirmi_bir_satir(self):
        if not os.path.exists(ORNEK_DAT):
            self.skipTest("örnek .dat bu ortamda yok")
        dosya = ornek_dat_oku(open(ORNEK_DAT, "rb").read())
        self.assertEqual(len(dosya.kayitlar), 21)
        self.assertEqual(dosya.cevap_sayisi, 75)
        adlar = {k.ad_soyad for k in dosya.kayitlar}
        self.assertIn("ÖMER KEREM SUCU", adlar)
        self.assertIn("ERTUĞRUL AZDEROĞLU", adlar)
        kaymis = [k for k in dosya.kayitlar if not k.numara_guvenilir]
        self.assertEqual(len(kaymis), 1)
        self.assertEqual(kaymis[0].ad_soyad, "MİRAÇ ÇİÇEK")
        yildiz = [k for k in dosya.kayitlar if "*" in k.cevaplar]
        self.assertEqual(yildiz[0].ad_soyad, "ÖMER KARAKAYA")


class AnaSiteyeBagliDegilTests(TestCase):
    def test_yonetim_optik_adresi_yok(self):
        with self.assertRaises(NoReverseMatch):
            reverse("yonetim:optik_form_listesi")
        yanit = self.client.get("/yonetim/denemeler/optik-formlar/", HTTP_HOST="localhost")
        self.assertEqual(yanit.status_code, 404)

    def test_sinav_sayfalari_ana_hostta_yok(self):
        yanit = self.client.get("/formlar/", HTTP_HOST="localhost")
        self.assertEqual(yanit.status_code, 404)

    def test_deneme_detayinda_optik_karti_yok(self):
        user = User.objects.create_superuser("site-admin", "a@b.com", "x")
        deneme = DenemeSinavi.objects.create(
            ad="Site denemesi",
            sinav_tarihi=date(2024, 11, 1),
            sinif_seviyesi="5",
            olusturan=user,
        )
        self.client.force_login(user)
        yanit = self.client.get(
            reverse("yonetim:deneme_detay", args=[deneme.pk]),
            HTTP_HOST="localhost",
        )
        self.assertEqual(yanit.status_code, 200)
        self.assertNotContains(yanit, "Optik okuma")
        self.assertNotContains(yanit, "optik_dosya")


@override_settings(SINAV_YONETICI_SIFRE=SIFRE)
class SinavHostTests(TestCase):
    def setUp(self):
        self.deneme = DenemeSinavi.objects.create(
            ad="Ana site denemesi",
            sinav_tarihi=date(2024, 11, 1),
            sinif_seviyesi="5",
        )

    def get(self, yol, **kw):
        return self.client.get(yol, HTTP_HOST=HOST, **kw)

    def post(self, yol, data=None, **kw):
        return self.client.post(yol, data or {}, HTTP_HOST=HOST, **kw)

    def giris(self):
        yanit = self.post("/giris/", {"sifre": SIFRE})
        self.assertEqual(yanit.status_code, 302)

    def test_giris_yokken_liste_acilmaz_ve_yonetim_yoktur(self):
        yanit = self.get("/")
        self.assertEqual(yanit.status_code, 302)
        self.assertIn("/giris/", yanit["Location"])
        self.assertEqual(self.get("/yonetim/denemeler/").status_code, 404)
        kapali = self.post("/giris/", {"sifre": "yanlis"})
        self.assertContains(kapali, "Şifre hatalı")

    def test_sifre_bosken_giris_kapali(self):
        with override_settings(SINAV_YONETICI_SIFRE=""):
            yanit = self.get("/giris/")
        self.assertContains(yanit, "Giriş kapalı")

    def test_form_sinav_ve_dat_satir_yazar_denemeye_yazmaz(self):
        self.giris()
        formlar = self.get("/formlar/")
        self.assertContains(formlar, ORNEK_FORM_AD)
        self.assertContains(formlar, "51")
        kisa = self.post(
            "/formlar/ekle/",
            {
                "ad": "Kısa form",
                "aciklama": "Başka kâğıt",
                "satir_uzunluk": "10",
                "kodlama": "utf-8",
                "alanlar": "numara 1 2\nsik 4 6",
            },
        )
        self.assertEqual(kisa.status_code, 302)
        self.assertEqual(OptikForm.objects.filter(ad="Kısa form").count(), 1)
        harita = harita_from_form(OptikForm.objects.get(ad="Kısa form"))
        dosya = optik_oku("21 ABC    ".encode(), harita)
        self.assertEqual(dosya.kayitlar[0].ogrenci_no, "21")
        self.assertEqual(dosya.kayitlar[0].cevaplar, "ABC")

        olustur = self.post("/", {"ad": "Kasım denemesi", "tarih": "2024-11-01"})
        self.assertEqual(olustur.status_code, 302)
        sinav = Sinav.objects.get(ad="Kasım denemesi")
        form = OptikForm.objects.get(ad=ORNEK_FORM_AD)
        tanimsiz = self.post(
            f"/sinavlar/{sinav.pk}/oku/",
            {"optik_dosya": SimpleUploadedFile("okuma.dat", _kayit(cevaplar="A" * 75).encode("cp1254"))},
        )
        self.assertEqual(tanimsiz.status_code, 302)
        self.assertEqual(SinavSatiri.objects.filter(sinav=sinav).count(), 0)

        self.post(f"/sinavlar/{sinav.pk}/", {"form_id": form.pk})
        tanim = self.post(
            f"/sinavlar/{sinav.pk}/",
            {
                "anahtar_excel": _anahtar_xlsx(
                    [
                        ["A", "Sözel (TÜR)", "Türkçe", i, "", "A", "", "Fiil" if i == 1 else ""]
                        for i in range(1, 76)
                    ]
                )
            },
        )
        self.assertEqual(tanim.status_code, 302)
        yukleme = self.post(
            f"/sinavlar/{sinav.pk}/oku/",
            {
                "optik_dosya": SimpleUploadedFile(
                    "okuma.dat",
                    _kayit(cevaplar=("A" * 10) + ("B" * 4) + "*" + (" " * 60)).encode("cp1254"),
                    content_type="application/octet-stream",
                )
            },
            follow=True,
        )
        self.assertContains(yukleme, "11,67")
        self.assertContains(yukleme, "ALI VELI")
        self.assertContains(yukleme, "ana siteden ayrıdır")
        satir = SinavSatiri.objects.get(sinav=sinav)
        self.assertEqual(satir.puan, Decimal("11.67"))
        self.assertEqual(satir.net, Decimal("8.75"))
        self.assertEqual(satir.dogru, 10)
        self.assertEqual(satir.yanlis, 5)
        self.assertEqual(satir.bos, 60)
        sorular = SinavSoru.objects.filter(satir=satir)
        self.assertEqual(sorular.count(), 75)
        self.assertEqual(sorular.get(soru_no=1).konu_ad, "Fiil")
        self.assertEqual(sorular.get(soru_no=1).sonuc, "dogru")
        self.assertFalse(DenemeSonucu.objects.filter(deneme=self.deneme).exists())
        self.assertEqual(DenemeSonucu.objects.count(), 0)

    def test_b_kitapcik_anahtarsiz_satir_saklanir_puan_bos(self):
        self.giris()
        self.post("/", {"ad": "B deneme", "tarih": "2024-11-02"})
        sinav = Sinav.objects.get(ad="B deneme")
        form = OptikForm.objects.get(ad=ORNEK_FORM_AD)
        self.post(f"/sinavlar/{sinav.pk}/", {"form_id": form.pk})
        self.post(
            f"/sinavlar/{sinav.pk}/",
            {
                "anahtar_excel": _anahtar_xlsx(
                    [["A", "Sözel (TÜR)", "Türkçe", i, "", "A", "", ""] for i in range(1, 76)]
                )
            },
        )
        self.post(
            f"/sinavlar/{sinav.pk}/oku/",
            {
                "optik_dosya": SimpleUploadedFile(
                    "b.dat",
                    _kayit(cevaplar="A" * 75, kitap="B", ad="ALI VELI").encode("cp1254"),
                )
            },
        )
        satir = SinavSatiri.objects.get(sinav=sinav)
        self.assertFalse(satir.puanlandi)
        self.assertIsNone(satir.puan)
        self.assertIn("B kitapçık", satir.uyarilar)
        self.assertEqual(DenemeSonucu.objects.count(), 0)
