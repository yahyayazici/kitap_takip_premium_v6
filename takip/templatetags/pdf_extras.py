from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def pdf_puan(value):
    """PDF çıktısı için ondalık ayraç: 96,67"""
    try:
        sayi = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "0,00"

    return f"{sayi:.2f}".replace(".", ",")


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
