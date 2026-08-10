"""AI günlük / haftalık bildirim görevleri (Render cron veya manuel)."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils.timezone import localdate

from takip.ai_bildirim_service import (
    ai_bildirim_aktif,
    erken_uyari_bildirimleri,
    veli_haftalik_brifing_gonder,
)


class Command(BaseCommand):
    help = (
        "AI bildirim görevleri: günlük erken uyarı, Pazar veli haftalık brifing. "
        "Render cron: 0 8 * * * python manage.py ai_haftalik_gorevler"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--erken-uyari",
            action="store_true",
            help="Yalnızca erken uyarı bildirimlerini gönder",
        )
        parser.add_argument(
            "--veli-brifing",
            action="store_true",
            help="Veli haftalık brifing (Pazar kontrolünü atla)",
        )
        parser.add_argument(
            "--yenile",
            action="store_true",
            help="AI önbelleğini yenileyerek veli brifing üret",
        )

    def handle(self, *args, **options):
        if not ai_bildirim_aktif():
            self.stdout.write(
                self.style.WARNING("AI platformu kapalı — bildirim gönderilmedi.")
            )
            return

        bugun = localdate()
        sadece_erken = options["erken_uyari"]
        sadece_veli = options["veli_brifing"]
        hepsi = not sadece_erken and not sadece_veli

        if hepsi or sadece_erken:
            n = erken_uyari_bildirimleri()
            self.stdout.write(self.style.SUCCESS(f"Erken uyarı: {n} bildirim gönderildi"))

        if sadece_veli or (hepsi and bugun.weekday() == 6):
            n = veli_haftalik_brifing_gonder(yenile=options["yenile"])
            self.stdout.write(
                self.style.SUCCESS(f"Veli haftalık brifing: {n} bildirim gönderildi")
            )
        elif hepsi and bugun.weekday() != 6:
            self.stdout.write("Veli brifing atlandı (Pazar değil).")
