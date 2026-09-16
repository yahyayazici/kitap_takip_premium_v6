#!/usr/bin/env python3
"""Panel base şablonlarının (base.html, ogretmen/talebe/veli/yonetim) her biri
her sayfada 20+ ayrı <link rel="stylesheet"> ile render'ı bekletiyordu. Bu
script, her panelde HER sayfada değişmeden yüklenen dosyaları, aralarındaki
SIRAYI KORUYARAK birkaç bundle dosyasında birleştirir; tarayıcı aynı CSS'i
çok daha az istekte indirir. {% block extra_css %} tam olarak eski konumunda
kaldığı için sayfa bazlı override davranışı değişmez.

Kaynaklardan biri (premium-system-v5.css) bir Google Fonts @import
içeriyordu; @import yalnızca bir stylesheet'in en başında geçerliyken burada
ortada kalıyordu (sessizce yok sayılıyordu). Buradan çıkarılıp her base
şablonuna gerçek bir <link> olarak taşındı — bu hem @import kısıtını ortadan
kaldırır hem de fontun CSS'in içine gömülü değil, HTML'den paralel
keşfedilmesini sağlayarak performansı iyileştirir.

collectstatic'ten ÖNCE çalıştırılmalı; build.sh bunu otomatik yapar.
Kaynak dosyalardan biri değişirse bu script'i tekrar çalıştırmak yeterli.
"""
from __future__ import annotations

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSS_DIR = BASE_DIR / "static" / "css"
OUT_DIR = CSS_DIR  # tüm bundle çıktıları static/css/ altına yazılır

_IMPORT_RE = re.compile(r"^@import\s+url\([^)]*fonts\.googleapis\.com[^)]*\)\s*;\s*$", re.M)


def _read(rel_path: str) -> str:
    """rel_path, static/ köküne göredir (örn. 'css/app.css' ya da
    'yonetim/css/yonetim.css') — böylece static/css/ dışındaki dosyalar da
    (örn. yonetim'e özel css) bundle'a katılabilir."""
    src = BASE_DIR / "static" / rel_path
    text = src.read_text(encoding="utf-8")
    text = _IMPORT_RE.sub("", text)
    return f"/* ---- {rel_path} ---- */\n{text.strip()}\n"


def _write_bundle(out_name: str, sources: list[str]) -> None:
    header = (
        "/* OTOMATIK ÜRETİLDİ — elle düzenlemeyin.\n"
        "   Kaynak: scripts/build_css_bundle.py.\n"
        "   Kaynak CSS dosyalarından biri değişince script'i tekrar\n"
        "   çalıştırın (build.sh collectstatic'ten önce otomatik yapar). */\n\n"
    )
    body = "\n".join(_read(s) for s in sources)
    out_path = OUT_DIR / out_name
    out_path.write_text(header + body, encoding="utf-8")
    print(f"yazildi: static/css/{out_name} ({out_path.stat().st_size} bayt)")


# —— Ana panel (templates/base.html) ——
# Sıra, base.html'deki eski <link> sırasıyla birebir aynı (CSS cascade).
MAIN_CORE = [
    "css/app.css",
    "css/cs-design-tokens.css",
    "css/topnav-v3.css",
    "css/premium-typography-v4.css",
    "css/premium-system-v5.css",
    "css/premium-system-v6.css",
    "css/nav-groups.css",
    "css/panel-unified.css",
    "css/panel-mobile-shared.css",
    "css/choice-chip-grid.css",
    "css/multi-select-filter.css",
    "css/bildirim-bell.css",
    "css/cs-design-constitution.css",
    "css/cs-design-phase2.css",
    "css/cs-design-phase3.css",
    "css/cs-design-phase4.css",
    "css/cs-design-phase5.css",
    "css/cs-design-phase6.css",
]

