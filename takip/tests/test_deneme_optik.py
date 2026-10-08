"""Günay optik .dat okuma — şık şeridi, anahtar ve deneme aktarımı."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from takip.deneme_excel import deneme_sonuclari_aktar
from takip.deneme_models import DenemeBransSonucu, DenemeKazanimSonucu, DenemeSinavi, DenemeSonucu, DenemeSoruSonucu
from takip.deneme_optik import (
    OptikHata,
    ORNEK_FORM_AD,
    anahtar_temizle,
    dagilim_coz,
    form_alanlarini_coz,
    harita_from_form,
    optik_oku,
    optik_onizleme,
    ornek_dat_oku,
)
from takip.models import EtutHocasi, OptikForm, SinifSube, Talebe

ORNEK_DAT = "/home/ubuntu/.cursor/projects/workspace/uploads/G_nay-2024_51b9.dat"

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


class GunayDatOkumaTests(TestCase):
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
        self.assertEqual(ilk.sinif, "")
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

    def test_ornek_form_kayitta_ve_adi_dosyanin_adi_degil(self):
        form = OptikForm.objects.get(ad=ORNEK_FORM_AD)
        self.assertNotIn("Günay", form.ad)
        self.assertEqual(harita_from_form(form).sik_sayisi, ornek_dat_oku(
            (SULEYMAN + "\n").encode("cp1254")
        ).cevap_sayisi)

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


class OptikPuanAktarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("optik-admin", "a@b.com", "x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Hoca", user=self.user)
        self.sinif = SinifSube.objects.create(sinif="5", sube="A")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.talebe = Talebe.objects.create(
            ad_soyad="Başka İsim",
            talebe_no="21",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.deneme = DenemeSinavi.objects.create(
            ad="Günay deneme",
            sinav_tarihi=date(2024, 11, 1),
            sinif_seviyesi="5",
            olusturan=self.user,
        )

    def _onizleme(self, cevaplar: str, anahtar: str, dagilim: str, **kayit_kw):
        satir = _kayit(cevaplar=cevaplar, **kayit_kw)
        dosya = ornek_dat_oku(satir.encode("cp1254"))
        dag = dagilim_coz(dagilim, dosya.cevap_sayisi)
        kilit = anahtar_temizle(anahtar, dosya.cevap_sayisi, kitapcik="A")
        return optik_onizleme(dosya, dag, kilit)

    def test_numara_ile_eslesir_net_ve_puan_yazilir(self):
        cevaplar = ("A" * 10) + ("B" * 4) + "*" + (" " * 60)
        onizleme = self._onizleme(cevaplar, "A" * 75, "Türkçe 75")
        satir = onizleme.satirlar[0]
        self.assertEqual(satir.talebe_id, self.talebe.id)
        self.assertEqual(satir.eslesme, "otomatik")
        self.assertEqual(satir.toplam["dogru"], 10)
        self.assertEqual(satir.toplam["yanlis"], 5)
        self.assertEqual(satir.toplam["bos"], 60)
        self.assertEqual(satir.toplam["net"], "8.75")
        self.assertEqual(satir.puan, "11.67")
        adet, hatalar = deneme_sonuclari_aktar(self.deneme, onizleme, self.user)
        self.assertEqual(hatalar, [])
        self.assertEqual(adet, 1)
        sonuc = DenemeSonucu.objects.get(deneme=self.deneme, talebe=self.talebe)
        self.assertEqual(sonuc.toplam_dogru, 10)
        self.assertEqual(sonuc.toplam_yanlis, 5)
        self.assertEqual(sonuc.toplam_bos, 60)
        self.assertEqual(sonuc.toplam_net, Decimal("8.75"))
        self.assertEqual(sonuc.puan, Decimal("11.67"))
        brans = DenemeBransSonucu.objects.get(sonuc=sonuc, brans="turkce")
        self.assertEqual(brans.net, Decimal("8.75"))
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.durum, DenemeSinavi.Durum.AKTIF)

    def test_b_kitapcik_anahtarsiz_aktarilmaz(self):
        satir = _kayit(cevaplar="A" * 75, kitap="B", ad="ALI VELI")
        dosya = ornek_dat_oku(satir.encode("cp1254"))
        onizleme = optik_onizleme(
            dosya,
            dagilim_coz("turkce 75", 75),
            anahtar_temizle("A" * 75, 75, kitapcik="A"),
        )
        self.assertEqual(onizleme.satirlar[0].puan, "")
        self.assertTrue(any("B kitapçık" in h for h in onizleme.satirlar[0].hatalar))
        adet, _hatalar = deneme_sonuclari_aktar(self.deneme, onizleme, self.user)
        self.assertEqual(adet, 0)
        self.assertFalse(DenemeSonucu.objects.filter(deneme=self.deneme).exists())

    def test_eslesmeyen_satir_listede_kalir(self):
        onizleme = self._onizleme("A" * 75, "A" * 75, "fen 75", no="00099", ad="KAYITSIZ TALABE")
        satir = onizleme.satirlar[0]
        self.assertIsNone(satir.talebe_id)
        self.assertEqual(satir.excel_ad_soyad, "KAYITSIZ TALABE")
        self.assertEqual(onizleme.eslesmeyen, 1)

    def test_tanim_yoksa_dosya_okunmaz(self):
        self.client.force_login(self.user)
        dosya = SimpleUploadedFile(
            "okuma.dat",
            _kayit(cevaplar="A" * 75).encode("cp1254"),
        )
        yanit = self.client.post(
            reverse("yonetim:deneme_optik_yukle", args=[self.deneme.pk]),
            {"optik_dosya": dosya},
            follow=True,
        )
        self.assertContains(yanit, "kaydedin")
        self.assertFalse(DenemeSonucu.objects.filter(deneme=self.deneme).exists())

    def test_yonetim_ekrani_okur_ve_aktarir(self):
        self.client.force_login(self.user)
        form = OptikForm.objects.get(ad=ORNEK_FORM_AD)
        tanim = self.client.post(
            reverse("yonetim:deneme_optik_tanim", args=[self.deneme.pk]),
            {
                "form_id": form.pk,
                "anahtar_a": "A" * 75,
                "anahtar_b": "",
                "dagilim": "turkce 75",
                "kazanimlar": "Fiil\n" + ("\n" * 74),
            },
            follow=True,
        )
        self.assertContains(tanim, "kaydedildi")
        dosya = SimpleUploadedFile(
            "okuma.dat",
            _kayit(cevaplar=("A" * 10) + ("B" * 4) + "*" + (" " * 60)).encode("cp1254"),
            content_type="application/octet-stream",
        )
        yukleme = self.client.post(
            reverse("yonetim:deneme_optik_yukle", args=[self.deneme.pk]),
            {"optik_dosya": dosya},
            follow=True,
        )
        self.assertEqual(yukleme.status_code, 200)
        self.assertContains(yukleme, "Optik önizleme")
        self.assertContains(yukleme, "11.67")
        self.assertContains(yukleme, "ALI VELI")
        aktar = self.client.post(
            reverse("yonetim:deneme_onizleme", args=[self.deneme.pk]),
            {"aksiyon": "aktar"},
            follow=True,
        )
        self.assertEqual(aktar.status_code, 200)
        sonuc = DenemeSonucu.objects.get(deneme=self.deneme)
        self.assertEqual(sonuc.talebe_id, self.talebe.id)
        self.assertEqual(sonuc.puan, Decimal("11.67"))
        sorular = DenemeSoruSonucu.objects.filter(deneme=self.deneme, talebe=self.talebe)
        self.assertEqual(sorular.count(), 75)
        self.assertEqual(sorular.get(soru_no=1).sonuc, DenemeSoruSonucu.Sonuc.DOGRU)
        self.assertEqual(sorular.get(soru_no=11).sonuc, DenemeSoruSonucu.Sonuc.YANLIS)
        self.assertEqual(sorular.get(soru_no=15).sonuc, DenemeSoruSonucu.Sonuc.YANLIS)
        self.assertEqual(sorular.get(soru_no=16).sonuc, DenemeSoruSonucu.Sonuc.BOS)
        kazanim = DenemeKazanimSonucu.objects.get(deneme=self.deneme, talebe=self.talebe)
        self.assertEqual(kazanim.konu_ad, "Fiil")
        self.assertEqual(kazanim.yuzde, Decimal("100.00"))

    def test_ikinci_form_ayri_kolonlardan_okunur(self):
        self.client.force_login(self.user)
        yanit = self.client.post(
            reverse("yonetim:optik_form_ekle"),
            {
                "ad": "Kısa form",
                "aciklama": "Başka kâğıt",
                "satir_uzunluk": "10",
                "kodlama": "utf-8",
                "alanlar": "numara 1 2\nsik 4 6",
            },
            follow=True,
        )
        self.assertContains(yanit, "Kısa form")
        harita = harita_from_form(OptikForm.objects.get(ad="Kısa form"))
        dosya = optik_oku("21 ABC    ".encode(), harita)
        self.assertEqual(dosya.kayitlar[0].ogrenci_no, "21")
        self.assertEqual(dosya.kayitlar[0].cevaplar, "ABC")
        self.assertEqual(OptikForm.objects.count(), 2)


class GunayOrnekDosyaTests(TestCase):
    def test_yuklenen_gunay_2024_yirmi_bir_talebe(self):
        if not os.path.exists(ORNEK_DAT):
            self.skipTest("Günay-2024.dat örneği bu ortamda yok")
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
