"""Seviye Tespit — salonlar ve kelebek yerleşimi."""

import datetime as dt
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from config.branding import SINAV_BASVURU_BASLIK
from takip.models import SinavBasvuru
from takip.sinav_bildirim_models import SinavTakvim
from takip.sinav_bildirim_service import AN_BIR_GUN, AN_SABAH, bildirim_metni, eposta_metni
from takip.sinav_salon_models import SinavSalon, SinavYerlesim
from takip.sinav_salon_service import YerlesimHatasi, kelebek_yerlestir

TZ = ZoneInfo("Europe/Istanbul")
URL = reverse("yonetim:sinav_basvuru_listesi")


def basvuru(ad, sinif, okul="Okul A", **ek):
    veri = dict(
        ad_soyad=ad, sinif=sinif, okul_adi=okul, veli_eposta="v@example.com",
        hatirlatma_turu="takvim", baba_adi="M", baba_telefon="05321112233", anne_adi="A",
        anne_telefon="05334445566", il="İstanbul", ilce="Başakşehir",
        dogum_tarihi=dt.date(2014, 5, 10), sinav_adi=SINAV_BASVURU_BASLIK,
    )
    veri.update(ek)
    return SinavBasvuru.objects.create(**veri)


def salon(ad, masa, kisi=1, sira=1):
    return SinavSalon.objects.create(
        sinav_adi=SINAV_BASVURU_BASLIK, ad=ad, masa_sayisi=masa, masa_kisi=kisi, sira=sira
    )


class KelebekTests(TestCase):
    def setUp(self):
        dagilim = {"4": 4, "5": 6, "6": 8, "7": 6, "8": 12}
        for sinif, n in dagilim.items():
            for i in range(n):
                basvuru(f"Öğrenci {sinif}-{i}", sinif, okul=f"Okul {i % 3}")
        self.eski = basvuru("Eski", "6", sinav_adi="Başka Sınav")

    def test_herkes_yerlesir_ve_komsular_farkli_sinif(self):
        salon("Salon 1", 10, kisi=2, sira=1)
        salon("Salon 2", 10, kisi=2, sira=2)
        sonuc = kelebek_yerlestir(SINAV_BASVURU_BASLIK, tohum=7)
        self.assertEqual(sonuc["ogrenci"], 36)
        self.assertFalse(SinavYerlesim.objects.filter(basvuru=self.eski).exists())
        for s in SinavSalon.objects.all():
            yerler = list(s.yerlesimler.select_related("basvuru").order_by("masa_no", "koltuk"))
            # Salonlara dengeli dağılır.
            self.assertEqual(len(yerler), 18)
            # Aynı salonda birden fazla sınıf olur.
            self.assertGreaterEqual(len({y.basvuru.sinif for y in yerler}), 4)
            # Aynı masadaki iki öğrenci farklı sınıftan.
            masalar = {}
            for y in yerler:
                masalar.setdefault(y.masa_no, []).append(y.basvuru.sinif)
            for siniflar in masalar.values():
                self.assertEqual(len(siniflar), len(set(siniflar)), masalar)

    def test_ogrenci_masadan_azsa_herkes_ayri_masada(self):
        salon("Salon 1", 40, kisi=2)
        kelebek_yerlestir(SINAV_BASVURU_BASLIK, tohum=1)
        self.assertFalse(SinavYerlesim.objects.filter(koltuk=2).exists())
        self.assertEqual(SinavYerlesim.objects.count(), 36)

    def test_yer_yetmezse_hata_ve_degisiklik_yok(self):
        salon("Salon 1", 10)
        with self.assertRaisesMessage(YerlesimHatasi, "26 kişilik yer daha"):
            kelebek_yerlestir(SINAV_BASVURU_BASLIK)
        self.assertEqual(SinavYerlesim.objects.count(), 0)

    def test_yeniden_yerlestirme_eskisini_siler(self):
        salon("Salon 1", 40)
        kelebek_yerlestir(SINAV_BASVURU_BASLIK, tohum=1)
        kelebek_yerlestir(SINAV_BASVURU_BASLIK, tohum=2)
        self.assertEqual(SinavYerlesim.objects.count(), 36)


class SalonSayfasiTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("idareci-salon", "a@b.com", "Sifre!2026x")
        self.client.login(username="idareci-salon", password="Sifre!2026x")
        self.takvim = SinavTakvim.objects.update_or_create(
            sinav_adi=SINAV_BASVURU_BASLIK,
            defaults={
                "baslangic": dt.datetime(2026, 10, 24, 11, 0, tzinfo=TZ),
                "bitis": dt.datetime(2026, 10, 24, 13, 10, tzinfo=TZ),
                "yer": "Çinili Saray",
            },
        )[0]
        self.ali = basvuru("Ali Kaya", "8")
        self.veli = basvuru("Veli Can", "5")

    def test_sekme_acilir(self):
        yanit = self.client.get(URL, {"bolum": "salonlar"})
        self.assertEqual(yanit.status_code, 200)
        self.assertContains(yanit, "Kelebek sistemi")
        self.assertContains(yanit, "Salonlar ve masalar")

    def test_salon_kaydet_kelebek_ve_yazdir(self):
        yanit = self.client.post(
            URL,
            {
                "action": "salon_kaydet",
                "bolum": "salonlar",
                "masa_kisi": "2",
                "salon_ad": ["Mavi Salon", "Salon 2", ""],
                "salon_masa": ["6", "4", "0"],
            },
        )
        self.assertEqual(yanit.status_code, 302)
        self.assertEqual(
            list(SinavSalon.objects.values_list("ad", "masa_sayisi", "masa_kisi")),
            [("Mavi Salon", 6, 2), ("Salon 2", 4, 2)],
        )

        self.client.post(URL, {"action": "kelebek", "bolum": "salonlar"})
        self.assertEqual(SinavYerlesim.objects.count(), 2)

        yanit = self.client.get(URL, {"bolum": "salonlar"})
        self.assertContains(yanit, "Yeniden yerleştir")
        self.assertContains(yanit, "Ali Kaya")

        for tur in ("kapi", "yoklama", "etiket", "oturma"):
            yazdir = self.client.get(reverse("yonetim:seviye_tespit_salon_yazdir"), {"tur": tur})
            self.assertEqual(yazdir.status_code, 200, tur)
            self.assertContains(yazdir, "Ali Kaya")

        detay = self.client.get(reverse("yonetim:sinav_basvuru_detay", args=[self.ali.pk]))
        self.assertContains(detay, "Masa ")

    def test_masa_duzeni_degisince_yerlesim_sifirlanir(self):
        salon("Salon 1", 10)
        kelebek_yerlestir(SINAV_BASVURU_BASLIK)
        self.client.post(
            URL,
            {"action": "salon_kaydet", "bolum": "salonlar", "masa_kisi": "1",
             "salon_ad": ["Salon 1"], "salon_masa": ["12"]},
        )
        self.assertEqual(SinavYerlesim.objects.count(), 0)

    def test_yalnizca_ad_degisirse_yerlesim_korunur(self):
        salon("Salon 1", 10)
        kelebek_yerlestir(SINAV_BASVURU_BASLIK)
        self.client.post(
            URL,
            {"action": "salon_kaydet", "bolum": "salonlar", "masa_kisi": "1",
             "salon_ad": ["Zemin Kat"], "salon_masa": ["10"]},
        )
        self.assertEqual(SinavYerlesim.objects.count(), 2)
        self.assertEqual(SinavSalon.objects.get().ad, "Zemin Kat")

    def test_hatirlatmalarda_salon_ve_masa(self):
        s = salon("Salon 3", 10)
        SinavYerlesim.objects.create(basvuru=self.ali, salon=s, masa_no=7)
        _, mesaj = bildirim_metni(AN_BIR_GUN, self.ali, self.takvim)
        self.assertIn("Salon 3, Masa 7", mesaj)
        _, sabah = bildirim_metni(AN_SABAH, self.ali, self.takvim)
        self.assertIn("Salon 3, Masa 7", sabah)
        _, govde = eposta_metni(AN_BIR_GUN, self.ali, self.takvim)
        self.assertIn("Salon ve masa: Salon 3, Masa 7", govde)
        # Yerleşimi olmayan öğrencide salon satırı çıkmaz.
        _, mesaj2 = bildirim_metni(AN_BIR_GUN, self.veli, self.takvim)
        self.assertNotIn("Salon", mesaj2)
