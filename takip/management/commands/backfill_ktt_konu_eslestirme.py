"""Mevcut KTT kayıtlarına standart konu eşleştirmesi uygular."""

from django.core.management.base import BaseCommand
from django.db import transaction

from takip.ktt_konu_normalize_service import ktt_konu_eslestir
from takip.models import KttSinav


class Command(BaseCommand):
    help = "Mevcut KTT sınavlarına konu normalizasyonu uygular (canlı veriyi otomatik silmez)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Kaydetmeden kaç KTT işleneceğini göster.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="İşlenecek maksimum KTT sayısı (0 = tümü).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        qs = KttSinav.objects.filter(aktif=True, konu_katalog__isnull=True).order_by("-id")
        if options["limit"]:
            qs = qs[: options["limit"]]
        toplam = qs.count()

        if options["dry_run"]:
            self.stdout.write(f"Eşleştirilecek KTT: {toplam}")
            return

        islenen = 0
        for ktt in qs.iterator():
            sonuc = ktt_konu_eslestir(ktt)
            islenen += 1
            self.stdout.write(
                f"  {ktt.ad} → {sonuc.konu.konu_ad if sonuc.konu else '—'} "
                f"({sonuc.guven}% / {sonuc.kaynak})"
            )

        self.stdout.write(self.style.SUCCESS(f"Tamamlandı: {islenen}/{toplam} KTT"))
