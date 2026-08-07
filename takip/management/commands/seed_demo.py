from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from config.branding import PANEL_NAME
from takip.models import Duyuru, EtutHocasi, ImamMuezzinListesi, PersonelProfili, ProgramPlan, ProgramSatir, Talebe, Kitap, Zimmet, OkumaKaydi, TemizlikAlani, TemizlikListesi, YemekciListesi, YemekOgun
from takip.imam_muezzin_service import otomatik_dagit
from takip.temizlik_service import otomatik_dagit as temizlik_dagit
from takip.yemekci_service import otomatik_dagit as yemekci_dagit

class Command(BaseCommand):
    help = "Demo verileri oluşturur."

    def handle(self, *args, **kwargs):
        admin, created = User.objects.get_or_create(username="admin")
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password("Admin123!")
        admin.save()

        user, _ = User.objects.get_or_create(username="yahya")
        user.set_password("Yahya123!")
        user.save()

        hoca, _ = EtutHocasi.objects.get_or_create(user=user, defaults={"ad_soyad": "Yahya Yazıcı"})
        if hoca.ad_soyad != "Yahya Yazıcı":
            hoca.ad_soyad = "Yahya Yazıcı"
            hoca.save()

        user.is_staff = True
        user.save(update_fields=["is_staff"])

        PersonelProfili.objects.update_or_create(
            user=user,
            defaults={
                "ad_soyad": hoca.ad_soyad,
                "ana_rol": PersonelProfili.Rol.ETUT_MESUL,
                "etut_hocasi": hoca,
                "aktif": True,
            },
        )

        PersonelProfili.objects.update_or_create(
            user=admin,
            defaults={
                "ad_soyad": "Admin",
                "ana_rol": PersonelProfili.Rol.IDARECI,
                "aktif": True,
            },
        )

        talebeler = []
        for ad in ["Ahmet Yılmaz", "Mehmet Kaya", "Yusuf Akın"]:
            t, _ = Talebe.objects.get_or_create(
                ad_soyad=ad, defaults={"sinif": "7", "sube": "A", "etut_hocasi": hoca}
            )
            talebeler.append(t)

        kitap, _ = Kitap.objects.get_or_create(
            ad="80 Günde Devriâlem",
            yazar="Jules Verne",
            defaults={"toplam_sayfa": 240, "sinif_seviyesi": "7. Sınıf", "olusturan": user, "son_duzenleyen": user}
        )

        for i, talebe in enumerate(talebeler):
            z, _ = Zimmet.objects.get_or_create(
                talebe=talebe, kitap=kitap, etut_hocasi=hoca,
                defaults={"olusturan": user, "son_duzenleyen": user}
            )
            if not z.okuma_kayitlari.exists():
                OkumaKaydi.objects.create(
                    zimmet=z, tarih=timezone.localdate(),
                    son_sayfa=35 + i * 18, olusturan=user, son_duzenleyen=user
                )

        ornek_duyurular = [
            {
                "baslik": "Dijital asistanınız hazır",
                "ozet": (
                    "Sağ alt köşedeki panel asistanı ile sohbet edebilir, okuma raporu alabilir "
                    "ve talebe bilgisine hızlıca ulaşabilirsiniz."
                ),
                "kategori": Duyuru.Kategori.KURUM,
                "ton": Duyuru.Ton.VIOLET,
                "sira": 0,
            },
            {
                "baslik": f"{PANEL_NAME}'e hoş geldiniz",
                "ozet": "Eğitim modülü aktif. Duyuru, program ve görev modülleri sırayla ekleniyor.",
                "kategori": Duyuru.Kategori.GENEL,
                "ton": Duyuru.Ton.NAVY,
                "sira": 1,
            },
            {
                "baslik": "Günlük okuma kayıtlarını unutmayın",
                "ozet": "Okuma takibi ekranından talebelerinizin sayfa ilerlemesini girebilirsiniz.",
                "kategori": Duyuru.Kategori.EGITIM,
                "ton": Duyuru.Ton.VIOLET,
                "sira": 2,
            },
            {
                "baslik": "Program modülü aktif",
                "ozet": "Günlük programı Programlar menüsünden görüntüleyebilir, PDF alabilirsiniz.",
                "kategori": Duyuru.Kategori.PROGRAM,
                "ton": Duyuru.Ton.TEAL,
                "sira": 3,
            },
        ]

        for veri in ornek_duyurular:
            Duyuru.objects.update_or_create(
                baslik=veri["baslik"],
                defaults={
                    **veri,
                    "hedef_kitle": Duyuru.HedefKitle.TUM_PERSONEL,
                    "baslangic": timezone.localdate(),
                    "aktif": True,
                    "olusturan": admin,
                },
            )

        bugun = timezone.localdate()
        program, _ = ProgramPlan.objects.update_or_create(
            ad="Günlük Kurum Programı",
            defaults={
                "aciklama": "Demo günlük akış programı",
                "baslangic_tarihi": bugun - timedelta(days=30),
                "bitis_tarihi": bugun + timedelta(days=120),
                "aktif": True,
                "olusturan": admin,
            },
        )
        program.satirlar.all().delete()

        demo_satirlar = [
            (1, time(6, 30), time(7, 15), ProgramSatir.FaaliyetTuru.NAMAZ, "Sabah namazı"),
            (2, time(7, 15), time(8, 0), ProgramSatir.FaaliyetTuru.YEMEK, "Kahvaltı"),
            (3, time(8, 0), time(9, 30), ProgramSatir.FaaliyetTuru.DERS, "Dini ders"),
            (4, time(9, 45), time(11, 15), ProgramSatir.FaaliyetTuru.ETUT, "Etüt"),
            (5, time(11, 30), time(12, 30), ProgramSatir.FaaliyetTuru.YEMEK, "Öğle yemeği"),
            (6, time(13, 0), time(15, 0), ProgramSatir.FaaliyetTuru.DERS, "Kur'an dersi"),
            (7, time(15, 15), time(16, 0), ProgramSatir.FaaliyetTuru.DINLENME, "Dinlenme", ProgramSatir.FaaliyetDurumu.PASIF),
        ]

        for veri in demo_satirlar:
            sira, bas, bit, tur, ad = veri[:5]
            durum = veri[5] if len(veri) > 5 else ProgramSatir.FaaliyetDurumu.ETKIN
            ProgramSatir.objects.create(
                program=program,
                sira=sira,
                baslangic_saati=bas,
                bitis_saati=bit,
                faaliyet_turu=tur,
                faaliyet_adi=ad,
                faaliyet_durumu=durum,
            )

        imam_liste, _ = ImamMuezzinListesi.objects.update_or_create(
            ad="Aylık İmam Müezzin Listesi",
            defaults={
                "baslangic_tarihi": bugun - timedelta(days=7),
                "bitis_tarihi": bugun + timedelta(days=60),
                "cumartesi_dahil": True,
                "pazar_dahil": False,
                "aktif": True,
                "olusturan": admin,
            },
        )
        otomatik_dagit(imam_liste)
        from takip.imam_muezzin_yonetim_service import liste_olustur

        liste_olustur(imam_liste)

        demo_alanlar = [
            (1, "Giriş ve merdiven", "Ana giriş, merdivenler"),
            (2, "1. Kat koridor", "Sınıf koridoru"),
            (3, "2. Kat koridor", "Yatakhane koridoru"),
            (4, "Yemekhane", "Yemek ve mutfak alanı"),
            (5, "Abdesthane", "Abdest ve lavabo"),
            (6, "Bahçe", "Avlu ve çevre düzen"),
        ]

        for sira, ad, aciklama in demo_alanlar:
            TemizlikAlani.objects.update_or_create(
                ad=ad,
                defaults={"sira": sira, "aciklama": aciklama, "aktif": True},
            )

        temizlik_liste, _ = TemizlikListesi.objects.update_or_create(
            ad="Haftalık Temizlik Listesi",
            defaults={
                "baslangic_tarihi": bugun - timedelta(days=7),
                "bitis_tarihi": bugun + timedelta(days=21),
                "cumartesi_dahil": True,
                "pazar_dahil": False,
                "aktif": True,
                "olusturan": admin,
            },
        )
        temizlik_liste.alanlar.set(
            TemizlikAlani.objects.filter(aktif=True).order_by("sira")
        )
        temizlik_dagit(temizlik_liste)

        from takip.temizlik_yonetim_service import gorevli_ekle, katlari_hazirla

        katlari_hazirla(temizlik_liste)
        talebeler = list(Talebe.objects.filter(aktif=True).order_by("ad_soyad")[:12])
        for i, alan in enumerate(TemizlikAlani.objects.filter(kat__liste=temizlik_liste, aktif=True)[:8]):
            if talebeler:
                gorevli_ekle(temizlik_liste, alan, talebeler[i % len(talebeler)].pk)

        demo_ogunler = [
            (1, "Kahvaltı", "Sabah yemeği servisi"),
            (2, "Öğle Yemeği", "Öğle servis ve mutfak"),
            (3, "Akşam Yemeği", "Akşam servis ve mutfak"),
        ]

        for sira, ad, aciklama in demo_ogunler:
            YemekOgun.objects.update_or_create(
                ad=ad,
                defaults={"sira": sira, "aciklama": aciklama, "aktif": True},
            )

        yemekci_liste, _ = YemekciListesi.objects.update_or_create(
            ad="Haftalık Yemekçilik Listesi",
            defaults={
                "baslangic_tarihi": bugun - timedelta(days=7),
                "bitis_tarihi": bugun + timedelta(days=21),
                "cumartesi_dahil": True,
                "pazar_dahil": False,
                "aktif": True,
                "olusturan": admin,
            },
        )
        yemekci_liste.ogunler.set(
            YemekOgun.objects.filter(aktif=True).order_by("sira")
        )
        yemekci_dagit(yemekci_liste)

        from django.core.management import call_command

        call_command("seed_wave0")

        from takip.veli_service import seed_veli_demo
        from takip.ktt_service import seed_ktt_demo
        from takip.akademik_mudahale_service import seed_akademik_mudahale_demo
        from takip.namaz_yoklama_service import seed_namaz_demo
        from takip.ogretmen_odeme_service import seed_ogretmen_odeme_demo
        from takip.ogretmen_service import seed_ogretmen_panel_demo
        from takip.rehberlik_service import seed_gorusme_turleri, seed_rehberlik_demo
        from takip.disiplin_service import seed_disiplin_turleri
        from takip.yazili_takip_service import seed_yazili_takip_demo
        from takip.talebe_panel_service import seed_talebe_panel_demo

        seed_veli_demo()
        seed_ktt_demo()
        seed_akademik_mudahale_demo()
        seed_namaz_demo()
        seed_ogretmen_odeme_demo()
        seed_ogretmen_panel_demo()
        seed_gorusme_turleri()
        seed_rehberlik_demo()
        seed_disiplin_turleri()
        seed_yazili_takip_demo()
        seed_talebe_panel_demo()

        self.stdout.write(self.style.SUCCESS(
            "Demo hazır. Admin: admin/Admin123! | Etüt: yahya/Yahya123! | "
            "Veli: veli/Veli123! | Öğretmen: kemal/Kemal123! | Talebe: talebe/Talebe123!"
        ))
