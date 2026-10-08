from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.deneme_models import DenemeSinavi, DenemeSonucu
from takip.dini_ders_takip_models import DiniDersKonu, DiniDersKonuKaydi, DiniDersTakipAlani
from takip.gunluk_takip_models import GunlukTakipKaydi
from takip.ktt_models import KttSinav, KttSonucu
from takip.models import (
    Ders,
    DiniDersSeviyesi,
    EtutHocasi,
    Kitap,
    OkumaKaydi,
    PersonelProfili,
    SinifSube,
    Talebe,
    Zimmet,
)
from takip.nehari_odev_models import NehariOdevIsaret
from takip.ogretmen_not_models import OgretmenSinavNotu
from takip.panel_permissions import panel_nav_items
from takip.yazili_takip_models import YaziliKamp, YaziliSinav, YaziliSonuc


class NehariOdevTests(TestCase):
    def setUp(self):
        self.tarih = date(2026, 10, 8)
        self.nehari = User.objects.create_user("neharihoca", password="Sifre!2026x")
        self.etut_user = User.objects.create_user("etuthoca", password="Sifre!2026x")
        PersonelProfili.objects.create(
            user=self.nehari,
            ad_soyad="Nehari Hoca",
            ana_rol=PersonelProfili.Rol.NEHARI_MESUL,
        )
        self.hoca = EtutHocasi.objects.create(ad_soyad="Etüt Hoca", user=self.etut_user)
        PersonelProfili.objects.create(
            user=self.etut_user,
            ad_soyad="Etüt Hoca",
            ana_rol=PersonelProfili.Rol.ETUT_MESUL,
            etut_hocasi=self.hoca,
        )
        self.sinif = SinifSube.objects.create(sinif="5", sube="A")
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.ali = Talebe.objects.create(
            ad_soyad="Ali Yıldız",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.veli = Talebe.objects.create(
            ad_soyad="Veli Demir",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        self.ders = Ders.objects.create(ad="Matematik", sira=1, aktif=True)
        GunlukTakipKaydi.objects.create(
            talebe=self.ali,
            tarih=self.tarih,
            devam=GunlukTakipKaydi.DevamDurumu.GELDI,
        )
        kitap = Kitap.objects.create(ad="Siyer", toplam_sayfa=120)
        zimmet = Zimmet.objects.create(
            talebe=self.ali,
            kitap=kitap,
            etut_hocasi=self.hoca,
            baslangic_sayfasi=0,
        )
        OkumaKaydi.objects.create(zimmet=zimmet, tarih=self.tarih, son_sayfa=18)
        ktt = KttSinav.objects.create(
            ad="5. sınıf KTT",
            ders=self.ders,
            sinif_seviyesi="5",
            hedef_siniflar="5-A",
            sinav_tarihi=self.tarih,
            soru_sayisi=20,
            etut_hocasi=self.hoca,
            olusturan=self.etut_user,
        )
        KttSonucu.objects.create(
            ktt=ktt,
            talebe=self.ali,
            dogru=16,
            yanlis=4,
            bos=0,
            kaydeden=self.etut_user,
        )
        deneme = DenemeSinavi.objects.create(
            ad="5. Deneme",
            sinav_tarihi=self.tarih,
            sinif_seviyesi="5",
            durum=DenemeSinavi.Durum.AKTIF,
        )
        DenemeSonucu.objects.create(
            deneme=deneme,
            talebe=self.ali,
            puan=Decimal("72.50"),
        )
        kamp = YaziliKamp.objects.create(
            ad="5. sınıf kamp",
            baslangic=self.tarih,
            bitis=self.tarih,
            sinif_seviyesi="5",
        )
        sinav = YaziliSinav.objects.create(
            kamp=kamp,
            ad="Matematik yazılı",
            sinav_tarihi=self.tarih,
            ders=self.ders,
            ders_ad="Matematik",
            durum=YaziliSinav.Durum.AKTIF,
        )
        YaziliSonuc.objects.create(sinav=sinav, talebe=self.ali, puan=Decimal("80"))
        seviye = DiniDersSeviyesi.objects.create(ad="Temel", sira=1)
        alan = DiniDersTakipAlani.objects.create(ad="İlmihal", sira=1)
        konu = DiniDersKonu.objects.create(alan=alan, seviye=seviye, ad="Abdest", sira=1)
        DiniDersKonuKaydi.objects.create(
            talebe=self.ali,
            konu=konu,
            tamamlandi=True,
            tamamlanma_tarihi=self.tarih,
            isaretleyen=self.nehari,
        )
        OgretmenSinavNotu.objects.create(
            talebe=self.ali,
            etut_hocasi=self.hoca,
            ders=self.ders,
            hafta_baslangic=date(2026, 10, 5),
            katilim=Decimal("80"),
        )

    def test_gun_yenilenir_ve_kutucuk_o_gunu_kapatir(self):
        self.client.force_login(self.nehari)
        url = reverse("nehari_odev_panel")
        acilis = self.client.get(url, {"tarih": "2026-10-08"})
        self.assertEqual(acilis.status_code, 200)
        self.assertContains(acilis, "Ali Yıldız")
        self.assertContains(acilis, "Veli Demir")
        self.assertContains(acilis, "data-nehari-etiket>Yapılmadı", count=2)
        self.assertContains(acilis, "Geldi")
        self.assertContains(acilis, "s. 18")
        self.assertContains(acilis, "1 konu")
        self.assertContains(acilis, "15 net")
        self.assertContains(acilis, "72,5 puan")
        self.assertContains(acilis, "Matematik 80")
        self.assertContains(acilis, "Bu hafta girildi")
        self.assertContains(acilis, "Girilmedi")

        isaret = self.client.post(
            reverse("nehari_odev_isaret"),
            {"talebe_id": self.ali.pk, "tarih": "2026-10-08", "yapildi": "1"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(isaret.status_code, 200)
        self.assertTrue(isaret.json()["yapildi"])
        self.assertTrue(
            NehariOdevIsaret.objects.get(talebe=self.ali, tarih=self.tarih).yapildi
        )

        tekrar = self.client.get(url, {"tarih": "2026-10-08"})
        self.assertContains(tekrar, "data-nehari-etiket>Yapıldı", count=1)
        self.assertContains(tekrar, "data-nehari-etiket>Yapılmadı", count=1)
        sonraki = self.client.get(url, {"tarih": "2026-10-09"})
        self.assertContains(sonraki, "data-nehari-etiket>Yapılmadı", count=2)
        self.assertNotContains(sonraki, "data-nehari-etiket>Yapıldı")

    def test_odev_metni_listeye_yazilir(self):
        self.client.force_login(self.nehari)
        cevap = self.client.post(
            reverse("nehari_odev_panel"),
            {
                "islem": "metin",
                "tarih": "2026-10-08",
                "metin": "Matematik sayfa 42-45",
            },
        )
        self.assertEqual(cevap.status_code, 302)
        sayfa = self.client.get(reverse("nehari_odev_panel"), {"tarih": "2026-10-08"})
        self.assertContains(sayfa, "Matematik sayfa 42-45")

    def test_ktt_yoklama_ve_kitap_girisi_acik(self):
        self.client.force_login(self.nehari)
        ktt = self.client.get(reverse("ktt_listesi"))
        self.assertEqual(ktt.status_code, 200)
        self.assertContains(ktt, 'name="sinif_subeler"')
        self.assertContains(ktt, "5-A")
        kayit = self.client.post(
            reverse("ktt_listesi"),
            {
                "ad": "Nehari KTT",
                "ders": self.ders.pk,
                "sinav_tarihi": "2026-10-08",
                "soru_sayisi": 10,
                "sinif_subeler": "5-A",
            },
        )
        self.assertEqual(kayit.status_code, 302)
        self.assertIn("/sonuclar/", kayit.url)
        sinav = KttSinav.objects.get(ad="Nehari KTT")
        self.assertEqual(sinav.olusturan, self.nehari)
        self.assertEqual(sinav.etut_hocasi.user, self.nehari)
        sonuc = self.client.get(kayit.url)
        self.assertEqual(sonuc.status_code, 200)
        self.assertContains(sonuc, "Ali Yıldız")
        self.assertContains(sonuc, "Veli Demir")

        yoklama = self.client.post(
            reverse("gunluk_takip_panel"),
            {"tarih": "2026-10-08", "devamsiz": str(self.veli.pk)},
        )
        self.assertEqual(yoklama.status_code, 302)
        self.assertEqual(
            GunlukTakipKaydi.objects.get(talebe=self.veli, tarih=self.tarih).devam,
            GunlukTakipKaydi.DevamDurumu.GELMEDI,
        )

        okuma = self.client.get(reverse("toplu_gunluk_okuma"))
        self.assertEqual(okuma.status_code, 200)
        self.assertContains(okuma, "Ali Yıldız")
        self.assertContains(okuma, "Siyer")
        zimmet = Zimmet.objects.get(talebe=self.ali)
        okuma_kayit = self.client.post(
            reverse("toplu_gunluk_okuma"),
            {f"son_sayfa_{zimmet.pk}": "24"},
        )
        self.assertEqual(okuma_kayit.status_code, 302)
        self.assertEqual(
            OkumaKaydi.objects.filter(zimmet=zimmet).order_by("-tarih", "-id").first().son_sayfa,
            24,
        )

        sinav = YaziliSinav.objects.get(ad="Matematik yazılı")
        yazili = self.client.get(reverse("yazili_sonuc_gir", args=[sinav.pk]))
        self.assertEqual(yazili.status_code, 200)
        self.assertContains(yazili, "Veli Demir")
        yazili_kayit = self.client.post(
            reverse("yazili_sonuc_gir", args=[sinav.pk]),
            {f"puan_{self.ali.pk}": "80", f"puan_{self.veli.pk}": "91"},
        )
        self.assertEqual(yazili_kayit.status_code, 302)
        self.assertEqual(
            YaziliSonuc.objects.get(sinav=sinav, talebe=self.veli).puan,
            Decimal("91"),
        )

        seviye = DiniDersSeviyesi.objects.get(ad="Temel")
        konu = DiniDersKonu.objects.get(ad="Abdest")
        self.hoca.sorumlu_dini_ders_seviyeleri.add(seviye)
        self.veli.dini_ders_seviyesi = seviye
        self.veli.save(update_fields=["dini_ders_seviyesi"])
        dini = self.client.get(
            reverse("dini_ders_panel"),
            {"seviye": seviye.pk, "alan": konu.alan_id},
        )
        self.assertEqual(dini.status_code, 200)
        self.assertContains(dini, "Veli Demir")
        dini_kayit = self.client.post(
            reverse("dini_ders_panel"),
            {
                "seviye_id": seviye.pk,
                "alan_id": konu.alan_id,
                f"d_{self.veli.pk}_{konu.pk}": "tamam",
            },
        )
        self.assertEqual(dini_kayit.status_code, 302)
        self.assertTrue(
            DiniDersKonuKaydi.objects.get(talebe=self.veli, konu=konu).tamamlandi
        )

        deneme = self.client.get(reverse("deneme_listesi"))
        self.assertEqual(deneme.status_code, 200)
        self.assertContains(deneme, "72,5")
        self.assertContains(deneme, "/denemeler/")

        pano = self.client.get(reverse("nehari_odev_panel"), {"tarih": "2026-10-08"})
        self.assertContains(pano, reverse("ktt_listesi"))
        self.assertContains(pano, reverse("gunluk_takip_panel"))

        anahtarlar = {item.key for item in panel_nav_items(self.nehari)}
        self.assertTrue(
            {"ktt", "deneme", "dini_ders_takip", "yazili_takip", "gunluk_takip", "okuma", "zimmetler"}
            <= anahtarlar
        )

    def test_etut_hocasi_goremez_nehari_menude_durur(self):
        self.client.force_login(self.etut_user)
        cevap = self.client.get(reverse("nehari_odev_panel"))
        self.assertEqual(cevap.status_code, 302)
        self.assertNotIn("nehari_odev", {item.key for item in panel_nav_items(self.etut_user)})

        self.client.force_login(self.nehari)
        anahtarlar = {item.key for item in panel_nav_items(self.nehari)}
        self.assertIn("nehari_odev", anahtarlar)
