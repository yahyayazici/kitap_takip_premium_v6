"""Seviye Tespit — sonuç Excel'i, karneler, karar ve veliye gönderim."""

import datetime as dt
import shutil
import tempfile
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from config.branding import SINAV_BASVURU_BASLIK
from takip.models import SinavBasvuru
from takip.sinav_bildirim_models import SinavBildirimLog, SinavTakvim
from takip.sinav_bildirim_service import basvuru_token
from takip.sinav_sonuc_models import SinavSonuc
from takip.sinav_sonuc_service import basvuru_eslestir, karne_kaydet

TZ = ZoneInfo("Europe/Istanbul")
URL = reverse("yonetim:sinav_basvuru_listesi")
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
)


def basvuru(ad, sinif, **ek):
    veri = dict(
        ad_soyad=ad, sinif=sinif, okul_adi="Okul", veli_eposta="veli@example.com",
        hatirlatma_turu="takvim", baba_adi="M", baba_telefon="05321112233", anne_adi="A",
        anne_telefon="05334445566", il="İstanbul", ilce="Başakşehir",
        dogum_tarihi=dt.date(2014, 5, 10), sinav_adi=SINAV_BASVURU_BASLIK,
    )
    veri.update(ek)
    return SinavBasvuru.objects.create(**veri)


def xlsx(satirlar):
    wb = Workbook()
    ws = wb.active
    for s in satirlar:
        ws.append(s)
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        "sonuc.xlsx", buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class _Temel(TestCase):
    def setUp(self):
        self.medya = tempfile.mkdtemp()
        self.ayar = override_settings(SINAV_SONUC_MEDIA_ROOT=self.medya, SINAV_SONUC_ARKA_PLAN=False)
        self.ayar.enable()
        User.objects.create_superuser("idareci-sonuc", "a@b.com", "Sifre!2026x")
        self.client.login(username="idareci-sonuc", password="Sifre!2026x")
        SinavTakvim.objects.update_or_create(
            sinav_adi=SINAV_BASVURU_BASLIK,
            defaults={
                "baslangic": dt.datetime(2026, 10, 24, 11, 0, tzinfo=TZ),
                "bitis": dt.datetime(2026, 10, 24, 13, 10, tzinfo=TZ),
            },
        )
        self.ahmet = basvuru("Ahmet Yılmaz", "6")
        self.ahmet2 = basvuru("Ahmet Yılmaz", "8")
        self.zeynep = basvuru("Mehmet Çelik", "6")
        self.ali = basvuru("Ali Kaya", "7", veli_eposta="")

    def tearDown(self):
        self.ayar.disable()
        shutil.rmtree(self.medya, ignore_errors=True)


class EslestirmeTests(_Temel):
    def test_ayni_ad_sinifla_ayrilir_ve_harf_farki_tolere_edilir(self):
        adaylar = list(SinavBasvuru.objects.all())
        b, tur, _ = basvuru_eslestir("AHMET YILMAZ", "6-A", adaylar)
        self.assertEqual((b, tur), (self.ahmet, "otomatik"))
        b, tur, _ = basvuru_eslestir("Ahmet Yilmaz", "8. Sınıf", adaylar)
        self.assertEqual((b, tur), (self.ahmet2, "otomatik"))
        b, tur, _ = basvuru_eslestir("Mehmet Celik", "", adaylar)
        self.assertEqual(b, self.zeynep)
        b, tur, _ = basvuru_eslestir("Hiç Yok", "", adaylar)
        self.assertIsNone(b)


