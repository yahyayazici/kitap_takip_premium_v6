from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from takip.models import EtutHocasi, Talebe, Kitap, Zimmet, OkumaKaydi
from django.utils import timezone

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

        self.stdout.write(self.style.SUCCESS(
            "Demo hazır. Admin: admin/Admin123! | Etüt: yahya/Yahya123!"
        ))
