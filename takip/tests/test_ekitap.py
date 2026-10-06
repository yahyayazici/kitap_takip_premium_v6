"""E-Kitap alt alan adı: host ayrımı, yönetici/PIN erişimi, PDF işleme, dosya yaşam döngüsü."""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from takip.ekitap_models import EKitap, EKitapAyar, EKitapBolum, EKitapSayfa

HOST = "ekitap.localhost"
SIFRE = "Yonetici-Test-Sifre-42"


def ornek_pdf(sayfa: int = 3, metin: str = "Soru") -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=A4)
    for i in range(sayfa):
        c.setFont("Helvetica", 28)
        c.drawString(72, 760, f"{metin} {i + 1}")
        c.showPage()
    c.save()
    return tampon.getvalue()


def pdf_dosyasi(ad: str, sayfa: int = 3) -> SimpleUploadedFile:
    return SimpleUploadedFile(ad, ornek_pdf(sayfa), content_type="application/pdf")


class EKitapTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.depo = tempfile.mkdtemp(prefix="ekitap-test-")
        self.ayarlar = override_settings(
            EKITAP_MEDIA_ROOT=Path(self.depo),
            EKITAP_YONETICI_SIFRE=SIFRE,
            EKITAP_ARKA_PLAN_ISLEME=False,
            EKITAP_SAYFA_GENISLIK=600,
        )
        self.ayarlar.enable()

    def tearDown(self):
        self.ayarlar.disable()
        shutil.rmtree(self.depo, ignore_errors=True)

    def get(self, yol, **kw):
        return self.client.get(yol, HTTP_HOST=HOST, **kw)

    def post(self, yol, data=None, **kw):
        return self.client.post(yol, data or {}, HTTP_HOST=HOST, **kw)

    def yonetici_giris(self):
        r = self.post("/yonetim/giris/", {"sifre": SIFRE})
        self.assertEqual(r.status_code, 302)

    def kitap_yukle(self, ad="7. Sınıf Kurumsal Deneme 1", gorunur=True):
        veri = {
            "ad": ad,
            "yeni_ad_0": "Sayısal",
            "yeni_pdf_0": pdf_dosyasi("1-Sayisal.pdf", 3),
            "yeni_ad_1": "Sözel",
            "yeni_pdf_1": pdf_dosyasi("2-Sozel.pdf", 2),
        }
        if gorunur:
            veri["gorunur"] = "on"
        r = self.post("/yonetim/kitap/yeni/", veri)
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context.get("hatalar"))
        return EKitap.objects.get(ad=ad)


class HostAyrimiTests(EKitapTestBase):
    def test_ekitap_hostu_kendi_urlconfunu_kullanir(self):
        r = self.get("/")
        self.assertRedirects(r, "/pin/?next=/", fetch_redirect_response=False)
        self.assertEqual(self.get("/panel/").status_code, 404)
        self.assertEqual(self.get("/admin/").status_code, 404)

    def test_ana_sitede_ekitap_adresleri_yok(self):
        self.assertEqual(self.client.get("/pin/").status_code, 404)
        self.assertEqual(self.client.get("/yonetim/kitap/yeni/").status_code, 404)

    def test_arama_motorlarina_kapali(self):
        r = self.get("/pin/")
        self.assertIn("noindex", r["X-Robots-Tag"])
        self.assertContains(r, 'name="robots" content="noindex')
        robots = self.get("/robots.txt")
        self.assertEqual(robots.content.decode(), "User-agent: *\nDisallow: /\n")

    def test_ana_site_superuser_oturumu_ekitapa_erisemez(self):
        User.objects.create_superuser("anaadmin", "a@example.com", "x")
        self.client.login(username="anaadmin", password="x")
        r = self.get("/yonetim/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/yonetim/giris/", r["Location"])


