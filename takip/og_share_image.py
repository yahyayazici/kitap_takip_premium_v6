"""WhatsApp / Open Graph paylaşım görseli — logo + kurs adı."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

from config.branding import PANEL_MODULE_LABEL, PANEL_NAME, PANEL_TAGLINE

OG_WIDTH = 1200
OG_HEIGHT = 630

_OG_FONT_CANDIDATES_BOLD = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
_OG_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _OG_FONT_CANDIDATES_BOLD if bold else _OG_FONT_CANDIDATES
    for path in candidates:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _brand_gradient(size: tuple[int, int]) -> Image.Image:
    base = Image.new("RGB", size, "#15427f")
    draw = ImageDraw.Draw(base)
    for y in range(size[1]):
        ratio = y / max(size[1] - 1, 1)
        r = int(21 + (42 - 21) * ratio)
        g = int(66 + (90 - 66) * ratio)
        b = int(127 + (158 - 127) * ratio)
        draw.line([(0, y), (size[0], y)], fill=(r, g, b))
    return base


def _fit_logo(logo: Image.Image, max_h: int, max_w: int) -> Image.Image:
    logo = logo.convert("RGBA")
    w, h = logo.size
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        logo = logo.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return logo


@lru_cache(maxsize=1)
def render_og_share_png() -> bytes:
    static_img = settings.BASE_DIR / "static" / "images" / "cinili-saray-og-share.png"
    if static_img.is_file():
        return static_img.read_bytes()

    canvas = _brand_gradient((OG_WIDTH, OG_HEIGHT))
    draw = ImageDraw.Draw(canvas)

    logo_path = settings.BASE_DIR / "static" / "images" / "cinili-saray-logo-white.png"
    if not logo_path.is_file():
        logo_path = settings.BASE_DIR / "static" / "images" / "cinili-saray-logo-transparent.png"

    logo_x = 72
    text_x = 420
    if logo_path.is_file():
        logo = _fit_logo(Image.open(logo_path), max_h=380, max_w=300)
        logo_y = (OG_HEIGHT - logo.height) // 2
        canvas.paste(logo, (logo_x, logo_y), logo)
    else:
        text_x = 80

    title_font = _load_font(56, bold=True)
    module_font = _load_font(30, bold=False)
    tagline_font = _load_font(24, bold=False)

    title = PANEL_NAME
    module = PANEL_MODULE_LABEL
    tagline = PANEL_TAGLINE

    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_h = title_bbox[3] - title_bbox[1]
    module_bbox = draw.textbbox((0, 0), module, font=module_font)
    module_h = module_bbox[3] - module_bbox[1]
    tag_bbox = draw.textbbox((0, 0), tagline, font=tagline_font)
    tag_h = tag_bbox[3] - tag_bbox[1]
    block_h = title_h + 18 + module_h + 14 + tag_h
    y = (OG_HEIGHT - block_h) // 2

    draw.text((text_x, y), title, fill="#ffffff", font=title_font)
    y += title_h + 18
    draw.text((text_x, y), module, fill="#c8daf5", font=module_font)
    y += module_h + 14
    draw.text((text_x, y), tagline, fill="#93b4e8", font=tagline_font)

    accent_y = OG_HEIGHT - 8
    draw.rectangle([(0, accent_y), (OG_WIDTH, OG_HEIGHT)], fill="#2f6ff3")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
