"""Deneme Kontrol, branş öğretmeninde değil; sorumlu sınıfı olan etüt hocasındadır."""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.deneme_kontrol_service import kazanim_ortalamalari, kazanimlari_derse_gore
from takip.deneme_models import DenemeKazanimSonucu, DenemeSinavi, DenemeSonucu
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


def _deneme(ad, gun, *, durum=DenemeSinavi.Durum.AKTIF):
    return DenemeSinavi.objects.create(
        ad=ad,
        sinav_tarihi=date(2026, 3, gun),
        sinif_seviyesi="8",
        durum=durum,
        tur=DenemeSinavi.Tur.GRUP,
    )


def _kazanim(deneme, talebe, ders, konu, yuzde):
    return DenemeKazanimSonucu.objects.create(
        deneme=deneme,
        talebe=talebe,
        ders_ad=ders,
        konu_ad=konu,
        ders_key=ders.lower(),
        konu_key=konu.lower().replace(" ", "-"),
        yuzde=Decimal(yuzde),
    )


class DenemeKontrolKazanimTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("etut-kazanim", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Etüt Kazanım", user=self.user, aktif=True)
        PersonelProfili.objects.create(
            user=self.user,
            ad_soyad="Etüt Kazanım",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=self.hoca,
        )
        self.sinif = SinifSube.objects.create(sinif="8", sube="K")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.ali = Talebe.objects.create(
            ad_soyad="Ali Yukselen",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.ayse = Talebe.objects.create(
            ad_soyad="Ayse Azartan",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.can = Talebe.objects.create(
            ad_soyad="Can Tekdeneme",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.ilk = _deneme("1. Deneme", 1)
        self.son = _deneme("2. Deneme", 20)
        DenemeSonucu.objects.create(deneme=self.ilk, talebe=self.ali, puan=Decimal("300"))
        DenemeSonucu.objects.create(deneme=self.son, talebe=self.ali, puan=Decimal("360"))
        DenemeSonucu.objects.create(deneme=self.ilk, talebe=self.ayse, puan=Decimal("400"))
        DenemeSonucu.objects.create(deneme=self.son, talebe=self.ayse, puan=Decimal("410"))
        DenemeSonucu.objects.create(deneme=self.son, talebe=self.can, puan=Decimal("250"))

        _kazanim(self.ilk, self.ali, "Türkçe", "Sözcükte Anlam", "70")
        _kazanim(self.ilk, self.ayse, "Türkçe", "Sözcükte Anlam", "50")
        _kazanim(self.ilk, self.ali, "Matematik", "Tam Sayılar", "40")
        _kazanim(self.ilk, self.ali, "Fen", "Uzay", "60")
        _kazanim(self.son, self.ali, "Fen", "Uzay", "80")
        _kazanim(self.son, self.ali, "Türkçe", "Paragraf", "90")

        arsiv = _deneme("Eski", 2, durum=DenemeSinavi.Durum.ARSIV)
        _kazanim(arsiv, self.ayse, "Fen", "Kuvvet", "55")
        _kazanim(arsiv, self.ali, "Fen", "Uzay", "10")
        taslak = _deneme("Taslak", 3, durum=DenemeSinavi.Durum.TASLAK)
        _kazanim(taslak, self.ali, "Fen", "Gizli Konu", "99")

        self.client.force_login(self.user)

    def test_yukselis_sirasi_ve_biriken_kazanimlar(self):
        sayfa = self.client.get(
            reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[self.sinif.id])
        )
        self.assertEqual(sayfa.status_code, 200)
        html = sayfa.content.decode()
        self.assertIn("Yükseliş sıralaması", html)
        self.assertLess(html.index("Ali Yukselen"), html.index("Ayse Azartan"))
        self.assertLess(html.index("Ayse Azartan"), html.index("Can Tekdeneme"))
        self.assertLess(html.index("Sözcükte Anlam"), html.index("Tam Sayılar"))
        self.assertLess(html.index("Tam Sayılar"), html.index("Uzay"))
        self.assertLess(html.index("Sözcükte Anlam"), html.index("Paragraf"))
        self.assertLess(html.index("Paragraf"), html.index("Tam Sayılar"))
        self.assertNotIn("Kuvvet", html)
        self.assertNotIn("Gizli Konu", html)
        self.assertIn("%70", html)
        self.assertNotIn("grup denemesi sonucu bulunmuyor", html)

    def test_sinif_ortalamasi_deneme_deneme(self):
        ozet = {o["konu_ad"]: o for o in kazanim_ortalamalari([self.ali.id, self.ayse.id, self.can.id])}
        self.assertEqual(ozet["Uzay"]["ortalama"], Decimal("70.00"))
        self.assertEqual(ozet["Uzay"]["deneme_sayisi"], 2)
        self.assertEqual(ozet["Uzay"]["son_yuzde"], Decimal("80.00"))
        self.assertEqual(ozet["Sözcükte Anlam"]["ortalama"], Decimal("60.00"))
        self.assertEqual(ozet["Sözcükte Anlam"]["deneme_sayisi"], 1)
        self.assertNotIn("Kuvvet", ozet)
        self.assertNotIn("Gizli Konu", ozet)
        gruplar = kazanimlari_derse_gore(list(ozet.values()))
        self.assertEqual([g["ders_ad"] for g in gruplar], ["Türkçe", "Matematik", "Fen"])
        self.assertEqual(
            [k["konu_ad"] for k in gruplar[0]["konular"]],
            ["Sözcükte Anlam", "Paragraf"],
        )

    def test_talebe_kazanimi_yalniz_kendini_ortalar(self):
        ali = self.client.get(
            reverse(
                "ogretmen_deneme_kontrol_ogrenci_detay",
                args=[self.sinif.id, self.ali.id],
            )
        )
        self.assertEqual(ali.status_code, 200)
        ali_html = ali.content.decode()
        self.assertIn("%70", ali_html)
        self.assertIn("Paragraf", ali_html)
        self.assertNotIn("Kuvvet", ali_html)

        ayse = self.client.get(
            reverse(
                "ogretmen_deneme_kontrol_ogrenci_detay",
                args=[self.sinif.id, self.ayse.id],
            )
        )
        ayse_html = ayse.content.decode()
        self.assertIn("%50", ayse_html)
        self.assertNotIn("Kuvvet", ayse_html)
        self.assertNotIn("Paragraf", ayse_html)
        self.assertNotIn("Uzay", ayse_html)
