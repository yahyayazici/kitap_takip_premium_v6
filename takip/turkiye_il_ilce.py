"""Türkiye il / ilçe listeleri."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent / "data" / "turkiye_il_ilce.json"


@lru_cache(maxsize=1)
def il_ilce_haritasi() -> dict[str, list[str]]:
    with _DATA_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return {str(il): [str(x) for x in ilceler] for il, ilceler in data.items()}


def turkiye_illeri() -> list[str]:
    return sorted(il_ilce_haritasi().keys(), key=lambda x: x.casefold())


def turkiye_ilceleri(il: str) -> list[str]:
    if not il:
        return []
    harita = il_ilce_haritasi()
    if il in harita:
        return list(harita[il])
    for key, vals in harita.items():
        if key.casefold() == il.casefold():
            return list(vals)
    return []


def il_secenekleri() -> list[tuple[str, str]]:
    return [("", "İl seçin")] + [(il, il) for il in turkiye_illeri()]


def ilce_secenekleri(il: str = "") -> list[tuple[str, str]]:
    ilceler = turkiye_ilceleri(il)
    if not ilceler:
        return [("", "Önce il seçin")]
    return [("", "İlçe seçin")] + [(x, x) for x in ilceler]


def tum_ilceler() -> list[str]:
    sonuc: list[str] = []
    for il in turkiye_illeri():
        for ilce in turkiye_ilceleri(il):
            sonuc.append(ilce)
    return sonuc


def memleket_gecerli(il: str, ilce: str = "") -> bool:
    if not il:
        return not ilce
    ilceler = turkiye_ilceleri(il)
    if not ilceler:
        return False
    if not ilce:
        return True
    return any(x.casefold() == ilce.casefold() for x in ilceler)
