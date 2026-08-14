"""Ölçme Merkezi — soru zimmetleme testleri."""

from django.contrib.auth.models import User
from django.test import TestCase

from takip.konu_destek_models import KonuKatalogu
from takip.models import Ders, EtutHocasi, KttSinav
from takip.olcme_models import OlcumSoru
from takip.olcme_service import (
    mevcut_ktt_backfill,
    sinav_dogrulama,
    soru_zimmet_guncelle,
    sorulari_olustur,
    toplu_zimmet_guncelle,
    zimmet_ozet,
)


class OlcumZimmetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("olcme_test", password="test")
        self.ders = Ders.objects.create(ad="Matematik", sira=1, aktif=True)
        self.hoca = EtutHocasi.objects.create(user=self.user, ad_soyad="Test Hoca", aktif=True)
        self.konu_a = KonuKatalogu.objects.create(
            sinif_seviyesi="7",
            brans="matematik",
            konu_ad="Üslü İfadeler",
        )
        self.konu_b = KonuKatalogu.objects.create(
            sinif_seviyesi="7",
            brans="matematik",
            konu_ad="Çarpanlar",
        )
        self.sinav = KttSinav.objects.create(
            ad="Test KTT",
            ders=self.ders,
            sinif_seviyesi="7",
            hedef_siniflar="7-A",
            sinav_tarihi="2026-08-14",
            soru_sayisi=4,
            etut_hocasi=self.hoca,
            olusturan=self.user,
            sinav_turu=KttSinav.SinavTuru.KTT,
            durum=KttSinav.SinavDurum.ZIMMETLEME,
        )

    def test_her_soru_ayri_kayit(self):
        sorulari_olustur(self.sinav, varsayilan_ders=self.ders)
        self.assertEqual(self.sinav.olcme_sorulari.count(), 4)
        nos = list(self.sinav.olcme_sorulari.values_list("soru_no", flat=True))
        self.assertEqual(nos, [1, 2, 3, 4])

    def test_farkli_konular_baginsiz(self):
        sorulari_olustur(self.sinav, varsayilan_ders=self.ders)
        s1 = self.sinav.olcme_sorulari.get(soru_no=1)
        s2 = self.sinav.olcme_sorulari.get(soru_no=2)
        ders_blok_id = s1.sinav_ders_id
        soru_zimmet_guncelle(
            s1,
            kullanici=self.user,
            sinav_ders_id=ders_blok_id,
            konu_id=self.konu_a.id,
        )
        soru_zimmet_guncelle(
            s2,
            kullanici=self.user,
            sinav_ders_id=ders_blok_id,
            konu_id=self.konu_b.id,
        )
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s1.konu_id, self.konu_a.id)
        self.assertEqual(s2.konu_id, self.konu_b.id)

    def test_toplu_zimmet_ayri_kayitlar(self):
        sorulari_olustur(self.sinav, varsayilan_ders=self.ders)
        ids = list(self.sinav.olcme_sorulari.values_list("id", flat=True)[:2])
        adet = toplu_zimmet_guncelle(
            self.sinav,
            ids,
            kullanici=self.user,
            sinav_ders_id=self.sinav.olcme_dersleri.first().id,
            konu_id=self.konu_a.id,
        )
        self.assertEqual(adet, 2)
        for sid in ids:
            self.assertEqual(
                OlcumSoru.objects.get(pk=sid).konu_id,
                self.konu_a.id,
            )

    def test_konu_degistirince_diger_etkilenmez(self):
        sorulari_olustur(self.sinav, varsayilan_ders=self.ders)
        s1 = self.sinav.olcme_sorulari.get(soru_no=1)
        s2 = self.sinav.olcme_sorulari.get(soru_no=2)
        soru_zimmet_guncelle(s1, kullanici=self.user, konu_id=self.konu_a.id)
        soru_zimmet_guncelle(s2, kullanici=self.user, konu_id=self.konu_a.id)
        soru_zimmet_guncelle(s1, kullanici=self.user, konu_id=self.konu_b.id)
        s2.refresh_from_db()
        self.assertEqual(s2.konu_id, self.konu_a.id)

    def test_backfill_idempotent(self):
        mevcut_ktt_backfill(self.sinav)
        mevcut_ktt_backfill(self.sinav)
        self.assertEqual(self.sinav.olcme_sorulari.count(), 4)

    def test_dogrulama_konu_eksik(self):
        sorulari_olustur(self.sinav, varsayilan_ders=self.ders)
        hatalar = sinav_dogrulama(self.sinav)
        kodlar = {h["kod"] for h in hatalar}
        self.assertIn("konu", kodlar)

    def test_zimmet_ozet(self):
        sorulari_olustur(self.sinav, varsayilan_ders=self.ders)
        ozet = zimmet_ozet(self.sinav)
        self.assertEqual(ozet["toplam"], 4)
        self.assertEqual(ozet["eksik"], 4)
