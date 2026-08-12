"""Etüt hocası rehber PDF ekran görüntüleri — Pillow ile üretim."""

from __future__ import annotations

import io
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

NAVY = "#173b80"
NAVY_DARK = "#0f2744"
BLUE = "#2563eb"
BG = "#f4f7fb"
WHITE = "#ffffff"
BORDER = "#dbe4f0"
TEXT = "#334155"
MUTED = "#64748b"
GOLD = "#b8860b"
GREEN = "#059669"
AMBER = "#d97706"

FONT_BOLD = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
FONT_REG = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (FONT_BOLD if bold else FONT_REG):
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str,
    outline: str | None = None,
    radius: int = 14,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)


def _top_nav(draw: ImageDraw.ImageDraw, w: int, title: str) -> None:
    draw.rectangle((0, 0, w, 52), fill=NAVY)
    draw.text((18, 16), "Çinili Saray Proje", fill=WHITE, font=_font(14, bold=True))
    draw.text((w - 220, 18), title, fill="#c8daf5", font=_font(11))


def _hero(draw: ImageDraw.ImageDraw, w: int, title: str, meta: str, y: int = 64) -> int:
    _rounded_rect(draw, (16, y, w - 16, y + 72), fill=WHITE, outline=BORDER)
    draw.text((32, y + 16), title, fill=NAVY_DARK, font=_font(20, bold=True))
    draw.text((32, y + 44), meta, fill=MUTED, font=_font(11))
    return y + 88


def _card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    kicker: str,
    title: str,
    value: str,
    accent: str,
) -> None:
    _rounded_rect(draw, box, fill=WHITE, outline=BORDER)
    x1, y1, x2, y2 = box
    draw.rectangle((x1, y1, x1 + 5, y2), fill=accent)
    draw.text((x1 + 18, y1 + 14), kicker.upper(), fill=MUTED, font=_font(9, bold=True))
    draw.text((x1 + 18, y1 + 34), title, fill=TEXT, font=_font(12, bold=True))
    draw.text((x1 + 18, y2 - 32), value, fill=NAVY, font=_font(18, bold=True))


def _table_header(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, cols: list[str]) -> int:
    _rounded_rect(draw, (x, y, x + w, y + 28), fill="#eef3fb", outline=BORDER, radius=8)
    col_w = w // len(cols)
    for i, col in enumerate(cols):
        draw.text((x + 12 + i * col_w, y + 8), col.upper(), fill=MUTED, font=_font(9, bold=True))
    return y + 28


def _table_row(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    cols: list[str],
    bold_first: bool = False,
) -> int:
    draw.line((x, y + 26, x + w, y + 26), fill=BORDER, width=1)
    col_w = w // len(cols)
    for i, col in enumerate(cols):
        font = _font(11, bold=bold_first and i == 0)
        draw.text((x + 12 + i * col_w, y + 6), col, fill=TEXT, font=font)
    return y + 28


def _save(img: Image.Image, name: str) -> Path:
    out_dir = settings.BASE_DIR / "static" / "images" / "rehber"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    img.save(path, format="PNG", optimize=True)
    return path


def gorsel_panel_dashboard() -> Path:
    w, h = 1200, 680
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    _top_nav(draw, w, "Etüt Mesulü · Panel")
    y = _hero(draw, w, "Hoş geldiniz, Yahya", "Etüt Mesulü · Kurum yönetim paneli")

    cards = [
        ("Etüt kapsamı", "Sınıf sayısı", "3 sınıf · 42 talebe", BLUE),
        ("Bugün", "İmam & müezzin", "Ahmet Hoca", GREEN),
        ("Yemekçi", "Öğle", "Mehmet Usta", AMBER),
        ("Namaz", "Gelmeyenler", "2 talebe", "#dc2626"),
    ]
    cw = (w - 48) // 4
    for i, (k, t, v, c) in enumerate(cards):
        x1 = 16 + i * (cw + 5)
        _card(draw, (x1, y, x1 + cw - 5, y + 110), k, t, v, c)

    y += 130
    draw.text((20, y), "Kısayollar", fill=NAVY, font=_font(14, bold=True))
    shortcuts = ["Haftalık Karneler", "Talebeler", "Kitap Takip", "Etüt Planı", "Namaz Yoklama", "Duyurular"]
    sx, sy = 16, y + 28
    sw = (w - 48) // 3
    for i, label in enumerate(shortcuts):
        col = i % 3
        row = i // 3
        bx1 = sx + col * (sw + 8)
        by1 = sy + row * 58
        _rounded_rect(draw, (bx1, by1, bx1 + sw, by1 + 48), fill=WHITE, outline=BORDER)
        draw.text((bx1 + 14, by1 + 16), label, fill=NAVY, font=_font(12, bold=True))

    return _save(img, "02-panel.png")