class YoneticiGirisTests(EKitapTestBase):
    def test_yanlis_ve_dogru_sifre(self):
        r = self.post("/yonetim/giris/", {"sifre": "yanlis"})
        self.assertContains(r, "Şifre hatalı")
        self.yonetici_giris()
        self.assertEqual(self.get("/yonetim/").status_code, 200)

    def test_hatali_denemeler_kilitlenir(self):
        for _ in range(5):
            self.post("/yonetim/giris/", {"sifre": "yanlis"})
        r = self.post("/yonetim/giris/", {"sifre": SIFRE})
        self.assertContains(r, "Çok fazla hatalı deneme")
        self.assertEqual(self.get("/yonetim/").status_code, 302)

    def test_sahte_forwarded_for_kilidi_atlatamaz(self):
        for i in range(5):
            self.post("/yonetim/giris/", {"sifre": "yanlis"}, HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, 203.0.113.9")
        r = self.post("/yonetim/giris/", {"sifre": SIFRE}, HTTP_X_FORWARDED_FOR="10.9.9.9, 203.0.113.9")
        self.assertContains(r, "Çok fazla hatalı deneme")

    @override_settings(EKITAP_YONETICI_SIFRE="")
    def test_sifre_tanimsizsa_yonetim_kapali(self):
        r = self.post("/yonetim/giris/", {"sifre": ""})
        self.assertContains(r, "EKITAP_YONETICI_SIFRE")
        self.assertEqual(self.get("/yonetim/").status_code, 302)

    def test_dis_adrese_yonlendirmez(self):
        r = self.post("/yonetim/giris/", {"sifre": SIFRE, "next": "https://kotu.example.com/"})
        self.assertEqual(r["Location"], "/yonetim/")


class KitapYonetimTests(EKitapTestBase):
    def setUp(self):
        super().setUp()
        self.yonetici_giris()

    def test_iki_pdfli_kitap_yuklenir_ve_islenir(self):
        kitap = self.kitap_yukle()
        bolumler = list(kitap.bolumler.order_by("sira"))
        self.assertEqual([b.ad for b in bolumler], ["Sayısal", "Sözel"])
        self.assertEqual([b.islem_durumu for b in bolumler], ["hazir", "hazir"])
        self.assertEqual([b.sayfa_sayisi for b in bolumler], [3, 2])
        sayfa = bolumler[0].sayfalar.first()
        self.assertEqual(sayfa.genislik, 600)
        self.assertTrue(Path(self.depo, sayfa.gorsel.name).exists())
        self.assertTrue(Path(self.depo, sayfa.kucuk.name).exists())

    def test_pdf_olmayan_dosya_reddedilir(self):
        r = self.post(
            "/yonetim/kitap/yeni/",
            {"ad": "Bozuk", "yeni_pdf_0": SimpleUploadedFile("x.pdf", b"merhaba", content_type="application/pdf")},
        )
        self.assertContains(r, "geçerli bir PDF değil")
        self.assertFalse(EKitap.objects.exists())

    def test_ad_ve_pdf_zorunlu(self):
        r = self.post("/yonetim/kitap/yeni/", {"ad": ""})
        self.assertContains(r, "Kitap adı gerekli")
        self.assertContains(r, "En az bir PDF")

    def test_gizle_goster_duzenle_sil(self):
        kitap = self.kitap_yukle()
        self.post(f"/yonetim/kitap/{kitap.pk}/gorunurluk/")
        kitap.refresh_from_db()
        self.assertFalse(kitap.gorunur)

        sayisal = kitap.bolumler.get(ad="Sayısal")
        sozel = kitap.bolumler.get(ad="Sözel")
        eski_sayfa_idleri = set(sayisal.sayfalar.values_list("pk", flat=True))
        eski_pdf_yolu = Path(self.depo, sayisal.pdf.name)
        r = self.post(
            f"/yonetim/kitap/{kitap.pk}/",
            {
                "ad": "Yeni Ad",
                "gorunur": "on",
                f"ad_{sayisal.pk}": "Sayısal Bölüm",
                f"sira_{sayisal.pk}": "0",
                f"pdf_{sayisal.pk}": pdf_dosyasi("yeni.pdf", 4),
                f"ad_{sozel.pk}": "Sözel",
                f"sira_{sozel.pk}": "1",
                "yeni_ad_0": "Ek",
                "yeni_pdf_0": pdf_dosyasi("ek.pdf", 1),
            },
        )
        self.assertEqual(r.status_code, 302)
        kitap.refresh_from_db()
        sayisal.refresh_from_db()
        self.assertEqual(kitap.ad, "Yeni Ad")
        self.assertTrue(kitap.gorunur)
        self.assertEqual(sayisal.ad, "Sayısal Bölüm")
        self.assertEqual(sayisal.sayfa_sayisi, 4)
        # Yeni sayfa kayıtları → yeni görsel adresleri (tahtadaki önbellek eski sayfayı göstermez)
        self.assertFalse(EKitapSayfa.objects.filter(pk__in=eski_sayfa_idleri).exists())
        self.assertEqual(
            len(list(Path(self.depo, "sayfa").glob(f"{sayisal.pk}-*.webp"))), 4
        )
        self.assertFalse(eski_pdf_yolu.exists())
        self.assertEqual(kitap.bolumler.count(), 3)
        self.assertEqual(kitap.bolumler.get(ad="Ek").sira, 2)

        sozel_pdf = Path(self.depo, sozel.pdf.name)
        self.post(f"/yonetim/bolum/{sozel.pk}/sil/")
        self.assertFalse(EKitapBolum.objects.filter(pk=sozel.pk).exists())
        self.assertFalse(sozel_pdf.exists())

        self.post(f"/yonetim/kitap/{kitap.pk}/sil/")
        self.assertFalse(EKitap.objects.exists())
        self.assertFalse(EKitapSayfa.objects.exists())
        kalan = [p for p in Path(self.depo).rglob("*") if p.is_file()]
        self.assertEqual(kalan, [])

    def test_bozuk_pdf_hata_durumuna_duser(self):
        kitap = EKitap.objects.create(ad="Bozuk")
        bolum = EKitapBolum.objects.create(
            kitap=kitap, ad="X", pdf=SimpleUploadedFile("x.pdf", b"%PDF-1.4 bozuk icerik")
        )
        from takip.ekitap_service import bolumleri_isle

        bolumleri_isle([bolum.pk])
        bolum.refresh_from_db()
        self.assertEqual(bolum.islem_durumu, "hata")
        self.assertIn("PDF açılamadı", bolum.islem_notu)
        r = self.get("/yonetim/")
        self.assertContains(r, "Yeniden işle")

    def test_pin_belirleme_dogrulama(self):
        r = self.post("/yonetim/pin/", {"pin": "12a4", "pin_tekrar": "12a4"}, follow=True)
        self.assertContains(r, "4–12 haneli")
        r = self.post("/yonetim/pin/", {"pin": "1234", "pin_tekrar": "1235"}, follow=True)
        self.assertContains(r, "eşleşmiyor")
        self.post("/yonetim/pin/", {"pin": "482910", "pin_tekrar": "482910"})
        ayar = EKitapAyar.al()
        self.assertTrue(ayar.pin_hash)
        self.assertNotIn("482910", ayar.pin_hash)


class GoruntulemeTests(EKitapTestBase):
    def setUp(self):
        super().setUp()
        self.yonetici_giris()
        self.kitap = self.kitap_yukle()
        self.gizli = self.kitap_yukle(ad="Gizli Kitap", gorunur=False)
        self.post("/yonetim/pin/", {"pin": "2468", "pin_tekrar": "2468"})
        self.post("/yonetim/cikis/")

    def pin_gir(self, pin="2468"):
        return self.post("/pin/", {"pin": pin, "next": "/"})

    def test_pin_olmadan_icerik_yok(self):
        self.assertEqual(self.get("/").status_code, 302)
        self.assertEqual(self.get(f"/kitap/{self.kitap.pk}/").status_code, 302)
        sayfa = EKitapSayfa.objects.filter(bolum__kitap=self.kitap).first()
        self.assertEqual(self.get(f"/sayfa/{sayfa.pk}.webp").status_code, 403)

    def test_pin_tanimsizsa_bilgilendirir(self):
        EKitapAyar.objects.update(pin_hash="")
        self.assertContains(self.get("/pin/"), "henüz belirlenmedi")

    def test_yanlis_pin_ve_kilit(self):
        self.assertContains(self.pin_gir("0000"), "PIN hatalı")
        for _ in range(8):
            self.pin_gir("0000")
        self.assertContains(self.pin_gir("2468"), "Çok fazla hatalı deneme")

    def test_liste_yalnizca_gorunur_kitaplari_gosterir(self):
        self.assertRedirects(self.pin_gir(), "/", fetch_redirect_response=False)
        r = self.get("/")
        self.assertContains(r, "7. Sınıf Kurumsal Deneme 1")
        self.assertNotContains(r, "Gizli Kitap")
        self.assertEqual(self.get(f"/kitap/{self.gizli.pk}/").status_code, 404)
        gizli_sayfa = EKitapSayfa.objects.filter(bolum__kitap=self.gizli).first()
        self.assertEqual(self.get(f"/sayfa/{gizli_sayfa.pk}.webp").status_code, 404)

    def test_okuyucu_sekmeler_ve_gorseller(self):
        self.pin_gir()
        r = self.get(f"/kitap/{self.kitap.pk}/")
        self.assertContains(r, 'class="ek-sekme"', count=2)
        self.assertContains(r, "Sayısal")
        self.assertContains(r, "Sözel")
        self.assertContains(r, "tamEkran")
        veri = r.context["veri"]
        self.assertEqual([len(b["sayfalar"]) for b in veri], [3, 2])
        g = self.get(veri[0]["sayfalar"][0]["src"])
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g["Content-Type"], "image/webp")
        self.assertIn("private", g["Cache-Control"])
        govde = b"".join(g.streaming_content)
        self.assertEqual(govde[8:12], b"WEBP")

    def test_pin_degisince_oturum_duser(self):
        self.pin_gir()
        self.assertEqual(self.get("/").status_code, 200)
        from takip.ekitap_service import pin_belirle

        pin_belirle("1357")
        self.assertEqual(self.get("/").status_code, 302)

    def test_yonetici_gizli_kitabi_onizler(self):
        self.yonetici_giris()
        r = self.get(f"/kitap/{self.gizli.pk}/")
        self.assertContains(r, "önizleme")

    def test_kilitle(self):
        self.pin_gir()
        self.post("/pin/cikis/")
        self.assertEqual(self.get("/").status_code, 302)


