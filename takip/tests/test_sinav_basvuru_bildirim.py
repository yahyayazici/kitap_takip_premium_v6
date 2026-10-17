"""Sınav başvurusu uygulama bildirimleri: abonelik, kayıt bildirimi, zamanlanmış hatırlatmalar."""

import datetime as dt
import json
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.urls import reverse

from config.branding import SINAV_BASVURU_BASLIK
from takip.models import SinavBasvuru
from takip.sinav_bildirim_models import SinavBasvuruPushAbonelik, SinavBildirimLog, SinavTakvim
from takip.sinav_bildirim_service import (
    AN_BIR_GUN,
    AN_BITIS,
    AN_KAYIT,
    AN_SABAH,
    AN_UC_GUN,
    basvuru_token,
    tokendan_basvuru,
    zamani_gelenleri_gonder,
)

TZ = ZoneInfo("Europe/Istanbul")
VAPID = {"VAPID_PUBLIC_KEY": "test-public", "VAPID_PRIVATE_KEY": "test-private"}
ABONELIK = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/test-cihaz",
    "keys": {"p256dh": "anahtar", "auth": "dogrulama"},
}


def yerel(yil, ay, gun, saat, dakika=0):
    return dt.datetime(yil, ay, gun, saat, dakika, tzinfo=TZ)


def basvuru_olustur(olusturulma=None, **ek):
    veri = dict(
        ad_soyad="Ahmet Yılmaz",
        sinif="6",
        okul_adi="Başakşehir Ortaokulu",
        baba_adi="Mehmet",
        baba_telefon="05321112233",
        anne_adi="Ayşe",
        anne_telefon="05334445566",
        il="İstanbul",
        ilce="Başakşehir",
        dogum_tarihi=dt.date(2014, 5, 10),
        sinav_adi=SINAV_BASVURU_BASLIK,
    )
    veri.update(ek)
    basvuru = SinavBasvuru.objects.create(**veri)
    if olusturulma:
        SinavBasvuru.objects.filter(pk=basvuru.pk).update(olusturulma=olusturulma)
        basvuru.refresh_from_db()
    return basvuru


class SinavBildirimTemelTests(TestCase):
    def setUp(self):
        SinavTakvim.objects.update_or_create(
            sinav_adi=SINAV_BASVURU_BASLIK,
            defaults={
                "baslangic": yerel(2026, 10, 24, 11, 0),
                "bitis": yerel(2026, 10, 24, 13, 10),
                "yer": "Çinili Saray Öğrenci Yurdu, Başakşehir",
                "bildirim_aktif": True,
            },
        )

    def test_token_geri_cozulur_bozuk_token_reddedilir(self):
        basvuru = basvuru_olustur()
        self.assertEqual(tokendan_basvuru(basvuru_token(basvuru)), basvuru)
        self.assertIsNone(tokendan_basvuru("bozuk"))
        self.assertIsNone(tokendan_basvuru(basvuru_token(basvuru) + "x"))

    @override_settings(**VAPID)
    def test_tesekkur_sayfasi_bildirim_kartini_gosterir(self):
        basvuru = basvuru_olustur()
        url = reverse("sinav_basvuru_tesekkur") + "?t=" + basvuru_token(basvuru)
        icerik = self.client.get(url).content.decode()
        self.assertIn("Bildirimleri aç", icerik)
        self.assertIn("manifest.webmanifest", icerik)

    @override_settings(**VAPID)
    def test_tokensiz_tesekkur_sayfasinda_kart_yok(self):
        icerik = self.client.get(reverse("sinav_basvuru_tesekkur")).content.decode()
        self.assertNotIn("Bildirimleri aç", icerik)

    def test_manifest_basvuruya_ozel(self):
        basvuru = basvuru_olustur()
        token = basvuru_token(basvuru)
        yanit = self.client.get(reverse("sinav_basvuru_bildirim_manifest", args=[token]))
        self.assertEqual(yanit.status_code, 200)
        self.assertIn(token, json.loads(yanit.content)["start_url"])
        self.assertEqual(
            self.client.get(reverse("sinav_basvuru_bildirim_manifest", args=["bozuk"])).status_code,
            404,
        )

    @override_settings(**VAPID)
    @mock.patch("pywebpush.webpush")
    def test_abonelik_kayit_bildirimini_bir_kez_gonderir(self, webpush):
        basvuru = basvuru_olustur()
        url = reverse("sinav_basvuru_bildirim_abone", args=[basvuru_token(basvuru)])
        for _ in range(2):
            yanit = self.client.post(url, data=json.dumps(ABONELIK), content_type="application/json")
            self.assertEqual(yanit.status_code, 200)
        self.assertEqual(SinavBasvuruPushAbonelik.objects.filter(basvuru=basvuru).count(), 1)
        log = SinavBildirimLog.objects.get(basvuru=basvuru, an_kodu=AN_KAYIT)
        self.assertEqual(log.gonderilen, 1)
        self.assertEqual(webpush.call_count, 1)
        self.assertIn("Ahmet", log.mesaj)

    @override_settings(**VAPID)
    def test_gecersiz_abonelik_reddedilir(self):
        basvuru = basvuru_olustur()
        url = reverse("sinav_basvuru_bildirim_abone", args=[basvuru_token(basvuru)])
        kotu = {"endpoint": "http://ornek.com/x", "keys": {"p256dh": "a", "auth": "b"}}
        yanit = self.client.post(url, data=json.dumps(kotu), content_type="application/json")
        self.assertEqual(yanit.status_code, 400)
        yanit = self.client.post(
            reverse("sinav_basvuru_bildirim_abone", args=["bozuk"]),
            data=json.dumps(ABONELIK),
            content_type="application/json",
        )
        self.assertEqual(yanit.status_code, 404)


