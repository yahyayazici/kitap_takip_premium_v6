"""Deneme Kontrol, branş öğretmeninde değil; sorumlu sınıfı olan etüt hocasındadır."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import EtutHocasi, PersonelProfili, SinifSube, Talebe


class DenemeKontrolEtutTests(TestCase):
    def _etut(self, username, *, rol=PersonelProfili.Rol.ETUT_MESUL, sinif=True):
        user = User.objects.create_user(username, password="x")
        hoca = EtutHocasi.objects.create(ad_soyad=username, user=user, aktif=True)
        PersonelProfili.objects.create(
            user=user,
            ad_soyad=username,
            ana_rol=rol,
            etut_hocasi=hoca,
        )
        if sinif:
            grup = SinifSube.objects.create(sinif="8", sube=username[:1].upper())
            hoca.sorumlu_sinif_subeler.add(grup)
        return user, hoca

    def test_sorumlu_etut_hocasi_deneme_kontrolu_gorur(self):
        user, hoca = self._etut("etut-deneme")
        sinif = hoca.sorumlu_sinif_subeler.get()
        Talebe.objects.create(
            ad_soyad="Deneme Talebe",
            sinif_sube=sinif,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
        )
        self.client.force_login(user)

        panel = self.client.get(reverse("dashboard"))
        self.assertContains(panel, "Deneme Kontrol")

        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi"))
        self.assertEqual(sayfa.status_code, 200)
        self.assertContains(sayfa, "Deneme Kontrol Merkezi")
        self.assertContains(sayfa, f"{sinif.sinif}-{sinif.sube}")

    def test_sinifsiz_etut_hocasi_menude_gormez(self):
        user, _hoca = self._etut("etut-sinifsiz", sinif=False)
        self.client.force_login(user)

        panel = self.client.get(reverse("dashboard"))
        self.assertNotContains(panel, "Deneme Kontrol")

        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi"))
        self.assertRedirects(sayfa, reverse("dashboard"))

    def test_brans_ogretmeninde_yok(self):
        user = User.objects.create_user("brans-deneme", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Branş", user=user, aktif=True)
        hoca.sorumlu_sinif_subeler.add(SinifSube.objects.create(sinif="6", sube="C"))
        self.client.force_login(user)

        panel = self.client.get(reverse("ogretmen_dashboard"))
        self.assertNotContains(panel, "Deneme Kontrol")

        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi"))
        self.assertRedirects(sayfa, reverse("ogretmen_dashboard"))

    def test_baska_sinifin_talebesine_giremez(self):
        user, hoca = self._etut("etut-kendi")
        kendi = hoca.sorumlu_sinif_subeler.get()
        baska = SinifSube.objects.create(sinif="9", sube="Z")
        diger_user = User.objects.create_user("diger-etut", password="x")
        diger = EtutHocasi.objects.create(ad_soyad="Diğer", user=diger_user, aktif=True)
        diger.sorumlu_sinif_subeler.add(baska)
        talebe = Talebe.objects.create(
            ad_soyad="Başka Talebe",
            sinif_sube=baska,
            etut_hocasi=diger,
            dini_ders_hocasi=diger,
        )
        self.client.force_login(user)

        detay = self.client.get(
            reverse(
                "ogretmen_deneme_kontrol_ogrenci_detay",
                args=[baska.id, talebe.id],
            )
        )
        self.assertRedirects(detay, reverse("ogretmen_deneme_kontrol_merkezi"))

        kendi_sayfa = self.client.get(
            reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[kendi.id])
        )
        self.assertEqual(kendi_sayfa.status_code, 200)
        self.assertContains(kendi_sayfa, f"{kendi.sinif}-{kendi.sube}")
        self.assertNotContains(kendi_sayfa, "9-Z")