class ExcelYuklemeTests(_Temel):
    def test_excel_onizle_eslestir_kaydet_ve_sirala(self):
        dosya = xlsx(
            [
                ["Ad Soyad", "Sınıf", "Türkçe Doğru", "Türkçe Yanlış", "Türkçe Net",
                 "Matematik Doğru", "Matematik Yanlış", "Matematik Net", "Puan"],
                ["AHMET YILMAZ", "6", 12, 3, 11, 10, 4, 8.67, 350.5],
                ["Mehmet Celik", "6", 14, 1, 13.67, 12, 0, 12, 410],
                ["Ali Kaya", "7", 8, 4, 6.67, 6, 6, 4, 280],
                ["Bilinmeyen Öğrenci", "5", 5, 5, 3.33, 5, 5, 3.33, 200],
            ]
        )
        yanit = self.client.post(URL, {"action": "sonuc_excel", "bolum": "sonuclar", "excel": dosya})
        self.assertEqual(yanit.status_code, 302)
        sayfa = self.client.get(URL, {"bolum": "sonuclar"})
        self.assertContains(sayfa, "Excel eşleştirmesi")
        self.assertContains(sayfa, "Eşleşmedi")
        onizleme = self.client.session["seviye_tespit_sonuc_onizleme"]
        secim = {f"eslesme_{s['satir_no']}": s["basvuru_id"] or "" for s in onizleme["satirlar"]}

        self.client.post(URL, {"action": "sonuc_excel_kaydet", "bolum": "sonuclar", **secim})
        self.assertEqual(SinavSonuc.objects.count(), 3)
        mehmet = SinavSonuc.objects.get(basvuru=self.zeynep)
        ahmet = SinavSonuc.objects.get(basvuru=self.ahmet)
        ali = SinavSonuc.objects.get(basvuru=self.ali)
        self.assertEqual((mehmet.genel_sira, ahmet.genel_sira, ali.genel_sira), (1, 2, 3))
        self.assertEqual((mehmet.sinif_sira, ahmet.sinif_sira, ali.sinif_sira), (1, 2, 1))
        self.assertEqual(mehmet.puan, Decimal("410"))
        self.assertEqual(mehmet.branslar["turkce"]["net"], "13.67")
        self.assertNotIn("seviye_tespit_sonuc_onizleme", self.client.session)

        sayfa = self.client.get(URL, {"bolum": "sonuclar"})
        self.assertContains(sayfa, "Mehmet Çelik")
        self.assertContains(sayfa, "Mat")


