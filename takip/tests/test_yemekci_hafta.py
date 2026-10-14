"""Yemekçilik hafta sonu filtresi: cumartesi ve pazar ayrı, hafta içi sırası aynı."""

from datetime import date

from django.test import SimpleTestCase

from takip.yemekci_service import aralik_gunleri, dongu_sira, workday_index


class YemekciHaftaAyriTests(SimpleTestCase):
    bas = date(2026, 10, 12)  # Pazartesi
    bit = date(2026, 10, 19)  # sonraki Pazartesi
    cuma = date(2026, 10, 16)
    cmt = date(2026, 10, 17)
    paz = date(2026, 10, 18)
    pzt = date(2026, 10, 19)

    def test_ikisi_de_cikinca_eski_hafta_ici_sirasi(self):
        gunler = aralik_gunleri(self.bas, self.bit, cumartesi_cikar=True, pazar_cikar=True)
        self.assertEqual(
            gunler,
            [
                date(2026, 10, 12),
                date(2026, 10, 13),
                date(2026, 10, 14),
                date(2026, 10, 15),
                self.cuma,
                self.pzt,
            ],
        )
        self.assertEqual(
            workday_index(self.pzt, self.bas, cumartesi_cikar=True, pazar_cikar=True),
            5,
        )
        self.assertEqual(workday_index(self.pzt, self.bas, True), 5)
        self.assertEqual(workday_index(self.cuma, self.bas, True), 4)

    def test_yalniz_cumartesi_cikar_pazari_siraya_koyar(self):
        gunler = aralik_gunleri(self.bas, self.bit, cumartesi_cikar=True, pazar_cikar=False)
        self.assertNotIn(self.cmt, gunler)
        self.assertIn(self.paz, gunler)
        self.assertEqual(
            workday_index(self.cuma, self.bas, cumartesi_cikar=True, pazar_cikar=False),
            4,
        )
        self.assertEqual(
            workday_index(self.paz, self.bas, cumartesi_cikar=True, pazar_cikar=False),
            5,
        )
        self.assertEqual(
            workday_index(self.pzt, self.bas, cumartesi_cikar=True, pazar_cikar=False),
            6,
        )

    def test_yalniz_pazar_cikar_cumartesiyi_siraya_koyar(self):
        gunler = aralik_gunleri(self.bas, self.bit, cumartesi_cikar=False, pazar_cikar=True)
        self.assertIn(self.cmt, gunler)
        self.assertNotIn(self.paz, gunler)
        self.assertEqual(
            workday_index(self.cuma, self.bas, cumartesi_cikar=False, pazar_cikar=True),
            4,
        )
        self.assertEqual(
            workday_index(self.cmt, self.bas, cumartesi_cikar=False, pazar_cikar=True),
            5,
        )
        self.assertEqual(
            workday_index(self.pzt, self.bas, cumartesi_cikar=False, pazar_cikar=True),
            6,
        )

    def test_dongu_sira_hafta_sonunu_atlayinca_yerinde_kalir(self):
        cuma = dongu_sira(self.cuma, self.bas, 10, cumartesi_cikar=True, pazar_cikar=True)
        self.assertTrue(cuma["gorev_gunu"])
        self.assertEqual(cuma["bugun"], 5)
        self.assertEqual(cuma["kalinan"], 5)
        self.assertEqual(cuma["siradaki"], 6)

        cmt = dongu_sira(self.cmt, self.bas, 10, cumartesi_cikar=True, pazar_cikar=True)
        self.assertFalse(cmt["gorev_gunu"])
        self.assertIsNone(cmt["bugun"])
        self.assertEqual(cmt["kalinan"], 5)
        self.assertEqual(cmt["siradaki"], 6)

        pzt = dongu_sira(self.pzt, self.bas, 10, cumartesi_cikar=True, pazar_cikar=True)
        self.assertEqual(pzt["bugun"], 6)
        self.assertEqual(pzt["siradaki"], 7)

        donus = dongu_sira(self.pzt, self.bas, 5, cumartesi_cikar=True, pazar_cikar=True)
        self.assertEqual(donus["bugun"], 1)
        self.assertEqual(donus["siradaki"], 2)

        bos = dongu_sira(self.cuma, self.bas, 0, cumartesi_cikar=True, pazar_cikar=True)
        self.assertIsNone(bos["kalinan"])
        self.assertIsNone(bos["siradaki"])
        self.assertEqual(bos["toplam"], 0)
