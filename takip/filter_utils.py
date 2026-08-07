"""GET filtreleri — çoklu seçim desteği."""

from __future__ import annotations

from typing import Any


def get_int_list(get_params: Any, key: str) -> list[int]:
    sonuc: list[int] = []
    for raw in get_params.getlist(key):
        deger = str(raw).strip()
        if deger.isdigit():
            sonuc.append(int(deger))
    return sonuc


def get_str_list(get_params: Any, key: str) -> list[str]:
    return [str(x).strip() for x in get_params.getlist(key) if str(x).strip()]


def tek_veya_coklu_id(deger: str | None, degerler: list[int] | None) -> list[int]:
    if degerler:
        return degerler
    if deger and str(deger).strip().isdigit():
        return [int(deger)]
    return []


def qs_filtre_id(qs, alan: str, deger: str | None = None, degerler: list[int] | None = None):
    idler = tek_veya_coklu_id(deger, degerler)
    if not idler:
        return qs
    if len(idler) == 1:
        return qs.filter(**{alan: idler[0]})
    return qs.filter(**{f"{alan}__in": idler})
