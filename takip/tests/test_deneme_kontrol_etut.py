"""Deneme Kontrol, branş öğretmeninde değil; sorumlu sınıfı olan etüt hocasındadır."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.deneme_kontrol_service import (
    _oncelik_metinleri,
    kazanim_ortalamalari,
    kazanimlari_derse_gore,
)
from takip.deneme_models import DenemeKazanimSonucu, DenemeSinavi, DenemeSonucu
from takip.models import DenemeBransSonucu, EtutHocasi, PersonelProfili, SinifSube, Talebe


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
        self.assertContains(panel, ">Deneme</a>")
        self.assertNotContains(panel, ">Deneme Kontrol</a>")
        self.assertNotContains(panel, ">Etüt Takip</a>")
        self.assertContains(panel, reverse("ogretmen_deneme_kontrol_merkezi"))

        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi"))
        self.assertEqual(sayfa.status_code, 200)
        self.assertContains(sayfa, "Deneme Kontrol")
        self.assertContains(sayfa, "Etüt Kontrol")
        self.assertContains(sayfa, "Denemeler")
        self.assertContains(sayfa, f"{sinif.sinif}-{sinif.sube}")

    def test_sinifsiz_etut_hocasi_menude_gormez(self):
        user, _hoca = self._etut("etut-sinifsiz", sinif=False)
        self.client.force_login(user)

        panel = self.client.get(reverse("dashboard"))
        self.assertNotContains(panel, "Deneme Kontrol")

        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi"))
        self.assertRedirects(sayfa, reverse("dashboard"))

    def test_egitim_mesulu_deneme_kontrol_sekmesini_gorur(self):
        user, hoca = self._etut(
            "egitim-deneme",
            rol=PersonelProfili.Rol.EGITIM_MESUL,
        )
        sinif = hoca.sorumlu_sinif_subeler.get()
        self.client.force_login(user)

        liste = self.client.get(reverse("deneme_listesi"))
        self.assertEqual(liste.status_code, 200)
        self.assertContains(liste, "Deneme Kontrol")
        self.assertContains(liste, "Etüt Kontrol")
        self.assertContains(liste, "Denemeler")

        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi"))
        self.assertEqual(sayfa.status_code, 200)
        self.assertContains(sayfa, f"{sinif.sinif}-{sinif.sube}")

    def test_personelsiz_demo_hocasi_kendi_sinifini_gorur(self):
        user = User.objects.create_superuser("demo-deneme", "demo@example.com", "x")
        hoca = EtutHocasi.objects.create(ad_soyad="Demo", user=user, aktif=True)
        sinif = SinifSube.objects.create(sinif="8", sube="A")
        hoca.sorumlu_sinif_subeler.add(sinif)
        self.client.force_login(user)

        liste = self.client.get(reverse("deneme_listesi"))
        self.assertContains(liste, "Deneme Kontrol")
        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi"))
        self.assertEqual(sayfa.status_code, 200)
        self.assertContains(sayfa, "8-A")

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
        self.assertNotIn("Sözcükte Anlam", html)
        self.assertNotIn("grup denemesi sonucu bulunmuyor", html)

        kazanim = self.client.get(
            reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[self.sinif.id])
            + "?ekran=kazanim"
        )
        self.assertEqual(kazanim.status_code, 200)
        khtml = kazanim.content.decode()
        self.assertIn("Kazanımlar", khtml)
        self.assertNotIn("Yükseliş sıralaması", khtml)
        self.assertNotIn("Nokta atışı", khtml)
        self.assertLess(khtml.index("Sözcükte Anlam"), khtml.index("Tam Sayılar"))
        self.assertLess(khtml.index("Tam Sayılar"), khtml.index("Uzay"))
        self.assertLess(khtml.index("Sözcükte Anlam"), khtml.index("Paragraf"))
        self.assertLess(khtml.index("Paragraf"), khtml.index("Tam Sayılar"))
        self.assertNotIn("Kuvvet", khtml)
        self.assertNotIn("Gizli Konu", khtml)
        self.assertIn("%70", khtml)

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


class DenemeKontrolTumuTests(TestCase):
    def test_tumu_ayni_seviyeyi_tek_ozette_toplar(self):
        user = User.objects.create_user("etut-tumu", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Etüt Tümü", user=user, aktif=True)
        PersonelProfili.objects.create(
            user=user,
            ad_soyad="Etüt Tümü",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=hoca,
        )
        sinif_a = SinifSube.objects.create(sinif="5", sube="A")
        sinif_b = SinifSube.objects.create(sinif="5", sube="B")
        hoca.sorumlu_sinif_subeler.add(sinif_a, sinif_b)
        ali = Talebe.objects.create(
            ad_soyad="Ali Besa", sinif_sube=sinif_a, etut_hocasi=hoca, dini_ders_hocasi=hoca
        )
        veli = Talebe.objects.create(
            ad_soyad="Veli Besa", sinif_sube=sinif_a, etut_hocasi=hoca, dini_ders_hocasi=hoca
        )
        ayse = Talebe.objects.create(
            ad_soyad="Ayse Besbe", sinif_sube=sinif_b, etut_hocasi=hoca, dini_ders_hocasi=hoca
        )
        deneme = DenemeSinavi.objects.create(
            ad="4. Deneme",
            sinav_tarihi=date(2026, 10, 1),
            sinif_seviyesi="5",
            durum=DenemeSinavi.Durum.AKTIF,
            tur=DenemeSinavi.Tur.GRUP,
            sira_no=4,
        )
        DenemeSonucu.objects.create(deneme=deneme, talebe=ali, puan=Decimal("100"))
        DenemeSonucu.objects.create(deneme=deneme, talebe=veli, puan=Decimal("100"))
        DenemeSonucu.objects.create(deneme=deneme, talebe=ayse, puan=Decimal("40"))

        self.client.force_login(user)
        tumu = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi"))
        self.assertEqual(tumu.status_code, 200)
        html = tumu.content.decode()
        self.assertEqual(html.count('class="dk-grup-baslik"'), 1)
        self.assertIn(">5. Sınıf<", html)
        self.assertIn("3 talebe", html)
        self.assertIn("Ali Besa", html)
        self.assertIn("Ayse Besbe", html)
        self.assertTrue("80.00" in html or "80,00" in html)
        self.assertIn(">5-A<", html)
        self.assertIn(">5-B<", html)
        self.assertIn('class="dk-filtre-satir"', html)
        self.assertLess(html.find("dk-filtre-satir"), html.find("dk-grup-baslik"))
        self.assertLess(html.find("dk-grup-baslik"), html.find(">Yükseliş<"))
        self.assertLess(html.find(">Yükseliş<"), html.find("dk-ozet-grid"))

        kazanim = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi") + "?ekran=kazanim")
        khtml = kazanim.content.decode()
        self.assertIn("?ekran=kazanim", khtml)
        self.assertIn(">5-A<", khtml)
        self.assertIn(">5-B<", khtml)
        self.assertNotIn("Ali Besa", khtml)
        self.assertNotIn("Yükseliş sıralaması", khtml)

        sadece_a = self.client.get(
            reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[sinif_a.id])
        )
        a_html = sadece_a.content.decode()
        self.assertIn(">5-A<", a_html)
        self.assertNotIn("Ayse Besbe", a_html)
        self.assertNotIn(">5. Sınıf<", a_html)
        self.assertTrue("100.00" in a_html or "100,00" in a_html)

    def test_tumu_ortak_denemenin_ortalamasini_ve_sirasini_gosterir(self):
        user = User.objects.create_user("etut-ort", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Etüt Ort", user=user, aktif=True)
        PersonelProfili.objects.create(
            user=user,
            ad_soyad="Etüt Ort",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=hoca,
        )
        sinif_a = SinifSube.objects.create(sinif="5", sube="A")
        sinif_b = SinifSube.objects.create(sinif="5", sube="B")
        hoca.sorumlu_sinif_subeler.add(sinif_a, sinif_b)
        ali = Talebe.objects.create(
            ad_soyad="Ali Orta", sinif_sube=sinif_a, etut_hocasi=hoca, dini_ders_hocasi=hoca
        )
        veli = Talebe.objects.create(
            ad_soyad="Veli Orta", sinif_sube=sinif_a, etut_hocasi=hoca, dini_ders_hocasi=hoca
        )
        ayse = Talebe.objects.create(
            ad_soyad="Ayse Orta", sinif_sube=sinif_b, etut_hocasi=hoca, dini_ders_hocasi=hoca
        )
        ayrilan = Talebe.objects.create(
            ad_soyad="Eski Orta",
            sinif_sube=sinif_a,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
            durum=Talebe.Durum.AYRILDI,
        )
        ortak = DenemeSinavi.objects.create(
            ad="Ortak Son",
            sinav_tarihi=date(2026, 9, 15),
            sinif_seviyesi="5",
            durum=DenemeSinavi.Durum.AKTIF,
            tur=DenemeSinavi.Tur.GRUP,
            sira_no=2,
        )
        DenemeSonucu.objects.create(deneme=ortak, talebe=ali, puan=Decimal("400"))
        DenemeSonucu.objects.create(deneme=ortak, talebe=veli, puan=Decimal("424.20"))
        DenemeSonucu.objects.create(deneme=ortak, talebe=ayse, puan=Decimal("412.10"))
        DenemeSonucu.objects.create(deneme=ortak, talebe=ayrilan, puan=Decimal("500"))
        yalniz_a = DenemeSinavi.objects.create(
            ad="4. Deneme",
            sinav_tarihi=date(2026, 10, 1),
            sinif_seviyesi="5",
            durum=DenemeSinavi.Durum.AKTIF,
            tur=DenemeSinavi.Tur.GRUP,
            sira_no=4,
        )
        DenemeSonucu.objects.create(deneme=yalniz_a, talebe=ali, puan=Decimal("416"))
        DenemeSonucu.objects.create(deneme=yalniz_a, talebe=veli, puan=Decimal("416"))

        self.client.force_login(user)
        tumu = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi"))
        html = tumu.content.decode()
        self.assertIn("Son Deneme: 1. Deneme", html)
        self.assertNotIn("Son Deneme: 4. Deneme", html)
        self.assertRegex(html, r'dk-metrik-sayi">\s*412[,.]10')
        self.assertNotRegex(html, r'dk-metrik-sayi">\s*416')
        self.assertNotIn("Eski Orta", html)

        sadece_a = self.client.get(
            reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[sinif_a.id])
        )
        a_html = sadece_a.content.decode()
        self.assertIn("Son Deneme: 2. Deneme", a_html)
        self.assertRegex(a_html, r'dk-metrik-sayi">\s*416')


def _brans(kod, net, yanlis, bos, dogru=10):
    return SimpleNamespace(
        brans=kod,
        net=Decimal(str(net)),
        yanlis=yanlis,
        bos=bos,
        dogru=dogru,
    )


def _sonuc(*branslar):
    return SimpleNamespace(brans_satirlari=SimpleNamespace(all=lambda: list(branslar)))


class OncelikAnalizTests(TestCase):
    def test_dususu_ders_yanlis_ve_sinifla_acar(self):
        matematik_eski = _brans("matematik", 16, 2, 1)
        matematik_yeni = _brans("matematik", 8, 10, 1)
        seri = [
            {"deneme_id": 1, "puan": 400, "net": 50, "sonuc": _sonuc(matematik_eski)},
            {"deneme_id": 2, "puan": 380, "net": 42, "sonuc": _sonuc(matematik_yeni)},
        ]
        sinif_ort = {1: (400.0, 8), 2: (397.0, 8)}
        calisma = [{"kod": "matematik", "etiket": "Matematik", "son_30_gun_soru": 149, "durum": "uyari"}]
        metinler, kritik = _oncelik_metinleri(seri, {
            "puan_dususu": 15.0,
            "net_dususu": 3.0,
            "bos_orani_artis_esik": 0.10,
            "soru_yuksek_esik": 80,
            "ardisik_negatif": 2,
        }, calisma, sinif_ort)
        self.assertTrue(kritik)
        birlesik = " ".join(metinler)
        self.assertIn("Son denemede puan -20,00, net -8,00.", birlesik)
        self.assertIn("Matematik -8,00 net, yanlış 2→10", birlesik)
        self.assertIn("düşüş bu talebeye ait", birlesik)
        self.assertIn("149 soru", birlesik)
        self.assertNotIn("net artmıyor", birlesik)

    def test_sinif_da_dustuyse_deneme_geneli_der(self):
        seri = [
            {"deneme_id": 1, "puan": 400, "net": 40, "sonuc": _sonuc()},
            {"deneme_id": 2, "puan": 380, "net": 36, "sonuc": _sonuc()},
        ]
        metinler, _kritik = _oncelik_metinleri(
            seri,
            {"puan_dususu": 15, "net_dususu": 3, "bos_orani_artis_esik": 0.10, "soru_yuksek_esik": 80, "ardisik_negatif": 2},
            [],
            {1: (410.0, 10), 2: (392.0, 10)},
        )
        self.assertIn("Sınıf ortalaması da -18,0 puan geriledi.", metinler)

    def test_sayfa_kaybin_dersini_ve_kazanimi_yazar(self):
        user = User.objects.create_user("etut-oncelik", password="x")
        hoca = EtutHocasi.objects.create(ad_soyad="Etüt Öncelik", user=user, aktif=True)
        PersonelProfili.objects.create(
            user=user,
            ad_soyad="Etüt Öncelik",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=hoca,
        )
        sinif = SinifSube.objects.create(sinif="8", sube="P")
        hoca.sorumlu_sinif_subeler.add(sinif)
        ali = Talebe.objects.create(
            ad_soyad="Ali Dusen", sinif_sube=sinif, etut_hocasi=hoca, dini_ders_hocasi=hoca
        )
        digerler = [
            Talebe.objects.create(
                ad_soyad=f"Sabit {n}",
                sinif_sube=sinif,
                etut_hocasi=hoca,
                dini_ders_hocasi=hoca,
            )
            for n in range(3)
        ]
        ilk = _deneme("İlk", 1)
        son = _deneme("Son", 20)
        DenemeSonucu.objects.create(deneme=ilk, talebe=ali, puan=Decimal("400"), toplam_net=Decimal("50"))
        ali_son = DenemeSonucu.objects.create(
            deneme=son, talebe=ali, puan=Decimal("380"), toplam_net=Decimal("42")
        )
        DenemeBransSonucu.objects.create(
            sonuc=DenemeSonucu.objects.get(deneme=ilk, talebe=ali),
            brans="matematik", dogru=16, yanlis=2, bos=1, net=Decimal("15.50"),
        )
        DenemeBransSonucu.objects.create(
            sonuc=ali_son, brans="matematik", dogru=10, yanlis=10, bos=1, net=Decimal("7.50")
        )
        for talebe in digerler:
            DenemeSonucu.objects.create(deneme=ilk, talebe=talebe, puan=Decimal("400"), toplam_net=Decimal("50"))
            DenemeSonucu.objects.create(deneme=son, talebe=talebe, puan=Decimal("400"), toplam_net=Decimal("50"))
        _kazanim(son, ali, "Matematik", "Üslü İfadeler", "22")
        _kazanim(son, ali, "Türkçe", "Sözcükte Anlam", "18")

        self.client.force_login(user)
        sayfa = self.client.get(reverse("ogretmen_deneme_kontrol_merkezi_sinif", args=[sinif.id]))
        html = sayfa.content.decode()
        self.assertIn("Ali Dusen", html)
        self.assertIn("Asıl kayıp", html)
        self.assertIn("yanlış 2→10", html)
        self.assertIn("Zayıf kazanım: Üslü İfadeler %22.", html)
        self.assertNotIn("Zayıf kazanım: Sözcükte Anlam", html)
        self.assertIn("düşüş bu talebeye ait", html)