@override_settings(**VAPID)
@mock.patch("pywebpush.webpush")
class SinavHatirlatmaZamanlamaTests(TestCase):
    def setUp(self):
        SinavTakvim.objects.update_or_create(
            sinav_adi=SINAV_BASVURU_BASLIK,
            defaults={
                "baslangic": yerel(2026, 10, 24, 11, 0),
                "bitis": yerel(2026, 10, 24, 13, 10),
                "yer": "Çinili Saray",
                "bildirim_aktif": True,
            },
        )
        self.basvuru = basvuru_olustur(olusturulma=yerel(2026, 10, 18, 10, 0))
        SinavBasvuruPushAbonelik.objects.create(
            basvuru=self.basvuru, endpoint=ABONELIK["endpoint"], p256dh="a", auth="b"
        )

    def _anlar(self):
        return set(
            SinavBildirimLog.objects.filter(basvuru=self.basvuru).values_list("an_kodu", flat=True)
        )

    def test_uc_gun_kala_bir_kez_gider(self, webpush):
        self.assertEqual(zamani_gelenleri_gonder(yerel(2026, 10, 21, 18, 59)), 0)
        self.assertEqual(zamani_gelenleri_gonder(yerel(2026, 10, 21, 19, 5)), 1)
        self.assertEqual(zamani_gelenleri_gonder(yerel(2026, 10, 21, 19, 10)), 0)
        self.assertEqual(self._anlar(), {AN_UC_GUN})

    def test_tum_anlar_sirasiyla(self, webpush):
        for an in [
            yerel(2026, 10, 21, 19, 1),
            yerel(2026, 10, 23, 19, 1),
            yerel(2026, 10, 24, 8, 31),
            yerel(2026, 10, 24, 13, 26),
        ]:
            zamani_gelenleri_gonder(an)
        self.assertEqual(self._anlar(), {AN_UC_GUN, AN_BIR_GUN, AN_SABAH, AN_BITIS})

    def test_pencere_disinda_gecikmis_hatirlatma_gitmez(self, webpush):
        self.assertEqual(zamani_gelenleri_gonder(yerel(2026, 10, 22, 2, 0)), 0)

    def test_gec_basvuran_eski_hatirlatmayi_almaz(self, webpush):
        gec = basvuru_olustur(olusturulma=yerel(2026, 10, 22, 12, 0), ad_soyad="Ali Kaya")
        SinavBasvuruPushAbonelik.objects.create(
            basvuru=gec, endpoint="https://fcm.googleapis.com/fcm/send/gec", p256dh="a", auth="b"
        )
        zamani_gelenleri_gonder(yerel(2026, 10, 21, 19, 30))
        zamani_gelenleri_gonder(yerel(2026, 10, 23, 19, 30))
        anlar = set(SinavBildirimLog.objects.filter(basvuru=gec).values_list("an_kodu", flat=True))
        self.assertEqual(anlar, {AN_BIR_GUN})

    def test_abonesi_olmayan_basvuruya_kayit_acilmaz(self, webpush):
        aboneliksiz = basvuru_olustur(olusturulma=yerel(2026, 10, 18, 10, 0), ad_soyad="Veli Yok")
        zamani_gelenleri_gonder(yerel(2026, 10, 21, 19, 5))
        self.assertFalse(SinavBildirimLog.objects.filter(basvuru=aboneliksiz).exists())

    def test_hatirlatmalar_kapaliyken_gonderilmez(self, webpush):
        SinavTakvim.objects.update(bildirim_aktif=False)
        self.assertEqual(zamani_gelenleri_gonder(yerel(2026, 10, 21, 19, 5)), 0)

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_vapid_yoksa_hic_calismaz(self, webpush):
        self.assertEqual(zamani_gelenleri_gonder(yerel(2026, 10, 21, 19, 5)), 0)
        self.assertFalse(SinavBildirimLog.objects.exists())


@override_settings(**VAPID)
class SinavBildirimHataKaydiTests(TestCase):
    @mock.patch("pywebpush.webpush", side_effect=ValueError("bozuk anahtar"))
    def test_gonderim_hatasi_kayda_yazilir(self, webpush):
        basvuru = basvuru_olustur()
        url = reverse("sinav_basvuru_bildirim_abone", args=[basvuru_token(basvuru)])
        self.client.post(url, data=json.dumps(ABONELIK), content_type="application/json")
        log = SinavBildirimLog.objects.get(basvuru=basvuru, an_kodu=AN_KAYIT)
        self.assertEqual(log.gonderilen, 0)
        self.assertIn("bozuk anahtar", log.push_hata)
