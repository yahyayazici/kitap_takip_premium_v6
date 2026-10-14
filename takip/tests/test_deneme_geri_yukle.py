import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import DenemeSinavi, DenemeSonucu, EtutHocasi, SinifSube, Talebe


class DenemeGeriYukleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("geri-admin", "a@b.com", "x")
        hoca = EtutHocasi.objects.create(ad_soyad="Hoca", user=self.user)
        sinif = SinifSube.objects.create(sinif="7", sube="A")
        hoca.sorumlu_sinif_subeler.add(sinif)
        talebe = Talebe.objects.create(ad_soyad="Ali Veli", sinif_sube=sinif, etut_hocasi=hoca)
        self.deneme = DenemeSinavi.objects.create(
            ad="Kurumsal Deneme-1", sinav_tarihi=datetime.date(2026, 10, 1), sinif_seviyesi="7", durum="aktif"
        )
        DenemeSonucu.objects.create(deneme=self.deneme, talebe=talebe, toplam_net=50, puan=400)
        self.client.force_login(self.user)

    def test_sil_arsivde_gor_geri_yukle(self):
        self.client.post(reverse("yonetim:deneme_sil", args=[self.deneme.pk]))
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.durum, DenemeSinavi.Durum.ARSIV)
        self.assertNotContains(self.client.get(reverse("yonetim:deneme_listesi")), "<strong>Kurumsal Deneme-1</strong>")
        arsiv = self.client.get(reverse("yonetim:deneme_listesi") + "?arsiv=1")
        self.assertContains(arsiv, "<strong>Kurumsal Deneme-1</strong>")
        self.assertContains(arsiv, "Geri yükle")

        self.client.post(reverse("yonetim:deneme_geri_yukle", args=[self.deneme.pk]))
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.durum, DenemeSinavi.Durum.AKTIF)
        self.assertEqual(self.deneme.sonuclar.count(), 1)
        self.assertContains(self.client.get(reverse("yonetim:deneme_listesi")), "<strong>Kurumsal Deneme-1</strong>")

    def test_sonucsuz_deneme_taslak_doner(self):
        bos = DenemeSinavi.objects.create(
            ad="Boş", sinav_tarihi=datetime.date(2026, 10, 2), sinif_seviyesi="7", durum="arsiv"
        )
        self.client.post(reverse("yonetim:deneme_geri_yukle", args=[bos.pk]))
        bos.refresh_from_db()
        self.assertEqual(bos.durum, DenemeSinavi.Durum.TASLAK)
