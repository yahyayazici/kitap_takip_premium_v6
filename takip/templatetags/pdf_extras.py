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


def deneme_yuz_puan(dogru, yanlis, bos) -> Decimal:
    """Doğru sayısı / soru sayısı × 100. Kitap sınavıyla aynı 100’lük puan."""
    toplam = int(dogru or 0) + int(yanlis or 0) + int(bos or 0)
    if toplam <= 0:
        return Decimal("0.00")
    return (
        Decimal(int(dogru or 0)) * Decimal("100") / Decimal(toplam)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _puan_metin(sayi: Decimal) -> str:
    return f"{sayi:.2f}".replace(".", ",")


@register.simple_tag
def deneme_satir_yuz_puan(sonuc):
    """Satır puanı, 100 üzerinden."""
    return _puan_metin(
        deneme_yuz_puan(
            getattr(sonuc, "toplam_dogru", 0),
            getattr(sonuc, "toplam_yanlis", 0),
            getattr(sonuc, "toplam_bos", 0),
        )
    )


@register.simple_tag
def deneme_yuz_ozet(sonuclar):
    """Listenin 100’lük puan ortalaması ve en yükseği."""
    puanlar = [
        deneme_yuz_puan(
            getattr(sonuc, "toplam_dogru", 0),
            getattr(sonuc, "toplam_yanlis", 0),
            getattr(sonuc, "toplam_bos", 0),
        )
        for sonuc in sonuclar
    ]
    if not puanlar:
        return {"ortalama": "—", "en_yuksek": "—"}
    ortalama = (sum(puanlar, Decimal("0")) / Decimal(len(puanlar))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {
        "ortalama": _puan_metin(ortalama),
        "en_yuksek": _puan_metin(max(puanlar)),
    }


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
def pdf_bant(value) -> str:
    """KTT başarı bandı: 85+ yüksek, 70–85 iyi, 50–70 orta, altı düşük."""
    try:
        sayi = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "dusuk"
    if sayi >= 85:
        return "yuksek"
    if sayi >= 70:
        return "iyi"
    if sayi >= 50:
        return "orta"
    return "dusuk"


@register.filter
def pdf_cember(value) -> str:
    """SVG halkası için 0–100 doluluk ve boşluk, nokta ayraçlı."""
    try:
        sayi = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        sayi = Decimal("0.0")
    if sayi < 0:
        sayi = Decimal("0.0")
    if sayi > 100:
        sayi = Decimal("100.0")
    kalan = Decimal("100.0") - sayi
    return f"{sayi:.1f} {kalan:.1f}"


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
