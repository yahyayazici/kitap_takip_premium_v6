"""Etüt Kontrol + KonuKazanimDetay import smoke tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from openpyxl import Workbook

from takip.deneme_kazanim_excel import import_kazanim_excel
from takip.deneme_models import DenemeKazanimSonucu, DenemeSinavi
from takip.etut_kontrol_service import etut_deneme_kutulari, etut_gelisim_serisi
from takip.models import EtutHocasi, SinifSube, Talebe


def _sample_xlsx(rows: list[tuple]) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.append(["", "", "Matematik", "Matematik", "Türkçe", "Türkçe"])
    ws.append(["", "", "Kesirler", "Kesirler", "Paragraf", "Paragraf"])
    ws.append(["Sınıf", "Ad Soyad", "Yüzde", "Net", "Yüzde", "Net"])
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = "KonuKazanimDetay_test.xlsx"
    return buf


class KazanimEtutKontrolTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("hoca1", password="x")
        self.hoca = EtutHocasi.objects.create(
            user=self.user, ad_soyad="Test Hoca", aktif=True
        )
        self.sinif = SinifSube.objects.create(sinif="8", sube="A", aktif=True)
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.talebe = Talebe.objects.create(
            ad_soyad="Ali Veli",
            sinif="8",
            sube="A",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            aktif=True,
            durum=Talebe.Durum.AKTIF,
        )
        self.deneme = DenemeSinavi.objects.create(
            ad="1. Deneme",
            sinav_tarihi=date(2026, 3, 1),
            sinif_seviyesi="8",
            durum=DenemeSinavi.Durum.AKTIF,
        )

    def test_import_and_etut_boxes(self):
        xlsx = _sample_xlsx(
            [
                ("8-A", "Ali Veli", 65, "5/8", 80, "7/8"),
            ]
        )
        stats = import_kazanim_excel(xlsx, deneme=self.deneme)
        self.assertGreaterEqual(stats.sonuc_yazilan, 1)
        self.assertEqual(stats.eslesen_talebe, 1)
        self.assertTrue(
            DenemeKazanimSonucu.objects.filter(
                deneme=self.deneme, talebe=self.talebe
            ).exists()
        )
        gelisim = etut_gelisim_serisi(self.hoca)
        self.assertEqual(len(gelisim["labels"]), 1)
        kutular = etut_deneme_kutulari(self.hoca)
        self.assertEqual(len(kutular), 1)
        self.assertIsInstance(kutular[0]["etut_ortalama"], Decimal)
