from django.core.management.base import BaseCommand

from takip.rehber_gorsel_uret import tum_rehber_gorsellerini_uret


class Command(BaseCommand):
    help = "Etüt hocası rehber PDF ekran görüntülerini üretir (static/images/rehber/)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yeniden-giris",
            action="store_true",
            help="01-giris.png dosyasını da yeniden üret.",
        )

    def handle(self, *args, **options):
        paths = tum_rehber_gorsellerini_uret(giris_koru=not options["yeniden_giris"])
        for path in paths:
            self.stdout.write(self.style.SUCCESS(f"✓ {path.name}"))