# Tüm panellerde {% block extra_css %}'ten SONRA birebir aynı sırada yüklenen
# kuyruk — 5 panelin de ortak son bloğu, tek bundle yeter.
PANEL_LATE = [
    "css/cs-design-phase7.css",
    "css/cs-design-phase8.css",
    "css/cs-ui-system.css",
]

# ogretmen/veli/yonetim panellerinde koşullu (asistan/ai_platform) bloklardan
# SONRA, extra_css'ten ÖNCE birebir aynı sırada yüklenen dizi.
PANEL_MID = [
    "css/cs-design-constitution.css",
    "css/cs-design-phase2.css",
    "css/cs-design-phase3.css",
    "css/cs-design-phase4.css",
    "css/cs-design-phase5.css",
    "css/cs-design-phase6.css",
]

# Her panelin koşullu bloklardan ÖNCEki, o panele özel dosya dizisi.
OGRETMEN_PRE = [
    "css/app.css",
    "css/cs-design-tokens.css",
    "css/topnav-v3.css",
    "css/premium-system-v5.css",
    "css/premium-system-v6.css",
    "css/nav-groups.css",
    "css/dashboard-home.css",
    "css/panel-unified.css",
    "css/panel-mobile-shared.css",
    "css/choice-chip-grid.css",
    "css/ogretmen-panel.css",
    "css/panel-apple-polish.css",
    "css/ogretmen-dash-wow.css",
    "css/bildirim-bell.css",
]

VELI_PRE = [
    "css/app.css",
    "css/cs-design-tokens.css",
    "css/topnav-v3.css",
    "css/premium-system-v5.css",
    "css/premium-system-v6.css",
    "css/nav-groups.css",
    "css/dashboard-home.css",
    "css/panel-unified.css",
    "css/panel-mobile-shared.css",
    "css/choice-chip-grid.css",
    "css/veli-panel.css",
    "css/panel-apple-polish.css",
    "css/ogretmen-dash-wow.css",
    "css/bildirim-bell.css",
]

YONETIM_PRE = [
    "yonetim/css/yonetim.css",
    "css/cs-design-tokens.css",
    "css/premium-system-v5.css",
    "css/premium-system-v6.css",
    "css/nav-groups.css",
    "css/yonetim-nav.css",
    "css/dashboard-home.css",
    "css/panel-unified.css",
    "css/panel-mobile-shared.css",
    "css/choice-chip-grid.css",
    "css/yonetim-premium.css",
    "css/multi-select-filter.css",
    "css/bildirim-bell.css",
]

# talebe/base.html: koşullu bloklardan ÖNCE constitution..phase5 de dahil
# (diğer panellerden farklı bir sırası var); phase6 koşullu bloklardan
# SONRA tek başına kalıyor (PANEL_MID'e uymuyor, o yüzden ayrı).
TALEBE_PRE = [
    "css/app.css",
    "css/cs-design-tokens.css",
    "css/topnav-v3.css",
    "css/premium-system-v5.css",
    "css/premium-system-v6.css",
    "css/nav-groups.css",
    "css/dashboard-home.css",
    "css/panel-unified.css",
    "css/panel-mobile-shared.css",
    "css/talebe-panel.css",
    "css/cs-design-constitution.css",
    "css/cs-design-phase2.css",
    "css/cs-design-phase3.css",
    "css/cs-design-phase4.css",
    "css/cs-design-phase5.css",
]


def main() -> None:
    _write_bundle("bundle-panel-core.css", MAIN_CORE)
    _write_bundle("bundle-panel-late.css", PANEL_LATE)
    _write_bundle("bundle-panel-mid.css", PANEL_MID)
    _write_bundle("bundle-ogretmen-pre.css", OGRETMEN_PRE)
    _write_bundle("bundle-veli-pre.css", VELI_PRE)
    _write_bundle("bundle-yonetim-pre.css", YONETIM_PRE)
    _write_bundle("bundle-talebe-pre.css", TALEBE_PRE)


if __name__ == "__main__":
    main()