def gorsel_haftalik_karneler() -> Path:
    w, h = 1200, 680
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    _top_nav(draw, w, "Haftalık Karneler")
    y = _hero(draw, w, "Haftalık Eğitim Karneleri", "Etüdünüzdeki talebelerin haftalık değerlendirme arşivi")

    _rounded_rect(draw, (16, y, w - 16, h - 20), fill=WHITE, outline=BORDER)
    draw.text((32, y + 16), "Aktif hafta · 12.08.2025 – 18.08.2025", fill=NAVY, font=_font(13, bold=True))
    draw.text((32, y + 38), "38 / 42 talebede bu hafta not var", fill=MUTED, font=_font(11))

    ty = y + 64
    cols = ["Talebe", "Sınıf", "Ders sayısı", "Ortalama", "Karne"]
    tw = w - 64
    ty = _table_header(draw, 32, ty, tw, cols)
    rows = [
        ("Ahmet Arif Demirci", "7-A", "6", "87", "PDF"),
        ("Ebubekir Başpınar", "7-A", "6", "92", "PDF"),
        ("Ahmed Enes Güneş", "7-B", "5", "78", "PDF"),
        ("Muhammed Ali Yıldız", "7-B", "6", "85", "PDF"),
        ("Ömer Faruk Kaya", "8-A", "6", "90", "PDF"),
    ]
    for row in rows:
        ty = _table_row(draw, 32, ty, tw, list(row), bold_first=True)

    return _save(img, "03-karneler.png")


def gorsel_kitap_takip() -> Path:
    w, h = 1200, 680
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    _top_nav(draw, w, "Kitap Takip")
    y = _hero(draw, w, "Günlük Okuma Girişi", "Zimmetli kitaplar için sayfa / okuma kaydı")

    _rounded_rect(draw, (16, y, w - 16, h - 20), fill=WHITE, outline=BORDER)
    draw.text((32, y + 16), "Toplu günlük okuma", fill=NAVY, font=_font(13, bold=True))
    draw.text((32, y + 38), "Sınıf: 7-A · Tarih: bugün", fill=MUTED, font=_font(11))

    ty = y + 64
    cols = ["Talebe", "Kitap", "Bugün okunan", "Toplam", "Durum"]
    tw = w - 64
    ty = _table_header(draw, 32, ty, tw, cols)
    rows = [
        ("Ahmet Arif Demirci", "Sonsuzluk Kandilinde", "12 sf", "148 sf", "Devam"),
        ("Ebubekir Başpınar", "Asr-ı Saadet 1", "8 sf", "96 sf", "Devam"),
        ("Ahmed Enes Güneş", "Hz. Ömer", "15 sf", "210 sf", "Devam"),
    ]
    for row in rows:
        ty = _table_row(draw, 32, ty, tw, list(row), bold_first=True)

    draw.text((32, ty + 16), "Kaydet butonu ile günlük okuma kayıtları sisteme işlenir.", fill=MUTED, font=_font(10))

    return _save(img, "04-kitap.png")


