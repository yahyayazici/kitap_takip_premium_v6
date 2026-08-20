"""Head'deki ardışık, koşulsuz CSS dosyalarını tek dosyada birleştirir.

Mobil PWA açılışında `templates/base.html` head'i 20+ ayrı senkron
<link rel="stylesheet"> isteği yapıyordu (her açılışta ekstra ağ
round-trip'i). Bu komut, base.html'deki üç ardışık koşulsuz CSS bloğunu
(cascade sırası korunarak) tek dosyalarda birleştirir; kaynak dosyalar
(static/css/*.css) değişmeden kalır, herkes onları düzenlemeye devam
eder — build.sh her deploy'da bu komutu (collectstatic'ten önce)
çalıştırarak bundle'ları güncel tutar.

Google Fonts @import'ları (CSS spesifikasyonu gereği bir stylesheet'in
en başında olmalı) birleştirilen dosyanın en üstüne taşınır; aksi halde
tarayıcı, dosyanın ortasındaki @import'u yok sayar ve font yüklenmez.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

CSS_DIR = Path(settings.BASE_DIR) / "static" / "css"

# templates/base.html'deki <link> sırasıyla BİREBİR aynı — cascade
# (override) sırası bu listeye bağlı, değiştirilirse base.html'i de
# güncelle.
BUNDLES: dict[str, list[str]] = {
    "app-bundle-1.css": [
        "app.css",
        "cs-design-tokens.css",
        "topnav-v3.css",
        "premium-typography-v4.css",
        "premium-system-v5.css",
        "premium-system-v6.css",
        "nav-groups.css",
        "dashboard-home.css",
        "panel-unified.css",
        "panel-mobile-shared.css",
        "choice-chip-grid.css",
        "multi-select-filter.css",
        "bildirim-bell.css",
    ],
    "app-bundle-2.css": [
        "cs-design-constitution.css",
        "cs-design-phase2.css",
        "cs-design-phase3.css",
        "cs-design-phase4.css",
        "cs-design-phase5.css",
        "cs-design-phase6.css",
    ],
    "app-bundle-3.css": [
        "cs-design-phase7.css",
        "cs-design-phase8.css",
    ],
}


def _build_bundle(source_names: list[str]) -> str:
    imports: list[str] = []
    gövde: list[str] = []

    for name in source_names:
        path = CSS_DIR / name
        metin = path.read_text(encoding="utf-8")
        satirlar = metin.splitlines()
        kalanlar = []
        for satir in satirlar:
            if satir.strip().startswith("@import"):
                imports.append(satir.strip())
            else:
                kalanlar.append(satir)
        gövde.append(f"/* --- {name} --- */\n" + "\n".join(kalanlar).strip() + "\n")

    parcalar = []
    if imports:
        parcalar.append("\n".join(imports) + "\n")
    parcalar.extend(gövde)
    return "\n".join(parcalar)


class Command(BaseCommand):
    help = "static/css altındaki koşulsuz head CSS dosyalarını tek bundle'larda birleştirir."

    def handle(self, *args, **options):
        for bundle_name, source_names in BUNDLES.items():
            eksik = [n for n in source_names if not (CSS_DIR / n).is_file()]
            if eksik:
                self.stderr.write(
                    self.style.ERROR(f"{bundle_name}: kaynak dosya(lar) bulunamadı: {eksik}")
                )
                continue
            icerik = _build_bundle(source_names)
            hedef = CSS_DIR / bundle_name
            hedef.write_text(icerik, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"{bundle_name} yazıldı ({len(source_names)} dosya)."))
