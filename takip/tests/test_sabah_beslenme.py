from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import EtutHocasi, PersonelProfili, SinifSube, Talebe
from takip.sabah_beslenme_models import SabahBeslenmeGunlukMenu, SabahBeslenmeSiparis
from takip.sabah_beslenme_service import (
    SabahBeslenmeHata,
    borc_kapat,
    etut_siparis_gruplari,
    gun_ozeti,
    menu_kaydet,
    odeme_turu_ayarla,
    siparis_kaydet,
    teslim_et,
    teslim_geri_al,
)


class SabahBeslenmeTests(TestCase):
    def setUp(self):
        self.tarih = date(2026, 9, 15)
        self.admin = User.objects.create_superuser("sbadmin", "sb@example.com", "x")
        self.etut_user = User.objects.create_user("sbetut", password="x")
        self.etut_user2 = User.objects.create_user("sbetut2", password="x")
        self.satis_user = User.objects.create_user("sbsatis", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Etüt Hoca", user=self.etut_user)
        self.hoca2 = EtutHocasi.objects.create(ad_soyad="Diğer Hoca", user=self.etut_user2)
        PersonelProfili.objects.create(
            user=self.etut_user,
            ad_soyad="Etüt Hoca",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=self.hoca,
        )
        PersonelProfili.objects.create(
            user=self.etut_user2,
            ad_soyad="Diğer Hoca",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=self.hoca2,
        )
        PersonelProfili.objects.create(
            user=self.satis_user,
            ad_soyad="Satış",
            ana_rol=PersonelProfili.Rol.NEHARI_MESUL,
        )
        self.sinif = SinifSube.objects.create(sinif="5", sube="A")
        self.sinif_b = SinifSube.objects.create(sinif="5", sube="B")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.hoca2.sorumlu_sinif_subeler.add(self.sinif_b)
        self.talebe = Talebe.objects.create(
            ad_soyad="Ahmet Yıldız",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.diger = Talebe.objects.create(
            ad_soyad="Mehmet Kaya",
            sinif_sube=self.sinif_b,
            etut_hocasi=self.hoca2,
            dini_ders_hocasi=self.hoca2,
        )
        self.menu = menu_kaydet(
            self.admin,
            tarih=self.tarih,
            urun="Simit",
            birim_fiyat=Decimal("12.50"),
            siparis_son_saati=time(23, 59),
            durum=SabahBeslenmeGunlukMenu.Durum.ACIK,
        )

    def test_etut_tum_talebelere_siparis_girer(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=2
        )
        self.assertEqual(siparis.adet, 2)
        self.assertEqual(siparis.tutar, Decimal("25.00"))
        diger = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.diger.pk, adet=1
        )
        self.assertEqual(diger.adet, 1)

    def test_siparis_listesi_namaz_gibi_tum_talebeleri_gosterir(self):
        gruplar = etut_siparis_gruplari(self.etut_user, self.menu)
        ids = {s["talebe"].pk for g in gruplar for s in g["satirlar"]}
        self.assertEqual(ids, {self.talebe.pk, self.diger.pk})
        etudum = etut_siparis_gruplari(self.etut_user, self.menu, etudum=True)
        etudum_ids = {s["talebe"].pk for g in etudum for s in g["satirlar"]}
        self.assertEqual(etudum_ids, {self.talebe.pk})

    def test_etut_teslim_edemez(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=1
        )
        with self.assertRaises(SabahBeslenmeHata):
            teslim_et(self.etut_user, siparis.pk)

    def test_pesin_teslim_borc_olusturmaz(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=1
        )
        teslim_et(self.satis_user, siparis.pk)
        siparis.refresh_from_db()
        self.assertTrue(siparis.teslim_edildi)
        self.assertFalse(siparis.borc_kaydi_olustu)
        self.assertEqual(siparis.teslim_eden, self.satis_user)
        self.assertIsNotNone(siparis.teslim_saati)

    def test_borc_teslim_tek_kayit_ve_mukerrer_engel(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=2
        )
        odeme_turu_ayarla(self.satis_user, siparis.pk, "borc")
        bir = teslim_et(self.satis_user, siparis.pk)
        iki = teslim_et(self.satis_user, siparis.pk)
        self.assertEqual(bir.pk, iki.pk)
        siparis.refresh_from_db()
        self.assertTrue(siparis.borc_kaydi_olustu)
        self.assertTrue(siparis.borc_acik)
        self.assertEqual(siparis.borc_tutari, Decimal("25.00"))
        self.assertEqual(
            SabahBeslenmeSiparis.objects.filter(
                menu=self.menu, talebe=self.talebe, borc_kaydi_olustu=True
            ).count(),
            1,
        )

    def test_teslim_edilmeyen_borc_yazilmaz(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=1
        )
        odeme_turu_ayarla(self.satis_user, siparis.pk, "borc")
        siparis.refresh_from_db()
        self.assertFalse(siparis.teslim_edildi)
        self.assertFalse(siparis.borc_kaydi_olustu)

    def test_sifir_adet_satis_olmaz(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=0
        )
        with self.assertRaises(SabahBeslenmeHata):
            teslim_et(self.satis_user, siparis.pk)

    def test_teslim_geri_al_borcu_siler(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=1
        )
        odeme_turu_ayarla(self.satis_user, siparis.pk, "borc")
        teslim_et(self.satis_user, siparis.pk)
        teslim_geri_al(self.satis_user, siparis.pk)
        siparis.refresh_from_db()
        self.assertFalse(siparis.teslim_edildi)
        self.assertFalse(siparis.borc_kaydi_olustu)

    def test_kapatilmis_borc_geri_alinamaz(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=1
        )
        odeme_turu_ayarla(self.satis_user, siparis.pk, "borc")
        teslim_et(self.satis_user, siparis.pk)
        borc_kapat(self.admin, siparis.pk)
        with self.assertRaises(SabahBeslenmeHata):
            teslim_geri_al(self.satis_user, siparis.pk)

    def test_gun_ozeti_canli_rakamlar(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=2
        )
        ozet = gun_ozeti(self.menu)
        self.assertEqual(ozet["toplam_siparis_adedi"], 2)
        self.assertEqual(ozet["bekleyen"], 1)
        teslim_et(self.satis_user, siparis.pk)
        ozet = gun_ozeti(self.menu)
        self.assertEqual(ozet["satisi_yapilan"], 1)
        self.assertEqual(ozet["pesin_tahsil"], "25.00")

    def test_menu_benzersiz_tarih(self):
        menu_kaydet(
            self.admin,
            tarih=self.tarih,
            urun="Poğaça",
            birim_fiyat=Decimal("15.00"),
            siparis_son_saati=time(7, 30),
            durum=SabahBeslenmeGunlukMenu.Durum.ACIK,
        )
        self.assertEqual(SabahBeslenmeGunlukMenu.objects.filter(tarih=self.tarih).count(), 1)
        self.menu.refresh_from_db()
        self.assertEqual(self.menu.urun, "Poğaça")

    def test_siparis_penceresi_kapali_etut_teslime_kadar_girebilir(self):
        self.menu.durum = SabahBeslenmeGunlukMenu.Durum.KAPALI
        self.menu.save(update_fields=["durum"])
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=1
        )
        self.assertEqual(siparis.adet, 1)

    def test_satis_ajax_idempotent(self):
        siparis = siparis_kaydet(
            self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=1
        )
        self.client.force_login(self.satis_user)
        url = reverse("sabah_beslenme_api_teslim", args=[siparis.pk])
        r1 = self.client.post(url, data="{}", content_type="application/json")
        r2 = self.client.post(url, data="{}", content_type="application/json")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(
            SabahBeslenmeSiparis.objects.filter(pk=siparis.pk, teslim_edildi=True).count(),
            1,
        )

    def test_satis_ekrani_satir_ve_ozet(self):
        siparis_kaydet(self.etut_user, menu=self.menu, talebe_id=self.talebe.pk, adet=1)
        self.client.force_login(self.satis_user)
        res = self.client.get(reverse("sabah_beslenme_satis") + f"?tarih={self.tarih.isoformat()}")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ahmet Yıldız")
        self.assertContains(res, "data-tick")
        self.assertContains(res, "Peşin")

    def test_etut_landing_siparise_gider(self):
        self.client.force_login(self.etut_user)
        res = self.client.get(reverse("sabah_beslenme_landing"), follow=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/siparis/", res["Location"])

    def test_etut_api_baska_talebe_kaydeder(self):
        self.client.force_login(self.etut_user)
        url = reverse("sabah_beslenme_api_siparis")
        res = self.client.post(
            url,
            data={"tarih": self.tarih.isoformat(), "talebe_id": self.diger.pk, "adet": 1},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])
        self.assertEqual(
            SabahBeslenmeSiparis.objects.get(menu=self.menu, talebe=self.diger).adet, 1
        )

    def test_siparis_ekrani_tum_talebeleri_listeler(self):
        self.client.force_login(self.etut_user)
        res = self.client.get(
            reverse("sabah_beslenme_siparis") + f"?tarih={self.tarih.isoformat()}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ahmet Yıldız")
        self.assertContains(res, "Mehmet Kaya")
        self.assertContains(res, "Tümü")
        self.assertContains(res, "Etüdüm")
