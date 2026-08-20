"""Performans/güvenilirlik — namaz yoklaması toplu kaydetme.

Önceki `yoklama_kaydet`, her öğrenci için ayrı ayrı update_or_create/
delete çağırıyordu (80+ öğrencilik bir sınıfta 150+ ayrı sorgu) — yavaş
bağlantıda "Bu Vakti Kaydet" isteği zaman aşımına uğrayıp 500 hatası
veriyordu (production'da bildirildi). Artık tek bir toplu upsert
(bulk_create + update_conflicts) kullanılıyor; bu testler doğru veri
üretildiğini doğruluyor (davranış aynı kalmalı, sadece sorgu sayısı
düşmeli).
"""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from takip.models import EtutHocasi, NamazDurumu, NamazYoklamaKaydi, SinifSube, Talebe
from takip.namaz_yoklama_service import yoklama_kaydet


class YoklamaKaydetTopluTests(TestCase):
    def setUp(self):
        sinif = SinifSube.objects.create(sinif="8", sube="B")
        hoca_user = User.objects.create_user("hoca-namaz-test", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Test Hoca", user=hoca_user)
        hoca.sorumlu_sinif_subeler.add(sinif)
        self.kaydeden = User.objects.create_user("kaydeden-namaz-test", password="x")

        self.talebeler = [
            Talebe.objects.create(
                ad_soyad=f"Talebe {i}",
                sinif_sube=sinif,
                etut_hocasi=hoca,
                dini_ders_hocasi=hoca,
            )
            for i in range(1, 6)
        ]
        self.tarih = date(2026, 8, 21)

    def test_ilk_kayitta_dogru_durumlar_olusur(self):
        talebe_ids = [t.pk for t in self.talebeler]
        durumlar = {
            self.talebeler[0].pk: NamazDurumu.GELMEDI,
            self.talebeler[1].pk: NamazDurumu.IZINLI,
            # talebeler[2..4] için durum boş → kayıt oluşturulmamalı
        }

        oturum = yoklama_kaydet(self.kaydeden, self.tarih, "sabah", durumlar, talebe_ids)

        self.assertEqual(oturum.tarih, self.tarih)
        self.assertEqual(oturum.kaydeden, self.kaydeden)
        kayitlar = {k.talebe_id: k.durum for k in oturum.kayitlar.all()}
        self.assertEqual(
            kayitlar,
            {
                self.talebeler[0].pk: NamazDurumu.GELMEDI,
                self.talebeler[1].pk: NamazDurumu.IZINLI,
            },
        )

    def test_tekrar_kaydedince_mevcut_kayit_guncellenir_hata_vermez(self):
        talebe_ids = [t.pk for t in self.talebeler]
        yoklama_kaydet(
            self.kaydeden,
            self.tarih,
            "sabah",
            {self.talebeler[0].pk: NamazDurumu.GELMEDI},
            talebe_ids,
        )

        # Aynı öğrenci için farklı bir durumla tekrar kaydet — çakışma
        # (UniqueConstraint) hatası VERMEMELİ, güncellemeli.
        oturum = yoklama_kaydet(
            self.kaydeden,
            self.tarih,
            "sabah",
            {self.talebeler[0].pk: NamazDurumu.TAKKE_TESBIH},
            talebe_ids,
        )

        self.assertEqual(
            NamazYoklamaKaydi.objects.filter(
                oturum=oturum, talebe=self.talebeler[0]
            ).count(),
            1,
        )
        kayit = NamazYoklamaKaydi.objects.get(oturum=oturum, talebe=self.talebeler[0])
        self.assertEqual(kayit.durum, NamazDurumu.TAKKE_TESBIH)

    def test_durum_bosaltilinca_kayit_silinir(self):
        talebe_ids = [t.pk for t in self.talebeler]
        oturum = yoklama_kaydet(
            self.kaydeden,
            self.tarih,
            "sabah",
            {self.talebeler[0].pk: NamazDurumu.GELMEDI},
            talebe_ids,
        )
        self.assertTrue(
            NamazYoklamaKaydi.objects.filter(
                oturum=oturum, talebe=self.talebeler[0]
            ).exists()
        )

        # Durum boş gönderilirse (öğrenci "geldi" işaretlendi) kayıt silinmeli.
        yoklama_kaydet(self.kaydeden, self.tarih, "sabah", {}, talebe_ids)

        self.assertFalse(
            NamazYoklamaKaydi.objects.filter(
                oturum=oturum, talebe=self.talebeler[0]
            ).exists()
        )

    def test_listeden_cikan_talebenin_kaydi_silinir(self):
        talebe_ids = [t.pk for t in self.talebeler]
        oturum = yoklama_kaydet(
            self.kaydeden,
            self.tarih,
            "sabah",
            {t.pk: NamazDurumu.GELMEDI for t in self.talebeler},
            talebe_ids,
        )
        self.assertEqual(oturum.kayitlar.count(), 5)

        # Filtre değişip talebe_ids daralırsa (örn. sınıf filtresi), listede
        # olmayan öğrencinin kaydı temizlenmeli.
        kalan_ids = [t.pk for t in self.talebeler[:2]]
        yoklama_kaydet(
            self.kaydeden,
            self.tarih,
            "sabah",
            {t.pk: NamazDurumu.GELMEDI for t in self.talebeler[:2]},
            kalan_ids,
        )
        self.assertEqual(oturum.kayitlar.count(), 2)

    def test_buyuk_sinif_dusuk_sorgu_sayisiyla_kaydedilir(self):
        """80+ öğrencilik bir sınıfta bile sorgu sayısı sabit/düşük kalmalı
        (önceki N+1 davranışının regresyonu — production'da 500/timeout'a
        yol açmıştı)."""
        sinif = SinifSube.objects.create(sinif="7", sube="Z")
        hoca_user = User.objects.create_user("hoca-namaz-buyuk-test", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Büyük Sınıf Hoca", user=hoca_user)
        hoca.sorumlu_sinif_subeler.add(sinif)
        buyuk_talebeler = [
            Talebe.objects.create(
                ad_soyad=f"Büyük Talebe {i}",
                sinif_sube=sinif,
                etut_hocasi=hoca,
                dini_ders_hocasi=hoca,
            )
            for i in range(80)
        ]
        talebe_ids = [t.pk for t in buyuk_talebeler]
        durumlar = {t.pk: NamazDurumu.GELMEDI for t in buyuk_talebeler}

        # 4 gerçek sorgu (oturum SELECT+INSERT, stale-kayıt DELETE, tek bir
        # toplu bulk_create/ON CONFLICT INSERT) + @transaction.atomic'in
        # SAVEPOINT/RELEASE defter kayıtları. Öğrenci sayısından BAĞIMSIZ
        # sabit bir sayı olması asıl önemli olan (önceden N ile artıyordu).
        with self.assertNumQueries(10):
            yoklama_kaydet(self.kaydeden, self.tarih, "ogle", durumlar, talebe_ids)
