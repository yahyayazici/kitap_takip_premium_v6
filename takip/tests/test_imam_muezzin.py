"""İmam–müezzin: elle seçim korunur, önceki görevliler yeni rapora girmez."""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from takip.imam_muezzin_service import otomatik_dagit
from takip.imam_muezzin_yonetim_service import liste_olustur
from takip.models import (
    EtutHocasi,
    ImamMuezzinAtama,
    ImamMuezzinHavuzKaydi,
    ImamMuezzinListesi,
    Talebe,
)


class ImamMuezzinDagitimTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("imam_hoca", "h@test.com", "x")
        self.hoca = EtutHocasi.objects.create(user=user, ad_soyad="Test Hoca")
        self.talebeler = [
            Talebe.objects.create(
                ad_soyad=f"Talebe {i}",
                talebe_no=f"IM{i:03d}",
                etut_hocasi=self.hoca,
                dini_ders_hocasi=self.hoca,
            )
            for i in range(10)
        ]
        self.liste = ImamMuezzinListesi.objects.create(
            ad="Eylül",
            baslangic_tarihi=date(2026, 9, 1),
            bitis_tarihi=date(2026, 9, 3),
            cumartesi_dahil=True,
            pazar_dahil=True,
        )
        for i, t in enumerate(self.talebeler[:5]):
            ImamMuezzinHavuzKaydi.objects.create(
                liste=self.liste,
                talebe=t,
                rol=ImamMuezzinHavuzKaydi.Rol.IMAM,
                sira=i + 1,
            )
        for i, t in enumerate(self.talebeler[5:]):
            ImamMuezzinHavuzKaydi.objects.create(
                liste=self.liste,
                talebe=t,
                rol=ImamMuezzinHavuzKaydi.Rol.MUEZZIN,
                sira=i + 1,
            )

    def test_liste_olustur_elle_secimi_silmez(self):
        imam_ids = set(
            self.liste.havuz_kayitlari.filter(rol="imam").values_list("talebe_id", flat=True)
        )
        adet = liste_olustur(self.liste)
        self.assertEqual(adet, 3)
        self.assertEqual(
            set(self.liste.havuz_kayitlari.filter(rol="imam").values_list("talebe_id", flat=True)),
            imam_ids,
        )

    def test_yeni_donemde_onceki_yapanlar_rapora_girmez(self):
        otomatik_dagit(self.liste)
        onceki_imam = set(
            ImamMuezzinAtama.objects.filter(liste=self.liste).values_list("imam_id", flat=True)
        )
        onceki_muezzin = set(
            ImamMuezzinAtama.objects.filter(liste=self.liste).values_list("muezzin_id", flat=True)
        )
        self.assertTrue(onceki_imam)
        self.assertTrue(onceki_muezzin)

        self.liste.baslangic_tarihi = date(2026, 10, 1)
        self.liste.bitis_tarihi = date(2026, 10, 2)
        self.liste.save()
        liste_olustur(self.liste)

        yeni_imam = set(self.liste.havuz_kayitlari.filter(rol="imam").values_list("talebe_id", flat=True))
        yeni_muezzin = set(
            self.liste.havuz_kayitlari.filter(rol="muezzin").values_list("talebe_id", flat=True)
        )
        self.assertFalse(yeni_imam & onceki_imam)
        self.assertFalse(yeni_muezzin & onceki_muezzin)
        self.assertFalse(
            set(self.liste.atamalar.values_list("imam_id", flat=True)) & onceki_imam
        )
        self.assertFalse(
            set(self.liste.atamalar.values_list("muezzin_id", flat=True)) & onceki_muezzin
        )
