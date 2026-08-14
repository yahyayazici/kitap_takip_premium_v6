"""Optik form karekod üretimi — segno (taranabilir PNG + SVG)."""

from __future__ import annotations

import base64
import io
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

KAREKOD_RE = re.compile(r"^OLCME;S(\d+);T(\d+);N([^;]+);K([A-E])$")
OPTIK_FOTO_PATH_RE = re.compile(r"/olcme/sinav/(\d+)/optik-foto/?$")


def optik_karekod_metni(sinav_id: int, talebe, kitapcik: str = "A") -> str:
    """Optik form ve foto tarama için sabit format."""
    kimlik = talebe.talebe_no if getattr(talebe, "talebe_no", None) else talebe.pk
    kitap = (kitapcik or "A").strip().upper()[:1] or "A"
    return f"OLCME;S{sinav_id};T{talebe.pk};N{kimlik};K{kitap}"


def optik_foto_deep_link(foto_base_url: str, talebe_id: int, kitapcik: str = "A") -> str:
    """Telefon kamerası ile doğrudan Foto Tara sayfasını açan URL."""
    kitap = (kitapcik or "A").strip().upper()[:1] or "A"
    base = (foto_base_url or "").rstrip("/")
    return f"{base}?talebe={talebe_id}&kitapcik={kitap}"


def optik_karekod_parse(metin: str) -> dict[str, Any] | None:
    text = (metin or "").strip()
    m = KAREKOD_RE.match(text)
    if m:
        return {
            "sinav_id": int(m.group(1)),
            "talebe_id": int(m.group(2)),
            "talebe_no": m.group(3),
            "kitapcik": m.group(4),
        }

    if "://" in text or text.startswith("/"):
        parsed = urlparse(text)
        path_m = OPTIK_FOTO_PATH_RE.search(parsed.path or "")
        if not path_m:
            return None
        qs = parse_qs(parsed.query)
        talebe_vals = qs.get("talebe") or []
        if not talebe_vals:
            return None
        kitap_vals = qs.get("kitapcik") or ["A"]
        kitap = (kitap_vals[0] or "A").strip().upper()[:1] or "A"
        try:
            return {
                "sinav_id": int(path_m.group(1)),
                "talebe_id": int(talebe_vals[0]),
                "talebe_no": talebe_vals[0],
                "kitapcik": kitap,
            }
        except (TypeError, ValueError):
            return None
    return None


def _segno_qr(metin: str):
    import segno

    return segno.make(metin, error="m")


def optik_karekod_png_data_uri(metin: str, *, scale: int = 8) -> str:
    """Yazdırma ve telefon taraması için yüksek kontrast PNG."""
    buf = io.BytesIO()
    _segno_qr(metin).save(
        buf,
        kind="png",
        scale=scale,
        border=4,
        dark="black",
        light="white",
    )
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def optik_karekod_svg(metin: str, *, scale: int = 5) -> str:
    svg = _segno_qr(metin).svg_inline(
        scale=scale,
        dark="#000000",
        light="#ffffff",
        border=4,
    )
    if svg.startswith("<?xml"):
        svg = svg.split("?>", 1)[-1].lstrip()
    return svg.strip()


def varsayilan_kitapcik(sinav) -> str:
    turler = (getattr(sinav, "kitapcik_turleri", None) or "A").split(",")
    return (turler[0].strip().upper()[:1] if turler else "A") or "A"


def optik_form_satirlari(
    sinav,
    talebeler,
    kitapcik: str | None = None,
    *,
    foto_base_url: str | None = None,
) -> list[dict[str, Any]]:
    kitap = kitapcik or varsayilan_kitapcik(sinav)
    satirlar = []
    for talebe in talebeler:
        metin = optik_karekod_metni(sinav.pk, talebe, kitap)
        qr_payload = (
            optik_foto_deep_link(foto_base_url, talebe.pk, kitap)
            if foto_base_url
            else metin
        )
        satirlar.append(
            {
                "talebe": talebe,
                "kitapcik": kitap,
                "karekod_metni": metin,
                "karekod_qr": qr_payload,
                "karekod_png": optik_karekod_png_data_uri(qr_payload),
                "karekod_svg": optik_karekod_svg(qr_payload),
            }
        )
    return satirlar
