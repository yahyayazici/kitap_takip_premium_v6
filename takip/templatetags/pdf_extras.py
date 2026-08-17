from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

register = template.Library()


def _pdf_bar_int(value) -> int:
    try:
        sayi = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return 0
    pct = int(sayi.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(0, min(100, pct))


@register.filter
def pdf_puan(value):
    """PDF çıktısı için ondalık ayraç: 96,67"""
    if value in (None, "", "—"):
        return "—"
    try:
        sayi = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "0,00"

    return f"{sayi:.2f}".replace(".", ",")


@register.filter
def pdf_bar_pct(value):
    """Başarı çubuğu doluluk yüzdesi (0–100)."""
    return _pdf_bar_int(value)


@register.filter
def pdf_density_class(count) -> str:
    """Satır sayısına göre tek sayfa PDF yoğunluk sınıfı."""
    try:
        satir = int(count)
    except (TypeError, ValueError):
        satir = 0

    if satir <= 14:
        return "density-s"
    if satir <= 22:
        return "density-m"
    if satir <= 32:
        return "density-l"
    return "density-xl"
