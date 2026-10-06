"""E-Kitap şablon filtreleri."""

from __future__ import annotations

import re

from django import template

register = template.Library()

_BASTAKI_SIRA = re.compile(r"^\s*\d+\s*[-_.)]\s*")


@register.filter
def insan_adi(ad: str) -> str:
    """Bölüm adı ham dosya adıysa okunur hale getirir.

    Yüklemede ad boş bırakılırsa dosya adı kullanılır (ör.
    "1-Sayisal-Bolum_Ogrenci-Kitapcigi_A"). Bu durumda baştaki sıra numarası
    atılır, ilk alt çizgiye kadarki kısım alınır ve tireler boşluğa çevrilir:
    "Sayisal Bolum". İnsan yazmış bir ad (boşluk içeren, alt çizgisiz) aynen kalır.
    """
    ad = (ad or "").strip()
    if not ad:
        return ""
    ham = "_" in ad or (" " not in ad and "-" in ad)
    if not ham:
        return ad
    govde = _BASTAKI_SIRA.sub("", ad).split("_", 1)[0]
    govde = re.sub(r"[-.]+", " ", govde).strip()
    return govde or ad
