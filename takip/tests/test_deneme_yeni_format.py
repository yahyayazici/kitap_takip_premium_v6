"""Yeni yükleme formatları: SinavSonucListe, Konu Analizi karnesi, KonuKazanimYuzdeAnalizi."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from openpyxl import Workbook

from takip.deneme_excel import deneme_excel_onizle, deneme_sonuclari_aktar
from takip.deneme_kazanim_excel import import_kazanim_excel
from takip.deneme_models import DenemeKazanimSonucu, DenemeSinavi, DenemeSonucu
from takip.deneme_service import deneme_bireysel_karne, deneme_karne_ortalamalari
from takip.deneme_soru_karne import _kimlik_ust, _Parca
from takip.models import EtutHocasi, SinifSube, Talebe

BASLIK = [
    "S.No", "Öğrenci No", "Ad Soyad", "Sınıf-Şube",
    "TURK D", "TURK Y", "TURK N", "INK D", "INK Y", "INK N",
    "Din K. D", "Din K. Y", "Din K. N", "ING D", "ING Y", "ING N",
    "MAT D", "MAT Y", "MAT N", "FEN D", "FEN Y", "FEN N",
    "Toplam D", "Toplam Y", "Toplam N", "Puan", "Genel Sıra", "Genel",
    "FirmaSube", "Sinif", "Sube", "Il", "Ilce", "MebOkul", "OkulTur",
]


def _xlsx(satirlar: list[list]) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    for satir in satirlar:
        ws.append(satir)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _sinav_sonuc_liste() -> BytesIO:
    return _xlsx(
        [
            ["ÇİNİLİ SARAY ÖĞRENCİ YURDU"],
            ["DOĞRU TAHMİN - 8.SINIF TURUNCU KUŞAK 1"],
            ["06.10.2026"],
            [],
            BASLIK,
            [1, "", "Ali Veli Kaya", "8 - A",
             20, 0, 20, 10, 0, 10, 8, 2, 7.33, 10, 0, 10,
             19, 1, 18.67, 20, 0, 20, 87, 3, 86, 489.01,
             1, 1, 1, 1, 1, 1, 1, None, None],
            [2, "", "Can Ak", "8 - A",
             13, 7, 10.67, 8, 2, 7.33, 8, 2, 7.33, 3, 3, 2,
             6, 3, 5, 15, 5, 13.33, 53, 22, 45.66, 343.76,
             145, 145, 2, 2, 2, 142, 41, None, None],
            ["Ortalama", "", "", "", 16.5, 3.5, 15.3],
        ]
    )


class SinavSonucListeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("yeni-format", "a@b.com", "x")
        hoca = EtutHocasi.objects.create(ad_soyad="Hoca", user=self.user)
        sinif = SinifSube.objects.create(sinif="8", sube="A")
        hoca.sorumlu_sinif_subeler.add(sinif)
        ortak = {"sinif_sube": sinif, "etut_hocasi": hoca, "dini_ders_hocasi": hoca}
        self.ali = Talebe.objects.create(ad_soyad="Ali Veli Kaya", **ortak)
        self.can = Talebe.objects.create(ad_soyad="Can Ak", **ortak)
        self.deneme = DenemeSinavi.objects.create(
            ad="Doğru Tahmin 1",
            sinav_tarihi=date(2026, 10, 6),
            sinif_seviyesi="8",
            olusturan=self.user,
        )

    def test_ust_bilgi_atlanir_kisaltmalar_okunur(self):
        onizleme = deneme_excel_onizle(_sinav_sonuc_liste())
        self.assertEqual(onizleme.hatalar, [])
        self.assertEqual(len(onizleme.satirlar), 2)
        ali, can = onizleme.satirlar
        self.assertEqual(ali.talebe_id, self.ali.id)
        self.assertEqual(ali.sinif, "8 - A")
        self.assertEqual(ali.puan, "489.01")
        self.assertEqual(
            ali.branslar["din"], {"dogru": 8, "yanlis": 2, "bos": 0, "net": "7.33"}
        )
        self.assertEqual(ali.branslar["sosyal"]["dogru"], 10)
        self.assertEqual(ali.branslar["ingilizce"]["net"], "10.00")
        self.assertEqual(ali.toplam, {"dogru": 87, "yanlis": 3, "bos": 0, "net": "86.00"})
        # Boş sütunu yok: dersin soru sayısından (en çok D+Y) hesaplanır
        self.assertEqual(can.branslar["matematik"]["bos"], 11)
        self.assertEqual(can.branslar["ingilizce"]["bos"], 4)
        self.assertEqual(can.toplam["bos"], 15)
        self.assertEqual(
            can.dis_siralama,
            {
                "Genel Sıra": "145",
                "Şube Sırası": "2",
                "İl Sırası": "142",
                "İlçe Sırası": "41",
            },
        )

    def test_aktarim_ve_karne(self):
        onizleme = deneme_excel_onizle(_sinav_sonuc_liste())
        sayi, hatalar = deneme_sonuclari_aktar(self.deneme, onizleme, self.user)
        self.assertEqual((sayi, hatalar), (2, []))
        sonuc = (
            DenemeSonucu.objects.filter(deneme=self.deneme, talebe=self.can)
            .select_related("talebe", "talebe__sinif_sube")
            .prefetch_related("brans_satirlari")
            .get()
        )
        self.assertEqual(sonuc.puan, Decimal("343.76"))
        self.assertEqual(sonuc.toplam_bos, 15)
        karne = deneme_bireysel_karne(
            self.deneme, sonuc, deneme_karne_ortalamalari(self.deneme)
        )
        mat = next(d for d in karne["dersler"] if d["ad"].lower().startswith("mat"))
        self.assertEqual(mat["soru"], 20)
        siralar = {s["ad"]: s for s in karne["siralama"]}
        self.assertEqual(siralar["GENEL"]["sira"], "145")
        self.assertEqual(siralar["ŞUBE"]["sira"], "2")
        self.assertEqual(karne["deneme_sirasi"], "2")


class KonuAnaliziKarneTests(SimpleTestCase):
    def test_ad_ve_sinif_sag_ust_basliktan(self):
        segmentler = [
            _Parca("Konu Analizi", 15, 89, 823),
            _Parca("Ali Veli Kaya - 8/A", 413, 580, 821),
            _Parca("Türkçe", 18, 43, 803),
        ]
        self.assertEqual(_kimlik_ust(segmentler, "", ""), ("Ali Veli Kaya", "8-A"))

    def test_ad_ayri_parcada(self):
        segmentler = [
            _Parca("Konu Analizi", 15, 89, 823),
            _Parca("Can Ak", 466, 549, 822.6),
            _Parca("- 8/A", 554, 580, 821),
            _Parca("Türkçe", 18, 43, 803),
        ]
        self.assertEqual(_kimlik_ust(segmentler, "", ""), ("Can Ak", "8-A"))


class KonuKazanimYuzdeAnaliziTests(TestCase):
    def setUp(self):
        user = User.objects.create_superuser("kazanim-yeni", "a@b.com", "x")
        hoca = EtutHocasi.objects.create(ad_soyad="Hoca", user=user)
        sinif = SinifSube.objects.create(sinif="8", sube="A")
        hoca.sorumlu_sinif_subeler.add(sinif)
        self.ali = Talebe.objects.create(
            ad_soyad="Ali Veli Kaya",
            sinif_sube=sinif,
            etut_hocasi=hoca,
            dini_ders_hocasi=hoca,
        )
        self.deneme = DenemeSinavi.objects.create(
            ad="Doğru Tahmin 1",
            sinav_tarihi=date(2026, 10, 6),
            sinif_seviyesi="8",
            olusturan=user,
        )

    def test_bloklar_okunur(self):
        basliklar = ["Öğrenci", "Şube", "Doğru %", "Doğru", "Yanlış", "Boş", "Net", "Toplam"]
        dosya = _xlsx(
            [
                ["KONU KAZANIM YÜZDE ANALİZİ"],
                [],
                ["Türkçe > T.8.2. KONUŞMA"],
                basliklar,
                ["ALİ VELİ KAYA", "8-A", 25, 1, 3, 0, 0, 4],
                ["MİSAFİR ÖĞRENCİ", "8-A", 50, 2, 2, 0, 1.33, 4],
                [],
                [],
                ["Matematik > M.8.1.1. Çarpanlar ve Katlar"],
                basliklar,
                ["ALİ VELİ KAYA", "8-A", 30.77, 4, 2, 7, 3.33, 13],
            ]
        )
        stats = import_kazanim_excel(dosya, deneme=self.deneme)
        self.assertEqual(stats.sonuc_yazilan, 2)
        self.assertEqual(stats.konu_sayisi, 2)
        self.assertEqual(stats.eslesen_talebe, 1)
        self.assertEqual(stats.eslesmeyen, ["MİSAFİR ÖĞRENCİ (8-A)"])
        mat = DenemeKazanimSonucu.objects.get(talebe=self.ali, ders_ad="Matematik")
        self.assertEqual(mat.konu_ad, "M.8.1.1. Çarpanlar ve Katlar")
        self.assertEqual(mat.yuzde, Decimal("30.77"))
        self.assertEqual(mat.net_dogru, Decimal("3.33"))
        self.assertEqual(mat.net_toplam, Decimal("13"))
        turkce = DenemeKazanimSonucu.objects.get(talebe=self.ali, ders_ad="Türkçe")
        self.assertEqual(turkce.konu_ad, "T.8.2. KONUŞMA")
        self.assertEqual(turkce.net_dogru, Decimal("0"))
