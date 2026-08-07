"""Dini ders müfredatı — JSON kaynağından seviye/alan/konu seed."""

from __future__ import annotations

import json
from pathlib import Path

from takip.models import DiniDersKonu, DiniDersSeviyesi, DiniDersTakipAlani

_DATA_PATH = Path(__file__).resolve().parent / "data" / "dini_ders_mufredat.json"

_ALAN_SIRA: tuple[tuple[str, int], ...] = (
    ("İlmihal", 1),
    ("Sure Ezberi", 2),
    ("Tecvid", 3),
    ("Arapça", 4),
    ("Adab-ı Muaşeret", 5),
)

_SEVIYE_SIRA: tuple[tuple[str, int], ...] = (
    ("Seviye 1", 1),
    ("Seviye 2", 2),
    ("Seviye 3", 3),
    ("Seviye 4", 4),
)


def _load_mufredat() -> dict[str, dict[str, list[str]]]:
    with _DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def seed_dini_ders_mufredat(*, replace_demo: bool = True) -> dict:
    """Seviye, alan ve konu kayıtlarını müfredat JSON dosyasından yükler."""
    mufredat = _load_mufredat()
    stats: dict = {
        "seviyeler": 0,
        "alanlar": 0,
        "konular_olusturulan": 0,
        "konular_guncellenen": 0,
        "konular_pasiflestirilen": 0,
    }

    seviyeler: dict[str, DiniDersSeviyesi] = {}
    for ad, sira in _SEVIYE_SIRA:
        seviye, _ = DiniDersSeviyesi.objects.update_or_create(
            ad=ad,
            defaults={"sira": sira, "aktif": True},
        )
        if seviye.sira != sira or not seviye.aktif:
            seviye.sira = sira
            seviye.aktif = True
            seviye.save(update_fields=["sira", "aktif"])
        seviyeler[ad] = seviye
        stats["seviyeler"] += 1

    alanlar: dict[str, DiniDersTakipAlani] = {}
    for ad, sira in _ALAN_SIRA:
        alan, _ = DiniDersTakipAlani.objects.update_or_create(
            ad=ad,
            defaults={"sira": sira, "aktif": True},
        )
        if alan.sira != sira or not alan.aktif:
            alan.sira = sira
            alan.aktif = True
            alan.save(update_fields=["sira", "aktif"])
        alanlar[ad] = alan
        stats["alanlar"] += 1

    beklenen: set[tuple[int, int, str]] = set()

    for seviye_ad, alan_konular in mufredat.items():
        seviye = seviyeler.get(seviye_ad)
        if not seviye:
            continue
        for alan_ad, konular in alan_konular.items():
            alan = alanlar.get(alan_ad)
            if not alan:
                continue
            for sira, konu_ad in enumerate(konular, start=1):
                beklenen.add((alan.pk, seviye.pk, konu_ad))
                konu, created = DiniDersKonu.objects.get_or_create(
                    alan=alan,
                    seviye=seviye,
                    ad=konu_ad,
                    defaults={"sira": sira, "aktif": True},
                )
                if created:
                    stats["konular_olusturulan"] += 1
                else:
                    changed = False
                    if konu.sira != sira:
                        konu.sira = sira
                        changed = True
                    if not konu.aktif:
                        konu.aktif = True
                        changed = True
                    if changed:
                        konu.save(update_fields=["sira", "aktif"])
                        stats["konular_guncellenen"] += 1

    if replace_demo:
        for konu in DiniDersKonu.objects.filter(aktif=True).select_related("alan", "seviye"):
            key = (konu.alan_id, konu.seviye_id, konu.ad)
            if key not in beklenen:
                konu.aktif = False
                konu.save(update_fields=["aktif"])
                stats["konular_pasiflestirilen"] += 1

    stats["konu_sayilari"] = {
        seviye_ad: sum(len(konular) for konular in alan_konular.values())
        for seviye_ad, alan_konular in mufredat.items()
    }
    return stats