class KarneVeGonderimTests(_Temel):
    def test_toplu_karne_dosya_adindan_eslesir(self):
        self.client.post(
            URL,
            {
                "action": "karne_toplu",
                "bolum": "sonuclar",
                "karneler": [
                    SimpleUploadedFile("Mehmet Çelik.png", PNG, content_type="image/png"),
                    SimpleUploadedFile("12_Ali_Kaya_karne.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
                    SimpleUploadedFile("Ahmet Yılmaz.pdf", b"%PDF-1.4", content_type="application/pdf"),
                    SimpleUploadedFile("Tanınmayan.pdf", b"%PDF-1.4", content_type="application/pdf"),
                ],
            },
        )
        self.assertTrue(SinavSonuc.objects.get(basvuru=self.zeynep).karne)
        self.assertTrue(SinavSonuc.objects.get(basvuru=self.ali).karne)
        # İki "Ahmet Yılmaz" var; dosya adı yetmez, satırdan yüklenmeli.
        self.assertFalse(SinavSonuc.objects.filter(basvuru__ad_soyad="Ahmet Yılmaz").exists())

    def test_yanlis_tur_reddedilir(self):
        self.client.post(
            URL,
            {"action": "karne_yukle", "bolum": "sonuclar", "basvuru_id": self.ali.pk,
             "karne": SimpleUploadedFile("x.exe", b"MZ")},
        )
        self.assertFalse(SinavSonuc.objects.filter(basvuru=self.ali).exists())

    def test_gonder_eposta_ekli_sayfa_acilir_ve_tekrar_gitmez(self):
        self.client.post(
            URL,
            {"action": "karne_yukle", "bolum": "sonuclar", "basvuru_id": self.ahmet.pk,
             "karne": SimpleUploadedFile("karne.pdf", b"%PDF-1.4 ahmet", content_type="application/pdf")},
        )
        token = basvuru_token(self.ahmet)
        # Gönderilmeden sonuç sayfası "henüz açıklanmadı" der, dosya verilmez.
        self.assertContains(self.client.get(reverse("sinav_basvuru_sonuc"), {"t": token}), "Henüz açıklanmadı")
        self.assertEqual(self.client.get(reverse("sinav_basvuru_sonuc_dosya"), {"t": token}).status_code, 404)

        self.client.post(URL, {"action": "sonuc_mesaj", "bolum": "sonuclar",
                               "sonuc_mesaji": "Sayın Veli, {ad} için sonuç ektedir."})
        self.client.post(URL, {"action": "sonuc_gonder", "bolum": "sonuclar", "kapsam": "bekleyen"})
        self.assertEqual(len(mail.outbox), 1)
        eposta = mail.outbox[0]
        self.assertEqual(eposta.to, ["veli@example.com"])
        self.assertIn("Ahmet için sonuç ektedir", eposta.body)
        self.assertEqual(eposta.attachments[0][0], "Ahmet Yılmaz - Sonuç.pdf")
        self.assertTrue(SinavBildirimLog.objects.filter(basvuru=self.ahmet, an_kodu="sonuc-1").exists())

        sayfa = self.client.get(reverse("sinav_basvuru_sonuc"), {"t": token})
        self.assertContains(sayfa, "Ahmet Yılmaz")
        self.assertContains(sayfa, "Sonucu indir")
        dosya = self.client.get(reverse("sinav_basvuru_sonuc_dosya"), {"t": token})
        self.assertEqual(dosya.status_code, 200)
        self.assertEqual(b"".join(dosya.streaming_content), b"%PDF-1.4 ahmet")

        # Aynı karne ikinci kez gitmez.
        self.client.post(URL, {"action": "sonuc_gonder", "bolum": "sonuclar", "kapsam": "bekleyen"})
        self.assertEqual(len(mail.outbox), 1)

        # Karne değişirse yeniden gönderilebilir.
        karne_kaydet(self.ahmet, SimpleUploadedFile("yeni.png", PNG, content_type="image/png"))
        self.client.post(URL, {"action": "sonuc_gonder", "bolum": "sonuclar", "basvuru_ids": [self.ahmet.pk]})
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(SinavBildirimLog.objects.filter(basvuru=self.ahmet, an_kodu="sonuc-2").exists())

    def test_karar_satir_ve_toplu(self):
        self.client.post(URL, {"action": "karar_satir", "bolum": "sonuclar",
                               f"karar_{self.ali.pk}": "kazandi", f"karar_{self.ahmet.pk}": ""})
        self.ali.refresh_from_db()
        self.assertEqual(self.ali.sonuc_karar, "kazandi")
        self.client.post(URL, {"action": "karar_toplu", "bolum": "sonuclar", "toplu_karar": "kazanamadi",
                               "basvuru_ids": [self.ahmet.pk, self.zeynep.pk]})
        self.assertEqual(SinavBasvuru.objects.filter(sonuc_karar="kazanamadi").count(), 2)
        sayfa = self.client.get(URL, {"bolum": "sonuclar", "karar": "kazandi"})
        self.assertContains(sayfa, "Ali Kaya")
        self.assertNotContains(sayfa, "Mehmet Çelik")
        detay = self.client.get(reverse("yonetim:sinav_basvuru_detay", args=[self.ali.pk]))
        self.assertContains(detay, "Kazandı")

    def test_yonetim_karne_goruntuleme(self):
        karne_kaydet(self.ali, SimpleUploadedFile("a.pdf", b"%PDF-1.4 ali", content_type="application/pdf"))
        yanit = self.client.get(reverse("yonetim:seviye_tespit_karne", args=[self.ali.pk]))
        self.assertEqual(yanit.status_code, 200)
        self.client.logout()
        yanit = self.client.get(reverse("yonetim:seviye_tespit_karne", args=[self.ali.pk]))
        self.assertNotEqual(yanit.status_code, 200)
