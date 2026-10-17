"""Yönetim — tek sayfa Seviye Tespit ekranı."""

import datetime as dt
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from config.branding import SINAV_BASVURU_BASLIK
from takip.models import SinavBasvuru, SinavBasvuruDurum
from takip.sinav_bildirim_models import SinavTakvim

TZ = ZoneInfo("Europe/Istanbul")
URL = reverse("yonetim:sinav_basvuru_listesi")


def basvuru(**ek):
    veri = dict(
        ad_soyad="Ahmet Yılmaz", sinif="6", okul_adi="Başakşehir Ortaokulu",
        veli_eposta="veli@example.com", hatirlatma_turu="takvim", baba_adi="M",
        baba_telefon="05321112233", anne_adi="A", anne_telefon="05334445566",
        il="İstanbul", ilce="Başakşehir", dogum_tarihi=dt.date(2014, 5, 10),
        sinav_adi=SINAV_BASVURU_BASLIK,
    )
    veri.update(ek)
    return SinavBasvuru.objects.create(**veri)


class SeviyeTespitSayfasiTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("idareci-st-test", "a@b.com", "Sifre!2026x")
        self.client.login(username="idareci-st-test", password="Sifre!2026x")
        SinavTakvim.objects.update_or_create(
            sinav_adi=SINAV_BASVURU_BASLIK,
            defaults={
                "baslangic": dt.datetime(2026, 10, 24, 11, 0, tzinfo=TZ),
                "bitis": dt.datetime(2026, 10, 24, 13, 10, tzinfo=TZ),
                "yer": "Çinili Saray",
            },
        )
        self.b1 = basvuru()
        self.b2 = basvuru(ad_soyad="Ali Kaya", sinif="8")
        self.eski = basvuru(ad_soyad="Eski Kayıt", sinav_adi="4A Proje Sınıfı Alım Sınavı")

    def test_tum_bolumler_acilir(self):
        for bolum, metin in [
            ("genel", "Sınıflara göre"),
            ("basvurular", "Ali Kaya"),
            ("bildirimler", "Bildirim takvimi"),
            ("ayarlar", "Sınav takvimi"),
        ]:
            yanit = self.client.get(URL, {"bolum": bolum})
            self.assertEqual(yanit.status_code, 200, bolum)
            self.assertContains(yanit, metin)
            self.assertContains(yanit, "Seviye Tespit")

    def test_varsayilan_liste_yalnizca_guncel_sinav(self):
        yanit = self.client.get(URL, {"bolum": "basvurular"})
        self.assertContains(yanit, "Ahmet Yılmaz")
        self.assertNotContains(yanit, "Eski Kayıt")
        yanit = self.client.get(URL, {"bolum": "basvurular", "sinav": ""})
        self.assertContains(yanit, "Eski Kayıt")

    def test_genel_bakis_sayilari(self):
        yanit = self.client.get(URL)
        genel = yanit.context["genel"]
        self.assertEqual(genel["toplam"], 2)
        self.assertEqual(genel["takvim"], 2)
        sayilar = {s["etiket"]: s["sayi"] for s in genel["siniflar"]}
        self.assertEqual(sayilar["6. sınıf"], 1)
        self.assertEqual(sayilar["8. sınıf"], 1)

    def test_takvim_kaydedilir_ve_ayarlara_doner(self):
        yanit = self.client.post(
            URL,
            {
                "action": "takvim_kaydet",
                "bolum": "ayarlar",
                "tarih": "2026-10-25",
                "baslangic": "10:00",
                "bitis": "12:30",
                "yer": "Yeni salon",
                "bildirim_aktif": "on",
            },
        )
        self.assertEqual(yanit.status_code, 302)
        self.assertTrue(yanit["Location"].endswith("?bolum=ayarlar"))
        t = SinavTakvim.objects.get(sinav_adi=SINAV_BASVURU_BASLIK)
        self.assertEqual(t.baslangic, dt.datetime(2026, 10, 25, 10, 0, tzinfo=TZ))
        self.assertEqual(t.yer, "Yeni salon")

    def test_bitis_baslangictan_once_olamaz(self):
        self.client.post(
            URL,
            {"action": "takvim_kaydet", "tarih": "2026-10-25", "baslangic": "12:00", "bitis": "10:00"},
        )
        t = SinavTakvim.objects.get(sinav_adi=SINAV_BASVURU_BASLIK)
        self.assertEqual(t.baslangic, dt.datetime(2026, 10, 24, 11, 0, tzinfo=TZ))

    def test_toplu_durum_basvurulara_doner(self):
        durum = SinavBasvuruDurum.objects.create(kod="kabul-test", ad="Kabul Test", aktif=True)
        yanit = self.client.post(
            URL,
            {
                "action": "toplu_durum",
                "bolum": "basvurular",
                "toplu_durum_id": durum.pk,
                "basvuru_ids": [self.b1.pk, self.b2.pk],
            },
        )
        self.assertTrue(yanit["Location"].endswith("?bolum=basvurular"))
        self.assertEqual(SinavBasvuru.objects.filter(durum=durum).count(), 2)

    def test_detay_sayfasi(self):
        yanit = self.client.get(reverse("yonetim:sinav_basvuru_detay", args=[self.b1.pk]))
        self.assertEqual(yanit.status_code, 200)
        self.assertContains(yanit, "Gönderilen hatırlatmalar")
        self.assertContains(yanit, "veli@example.com")
