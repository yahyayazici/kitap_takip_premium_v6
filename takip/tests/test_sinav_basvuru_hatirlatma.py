"""Formdaki zorunlu hatırlatma adımı, e-posta ve takvim dosyası."""

import datetime as dt
import json
from unittest import mock
from zoneinfo import ZoneInfo

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from config.branding import SINAV_BASVURU_BASLIK
from takip.models import SinavBasvuru
from takip.sinav_bildirim_models import SinavBasvuruPushAbonelik, SinavBildirimLog, SinavTakvim
from takip.sinav_bildirim_service import AN_BIR_GUN, AN_KAYIT, AN_UC_GUN, zamani_gelenleri_gonder

TZ = ZoneInfo("Europe/Istanbul")
FORM_URL = reverse("sinav_basvuru_form")
VAPID = {"VAPID_PUBLIC_KEY": "test-public", "VAPID_PRIVATE_KEY": "test-private"}
ABONELIK = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/form-cihaz",
    "keys": {"p256dh": "anahtar", "auth": "dogrulama"},
}


def veri(**degisiklik):
    v = {
        "ad_soyad": "Ahmet Yılmaz",
        "sinif": "6",
        "okul_adi": "Başakşehir Ortaokulu",
        "veli_eposta": "Veli@Example.com",
        "hatirlatma_turu": "takvim",
        "bildirim_abonelik": "",
        "baba_adi": "Mehmet",
        "baba_telefon": "0532 111 22 33",
        "anne_adi": "Ayşe",
        "anne_telefon": "0533 444 55 66",
        "il": "İstanbul",
        "ilce": "Başakşehir",
        "dogum_tarihi": "2014-05-10",
        "bilgilendirme_onay": "on",
    }
    v.update(degisiklik)
    return v


class TakvimliTestCase(TestCase):
    def setUp(self):
        SinavTakvim.objects.update_or_create(
            sinav_adi=SINAV_BASVURU_BASLIK,
            defaults={
                "baslangic": dt.datetime(2026, 10, 24, 11, 0, tzinfo=TZ),
                "bitis": dt.datetime(2026, 10, 24, 13, 10, tzinfo=TZ),
                "yer": "Çinili Saray Öğrenci Yurdu, Başakşehir",
                "bildirim_aktif": True,
            },
        )


class FormHatirlatmaTests(TakvimliTestCase):
    def test_hatirlatma_acilmadan_gonderilemez(self):
        yanit = self.client.post(FORM_URL, veri(hatirlatma_turu=""))
        self.assertEqual(yanit.status_code, 200)
        self.assertIn("hatirlatma_turu", yanit.context["form"].errors)
        self.assertFalse(SinavBasvuru.objects.exists())

    def test_eposta_zorunlu(self):
        yanit = self.client.post(FORM_URL, veri(veli_eposta=""))
        self.assertEqual(yanit.status_code, 200)
        self.assertIn("veli_eposta", yanit.context["form"].errors)
        self.assertFalse(SinavBasvuru.objects.exists())

    def test_push_secilip_abonelik_yoksa_reddedilir(self):
        yanit = self.client.post(FORM_URL, veri(hatirlatma_turu="push", bildirim_abonelik="{}"))
        self.assertEqual(yanit.status_code, 200)
        self.assertFalse(SinavBasvuru.objects.exists())

    def test_takvim_yolu_kayit_epostasini_takvim_ekiyle_gonderir(self):
        yanit = self.client.post(FORM_URL, veri())
        self.assertEqual(yanit.status_code, 302)
        basvuru = SinavBasvuru.objects.get()
        self.assertEqual(basvuru.hatirlatma_turu, "takvim")
        self.assertEqual(basvuru.veli_eposta, "veli@example.com")
        self.assertEqual(len(mail.outbox), 1)
        eposta = mail.outbox[0]
        self.assertEqual(eposta.to, ["veli@example.com"])
        self.assertIn("Ahmet Yılmaz", eposta.body)
        self.assertIn("2 örnek yazılı", eposta.body)
        self.assertEqual(eposta.attachments[0][0], "sinav.ics")
        log = SinavBildirimLog.objects.get(basvuru=basvuru, an_kodu=AN_KAYIT)
        self.assertTrue(log.eposta_gonderildi)
        self.assertEqual(log.gonderilen, 0)

    @override_settings(**VAPID)
    @mock.patch("pywebpush.webpush")
    def test_push_yolu_abonelik_kaydeder_ve_bildirim_gonderir(self, webpush):
        yanit = self.client.post(
            FORM_URL,
            veri(hatirlatma_turu="push", bildirim_abonelik=json.dumps(ABONELIK)),
        )
        self.assertEqual(yanit.status_code, 302)
        basvuru = SinavBasvuru.objects.get()
        self.assertEqual(basvuru.hatirlatma_turu, "push")
        self.assertTrue(SinavBasvuruPushAbonelik.objects.filter(basvuru=basvuru).exists())
        log = SinavBildirimLog.objects.get(basvuru=basvuru, an_kodu=AN_KAYIT)
        self.assertEqual(log.gonderilen, 1)
        self.assertTrue(log.eposta_gonderildi)
        self.assertEqual(webpush.call_count, 1)

    @override_settings(**VAPID)
    def test_form_vapid_anahtarini_sayfaya_koyar(self):
        icerik = self.client.get(FORM_URL).content.decode()
        self.assertIn('data-vapid-key="test-public"', icerik)


class TakvimDosyasiTests(TakvimliTestCase):
    def test_takvim_dosyasi_uc_hatirlatma_icerir(self):
        yanit = self.client.get(reverse("sinav_basvuru_takvim"))
        self.assertEqual(yanit.status_code, 200)
        self.assertTrue(yanit["Content-Type"].startswith("text/calendar"))
        ics = yanit.content.decode()
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("DTSTART:20261024T080000Z", ics)
        self.assertEqual(ics.count("BEGIN:VALARM"), 3)
        for tetik in ("TRIGGER:-P2DT16H", "TRIGGER:-PT16H", "TRIGGER:-PT2H30M"):
            self.assertIn(tetik, ics)
        self.assertIn("Başakşehir", ics)
        self.assertIn("\r\n", ics)


class EpostaZamanlamaTests(TakvimliTestCase):
    def test_sadece_epostali_basvuruya_bir_gun_kala_eposta_gider(self):
        basvuru = SinavBasvuru.objects.create(
            ad_soyad="Ali Kaya", sinif="7", okul_adi="Okul", veli_eposta="ali@example.com",
            hatirlatma_turu="takvim", baba_adi="A", baba_telefon="05320000000", anne_adi="B",
            anne_telefon="05330000000", il="İstanbul", ilce="Başakşehir",
            dogum_tarihi=dt.date(2013, 1, 1), sinav_adi=SINAV_BASVURU_BASLIK,
        )
        SinavBasvuru.objects.filter(pk=basvuru.pk).update(
            olusturulma=dt.datetime(2026, 10, 18, 10, 0, tzinfo=TZ)
        )
        zamani_gelenleri_gonder(dt.datetime(2026, 10, 21, 19, 5, tzinfo=TZ))
        self.assertFalse(SinavBildirimLog.objects.filter(basvuru=basvuru, an_kodu=AN_UC_GUN).exists())
        zamani_gelenleri_gonder(dt.datetime(2026, 10, 23, 19, 5, tzinfo=TZ))
        log = SinavBildirimLog.objects.get(basvuru=basvuru, an_kodu=AN_BIR_GUN)
        self.assertTrue(log.eposta_gonderildi)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("yarın", mail.outbox[0].body)
