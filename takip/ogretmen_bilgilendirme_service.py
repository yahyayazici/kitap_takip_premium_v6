"""Etüt hocası kullanım rehberi — HTML/PDF üretimi."""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from config.branding import PANEL_MODULE_LABEL, PANEL_NAME, PANEL_ORG, PANEL_SHORT, PANEL_TAGLINE
from takip.pdf_utils import html_to_pdf


@dataclass(frozen=True)
class RehberGorsel:
    anahtar: str
    dosya: str
    baslik: str


REHBER_GORSELLER: tuple[RehberGorsel, ...] = (
    RehberGorsel("giris", "01-giris.png", "Giriş ekranı"),
    RehberGorsel("panel", "02-panel.png", "Personel paneli"),
    RehberGorsel("karneler", "03-karneler.png", "Haftalık karneler"),
    RehberGorsel("kitap", "04-kitap.png", "Kitap takip"),
    RehberGorsel("talebeler", "05-talebeler.png", "Talebe listesi"),
    RehberGorsel("mobil", "06-mobil.png", "Mobil görünüm"),
)


def _rehber_gorsel_dizini() -> Path:
    return settings.BASE_DIR / "static" / "images" / "rehber"


def rehber_gorsel_data_uri(dosya: str) -> str:
    """PNG/JPEG dosyasını PDF'e gömülü data URI olarak döndürür."""
    path = _rehber_gorsel_dizini() / dosya
    if not path.is_file():
        return ""
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def rehber_gorsel_haritasi() -> dict[str, str]:
    """Anahtar → base64 data URI (PDF'de link değil gömülü görsel)."""
    return {
        g.anahtar: rehber_gorsel_data_uri(g.dosya)
        for g in REHBER_GORSELLER
    }


def ogretmen_bilgilendirme_pdf_html(request: HttpRequest) -> str:
    panel_giris_url = request.build_absolute_uri(reverse("login"))
    logo_path = settings.BASE_DIR / "static" / "images" / "cinili-saray-logo-white.png"
    logo_uri = ""
    if logo_path.is_file():
        encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        logo_uri = f"data:image/png;base64,{encoded}"
    else:
        logo_uri = request.build_absolute_uri(static("images/cinili-saray-logo-white.png"))

    return render_to_string(
        "ogretmen_bilgilendirme_pdf.html",
        {
            "panel_org": PANEL_ORG,
            "panel_name": PANEL_NAME,
            "panel_short": PANEL_SHORT,
            "panel_module": PANEL_MODULE_LABEL,
            "panel_tagline": PANEL_TAGLINE,
            "panel_giris_url": panel_giris_url,
            "logo_url": logo_uri,
            "gorseller": rehber_gorsel_haritasi(),
            "tarih": timezone.localdate(),
            "hedef_kitle": "Etüt Hocaları",
        },
        request=request,
    )


def ogretmen_bilgilendirme_pdf_olustur(request: HttpRequest) -> bytes | None:
    html = ogretmen_bilgilendirme_pdf_html(request)
    return html_to_pdf(html, base_url=request.build_absolute_uri("/"))
