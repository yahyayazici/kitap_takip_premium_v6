"""Telefon numarası normalizasyon / gösterim formatı."""

from __future__ import annotations


def telefon_rakamlar(telefon: str) -> str:
    return "".join(ch for ch in (telefon or "") if ch.isdigit())


def telefon_formatla(telefon: str) -> str:
    """TR cep/sabit numarayı 05XX XXX XX XX formatına çevirir."""
    digits = telefon_rakamlar(telefon)
    if not digits:
        return ""

    if digits.startswith("90") and len(digits) >= 12:
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("5"):
        digits = "0" + digits
    elif len(digits) == 10 and not digits.startswith("0"):
        digits = "0" + digits

    if len(digits) == 11 and digits.startswith("0"):
        return f"{digits[:4]} {digits[4:7]} {digits[7:9]} {digits[9:]}"

    return (telefon or "").strip()


def telefon_temizle_veya_hata(telefon: str) -> str:
    """Boşsa boş döner; doluysa formatlar, geçersizse ValueError."""
    ham = (telefon or "").strip()
    if not ham:
        return ""
    digits = telefon_rakamlar(ham)
    if digits.startswith("90") and len(digits) >= 12:
        local = digits[2:]
    elif digits.startswith("0"):
        local = digits[1:]
    else:
        local = digits
    if len(local) != 10:
        raise ValueError("Telefon 10 haneli olmalı (örn. 05XX XXX XX XX).")
    return telefon_formatla(ham)
