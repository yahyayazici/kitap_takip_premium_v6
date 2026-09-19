"""Öğretmen Ödeme — etüt mesulü ekranında arşiv gösterilmemesi ve tek tıkla tablo.

İstek: yönetici aktif ödeme dönemini değiştirdiğinde bu, etüt mesulünün
ekranına yansımalı; mesul ekranında geçmiş (kapanmış) dönemler görünmemeli,
yalnızca o an açık olan aktif pencereyle eşleşen dönem gösterilmeli. Tam
yetkili roller (idareci/ic_mesul/egitim_mesul/muhasebeci) için mevcut
arşiv davranışı DEĞİŞMEMELİ — onlar geçmişi de görmeye devam eder.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import EtutHocasi, PersonelProfili, SinifSube
from takip.ogretmen_odeme_models import OgretmenOdemeAktifDonem, OgretmenOdemeDonemi
from takip.ogretmen_odeme_service import yetkili_odeme_donemleri_liste_icin


class MesulArsivGizlemeTestleri(TestCase):
    def setUp(self):
        self.sinif = SinifSube.objects.create(sinif="7", sube="A", aktif=True)

        # Etüt mesulü — kendi EtutHocasi kaydı üzerinden sınıf kapsamı belirlenir.
        self.mesul_user = User.objects.create_user("mesul", password="test-12345")
        PersonelProfili.objects.create(
            user=self.mesul_user, ad_soyad="Etüt Mesulü", ana_rol=PersonelProfili.Rol.ETUT_MESUL
        )
        self.mesul_hoca = EtutHocasi.objects.create(user=self.mesul_user, ad_soyad="Etüt Mesulü", aktif=True)
        self.mesul_hoca.sorumlu_sinif_subeler.add(self.sinif)

        # Ücret alan branş öğretmeni — ayrı bir kullanıcı + EtutHocasi kaydı.
        # personel_kaydi hiçbir PersonelProfili'den işaret edilmediği için
        # boş kalır; aktif_ogretmenler() bu şekilde branş öğretmenini
        # mesul/idareci personel kayıtlarından ayırt eder.
        self.ogretmen_user = User.objects.create_user("ahmet_ogretmen", password="test-12345")
        self.ogretmen = EtutHocasi.objects.create(
            user=self.ogretmen_user, ad_soyad="Ahmet Yılmaz", aktif=True
        )
        self.ogretmen.sorumlu_sinif_subeler.add(self.sinif)

        # Tam yetkili idareci.
        self.idareci_user = User.objects.create_user("idareci", password="test-12345")
        PersonelProfili.objects.create(
            user=self.idareci_user, ad_soyad="İdareci", ana_rol=PersonelProfili.Rol.IDARECI
        )

        # Aktif pencere: yönetici tarafından açılmış güncel dönem.
        self.aktif_pencere = OgretmenOdemeAktifDonem.objects.create(
            baslangic=date(2026, 9, 14), bitis=date(2026, 10, 12)
        )

        # Aktif pencereyle BİREBİR eşleşen güncel dönem kaydı.
        self.guncel_donem = OgretmenOdemeDonemi.objects.create(
            etut_hocasi=self.ogretmen,
            baslangic=self.aktif_pencere.baslangic,
            bitis=self.aktif_pencere.bitis,
            saatlik_ucret=Decimal("100.00"),
        )

        # Kapanmış (arşiv) dönem — farklı ve daha eski tarih aralığı.
        self.eski_donem = OgretmenOdemeDonemi.objects.create(
            etut_hocasi=self.ogretmen,
            baslangic=date(2026, 8, 1),
            bitis=date(2026, 8, 29),
            saatlik_ucret=Decimal("100.00"),
        )

    # —— Servis katmanı ——

    def test_mesul_yalnizca_aktif_pencereyi_gorur(self):
        gorunen = list(yetkili_odeme_donemleri_liste_icin(self.mesul_user))
        self.assertEqual(gorunen, [self.guncel_donem])
        self.assertNotIn(self.eski_donem, gorunen)

    def test_idareci_arsivi_de_gorur(self):
        """Tam yetkili rol için mevcut davranış bozulmamalı."""
        gorunen = set(yetkili_odeme_donemleri_liste_icin(self.idareci_user))
        self.assertEqual(gorunen, {self.guncel_donem, self.eski_donem})

    def test_aktif_pencere_kapaninca_mesul_bos_gorur(self):
        """Aktif pencere silinirse (yeni dönem henüz açılmadıysa) mesul hiçbir
        şey görmemeli — eski, artık aktif olmayan dönemi ASLA göstermemeli."""
        self.aktif_pencere.delete()
        gorunen = list(yetkili_odeme_donemleri_liste_icin(self.mesul_user))
        self.assertEqual(gorunen, [])

    def test_pencere_yeni_tarihe_tasinca_eski_donem_mesulden_dusuyor(self):
        """Yönetici pencereyi yeni bir tarih aralığına taşıdığında (yeni dönem
        açtığında), önceki dönem veritabanından silinmez ama mesul ekranından
        kalkar — tam da 'arşiv görünmesin' isteği budur."""
        self.aktif_pencere.baslangic = date(2026, 10, 13)
        self.aktif_pencere.bitis = date(2026, 11, 10)
        self.aktif_pencere.save()

        gorunen = list(yetkili_odeme_donemleri_liste_icin(self.mesul_user))
        self.assertEqual(gorunen, [])
        # Kayıt hâlâ veritabanında duruyor, yalnızca mesul ekranında görünmüyor.
        self.assertTrue(OgretmenOdemeDonemi.objects.filter(pk=self.guncel_donem.pk).exists())

    # —— Görünüm katmanı ——

    def test_liste_sayfasi_mesule_arsivi_gostermez(self):
        self.client.force_login(self.mesul_user)
        yanit = self.client.get(reverse("ogretmen_odeme_listesi"))
        self.assertEqual(yanit.status_code, 200)

        govde = yanit.content.decode()
        self.assertIn("14.09.2026", govde)  # güncel dönem görünüyor
        self.assertNotIn("01.08.2026", govde)  # eski dönem görünmüyor

    def test_liste_sayfasi_idareciye_arsivi_gosterir(self):
        self.client.force_login(self.idareci_user)
        yanit = self.client.get(reverse("ogretmen_odeme_listesi"))
        govde = yanit.content.decode()
        self.assertIn("14.09.2026", govde)
        self.assertIn("01.08.2026", govde)

    def test_aktif_pencere_yaziyi_mesul_ekraninda_da_gorunur(self):
        """İstek: admin'in başlattığı aktif dönem mesulün ekranına da yansısın."""
        self.client.force_login(self.mesul_user)
        govde = self.client.get(reverse("ogretmen_odeme_listesi")).content.decode()
        self.assertIn("Aktif dönem:", govde)
        self.assertIn("14.09.2026", govde)
        # Mesul pencereyi DÜZENLEYEMEMELİ — yalnız görsün.
        self.assertNotIn("Pencereyi Güncelle", govde)

    def test_ogretmen_secince_tek_adimda_tabloya_gidiyor(self):
        """Öğretmen seçilip form gönderilince doğrudan ders saati tablosuna
        (detay sayfasına) düşülmeli — ara bir onay adımı olmamalı."""
        self.client.force_login(self.mesul_user)
        yanit = self.client.post(
            reverse("ogretmen_odeme_listesi"),
            {"islem": "olustur", "etut_hocasi": self.ogretmen.pk},
        )
        self.assertEqual(yanit.status_code, 302)
        donem = OgretmenOdemeDonemi.objects.get(
            etut_hocasi=self.ogretmen,
            baslangic=self.aktif_pencere.baslangic,
            bitis=self.aktif_pencere.bitis,
        )
        self.assertEqual(yanit.url, reverse("ogretmen_odeme_detay", args=[donem.pk]))

    def test_ogretmen_secim_kutusu_otomatik_gonderim_scripti_iceriyor(self):
        """Seçince ekstra bir 'Tabloyu Aç' tıklaması beklenmeden form
        gönderilsin — select değişince otomatik submit eden script olmalı."""
        self.client.force_login(self.mesul_user)
        govde = self.client.get(reverse("ogretmen_odeme_listesi")).content.decode()
        self.assertIn('id="oo-ogretmen-sec-form"', govde)
        self.assertIn("addEventListener(\"change\"", govde)
        self.assertIn("form.submit()", govde)
