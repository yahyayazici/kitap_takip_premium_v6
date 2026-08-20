"""Performans — /panel/ (dashboard) giriş noktasındaki gereksiz HTTP
redirect'in kaldırılması regresyon testleri.

Kapsam:
- Veli/talebe/öğretmen `/panel/`'e giderse artık 302 DEĞİL, doğrudan
  kendi paneli render ediliyor (bir ağ round-trip'i daha az).
- Tek çocuklu veli için `veli_dashboard`'ın kendi iç mantığı (talebe
  panosuna redirect) DOKUNULMADAN aynen çalışmaya devam ediyor.
- Çok çocuklu veli için hâlâ 200 (seçim ekranı) dönüyor.
- Personel/yönetim kullanıcısı için davranış hiç değişmedi (kendi
  dashboard'u render ediliyor, zaten redirect yoktu).
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import EtutHocasi, SinifSube, Talebe, TalebeHesap
from takip.veli_hesap_util import veli_panel_ensure

DASHBOARD_URL = reverse("dashboard")


class DashboardRedirectKaldirmaTests(TestCase):
    def _hoca(self, username):
        user = User.objects.create_user(username, password="x")
        return EtutHocasi.objects.create(ad_soyad="Test Hoca", user=user)

    def test_personel_dashboard_dogrudan_render_edilir(self):
        User.objects.create_superuser("idareci-redirect-test", "a@b.com", "Sifre!2026x")
        self.client.force_login(User.objects.get(username="idareci-redirect-test"))
        response = self.client.get(DASHBOARD_URL)
        self.assertEqual(response.status_code, 200)

    def test_talebe_panel_dogrudan_render_edilir_redirect_yok(self):
        sinif = SinifSube.objects.create(sinif="7", sube="D")
        hoca = self._hoca("hoca-talebe-redirect-test")
        hoca.sorumlu_sinif_subeler.add(sinif)
        talebe = Talebe.objects.create(
            ad_soyad="Talebe Redirect Test",
            sinif_sube=sinif,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
        )
        user = User.objects.create_user("talebe-redirect-test", password="x")
        TalebeHesap.objects.create(user=user, talebe=talebe, aktif=True)
        self.client.force_login(user)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "talebe/dashboard.html")

    def test_ogretmen_panel_dogrudan_render_edilir_redirect_yok(self):
        user = User.objects.create_user("hoca-redirect-test", password="x")
        self._hoca_user = EtutHocasi.objects.create(
            ad_soyad="Test Hoca Redirect", user=user, aktif=True
        )
        self.client.force_login(user)

        response = self.client.get(DASHBOARD_URL)

        # Ekstra RBAC rolü yok → ogretmen_not_girisi doğrudan render edilmeli.
        self.assertEqual(response.status_code, 200)

    def test_tek_cocuklu_veli_ic_redirect_mantigi_bozulmadi(self):
        """veli_dashboard'ın KENDİ içindeki tek-çocuk kısayolu (redirect)
        bu değişiklikten etkilenmemeli — hâlâ 302 ile talebe panosuna
        yönlendirmeli."""
        sinif = SinifSube.objects.create(sinif="8", sube="A")
        hoca = self._hoca("hoca-veli-tek-cocuk-test")
        hoca.sorumlu_sinif_subeler.add(sinif)
        talebe = Talebe.objects.create(
            ad_soyad="Tek Çocuk Test",
            sinif_sube=sinif,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
            tc_kimlik="11122233344",
        )
        sonuc = veli_panel_ensure(talebe, "11122233344", "Veli Redirect Test")
        self.assertTrue(sonuc.basarili and sonuc.olusturuldu)
        veli_user = User.objects.get(username="11122233344")
        self.client.force_login(veli_user)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("veli_talebe_dashboard", kwargs={"talebe_id": talebe.pk}),
        )

    def test_coklu_cocuklu_veli_secim_ekrani_dogrudan_render_edilir(self):
        sinif = SinifSube.objects.create(sinif="8", sube="B")
        hoca = self._hoca("hoca-veli-coklu-cocuk-test")
        hoca.sorumlu_sinif_subeler.add(sinif)

        talebe1 = Talebe.objects.create(
            ad_soyad="Çocuk Bir",
            sinif_sube=sinif,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
            tc_kimlik="22233344455",
        )
        talebe2 = Talebe.objects.create(
            ad_soyad="Çocuk İki",
            sinif_sube=sinif,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
            tc_kimlik="33344455566",
        )
        sonuc1 = veli_panel_ensure(talebe1, "22233344455", "Veli Çoklu Test")
        self.assertTrue(sonuc1.basarili and sonuc1.olusturuldu)
        veli_user = User.objects.get(username="22233344455")

        # veli_panel_ensure tek-çocuklu bağlama için tasarlanmış; ikinci
        # çocuğu aynı veliye bağlamak için (yönetim panelindeki
        # VeliHesapForm'un yaptığı gibi) doğrudan bağlantı kaydı ekliyoruz.
        from takip.wave0_models import VeliKisi, VeliTalebeBaglantisi

        veli_hesap = veli_user.veli_hesabi
        VeliTalebeBaglantisi.objects.get_or_create(
            veli=veli_hesap,
            talebe=talebe2,
            defaults={"yakinlik": VeliKisi.Yakinlik.VELI},
        )

        self.client.force_login(veli_user)
        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "veli/dashboard.html")
