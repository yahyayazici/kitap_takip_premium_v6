"""Analitik Okuma değerlendirme alanları — öğretmen, veli, yönetim."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import localdate

from takip.analitik_okuma import (
    ANALITIK_OKUMA_KOD,
    AnalitikAlan,
    AnalitikKayitDurumu,
    GELMEDI_NOTU,
    bir_ondalik,
    ders_analitik_okuma_mi,
)
from takip.analitik_okuma_service import (
    kavram_ortalamasi,
    talebe_analitik_alan_ozeti,
)
from takip.models import Ders, EtutHocasi, SinifSube, Talebe
from takip.ogretmen_not_models import OgretmenHaftalikKonu, OgretmenSinavNotu
from takip.ogretmen_not_service import ogretmen_not_kaydet
from takip.ogretmen_odeme_models import OgretmenOdemeProfili
from takip.veli_hesap_util import veli_panel_ensure
from takip.wave0_models import Brans


def _post(data: dict) -> QueryDict:
    q = QueryDict(mutable=True)
    for key, value in data.items():
        if isinstance(value, (list, tuple)):
            q.setlist(key, [str(v) for v in value])
        else:
            q[key] = "" if value is None else str(value)
    return q


@patch("takip.ogretmen_not_service.hafta_yazilabilir_mi", return_value=True)
class AnalitikOkumaDegerlendirmeTests(TestCase):
    def setUp(self):
        self.brans_ao, _ = Brans.objects.get_or_create(
            ad="Analitik", defaults={"sira": 1, "aktif": True}
        )
        self.brans_mat, _ = Brans.objects.get_or_create(
            ad="Matematik", defaults={"sira": 2, "aktif": True}
        )
        self.ao = Ders.objects.create(
            ad="Analitik Okuma",
            kod=ANALITIK_OKUMA_KOD,
            brans=self.brans_ao,
            sira=1,
            aktif=True,
        )
        self.mat = Ders.objects.create(
            ad="Matematik",
            kod="matematik",
            brans=self.brans_mat,
            sira=2,
            aktif=True,
        )
        self.sinif = SinifSube.objects.create(sinif="6", sube="A")
        self.diger_sinif = SinifSube.objects.create(sinif="6", sube="B")

        self.ao_user = User.objects.create_user("ao-ogretmen", password="x")
        self.ao_hoca = EtutHocasi.objects.create(
            ad_soyad="Analitik Öğretmen", user=self.ao_user, aktif=True
        )
        self.ao_hoca.sorumlu_sinif_subeler.add(self.sinif)
        OgretmenOdemeProfili.objects.create(
            etut_hocasi=self.ao_hoca, brans=self.brans_ao, aktif=True
        )

        self.mat_user = User.objects.create_user("mat-ogretmen", password="x")
        self.mat_hoca = EtutHocasi.objects.create(
            ad_soyad="Matematik Öğretmen", user=self.mat_user, aktif=True
        )
        self.mat_hoca.sorumlu_sinif_subeler.add(self.sinif)
        OgretmenOdemeProfili.objects.create(
            etut_hocasi=self.mat_hoca, brans=self.brans_mat, aktif=True
        )

        self.talebe = Talebe.objects.create(
            ad_soyad="Ahmed Arif Küçük",
            sinif_sube=self.sinif,
            etut_hocasi=self.ao_hoca,
            dini_ders_hocasi=self.ao_hoca,
            tc_kimlik="10000000016",
        )
        self.talebe2 = Talebe.objects.create(
            ad_soyad="Faruk Selim Kara",
            sinif_sube=self.sinif,
            etut_hocasi=self.ao_hoca,
            dini_ders_hocasi=self.ao_hoca,
            tc_kimlik="10000000113",
        )

    def _tamamla(self, hoca, ders, *, yok_ids=None, puan=85, kavram=9, aciklama="İyi takip"):
        yok_ids = yok_ids or []
        data = {
            "ders_id": ders.id,
            "kayit_modu": "tamamla",
            "analitik_alan": AnalitikAlan.CIKARIM,
            "yok_talebe": yok_ids,
            f"katilim_{self.talebe.id}": "" if self.talebe.id in yok_ids else str(puan),
            f"kavram_{self.talebe.id}": "" if self.talebe.id in yok_ids else str(kavram),
            f"aciklama_{self.talebe.id}": GELMEDI_NOTU if self.talebe.id in yok_ids else aciklama,
            f"katilim_{self.talebe2.id}": "70",
            f"kavram_{self.talebe2.id}": "8",
            f"aciklama_{self.talebe2.id}": "Grafikteki verileri okudu.",
        }
        if self.talebe2.id in yok_ids:
            data[f"katilim_{self.talebe2.id}"] = ""
            data[f"kavram_{self.talebe2.id}"] = ""
            data[f"aciklama_{self.talebe2.id}"] = GELMEDI_NOTU
        return ogretmen_not_kaydet(hoca, self.sinif.id, _post(data))

    def test_ders_kodu_ile_tanimlanir(self, _mock):
        self.assertTrue(ders_analitik_okuma_mi(self.ao))
        self.assertFalse(ders_analitik_okuma_mi(self.mat))

    def test_ogretmen_yetkili_sinifta_alanlari_gorur(self, _mock):
        self.client.force_login(self.ao_user)
        url = reverse("ogretmen_not_girisi_sinif", args=[self.sinif.id])
        res = self.client.get(url, {"ders": self.ao.id})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Kavram Öğretimi")
        self.assertContains(res, "Gelmedi")
        self.assertNotContains(res, "Haftanın kavramı")
        self.assertContains(res, "Analitik Okuma Puanı")
        self.assertContains(res, "Çıkarım Yapma ve Derin Anlama")

    def test_atanmamis_ogretmen_erisemez(self, _mock):
        self.client.force_login(self.mat_user)
        url = reverse("ogretmen_not_girisi_sinif", args=[self.sinif.id])
        res = self.client.get(url, {"ders": self.ao.id})
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "Haftanın kavramı")
        hatalar, _ = ogretmen_not_kaydet(
            self.mat_hoca,
            self.sinif.id,
            _post({"ders_id": self.ao.id, "kayit_modu": "tamamla"}),
        )
        self.assertTrue(hatalar)

    def test_yetkisiz_sinif_kaydedilemez(self, _mock):
        hatalar, _ = ogretmen_not_kaydet(
            self.ao_hoca,
            self.diger_sinif.id,
            _post({"ders_id": self.ao.id, "kayit_modu": "taslak"}),
        )
        self.assertIn("yetkiniz yok", " ".join(hatalar))

    def test_diger_derste_analitik_alanlari_yok(self, _mock):
        self.client.force_login(self.mat_user)
        url = reverse("ogretmen_not_girisi_sinif", args=[self.sinif.id])
        res = self.client.get(url, {"ders": self.mat.id})
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "Kavram Öğretimi")
        self.assertNotContains(res, "Haftanın kavramı")
        self.assertContains(res, "Katılım (30%)")

    def test_mevcut_puan_alani_kullanilir(self, _mock):
        hatalar, _ = self._tamamla(self.ao_hoca, self.ao)
        self.assertEqual(hatalar, [])
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.ao)
        self.assertEqual(notu.katilim, Decimal("85"))
        self.assertEqual(notu.takip, Decimal("85"))
        self.assertEqual(notu.disiplin, Decimal("85"))
        self.assertEqual(notu.puan, Decimal("85.00"))
        self.assertFalse(hasattr(notu, "analitik_puani"))

    def test_degerlendirme_notu_korunur(self, _mock):
        self._tamamla(self.ao_hoca, self.ao, aciklama="Örtülü anlamları fark ediyor.")
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.ao)
        self.assertEqual(notu.aciklama, "Örtülü anlamları fark ediyor.")

    def test_gelmedi_mevcut_yoklama_ile(self, _mock):
        self._tamamla(self.ao_hoca, self.ao, yok_ids=[self.talebe.id])
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.ao)
        self.assertIsNone(notu.puan)
        self.assertIsNone(notu.kavram_puani)
        self.assertEqual(notu.aciklama, GELMEDI_NOTU)

    def test_katilan_puan_ve_kavram_kaydedilir(self, _mock):
        self._tamamla(self.ao_hoca, self.ao, puan=85, kavram=9)
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.ao)
        self.assertEqual(notu.kavram_puani, 9)
        self.assertEqual(int(notu.puan), 85)

    def test_kavram_1_10_disi_reddedilir(self, _mock):
        data = _post(
            {
                "ders_id": self.ao.id,
                "kayit_modu": "tamamla",
                "analitik_alan": AnalitikAlan.GORSEL,
                f"katilim_{self.talebe.id}": "80",
                f"kavram_{self.talebe.id}": "11",
                f"aciklama_{self.talebe.id}": "Not",
                f"katilim_{self.talebe2.id}": "70",
                f"kavram_{self.talebe2.id}": "8",
                f"aciklama_{self.talebe2.id}": "Not",
            }
        )
        hatalar, _ = ogretmen_not_kaydet(self.ao_hoca, self.sinif.id, data)
        self.assertTrue(any("1–10" in h or "1-10" in h for h in hatalar))
        notu = OgretmenSinavNotu(
            talebe=self.talebe,
            etut_hocasi=self.ao_hoca,
            ders=self.ao,
            hafta_baslangic=localdate(),
            kavram_puani=11,
        )
        with self.assertRaises(IntegrityError):
            notu.save()

    def test_gelmeyen_ortalamaya_katilmaz(self, _mock):
        self._tamamla(self.ao_hoca, self.ao, yok_ids=[self.talebe.id], kavram=8)
        self.assertIsNone(kavram_ortalamasi(self.talebe, ders=self.ao))
        self.assertEqual(kavram_ortalamasi(self.talebe2, ders=self.ao), Decimal("8"))

    def test_taslak_eksik_alana_izin_verir(self, _mock):
        hatalar, meta = ogretmen_not_kaydet(
            self.ao_hoca,
            self.sinif.id,
            _post({"ders_id": self.ao.id, "kayit_modu": "taslak"}),
        )
        self.assertEqual(hatalar, [])
        self.assertFalse(meta["tamamlandi"])
        konu = OgretmenHaftalikKonu.objects.get(ders=self.ao, sinif_sube=self.sinif)
        self.assertEqual(konu.durum, AnalitikKayitDurumu.TASLAK)
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.ao)
        self.assertFalse(notu.veliye_goster)

    def test_tamamlama_eksik_alani_reddeder(self, _mock):
        hatalar, meta = ogretmen_not_kaydet(
            self.ao_hoca,
            self.sinif.id,
            _post(
                {
                    "ders_id": self.ao.id,
                    "kayit_modu": "tamamla",
                    "analitik_alan": AnalitikAlan.SOZEL,
                    f"katilim_{self.talebe.id}": "80",
                    f"aciklama_{self.talebe.id}": "Not",
                    f"katilim_{self.talebe2.id}": "70",
                    f"kavram_{self.talebe2.id}": "8",
                    f"aciklama_{self.talebe2.id}": "Not",
                }
            ),
        )
        self.assertTrue(any("Kavram Öğretimi" in h and "Ahmed" in h for h in hatalar))
        self.assertIn(self.talebe.id, meta["hata_talebe_ids"])

    def test_tek_ana_baslik_secilir(self, _mock):
        self._tamamla(self.ao_hoca, self.ao)
        konu = OgretmenHaftalikKonu.objects.get(ders=self.ao, sinif_sube=self.sinif)
        self.assertEqual(konu.analitik_alan, AnalitikAlan.CIKARIM)
        self.assertEqual(konu.haftanin_kavrami, "")

    def test_alan_ortalari_ayri_hesaplanir(self, _mock):
        self._tamamla(self.ao_hoca, self.ao)
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.ao)
        notu.hafta_baslangic = notu.hafta_baslangic - timedelta(days=7)
        notu.katilim = notu.takip = notu.disiplin = Decimal("70")
        notu.save()
        OgretmenHaftalikKonu.objects.filter(
            ders=self.ao, sinif_sube=self.sinif, etut_hocasi=self.ao_hoca
        ).update(
            hafta_baslangic=notu.hafta_baslangic,
            analitik_alan=AnalitikAlan.SOZEL,
        )
        self._tamamla(self.ao_hoca, self.ao, puan=90, kavram=10)
        ozet = {s["kod"]: s for s in talebe_analitik_alan_ozeti(self.talebe)}
        self.assertEqual(ozet[AnalitikAlan.SOZEL]["adet"], 1)
        self.assertEqual(ozet[AnalitikAlan.CIKARIM]["adet"], 1)
        self.assertEqual(ozet[AnalitikAlan.SOZEL]["ortalama"], Decimal("70.00"))
        self.assertEqual(ozet[AnalitikAlan.CIKARIM]["ortalama"], Decimal("90.00"))

    def test_kavram_ortalamasi_bir_ondalik(self, _mock):
        self._tamamla(self.ao_hoca, self.ao, kavram=8)
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.ao)
        eski_hafta = notu.hafta_baslangic - timedelta(days=7)
        OgretmenSinavNotu.objects.create(
            talebe=self.talebe,
            etut_hocasi=self.ao_hoca,
            ders=self.ao,
            hafta_baslangic=eski_hafta,
            katilim=80,
            takip=80,
            disiplin=80,
            kavram_puani=9,
            veliye_goster=True,
        )
        ham = kavram_ortalamasi(self.talebe, ders=self.ao)
        self.assertEqual(ham, Decimal("8.5"))
        self.assertEqual(bir_ondalik(ham), "8,5")

    def test_ayni_oturum_ikinci_kayit_olusturmaz(self, _mock):
        h1, _ = self._tamamla(self.ao_hoca, self.ao, puan=80, kavram=7)
        self.assertEqual(h1, [])
        h2, meta = self._tamamla(self.ao_hoca, self.ao, puan=90, kavram=10)
        self.assertEqual(h2, [])
        self.assertEqual(
            OgretmenSinavNotu.objects.filter(talebe=self.talebe, ders=self.ao).count(),
            1,
        )
        self.assertEqual(
            OgretmenHaftalikKonu.objects.filter(ders=self.ao, sinif_sube=self.sinif).count(),
            1,
        )
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.ao)
        self.assertEqual(int(notu.puan), 90)

    def test_taslak_velide_gorunmez_tamamlanan_gorunur(self, _mock):
        ogretmen_not_kaydet(
            self.ao_hoca,
            self.sinif.id,
            _post({"ders_id": self.ao.id, "kayit_modu": "taslak"}),
        )
        sonuc = veli_panel_ensure(self.talebe, "10000000016", "Veli Ahmed")
        self.assertTrue(sonuc.basarili)
        veli_user = User.objects.get(username="10000000016")
        self.client.force_login(veli_user)
        url = reverse("veli_talebe_ders_notlari", args=[self.talebe.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "Haftanın kavramı")
        h, meta = self._tamamla(self.ao_hoca, self.ao)
        self.assertEqual(h, [])
        self.assertTrue(meta["tamamlandi"])
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.ao)
        self.assertTrue(notu.veliye_goster)
        self.assertEqual(int(notu.puan), 85)
        res = self.client.get(url)
        self.assertContains(res, "Çıkarım Yapma ve Derin Anlama")
        self.assertContains(res, "85")

    def test_veli_yalnizca_kendi_talebesini_gorur(self, _mock):
        self._tamamla(self.ao_hoca, self.ao)
        veli_panel_ensure(self.talebe, "10000000016", "Veli Ahmed")
        veli_panel_ensure(self.talebe2, "10000000113", "Veli Faruk")
        faruk = User.objects.get(username="10000000113")
        self.client.force_login(faruk)
        res = self.client.get(reverse("veli_talebe_ders_notlari", args=[self.talebe.id]))
        self.assertEqual(res.status_code, 404)

    def test_diger_ders_karnesi_ayni_kalir(self, _mock):
        data = _post(
            {
                "ders_id": self.mat.id,
                "islenen_konu": "Kesirler",
                f"katilim_{self.talebe.id}": "80",
                f"takip_{self.talebe.id}": "80",
                f"disiplin_{self.talebe.id}": "80",
                f"aciklama_{self.talebe.id}": "Düzenli çalışıyor.",
                f"kavram_{self.talebe.id}": "9",
                f"katilim_{self.talebe2.id}": "75",
                f"takip_{self.talebe2.id}": "75",
                f"disiplin_{self.talebe2.id}": "75",
                f"aciklama_{self.talebe2.id}": "İyi.",
            }
        )
        hatalar, _ = ogretmen_not_kaydet(self.mat_hoca, self.sinif.id, data)
        self.assertEqual(hatalar, [])
        notu = OgretmenSinavNotu.objects.get(talebe=self.talebe, ders=self.mat)
        self.assertIsNone(notu.kavram_puani)
        konu = OgretmenHaftalikKonu.objects.get(ders=self.mat, sinif_sube=self.sinif)
        self.assertEqual(konu.analitik_alan, "")
        self.assertEqual(konu.konu, "Kesirler")
        veli_panel_ensure(self.talebe, "10000000016", "Veli Ahmed")
        self.client.force_login(User.objects.get(username="10000000016"))
        res = self.client.get(reverse("veli_talebe_ders_notlari", args=[self.talebe.id]))
        self.assertContains(res, "Kesirler")
        self.assertNotContains(res, "Haftanın Kavramı")

    def test_yonetim_analitik_oturumu_gorur(self, _mock):
        self._tamamla(self.ao_hoca, self.ao)
        admin = User.objects.create_superuser("ao-admin", "ao@ex.com", "x")
        self.client.force_login(admin)
        res = self.client.get(reverse("yonetim:ogretmen_degerlendirme_rapor"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Kavram ort.")
        self.assertContains(res, "Çıkarım Yapma ve Derin Anlama")
