"""Ana sayfa dershane özeti — sınıf zimmetinden grup bulur."""

from __future__ import annotations

from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase

from takip.dershane_program_models import (
    DershaneDersAtamasi,
    DershaneEtutGrubu,
    DershaneProgrami,
    DershaneSaatBloku,
)
from takip.etut_plan_service import dershane_hafta_onizleme
from takip.models import EtutHocasi, SinifSube


class DershaneHaftaOnizlemeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("oniz-admin", "a@b.c", "x")
        self.program = DershaneProgrami.objects.create(
            ad="2026 Dershane",
            baslangic_tarihi=date(2026, 9, 1),
            bitis_tarihi=date(2027, 6, 30),
            aktif=True,
            olusturan=self.user,
        )
        self.grup_a = DershaneEtutGrubu.objects.create(
            program=self.program,
            etiket="8. Sınıf Etüt-A",
            sinif_seviye="8",
            sira=0,
        )
        self.grup_b = DershaneEtutGrubu.objects.create(
            program=self.program,
            etiket="8. Sınıf Etüt-B",
            sinif_seviye="8",
            sira=1,
        )
        self.saat = DershaneSaatBloku.objects.create(
            program=self.program,
            gun=0,
            baslangic_saati=time(8, 30),
            bitis_saati=time(9, 10),
            tur=DershaneSaatBloku.Tur.DERS,
            aciklama="1. ders",
            sira=1,
        )
        DershaneDersAtamasi.objects.create(
            program=self.program,
            saat_bloku=self.saat,
            etut_grubu=self.grup_a,
            ders_adi="Matematik",
        )
        DershaneDersAtamasi.objects.create(
            program=self.program,
            saat_bloku=self.saat,
            etut_grubu=self.grup_b,
            ders_adi="Türkçe",
        )
        self.sinif = SinifSube.objects.create(sinif="8", sube="A")
        hoca_user = User.objects.create_user("oniz-hoca", password="x")
        self.hoca = EtutHocasi.objects.create(
            ad_soyad="Demo Hoca", user=hoca_user, aktif=True
        )
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)

    def _dersler(self, hoca=None):
        gunler = dershane_hafta_onizleme(self.user, hoca or self.hoca)
        return [ders for gun in gunler for ders in gun["dersler"]]

    def test_hoca_fk_bosken_sinif_zimmetinden_gorunur(self):
        self.assertIn("Matematik", self._dersler())
        self.assertNotIn("Türkçe", self._dersler())

    def test_baska_sube_dersini_almaz(self):
        diger_user = User.objects.create_user("oniz-b", password="x")
        diger = EtutHocasi.objects.create(
            ad_soyad="B Şubesi", user=diger_user, aktif=True
        )
        diger.sorumlu_sinif_subeler.add(SinifSube.objects.create(sinif="8", sube="B"))
        dersler = self._dersler(diger)
        self.assertIn("Türkçe", dersler)
        self.assertNotIn("Matematik", dersler)

    def test_dogrudan_hoca_bagi_sinifi_ezer(self):
        self.grup_b.etut_hocasi = self.hoca
        self.grup_b.save(update_fields=["etut_hocasi"])
        dersler = self._dersler()
        self.assertEqual(dersler, ["Türkçe"])
