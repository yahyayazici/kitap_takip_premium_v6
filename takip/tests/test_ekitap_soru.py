"""E-Kitap soru tespiti, soru görselleri ve soru görünümü verisi."""

from __future__ import annotations

import io
import json
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from takip.ekitap_models import EKitap, EKitapBolum, EKitapSayfa, EKitapSoru, EKitapSoruAlan
from takip.ekitap_soru_tespit import tespit_et
from takip.tests.ekitap_pdf_ornekleri import deneme_pdf, taranmis_pdf
from takip.tests.test_ekitap import EKitapTestBase


def _belge(veri: bytes):
    import pypdfium2 as pdfium

    return pdfium.PdfDocument(veri)


class TespitAlgoritmasiTests(EKitapTestBase):
    """Saf tespit: veritabanı kullanılmaz."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sonuc = tespit_et(_belge(deneme_pdf()))

    def soru(self, test_no, no):
        for s in self.sonuc.sorular:
            if s.test_no == test_no and s.no == no:
                return s
        self.fail(f"T{test_no}-{no} bulunamadı")

    def test_numaralar_ve_yeniden_baslayan_test(self):
        self.assertEqual(self.sonuc.durum, "tamam")
        kimlikler = [(s.test_no, s.no) for s in self.sonuc.sorular]
        beklenen = [(1, n) for n in range(1, 16)] + [(2, n) for n in (1, 2, 3, 4, 5, 6, 7, 9)]
        self.assertEqual(kimlikler, beklenen)
        # Okuma sırası tam sırayla artar
        self.assertEqual([s.sira for s in self.sonuc.sorular], list(range(len(beklenen))))

    def test_kapak_ve_ust_bant_ve_ic_maddeler_soru_sayilmaz(self):
        # Kapak sayfası (0) ve "7. SINIF" başlığı soru değildir; 2. sorudaki
        # "1. 2. 3. madde" girintili satırları da ayrı soru olmaz.
        self.assertFalse(any(s.alanlar[0][0] == 0 for s in self.sonuc.sorular))
        self.assertEqual(sum(1 for s in self.sonuc.sorular if s.test_no == 1), 15)

    def test_iki_sutun_okuma_sirasi(self):
        for no in (1, 2, 3):
            self.assertLess(self.soru(1, no).alanlar[0][1].x0, 0.5)
        for no in (4, 5, 6):
            self.assertGreater(self.soru(1, no).alanlar[0][1].x0, 0.5)
        # Sol sütun kutusu ortadaki ayırıcı çizgiyi (x=0.5) aşmaz
        self.assertLess(self.soru(1, 1).alanlar[0][1].x1, 0.5)

    def test_soru_alani_kok_sekil_ve_siklari_kapsar(self):
        # 2. soru: 5 satır kök + 3 madde + 4 şık ≈ 12 satır * 14pt
        kutu = self.soru(1, 2).alanlar[0][1]
        self.assertGreater(kutu.yukseklik * 841.89, 12 * 14)
        # 3. soru şekil içerir: alan, şeklin altındaki şıklara kadar uzanır
        kutu3 = self.soru(1, 3).alanlar[0][1]
        self.assertGreater(kutu3.yukseklik * 841.89, 3 * 14 + 80 + 3 * 14)
        # Alanlar çakışmaz
        k1, k2 = self.soru(1, 1).alanlar[0][1], self.soru(1, 2).alanlar[0][1]
        self.assertLessEqual(k1.y1, k2.y0 + 1e-6)

    def test_sayfa_sonunda_devam_eden_soru_birlesir(self):
        s11 = self.soru(1, 11)
        self.assertEqual([sayfa for sayfa, _ in s11.alanlar], [2, 3])
        devam = s11.alanlar[1][1]
        self.assertLess(devam.x0, 0.5)  # sonraki sayfanın sol sütunu, en üstte
        self.assertLess(devam.y0, self.soru(1, 12).alanlar[0][1].y0)
        self.assertLess(s11.guven, 0.9)
        self.assertTrue(any("devam" in n for n in self.sonuc.sayfalar[3].notlar))

    def test_atlanan_numara_ve_taranmis_sayfa_isaretlenir(self):
        self.assertTrue(any("7 → 9" in n for n in self.sonuc.sayfalar[5].notlar))
        self.assertFalse(self.sonuc.sayfalar[6].metinli)
        self.assertEqual(self.sonuc.sayfalar[1].notlar, [])

    def test_taranmis_pdf(self):
        sonuc = tespit_et(_belge(taranmis_pdf()))
        self.assertEqual(sonuc.durum, "taranmis")
        self.assertEqual(sonuc.sorular, [])
        self.assertTrue(all(not b.metinli for b in sonuc.sayfalar.values()))


class SoruKayitTests(EKitapTestBase):
    def setUp(self):
        super().setUp()
        self.yonetici_giris()
        self.post("/yonetim/pin/", {"pin": "2468", "pin_tekrar": "2468"})
        r = self.post(
            "/yonetim/kitap/yeni/",
            {
                "ad": "Soru Kitabı",
                "gorunur": "on",
                "yeni_ad_0": "Sayısal",
                "yeni_pdf_0": SimpleUploadedFile("s.pdf", deneme_pdf(), content_type="application/pdf"),
                "yeni_ad_1": "Taranmış",
                "yeni_pdf_1": SimpleUploadedFile("t.pdf", taranmis_pdf(), content_type="application/pdf"),
            },
        )
        self.assertEqual(r.status_code, 302)
        self.kitap = EKitap.objects.get(ad="Soru Kitabı")
        self.sayisal, self.taranmis = list(self.kitap.bolumler.order_by("sira"))

    def test_yuklemede_sorular_ve_gorseller_hazirlanir(self):
        self.assertEqual(EKitapBolum.objects.get(pk=self.sayisal.pk).tespit_durumu, "tamam")
        self.assertEqual(self.sayisal.sorular.count(), 23)
        self.assertEqual(self.sayisal.sorular.filter(test_no=2).count(), 8)
        alanlar = EKitapSoruAlan.objects.filter(soru__bolum=self.sayisal)
        self.assertEqual(alanlar.count(), 24)  # 11. soru iki alanlı
        for alan in alanlar:
            self.assertTrue(alan.gorsel, alan.pk)
            self.assertTrue(Path(alan.gorsel.path).exists())
            # Sayfa görselinden (600 px) çok daha net: uzun kenar ~2000 px
            self.assertGreaterEqual(max(alan.genislik, alan.yukseklik), 1500)
        kontrol = list(self.sayisal.sayfalar.filter(kontrol_gerekli=True).values_list("sira", flat=True))
        self.assertEqual(sorted(kontrol), [3, 5, 6])

    def test_taranmis_pdf_isaretlenir_ve_panelde_gorunur(self):
        bolum = EKitapBolum.objects.get(pk=self.taranmis.pk)
        self.assertEqual(bolum.tespit_durumu, "taranmis")
        self.assertEqual(bolum.sorular.count(), 0)
        self.assertFalse(bolum.sayfalar.filter(metinli=True).exists())
        r = self.get("/yonetim/")
        self.assertContains(r, "Taranmış PDF · sorular elle işaretlenmeli")
        self.assertContains(r, "23 soru")
        self.assertContains(r, "Kontrol edin · 3 sayfa")

    def test_okuyucu_verisi_ve_soru_gorseli_erisimi(self):
        self.post("/yonetim/cikis/")
        self.post("/pin/", {"pin": "2468"})
        r = self.get(f"/kitap/{self.kitap.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "soruGorunum")
        veri = json.loads(r.content.decode().split('id="ekitapVeri" type="application/json">')[1].split("</script>")[0])
        sorular = veri[0]["sorular"]
        self.assertEqual(len(sorular), 23)
        s11 = next(s for s in sorular if s["no"] == 11 and s["t"] == 1)
        self.assertEqual([a["s"] for a in s11["alanlar"]], [2, 3])
        self.assertTrue(all(a["src"] and "?v=" in a["src"] for a in s11["alanlar"]))
        self.assertEqual(veri[1]["sorular"], [])
        gorsel = self.get(s11["alanlar"][0]["src"])
        self.assertEqual(gorsel.status_code, 200)
        self.assertEqual(gorsel["Content-Type"], "image/webp")
        # PIN olmadan görsel yok
        self.post("/pin/cikis/")
        self.assertEqual(self.get(s11["alanlar"][0]["src"]).status_code, 403)

    def test_gizli_kitabin_soru_gorseli_kapali(self):
        alan = EKitapSoruAlan.objects.filter(soru__bolum=self.sayisal).first()
        self.kitap.gorunur = False
        self.kitap.save()
        self.post("/yonetim/cikis/")
        self.post("/pin/", {"pin": "2468"})
        self.assertEqual(self.get(f"/soru/{alan.pk}.webp").status_code, 404)

    def test_toplu_komut_tekrar_calistirilabilir_ve_kimlikleri_korur(self):
        once = list(self.sayisal.sorular.order_by("sira").values_list("pk", "test_no", "no"))
        gorseller = set(EKitapSoruAlan.objects.values_list("gorsel", flat=True))
        cikti = io.StringIO()
        call_command("ekitap_sorulari_bul", stdout=cikti)
        call_command("ekitap_sorulari_bul", "--kitap", str(self.kitap.pk), stdout=cikti)
        self.assertIn("23 soru", cikti.getvalue())
        sonra = list(self.sayisal.sorular.order_by("sira").values_list("pk", "test_no", "no"))
        self.assertEqual(once, sonra)
        # Alanlar değişmediği için görseller yeniden üretilmez
        self.assertEqual(gorseller, set(EKitapSoruAlan.objects.values_list("gorsel", flat=True)))

    def test_elle_onayli_soru_korunur_pdf_degisince_inceleme_ister(self):
        soru = self.sayisal.sorular.get(test_no=1, no=5)
        alan = soru.alanlar.get()
        alan.y1 = min(alan.y1 + 0.02, 1.0)
        alan.save()
        soru.onayli = True
        soru.kaynak = EKitapSoru.Kaynak.ELLE
        soru.save()
        call_command("ekitap_sorulari_bul", stdout=io.StringIO())
        soru.refresh_from_db()
        self.assertFalse(soru.inceleme_gerekli)
        self.assertEqual(self.sayisal.sorular.filter(test_no=1, no=5).count(), 1)
        self.assertAlmostEqual(soru.alanlar.get().y1, alan.y1)

        # PDF değiştirilir → yeniden işlenir; elle düzeltme kalır ama incelenmeli
        r = self.post(
            f"/yonetim/kitap/{self.kitap.pk}/",
            {
                "ad": "Soru Kitabı",
                "gorunur": "on",
                f"ad_{self.sayisal.pk}": "Sayısal",
                f"sira_{self.sayisal.pk}": "0",
                f"pdf_{self.sayisal.pk}": SimpleUploadedFile(
                    "s2.pdf", deneme_pdf() + b"\n%degisti\n", content_type="application/pdf"
                ),
                f"ad_{self.taranmis.pk}": "Taranmış",
                f"sira_{self.taranmis.pk}": "1",
            },
        )
        self.assertEqual(r.status_code, 302)
        soru.refresh_from_db()
        self.assertTrue(soru.inceleme_gerekli)
        self.assertEqual(self.sayisal.sorular.filter(test_no=1, no=5).count(), 1)
        self.assertEqual(self.sayisal.sorular.count(), 23)
        sayfa = EKitapSayfa.objects.get(bolum=self.sayisal, sira=alan.sayfa_sira)
        self.assertTrue(sayfa.kontrol_gerekli)
        self.assertIn("yeniden inceleyin", sayfa.kontrol_notu)

    def test_yonetimden_sorulari_bul(self):
        self.assertEqual(self.post("/yonetim/sorulari-bul/", {"bolum": self.sayisal.pk}).status_code, 302)
        self.assertEqual(EKitapBolum.objects.get(pk=self.sayisal.pk).tespit_durumu, "tamam")
        self.post("/yonetim/cikis/")
        r = self.post("/yonetim/sorulari-bul/")
        self.assertIn("/yonetim/giris/", r["Location"])

    def test_kitap_silinince_soru_gorselleri_diskten_silinir(self):
        yollar = [Path(a.gorsel.path) for a in EKitapSoruAlan.objects.all()]
        self.assertTrue(yollar and all(y.exists() for y in yollar))
        self.post(f"/yonetim/kitap/{self.kitap.pk}/sil/")
        self.assertFalse(any(y.exists() for y in yollar))
        self.assertEqual(EKitapSoru.objects.count(), 0)
