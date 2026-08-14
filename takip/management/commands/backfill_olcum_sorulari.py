"""Mevcut KTT kayıtları için OlcumSoru satırları üretir."""

from django.core.management.base import BaseCommand

from takip.models import KttSinav
from takip.olcme_service import mevcut_ktt_backfill


class Command(BaseCommand):
    help = "Mevcut KTT sınavları için soru satırları oluşturur (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--pk", type=int, help="Yalnızca belirli KTT pk")

    def handle(self, *args, **options):
        qs = KttSinav.objects.filter(aktif=True).order_by("id")
        if options.get("pk"):
            qs = qs.filter(pk=options["pk"])

        toplam = 0
        for sinav in qs:
            eklenen = mevcut_ktt_backfill(sinav)
            if eklenen:
                self.stdout.write(f"KTT #{sinav.pk} {sinav.ad}: +{eklenen} soru")
            toplam += eklenen

        self.stdout.write(self.style.SUCCESS(f"Tamamlandı. Yeni soru satırı: {toplam}"))
