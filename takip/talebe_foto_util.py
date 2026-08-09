"""Talebe biyometrik fotoğraf yardımcıları."""

from __future__ import annotations

from django.core.exceptions import ValidationError

MAX_BIYOMETRIK_FOTO_BOYUT = 5 * 1024 * 1024


def dogrula_biyometrik_foto(foto) -> None:
    if not foto:
        return
    if foto.size > MAX_BIYOMETRIK_FOTO_BOYUT:
        raise ValidationError("Fotoğraf en fazla 5 MB olabilir.")


def talebe_foto_meta(talebe) -> dict[str, str]:
    ad = getattr(talebe, "ad_soyad", "") or ""
    bas_harf = ad[:1].upper() if ad else "?"
    foto = getattr(talebe, "biyometrik_foto", None)
    url = foto.url if foto else ""
    return {"foto_url": url, "bas_harf": bas_harf}
