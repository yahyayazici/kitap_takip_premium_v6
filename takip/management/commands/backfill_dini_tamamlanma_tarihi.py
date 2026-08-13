"""Tamamlanma tarihi alanını mevcut kayıtlardan doldurur."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from takip.models import DiniDersKonuKaydi


class Command(BaseCommand):
    help = "Tamamlanan dini ders konu kayıtlarına tamamlanma_tarihi yazar (guncellenme tarihinden)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Kaydetmeden kaç kayıt güncelleneceğini göster.",
        )

    def handle(self, *args, **options):
        qs = DiniDersKonuKaydi.objects.filter(
            tamamlandi=True,
            tamamlanma_tarihi__isnull=True,
        )
        toplam = qs.count()
        if options["dry_run"]:
            self.stdout.write(f"Güncellenecek kayıt: {toplam}")
            return

        bugun = timezone.localdate()
        guncellenen = 0
        for kayit in qs.iterator():
            tarih = kayit.guncellenme.date() if kayit.guncellenme else bugun
            kayit.tamamlanma_tarihi = tarih
            kayit.save(update_fields=["tamamlanma_tarihi"])
            guncellenen += 1

        self.stdout.write(
            self.style.SUCCESS(f"Tamamlanma tarihi güncellendi: {guncellenen}/{toplam}")
        )
