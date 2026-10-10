import io
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.ktt_models import KttSinav, KttSonucu
from takip.models import Ders, EtutHocasi, SinifSube, Talebe
def _pdf_sayfa_sayisi(veri: bytes) -> int:
    import pypdfium2 as pdfium

    return len(pdfium.PdfDocument(io.BytesIO(veri)))


class KttDetayPdfTests(TestCase):
    def setUp(self):
        self.sinif = SinifSube.objects.create(sinif="7", sube="A")
        self.ders = Ders.objects.create(ad="Paragraf", sira=2, aktif=True)
        user = User.objects.create_user("ktt-detay-hoca", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Detay Hoca", user=user)
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.ktt = KttSinav.objects.create(
            ad="Paragrafta Yardımcı Düşünce",
            ders=self.ders,
            sinif_seviyesi="7",
            hedef_siniflar="7-A, 7-B",
            sinav_tarihi=date(2026, 9, 22),
            soru_sayisi=20,
            etut_hocasi=self.hoca,
        )

    def _sonuc(self, sira, dogru):
        talebe = Talebe.objects.create(
            ad_soyad=f"Talebe {sira:02d} Deneme",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
        )
        yanlis = 20 - dogru
        KttSonucu.objects.create(
            ktt=self.ktt,
            talebe=talebe,
            dogru=dogru,
            yanlis=yanlis,
            bos=0,
        )

    def test_yirmi_dort_kisi_tek_sayfada_tek_sutun(self):
        for sira in range(1, 25):
            self._sonuc(sira, 20 - (sira % 8))
        user = User.objects.create_superuser("ktt-detay-super", password="x")
        self.client.force_login(user)
        yanit = self.client.get(reverse("ktt_detay_pdf", args=[self.ktt.pk]))
        self.assertEqual(yanit.status_code, 200)
        self.assertEqual(yanit["Content-Type"], "application/pdf")
        self.assertEqual(_pdf_sayfa_sayisi(yanit.content), 1)
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        from django.utils.timezone import now
        from takip.ktt_views import _ktt_sonuc_ozeti

        sonuclar = list(self.ktt.sonuclar.select_related("talebe"))
        rf = RequestFactory()
        request = rf.get("/", HTTP_HOST="127.0.0.1")
        request.user = user
        html = render_to_string(
            "ktt_detay_pdf.html",
            {
                "ktt": self.ktt,
                "sonuclar": sonuclar,
                "sonuclar_sol": sonuclar,
                "sonuclar_sag": [],
                "sonuc_split": False,
                "split_at": 24,
                "ozet": _ktt_sonuc_ozeti(sonuclar),
                "olusturma_tarihi": now(),
            },
            request=request,
        )
        self.assertIn("Paragrafta Yardımcı Düşünce", html)
        self.assertIn("cinili-saray-logo-white.png", html)
        self.assertIn("linearGradient", html)
        self.assertIn("olcu-sayi altin", html)
        self.assertIn("yanlis", html)
        self.assertNotIn("ktt-split-layout", html)
        self.assertNotIn('class="bol"', html)
        self.assertEqual(html.count("Deneme"), 24)

    def test_yirmi_bes_kisi_iki_sutuna_bolunur(self):
        for sira in range(1, 26):
            self._sonuc(sira, 12)
        user = User.objects.create_superuser("ktt-detay-super-25", password="x")
        self.client.force_login(user)
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        from django.utils.timezone import now
        from takip.ktt_views import _ktt_sonuc_ozeti

        sonuclar = list(
            self.ktt.sonuclar.select_related("talebe").order_by("-puan", "-net", "talebe__ad_soyad")
        )
        split_at = (len(sonuclar) + 1) // 2
        rf = RequestFactory()
        request = rf.get("/", HTTP_HOST="127.0.0.1")
        request.user = user
        html = render_to_string(
            "ktt_detay_pdf.html",
            {
                "ktt": self.ktt,
                "sonuclar": sonuclar,
                "sonuclar_sol": sonuclar[:split_at],
                "sonuclar_sag": sonuclar[split_at:],
                "sonuc_split": True,
                "split_at": split_at,
                "ozet": _ktt_sonuc_ozeti(sonuclar),
                "olusturma_tarihi": now(),
            },
            request=request,
        )
        self.assertIn('class="bol"', html)
        self.assertIn("dokum-kompakt", html)