def gorsel_talebe_listesi() -> Path:
    w, h = 1200, 680
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    _top_nav(draw, w, "Talebeler")
    y = _hero(draw, w, "Talebe Listesi", "Etüt grubunuza bağlı aktif talebeler")

    _rounded_rect(draw, (16, y, (w // 2) - 8, h - 20), fill=WHITE, outline=BORDER)
    draw.text((32, y + 16), "Filtreler", fill=NAVY, font=_font(13, bold=True))
    filters = ["Sınıf: Tümü", "Durum: Aktif", "Etüt: Yahya Yazıcı"]
    fy = y + 44
    for f in filters:
        _rounded_rect(draw, (32, fy, 280, fy + 32), fill="#eff6ff", outline="#bfdbfe", radius=8)
        draw.text((44, fy + 9), f, fill=NAVY, font=_font(10))
        fy += 40

    rx = (w // 2) + 8
    _rounded_rect(draw, (rx, y, w - 16, h - 20), fill=WHITE, outline=BORDER)
    ty = y + 16
    cols = ["Ad Soyad", "Sınıf", "Etüt", "Durum"]
    tw = w - rx - 32
    ty = _table_header(draw, rx + 16, ty, tw, cols)
    rows = [
        ("Ahmet Arif Demirci", "7-A", "Yahya Y.", "Aktif"),
        ("Ebubekir Başpınar", "7-A", "Yahya Y.", "Aktif"),
        ("Ahmed Enes Güneş", "7-B", "Yahya Y.", "Aktif"),
    ]
    for row in rows:
        ty = _table_row(draw, rx + 16, ty, tw, list(row), bold_first=True)

    return _save(img, "05-talebeler.png")


def gorsel_mobil_panel() -> Path:
    w, h = 390, 720
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, w, 44), fill=NAVY)
    draw.text((14, 14), "Çinili Saray", fill=WHITE, font=_font(12, bold=True))

    _rounded_rect(draw, (12, 56, w - 12, 130), fill=WHITE, outline=BORDER)
    draw.text((24, 72), "Hoş geldiniz", fill=NAVY_DARK, font=_font(16, bold=True))
    draw.text((24, 98), "Etüt Mesulü · 3 sınıf", fill=MUTED, font=_font(10))

    y = 146
    for title, sub in [
        ("Haftalık Karneler", "Not arşivi"),
        ("Talebeler", "42 aktif"),
        ("Kitap Takip", "Okuma girişi"),
        ("Namaz Yoklama", "Günlük"),
    ]:
        _rounded_rect(draw, (12, y, w - 12, y + 64), fill=WHITE, outline=BORDER)
        draw.text((24, y + 14), title, fill=NAVY, font=_font(13, bold=True))
        draw.text((24, y + 36), sub, fill=MUTED, font=_font(10))
        y += 72

    return _save(img, "06-mobil.png")


def tum_rehber_gorsellerini_uret(*, giris_koru: bool = True) -> list[Path]:
    """Tüm rehber PNG'lerini üretir. 01-giris.png varsa korunur."""
    uretilen: list[Path] = []
    giris = settings.BASE_DIR / "static" / "images" / "rehber" / "01-giris.png"
    if not giris.is_file() or not giris_koru:
        # Basit giriş mock — gerçek ekran görüntüsü yoksa
        w, h = 1200, 680
        img = Image.new("RGB", (w, h), "#faf8f5")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, w // 2, h), fill="#f0ebe3")
        draw.text((w // 2 + 80, 180), "Çinili Saray Proje", fill=NAVY_DARK, font=_font(28, bold=True))
        draw.text((w // 2 + 80, 220), "YÖNETİM PLATFORMU", fill=GOLD, font=_font(12, bold=True))
        _rounded_rect(draw, (w // 2 + 60, 260, w - 60, 520), fill=WHITE, outline=BORDER)
        draw.text((w // 2 + 90, 290), "Oturum açın", fill=NAVY_DARK, font=_font(22, bold=True))
        draw.text((w // 2 + 90, 360), "Kullanıcı adı", fill=MUTED, font=_font(10, bold=True))
        _rounded_rect(draw, (w // 2 + 90, 378, w - 90, 418), fill="#f8fafc", outline=BORDER)
        draw.text((w // 2 + 90, 432), "Şifre", fill=MUTED, font=_font(10, bold=True))
        _rounded_rect(draw, (w // 2 + 90, 450, w - 90, 490), fill="#f8fafc", outline=BORDER)
        _rounded_rect(draw, (w // 2 + 90, 510, w - 90, 550), fill=GOLD, outline=GOLD)
        draw.text((w // 2 + 170, 524), "GİRİŞ YAP", fill=WHITE, font=_font(14, bold=True))
        uretilen.append(_save(img, "01-giris.png"))
    else:
        uretilen.append(giris)

    uretilen.extend([
        gorsel_panel_dashboard(),
        gorsel_haftalik_karneler(),
        gorsel_kitap_takip(),
        gorsel_talebe_listesi(),
        gorsel_mobil_panel(),
    ])
    return uretilen
