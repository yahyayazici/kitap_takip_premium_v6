"""Rehber ekran görüntülerinden tarayıcı ve macOS dock alanını kırpar."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image


def crop_chrome_screenshot(im: Image.Image) -> Image.Image:
    """Chrome sekmeleri + adres çubuğu + dock dışında uygulama alanını bırakır."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()

    # Zaten kırpılmış (giriş sayfası vb.)
    if h <= 520:
        return im

    top = 0
    for y in range(min(160, h)):
        nav = sum(
            1
            for x in range(0, w, 6)
            if px[x, y][0] < 70 and px[x, y][1] < 100 and px[x, y][2] > 120
        ) / (w // 6)
        if nav > 0.25:
            top = y
            break

    bottom = h
    for y in range(h - 1, max(top + 80, h - 140), -1):
        avg = sum(sum(px[x, y][:3]) for x in range(0, w, 8)) / (w // 8)
        if avg > 650:
            bottom = min(h, y + 10)
            break

    if bottom > h - 45:
        bottom = h - 48

    if bottom - top < 200:
        return im

    return im.crop((0, top, w, bottom))


class Command(BaseCommand):
    help = "Rehber PNG'lerinden tarayıcı ve dock alanını kırpar."

    def add_arguments(self, parser):
        parser.add_argument(
            "--atla",
            nargs="*",
            default=["01-giris.png", "06-mobil.png"],
            help="Kırpılmayacak dosya adları",
        )

    def handle(self, *args, **options):
        skip = set(options["atla"] or [])
        dizin = Path(settings.BASE_DIR) / "static" / "images" / "rehber"
        kirpildi = 0
        atlandi = 0

        for path in sorted(dizin.glob("*.png")):
            if path.name in skip:
                atlandi += 1
                continue
            with Image.open(path) as im:
                eski = im.size
                yeni_im = crop_chrome_screenshot(im)
                if yeni_im.size == eski:
                    atlandi += 1
                    continue
                yeni_im.save(path, optimize=True)
                kirpildi += 1
                self.stdout.write(f"  {path.name}: {eski[0]}x{eski[1]} → {yeni_im.size[0]}x{yeni_im.size[1]}")

        self.stdout.write(self.style.SUCCESS(f"Tamam: {kirpildi} kırpıldı, {atlandi} atlandı."))
