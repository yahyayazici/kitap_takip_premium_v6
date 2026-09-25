"""KonuKazanimDetay Excel → DenemeKazanimSonucu.

Format (deneme kutuğu):
  satır 1 → ders (merged / forward-fill)
  satır 2 → konu / kazanım
  satır 3 → Yüzde | Net
  satır 4+ → Sınıf | Ad Soyad | değerler

Mevcut Talebe kayıtlarıyla eşleştirir; yeni talebe oluşturmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from openpyxl import load_workbook

from takip.deneme_excel import talebe_eslestir
from takip.deneme_models import DenemeKazanimSonucu, DenemeSinavi


def clean_label(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def name_key(value: str) -> str:
    return clean_label(value).casefold()


def parse_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace("%", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_net(value) -> tuple[Decimal | None, Decimal | None]:
    if value is None or value == "":
        return None, None
    text = str(value).strip()
    if not text:
        return None, None
    match = re.match(
        r"^\s*(-?\d+(?:[.,]\d+)?)\s*/\s*(-?\d+(?:[.,]\d+)?)\s*$",
        text,
    )
    if not match:
        return None, None
    return parse_decimal(match.group(1)), parse_decimal(match.group(2))


@dataclass
class KazanimImportStats:
    sonuc_yazilan: int = 0
    atlanan_bos: int = 0
    eslesen_talebe: int = 0
    eslesmeyen: list[str] = field(default_factory=list)
    konu_sayisi: int = 0
    uyari: list[str] = field(default_factory=list)


def _forward_fill(values: list) -> list[str | None]:
    filled: list[str | None] = []
    current: str | None = None
    for value in values:
        label = clean_label(value)
        if label:
            current = label
        filled.append(current)
    return filled


def _read_columns(ws) -> list[dict]:
    row1 = [cell.value for cell in ws[1]]
    row2 = [cell.value for cell in ws[2]]
    row3 = [cell.value for cell in ws[3]]
    subjects = _forward_fill(row1)
    topics = _forward_fill(row2)
    columns: list[dict] = []
    for index in range(2, len(row3)):
        metric_raw = clean_label(row3[index]).casefold()
        if metric_raw not in {"yüzde", "yuzde", "net"}:
            continue
        subject = subjects[index] if index < len(subjects) else None
        topic = topics[index] if index < len(topics) else None
        if not subject or not topic:
            continue
        columns.append(
            {
                "col": index + 1,
                "ders": subject,
                "konu": topic,
                "metrik": (
                    "yuzde"
                    if "yuzde" in metric_raw or "yüzde" in metric_raw
                    else "net"
                ),
            }
        )
    return columns


@transaction.atomic
def import_kazanim_excel(uploaded_file, *, deneme: DenemeSinavi) -> KazanimImportStats:
    stats = KazanimImportStats()
    wb = load_workbook(uploaded_file, data_only=True, read_only=False)
    try:
        ws = wb[wb.sheetnames[0]]
        columns = _read_columns(ws)
        if not columns:
            raise ValueError(
                "Excel'de konu kolonları bulunamadı. "
                "KonuKazanimDetay formatında (ders / konu / Yüzde-Net) olmalı."
            )

        topic_cols: dict[tuple[str, str], dict] = {}
        for col in columns:
            key = (name_key(col["ders"]), name_key(col["konu"]))
            bucket = topic_cols.setdefault(
                key,
                {
                    "ders": col["ders"],
                    "konu": col["konu"],
                    "ders_key": key[0],
                    "konu_key": key[1],
                    "yuzde_col": None,
                    "net_col": None,
                },
            )
            if col["metrik"] == "yuzde":
                bucket["yuzde_col"] = col["col"]
            else:
                bucket["net_col"] = col["col"]
        stats.konu_sayisi = len(topic_cols)

        eslesen: set[int] = set()
        yazilacak: dict[tuple, DenemeKazanimSonucu] = {}
        for row in ws.iter_rows(min_row=4, values_only=False):
            if not row:
                continue
            sinif_ad = clean_label(row[0].value if len(row) > 0 else None)
            ad_soyad = clean_label(row[1].value if len(row) > 1 else None)
            if not ad_soyad:
                continue

            talebe, _tip, _oneriler = talebe_eslestir(ad_soyad, sinif_ad)
            if talebe is None:
                etiket = f"{ad_soyad}" + (f" ({sinif_ad})" if sinif_ad else "")
                if etiket not in stats.eslesmeyen and len(stats.eslesmeyen) < 40:
                    stats.eslesmeyen.append(etiket)
                continue
            eslesen.add(talebe.id)

            for meta in topic_cols.values():
                yuzde = None
                net_dogru = None
                net_toplam = None
                if meta["yuzde_col"]:
                    idx = meta["yuzde_col"] - 1
                    if idx < len(row):
                        yuzde = parse_decimal(row[idx].value)
                if meta["net_col"]:
                    idx = meta["net_col"] - 1
                    if idx < len(row):
                        net_dogru, net_toplam = parse_net(row[idx].value)
                if yuzde is None and net_dogru is None and net_toplam is None:
                    stats.atlanan_bos += 1
                    continue
                anahtar = (talebe.id, meta["ders_key"], meta["konu_key"])
                yazilacak[anahtar] = DenemeKazanimSonucu(
                    deneme=deneme,
                    talebe=talebe,
                    ders_key=meta["ders_key"],
                    konu_key=meta["konu_key"],
                    ders_ad=meta["ders"][:120],
                    konu_ad=meta["konu"][:300],
                    yuzde=yuzde,
                    net_dogru=net_dogru,
                    net_toplam=net_toplam,
                )
        if yazilacak:
            DenemeKazanimSonucu.objects.filter(deneme=deneme).delete()
            DenemeKazanimSonucu.objects.bulk_create(yazilacak.values())
            stats.sonuc_yazilan = len(yazilacak)
        stats.eslesen_talebe = len(eslesen)
    finally:
        wb.close()

    if stats.sonuc_yazilan == 0:
        stats.uyari.append("Hiç kazanım satırı yazılmadı; dosya veya eşleşmeleri kontrol edin.")
    if stats.eslesmeyen:
        stats.uyari.append(
            f"{len(stats.eslesmeyen)} isim eşleşmedi (ör. {', '.join(stats.eslesmeyen[:5])})."
        )
    return stats
