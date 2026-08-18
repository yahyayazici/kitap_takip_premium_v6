"""Hatim Takip Merkezi testleri."""

from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from takip.hatim_models import CuzAtamasi, HatimProgrami
from takip.hatim_service import (
    cuz_cakisma_kontrolu,
    cuzleri_dagit,
    donem_planlari_uret,
    donemleri_olustur,
    hatim_yonetebilir,
    kullanici_atamalari,
    program_baslat,
)
from takip.models import PersonelProfili


class DonemPlanTests(TestCase):
    def test_yahya_ornegi_iki_gunde_bir(self):
        program = HatimProgrami(
            ad="Personel Hatmi",
            tur=HatimProgrami.Tur.PERSONEL,
            baslangic_tarihi=date(2026, 8, 18),
            program_bitis_tarihi=date(2026, 8, 30),
            son_tamamlama_saati=time(20, 0),
            tekrar_turu=HatimProgrami.Tekrar.IKI_GUN,
            hafta_sonu_dahil=True,
            yarim_son_donem=True,
        )
        planlar = donem_planlari_uret(program)
        self.assertEqual(len(planlar), 6)
        self.assertEqual(planlar[0][0].date(), date(2026, 8, 18))
        self.assertEqual(planlar[0][1].date(), date(2026, 8, 20))
        self.assertEqual(planlar[0][1].time(), time(20, 0))
        self.assertEqual(planlar[5][0].date(), date(2026, 8, 28))
        self.assertEqual(planlar[5][1].date(), date(2026, 8, 30))

    def test_bitis_tarihi_opsiyonel_tek_donem(self):
        program = HatimProgrami(
            ad="Açık uçlu",
            baslangic_tarihi=date(2026, 9, 1),
            son_tamamlama_saati=time(20, 0),
            tekrar_turu=HatimProgrami.Tekrar.GUNLUK,
            program_bitis_tarihi=None,
        )
        planlar = donem_planlari_uret(program)
        self.assertEqual(len(planlar), 1)


class HatimDagitimTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("hatim_admin", "a@test.com", "x")
        self.user1 = User.objects.create_user("yahya", "y@test.com", "x")
        self.user2 = User.objects.create_user("ayhan", "b@test.com", "x")
        self.p1 = PersonelProfili.objects.create(
            user=self.user1,
            ad_soyad="Yahya Yazıcı",
            ana_rol="etut_mesul",
        )
        self.p2 = PersonelProfili.objects.create(
            user=self.user2,
            ad_soyad="Ayhan Eroğlu",
            ana_rol="etut_mesul",
        )

    def test_otomatik_dagitim_cakisma_yok(self):
        program = HatimProgrami.objects.create(
            ad="Test Hatmi",
            tur=HatimProgrami.Tur.PERSONEL,
            baslangic_tarihi=date(2026, 8, 18),
            program_bitis_tarihi=date(2026, 8, 30),
            son_tamamlama_saati=time(20, 0),
            tekrar_turu=HatimProgrami.Tekrar.IKI_GUN,
            kisi_basina_cuz=2,
            olusturan=self.admin,
        )
        program_baslat(program, [self.p1, self.p2], olusturan=self.admin)
        donem = program.donemler.first()
        self.assertIsNotNone(donem)
        atamalar = list(donem.cuz_atamalari.order_by("cuz_baslangic"))
        self.assertEqual(len(atamalar), 2)
        self.assertEqual(atamalar[0].cuz_baslangic, 1)
        self.assertEqual(atamalar[0].cuz_bitis, 2)
        self.assertEqual(atamalar[1].cuz_baslangic, 3)
        self.assertEqual(atamalar[1].cuz_bitis, 4)
        self.assertEqual(cuz_cakisma_kontrolu(donem), [])

    def test_ayni_cuz_stratejisi_ikinci_donem(self):
        program = HatimProgrami.objects.create(
            ad="Aynı cüz",
            tur=HatimProgrami.Tur.PERSONEL,
            baslangic_tarihi=date(2026, 8, 18),
            program_bitis_tarihi=date(2026, 8, 30),
            son_tamamlama_saati=time(20, 0),
            tekrar_turu=HatimProgrami.Tekrar.IKI_GUN,
            cuz_donem_stratejisi=HatimProgrami.CuzStrateji.AYNI,
            kisi_basina_cuz=2,
            olusturan=self.admin,
        )
        program_baslat(program, [self.p1], olusturan=self.admin)
        kat = program.katilimcilar.first()
        kat.varsayilan_cuz_bas = 15
        kat.varsayilan_cuz_bit = 16
        kat.save()
        donem1 = program.donemler.first()
        donem1.cuz_atamalari.all().delete()
        cuzleri_dagit(program, donem1)
        donem2 = donemleri_olustur(program, ilk_sayi=2)[-1]
        cuzleri_dagit(program, donem2, onceki_donem=donem1)
        a2 = donem2.cuz_atamalari.first()
        self.assertEqual(a2.cuz_baslangic, 15)
        self.assertEqual(a2.cuz_bitis, 16)


class HatimYetkiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("adm", "a@t.com", "x")
        self.personel_user = User.objects.create_user("pers", "p@t.com", "x")
        self.profil = PersonelProfili.objects.create(
            user=self.personel_user,
            ad_soyad="Personel",
            ana_rol="etut_mesul",
        )
        self.baska = User.objects.create_user("baska", "b@t.com", "x")
        program = HatimProgrami.objects.create(
            ad="Gizli",
            tur=HatimProgrami.Tur.PERSONEL,
            baslangic_tarihi=timezone.localdate(),
            son_tamamlama_saati=time(20, 0),
            durum=HatimProgrami.Durum.AKTIF,
            olusturan=self.admin,
        )
        program_baslat(program, [self.profil], olusturan=self.admin)

    def test_personel_sadece_kendi_atamasini_gorur(self):
        self.assertTrue(hatim_yonetebilir(self.admin))
        qs = kullanici_atamalari(self.personel_user)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(kullanici_atamalari(self.baska).count(), 0)

    def test_tamamlama_durumu(self):
        atama = kullanici_atamalari(self.personel_user).first()
        from takip.hatim_service import atama_tamamla

        atama_tamamla(atama, self.personel_user)
        atama.refresh_from_db()
        self.assertEqual(atama.durum, CuzAtamasi.Durum.TAMAMLANDI)
        self.assertIsNotNone(atama.tamamlama_zamani)
