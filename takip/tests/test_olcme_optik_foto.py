"""Ölçme Merkezi — optik foto kayıt testi."""

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from takip.konu_destek_models import KonuKatalogu
from takip.models import Ders, EtutHocasi, KttSinav, KttSonucu, Talebe
from takip.olcme_models import OlcumCevapAnahtari
from takip.olcme_service import sorulari_olustur


class OlcumOptikFotoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("olcme_foto", password="test")
        self.client = Client()
        self.client.login(username="olcme_foto", password="test")
        self.ders = Ders.objects.create(ad="Matematik", sira=1, aktif=True)
        self.hoca = EtutHocasi.objects.create(user=self.user, ad_soyad="Hoca", aktif=True)
        self.konu = KonuKatalogu.objects.create(
            sinif_seviyesi="7",
            brans="matematik",
            konu_ad="Kesirler",
        )
        self.sinav = KttSinav.objects.create(
            ad="Foto Test",
            ders=self.ders,
            sinif_seviyesi="7",
            hedef_siniflar="7-A",
            sinav_tarihi="2026-08-14",
            soru_sayisi=3,
            etut_hocasi=self.hoca,
            olusturan=self.user,
        )
        self.talebe = Talebe.objects.create(
            ad_soyad="Ali Veli",
            sinif="7-A",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            aktif=True,
        )
        sorulari_olustur(self.sinav, varsayilan_ders=self.ders)
        for soru in self.sinav.olcme_sorulari.all():
            OlcumCevapAnahtari.objects.update_or_create(
                soru=soru,
                kitapcik="A",
                defaults={"dogru_secenek": "A"},
            )

    def test_optik_foto_sayfa(self):
        url = reverse("olcme_optik_foto", kwargs={"pk": self.sinav.pk})
        resp = self.client.get(f"{url}?talebe={self.talebe.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "OPTİK TARA")

    def test_optik_foto_kaydet(self):
        url = reverse("olcme_optik_foto", kwargs={"pk": self.sinav.pk})
        resp = self.client.post(
            url,
            {
                "talebe_id": self.talebe.pk,
                "kitapcik": "A",
                "s_1": "A",
                "s_2": "B",
                "s_3": "A",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            KttSonucu.objects.filter(ktt=self.sinav, talebe=self.talebe).exists()
        )

    def test_karekod_metin_yonlendirme(self):
        url = reverse("olcme_optik_foto", kwargs={"pk": self.sinav.pk})
        k = f"OLCME;S{self.sinav.pk};T{self.talebe.pk};N1;KA"
        resp = self.client.get(url, {"k": k})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"talebe={self.talebe.pk}", resp.url)
