"""Kitap sınavı sonucu kaydedilince puanın yazıldığını doğrular."""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from takip.models import EtutHocasi, Kitap, Sinav, SinavSonucu, Talebe


class SinavSonucuPuanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "sinav-puan",
            password="test-pass-123",
        )
        self.hoca = EtutHocasi.objects.create(
            user=self.user,
            ad_soyad="Etüt Hocası",
            aktif=True,
        )
        self.kitap = Kitap.objects.create(
            ad="Thames Nehri Haydutları",
            toplam_sayfa=180,
        )
        self.sinav = Sinav.objects.create(
            etut_hocasi=self.hoca,
            kitap=self.kitap,
            ad="Thames Nehri Haydutları",
            soru_sayisi=15,
            sinav_tarihi=date(2026, 10, 2),
            olusturan=self.user,
        )
        self.talebe = Talebe.objects.create(
            ad_soyad="Abdullah Bedestenci",
            sinif="7",
            sube="A",
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            aktif=True,
        )
        self.client.force_login(self.user)

    def _post(self, dogru, yanlis, bos):
        return self.client.post(
            reverse("sinav_sonuclari_gir", args=[self.sinav.id]),
            {
                f"dogru_{self.talebe.id}": str(dogru),
                f"yanlis_{self.talebe.id}": str(yanlis),
                f"bos_{self.talebe.id}": str(bos),
            },
        )

    def test_ilk_kayit_puani_yazar(self):
        response = self._post(14, 1, 0)
        self.assertEqual(response.status_code, 302)
        sonuc = SinavSonucu.objects.get(sinav=self.sinav, talebe=self.talebe)
        self.assertEqual(sonuc.dogru, 14)
        self.assertEqual(sonuc.puan, Decimal("93.33"))

    def test_guncellemede_puan_yeniden_hesaplanir(self):
        self._post(0, 0, 15)
        self.assertEqual(
            SinavSonucu.objects.get(talebe=self.talebe).puan,
            Decimal("0.00"),
        )

        response = self._post(14, 1, 0)
        self.assertEqual(response.status_code, 302)
        sonuc = SinavSonucu.objects.get(sinav=self.sinav, talebe=self.talebe)
        self.assertEqual(sonuc.dogru, 14)
        self.assertEqual(sonuc.yanlis, 1)
        self.assertEqual(sonuc.bos, 0)
        self.assertEqual(sonuc.puan, Decimal("93.33"))

    def test_sayfa_eski_sifir_puani_duzeltir(self):
        sonuc = SinavSonucu.objects.create(
            sinav=self.sinav,
            talebe=self.talebe,
            dogru=14,
            yanlis=1,
            bos=0,
        )
        SinavSonucu.objects.filter(pk=sonuc.pk).update(puan=Decimal("0.00"))

        response = self.client.get(
            reverse("sinav_sonuclari_gir", args=[self.sinav.id])
        )
        self.assertEqual(response.status_code, 200)
        sonuc.refresh_from_db()
        self.assertEqual(sonuc.puan, Decimal("93.33"))
        body = response.content.decode()
        self.assertTrue("93,33" in body or "93.33" in body)
