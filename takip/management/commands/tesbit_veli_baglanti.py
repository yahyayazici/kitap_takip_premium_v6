"""GEÇİCİ teşhis komutu — Taşdan/Sevban ailesindeki veli-öğrenci bağlantı
kopukluğunu build log'una yazdırır. İş bitince kaldırılacak."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from takip.models import Talebe
from takip.wave0_models import VeliTalebeBaglantisi


class Command(BaseCommand):
    help = "GEÇİCİ: Taşdan/Sevban ile eşleşen öğrenci+veli kayıtlarını yazdırır."

    def handle(self, *args, **options):
        self.stdout.write("=== TALEBE eşleşmeleri ===")
        for t in Talebe.objects.filter(ad_soyad__icontains="taşdan") | Talebe.objects.filter(
            ad_soyad__icontains="sevban"
        ):
            self.stdout.write(
                f"talebe id={t.pk} ad='{t.ad_soyad}' tc='{t.tc_kimlik}' "
                f"anne='{t.anne_adi}' baba='{t.baba_adi}' aktif={t.aktif}"
            )
            baglantilar = VeliTalebeBaglantisi.objects.filter(talebe=t).select_related(
                "veli__user"
            )
            for b in baglantilar:
                self.stdout.write(
                    f"    -> bağlı veli: username='{b.veli.user.username}' "
                    f"ad='{b.veli.ad_soyad}' aktif={b.veli.aktif}"
                )
            if not baglantilar:
                self.stdout.write("    -> HİÇBİR VELİYE BAĞLI DEĞİL")

        self.stdout.write("=== USER (first_name) eşleşmeleri ===")
        for u in User.objects.filter(first_name__icontains="taşdan") | User.objects.filter(
            first_name__icontains="mücahit"
        ):
            hesap = getattr(u, "veli_hesabi", None)
            self.stdout.write(
                f"user username='{u.username}' first_name='{u.first_name}' "
                f"is_active={u.is_active} veli_hesabi={'var' if hesap else 'YOK'}"
            )
            if hesap:
                baglilar = list(
                    VeliTalebeBaglantisi.objects.filter(veli=hesap).values_list(
                        "talebe__ad_soyad", flat=True
                    )
                )
                self.stdout.write(f"    -> bağlı öğrenciler: {baglilar or 'HİÇBİRİ'}")
