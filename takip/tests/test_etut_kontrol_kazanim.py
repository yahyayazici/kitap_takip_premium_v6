"""Etüt Kontrol + KonuKazanimDetay import smoke tests."""

from __future__ import annotations

import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from openpyxl import Workbook

from takip.deneme_excel import talebe_eslestir
from takip.deneme_kazanim_excel import import_kazanim_excel
from takip.deneme_models import DenemeKazanimSonucu, DenemeSinavi, DenemeSonucu
from takip.deneme_service import deneme_sinavini_sil
from takip.etut_kontrol_service import (
    deneme_ortalama,
    etut_deneme_kutulari,
    etut_dikkat,
    etut_gelisim_serisi,
    etut_gorunum_serisi,
    hoca_seviye_kirilimi,
    kullanici_etut_hocalari,
    talebe_gelisim_serisi,
)
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

    def test_mesul_baska_etudu_gormez_admin_hepsini_gorur(self):
        diger_user = User.objects.create_user("hoca2", password="x", is_staff=True)
        diger = EtutHocasi.objects.create(user=diger_user, ad_soyad="Başka Hoca", aktif=True)
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        kendi = kullanici_etut_hocalari(self.user)
        self.assertEqual([h.id for h in kendi], [self.hoca.id])

        admin = User.objects.create_superuser("admin1", "a@b.c", "x")
        hepsi = {h.id for h in kullanici_etut_hocalari(admin)}
        self.assertIn(self.hoca.id, hepsi)
        self.assertIn(diger.id, hepsi)

        yabanci = User.objects.create_user("yabanci", password="x", is_staff=True)
        self.assertEqual(kullanici_etut_hocalari(yabanci), [])

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
        DenemeSonucu.objects.create(deneme=self.deneme, talebe=self.talebe, puan=Decimal("420.00"))
        gelisim = etut_gelisim_serisi(self.hoca)
        self.assertEqual(gelisim["labels"], ["1. Deneme"])
        self.assertEqual(gelisim["sinif"], [420.0])
        kutular = etut_deneme_kutulari(self.hoca)
        self.assertEqual(len(kutular), 1)
        self.assertEqual(kutular[0]["etut_ortalama"], Decimal("420.00"))

    def test_kazanim_yeniden_yukleme_eskisini_siler(self):
        import_kazanim_excel(
            _sample_xlsx([("8-A", "Ali Veli", 65, "5/8", 80, "7/8")]),
            deneme=self.deneme,
        )
        ilk = DenemeKazanimSonucu.objects.filter(deneme=self.deneme).count()
        self.assertGreaterEqual(ilk, 1)
        import_kazanim_excel(
            _sample_xlsx([("8-A", "Ali Veli", 40, "2/8", 90, "8/8")]),
            deneme=self.deneme,
        )
        self.assertEqual(
            DenemeKazanimSonucu.objects.filter(deneme=self.deneme).count(),
            ilk,
        )
        kesir = DenemeKazanimSonucu.objects.get(
            deneme=self.deneme, talebe=self.talebe, konu_key="kesirler"
        )
        self.assertEqual(kesir.yuzde, Decimal("40"))

    def test_katilmayan_sifir_sayilmaz_ve_grafikte_bosluk_kalir(self):
        diger = Talebe.objects.create(
            ad_soyad="Ayse Yilmaz",
            sinif="8",
            sube="A",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            aktif=True,
            durum=Talebe.Durum.AKTIF,
        )
        ikinci = DenemeSinavi.objects.create(
            ad="2. Deneme",
            sinav_tarihi=date(2026, 4, 1),
            sinif_seviyesi="8",
            durum=DenemeSinavi.Durum.AKTIF,
        )
        DenemeSonucu.objects.create(deneme=self.deneme, talebe=self.talebe, puan=Decimal("400"))
        DenemeSonucu.objects.create(deneme=self.deneme, talebe=diger, puan=Decimal("0"))
        DenemeSonucu.objects.create(deneme=ikinci, talebe=diger, puan=Decimal("450"))
        self.assertEqual(deneme_ortalama(self.deneme, [self.talebe.id, diger.id]), Decimal("400"))
        seri = talebe_gelisim_serisi(self.talebe)
        self.assertEqual(seri["puanlar"], [400.0, None])

    def test_dikkat_ayni_kazanimli_denemeler(self):
        import_kazanim_excel(
            _sample_xlsx([("8-A", "Ali Veli", 50, "4/8", 80, "7/8")]),
            deneme=self.deneme,
        )
        DenemeSonucu.objects.create(deneme=self.deneme, talebe=self.talebe, puan=Decimal("400"))
        kazanim_siz = DenemeSinavi.objects.create(
            ad="Puan denemesi",
            sinav_tarihi=date(2026, 5, 1),
            sinif_seviyesi="8",
            durum=DenemeSinavi.Durum.AKTIF,
        )
        DenemeSonucu.objects.create(deneme=kazanim_siz, talebe=self.talebe, puan=Decimal("300"))
        dikkat = etut_dikkat(self.hoca)
        self.assertEqual(dikkat["deneme"].id, self.deneme.id)
        self.assertIsNone(dikkat["onceki_deneme"])
        self.assertEqual(dikkat["dusen_talebeler"], [])

    def test_ayni_talebe_ayni_denemede_tek_sonuc(self):
        DenemeSonucu.objects.create(deneme=self.deneme, talebe=self.talebe, puan=Decimal("10"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DenemeSonucu.objects.create(deneme=self.deneme, talebe=self.talebe, puan=Decimal("20"))

    def test_yanlis_sinif_otomatik_eslesmez(self):
        talebe, tip, _ = talebe_eslestir("Ali Veli", "8-B")
        self.assertIsNone(talebe)
        self.assertNotEqual(tip, "otomatik")

    def test_top_left_cell_exceli_kabul_eder(self):
        xlsx = _sample_xlsx([("8-A", "Ali Veli", 65, "5/8", 80, "7/8")])
        raw = xlsx.getvalue()
        out = BytesIO()
        with zipfile.ZipFile(BytesIO(raw)) as src, zipfile.ZipFile(out, "w") as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename.startswith("xl/worksheets/sheet"):
                    text = data.decode()
                    text = text.replace(
                        '<selection activeCell="A1" sqref="A1" />',
                        '<selection activeCell="A1" sqref="A1" topLeftCell="A1"/>',
                    )
                    data = text.encode()
                dst.writestr(info, data)
        out.seek(0)
        out.name = "KonuKazanimDetay_topLeft.xlsx"
        stats = import_kazanim_excel(out, deneme=self.deneme)
        self.assertGreaterEqual(stats.sonuc_yazilan, 1)

    def test_seviye_geneli_ve_sube_cizgileri(self):
        sinif_a = SinifSube.objects.create(sinif="7", sube="A", aktif=True)
        sinif_b = SinifSube.objects.create(sinif="7", sube="B", aktif=True)
        self.hoca.sorumlu_sinif_subeler.add(sinif_a, sinif_b)
        a = Talebe.objects.create(
            ad_soyad="Yedi A", sinif="7", sube="A", sinif_sube=sinif_a,
            etut_hocasi=self.hoca, aktif=True, durum=Talebe.Durum.AKTIF,
        )
        b = Talebe.objects.create(
            ad_soyad="Yedi B", sinif="7", sube="B", sinif_sube=sinif_b,
            etut_hocasi=self.hoca, aktif=True, durum=Talebe.Durum.AKTIF,
        )
        deneme = DenemeSinavi.objects.create(
            ad="7 deneme", sinav_tarihi=date(2026, 6, 1),
            sinif_seviyesi="7", durum=DenemeSinavi.Durum.AKTIF,
        )
        DenemeSonucu.objects.create(deneme=deneme, talebe=a, puan=Decimal("300"))
        DenemeSonucu.objects.create(deneme=deneme, talebe=b, puan=Decimal("500"))
        kirilim = hoca_seviye_kirilimi(self.hoca)
        self.assertEqual(kirilim["seviye"], "7")
        self.assertEqual(len(kirilim["subeler"]), 2)
        genel = etut_gorunum_serisi(self.hoca, kirilim, ayrim=False)
        self.assertEqual(genel["seriler"][0]["degerler"], [400.0])
        ayrik = etut_gorunum_serisi(self.hoca, kirilim, ayrim=True)
        self.assertEqual([s["ad"] for s in ayrik["seriler"]], ["7-A", "7-B"])
        self.assertEqual(ayrik["seriler"][0]["degerler"], [300.0])
        self.assertEqual(ayrik["seriler"][1]["degerler"], [500.0])

    def test_silme_arsivler_sonuclari_birakir(self):
        DenemeSonucu.objects.create(deneme=self.deneme, talebe=self.talebe, puan=Decimal("410"))
        deneme_sinavini_sil(self.user, self.deneme)
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.durum, DenemeSinavi.Durum.ARSIV)
        self.assertTrue(DenemeSonucu.objects.filter(deneme=self.deneme).exists())
