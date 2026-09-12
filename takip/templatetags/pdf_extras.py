from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

register = template.Library()


# Ders kategorisi -> (aksan rengi, soluk zemin rengi). Anahtarlar
# takip.dershane_program_service.DERS_RENKLERI ile aynı eşleştirme mantığını
# kullanır (isimde geçen anahtar kelime ile bulunur).
_DERS_TON_PALETI: dict[str, tuple[str, str]] = {
    "matematik": ("#0a6cff", "#eef4ff"),
    "fen bilimleri": ("#1fae66", "#eafaf1"),
    "fen": ("#1fae66", "#eafaf1"),
    "türkçe": ("#12a3ad", "#e8f9fa"),
    "turkce": ("#12a3ad", "#e8f9fa"),
    "sosyal bilgiler": ("#e8730f", "#fef3e8"),
    "sosyal": ("#e8730f", "#fef3e8"),
    "ingilizce": ("#8b3fd1", "#f5edfc"),
    "din kültürü": ("#c99a06", "#fbf5df"),
    "din": ("#c99a06", "#fbf5df"),
    "rehberlik": ("#0f9dbd", "#e6f7fb"),
    "etüt": ("#6c4fd1", "#efecfc"),
}
_DERS_TON_VARSAYILAN = ("#6b7688", "#f4f5f7")


def _ders_ton(ders_adi) -> tuple[str, str]:
    anahtar = (str(ders_adi or "")).strip().lower()
    for key, ton in _DERS_TON_PALETI.items():
        if key in anahtar:
            return ton
    return _DERS_TON_VARSAYILAN


@register.filter
def ders_aksan(ders_adi):
    """Ders adına göre koyu/doygun aksan rengi (sol çizgi için)."""
    return _ders_ton(ders_adi)[0]


@register.filter
def ders_ton_zemin(ders_adi):
    """Ders adına göre çok soluk zemin rengi."""
    return _ders_ton(ders_adi)[1]


@register.filter
def saat_bas(saat_araligi):
    """'14:40 – 15:20' -> '14:40'"""
    parcalar = str(saat_araligi or "").split("–")
    return parcalar[0].strip() if parcalar else ""


@register.filter
def saat_bit(saat_araligi):
    """'14:40 – 15:20' -> '15:20'"""
    parcalar = str(saat_araligi or "").split("–")
    return parcalar[1].strip() if len(parcalar) > 1 else ""


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
