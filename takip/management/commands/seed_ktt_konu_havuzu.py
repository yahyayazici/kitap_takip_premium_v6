"""Standart KTT konu havuzunu yükler."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from takip.konu_destek_models import KonuKatalogu


class Command(BaseCommand):
    help = "Sınıf × branş standart konu havuzunu KonuKatalogu'na yükler."

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(__file__).resolve().parents[1] / "data" / "ktt_konu_havuzu.json"
        veri = json.loads(path.read_text(encoding="utf-8"))
        olusturulan = 0
        for blok in veri:
            sinif = blok["sinif"]
            brans = blok["brans"]
            for konu_ad in blok["konular"]:
                _, created = KonuKatalogu.objects.get_or_create(
                    sinif_seviyesi=sinif,
                    brans=brans,
                    konu_ad=konu_ad,
                    defaults={"aktif": True},
                )
                if created:
                    olusturulan += 1
        self.stdout.write(
            self.style.SUCCESS(f"Konu havuzu yüklendi. Yeni konu: {olusturulan}")
        )
