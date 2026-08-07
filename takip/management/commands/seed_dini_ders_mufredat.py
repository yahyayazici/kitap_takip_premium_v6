"""Dini ders seviye/alan/konu müfredatını yükler."""

from django.core.management.base import BaseCommand
from django.db import transaction

from takip.dini_ders_mufredat import seed_dini_ders_mufredat


class Command(BaseCommand):
    help = "Dini ders seviyeleri, takip alanları ve konu listesini müfredat dosyasından yükler."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-demo",
            action="store_true",
            help="Eski demo konuları pasifleştirme (yalnızca yeni konular eklenir/güncellenir).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        stats = seed_dini_ders_mufredat(replace_demo=not options["keep_demo"])
        self.stdout.write(
            self.style.SUCCESS(
                "Dini ders müfredatı yüklendi: "
                f"{stats['seviyeler']} seviye, {stats['alanlar']} alan, "
                f"{stats['konular_olusturulan']} yeni konu, "
                f"{stats['konular_guncellenen']} güncellenen, "
                f"{stats['konular_pasiflestirilen']} pasifleştirilen."
            )
        )
        for seviye, adet in stats.get("konu_sayilari", {}).items():
            self.stdout.write(f"  {seviye}: {adet} konu")