class KitaplikGorunumTests(EKitapTestBase):
    def test_insan_adi_filtresi(self):
        from takip.templatetags.ekitap_etiketleri import insan_adi

        self.assertEqual(insan_adi("1-Sayisal-Bolum_Ogrenci-Kitapcigi_A"), "Sayisal Bolum")
        self.assertEqual(insan_adi("2_Sozel"), "Sozel")
        self.assertEqual(insan_adi("Tam sayılarla işlemler"), "Tam sayılarla işlemler")
        self.assertEqual(insan_adi("Sayısal"), "Sayısal")
        self.assertEqual(insan_adi(""), "")

    def test_kitaplik_meta_tek_satir_ve_ham_ad_yok(self):
        self.yonetici_giris()
        kitap = EKitap.objects.create(ad="Deneme", gorunur=True)
        for i, ad in enumerate(["1-Sayisal-Bolum_Ogrenci-Kitapcigi_A", "2-Sozel-Bolum_Ogrenci-Kitapcigi_A"]):
            EKitapBolum.objects.create(kitap=kitap, ad=ad, sira=i, pdf=pdf_dosyasi(f"{i}.pdf", 2))
        from takip.ekitap_service import bolumleri_isle

        bolumleri_isle(list(kitap.bolumler.values_list("pk", flat=True)))
        self.post("/yonetim/pin/", {"pin": "2468", "pin_tekrar": "2468"})
        r = self.get("/")
        self.assertContains(r, '<span class="ek-eser-meta">Sayisal Bolum +1 · 4 sayfa</span>', html=False)
        self.assertNotContains(r, "Kitapcigi")
        self.assertContains(r, "ek-raf-ortala")
        self.assertContains(r, '<span class="ek-bas-sayi">1 kitap</span>')
