"""Zamanı gelen sınav başvurusu hatırlatmalarını gönderir (elle veya cron ile)."""

from django.core.management.base import BaseCommand

from takip.sinav_bildirim_service import zamani_gelenleri_gonder


class Command(BaseCommand):
    help = "Zamanı gelen sınav başvurusu uygulama bildirimlerini gönderir."

    def handle(self, *args, **options):
        adet = zamani_gelenleri_gonder()
        self.stdout.write(self.style.SUCCESS(f"{adet} bildirim gönderildi."))
