"""Ölçme Merkezi — Excel raporları."""

from __future__ import annotations

from takip.excel_rapor import ExcelKolon, ExcelSayfa, coklu_rapor_xlsx
from takip.ktt_models import KttSinav
from takip.olcme_service import sinav_kazanim_analizi, sinav_konu_analizi, sinav_sonuc_ozet
from takip.ktt_service import ktt_sonuc_talebeleri


def sinav_analiz_xlsx(sinav: KttSinav, user) -> bytes:
    konu = sinav_konu_analizi(sinav)
    kazanim = sinav_kazanim_analizi(sinav)
    ozet = sinav_sonuc_ozet(sinav, ktt_sonuc_talebeleri(user, sinav))

    konu_satirlar = [
        (
            r["konu_ad"],
            r["soru_sayisi"],
            r.get("dogru", ""),
            r.get("yanlis", ""),
            r.get("bos", ""),
            f"{r.get('basari_yuzde', '')}%",
        )
        for r in konu
    ]
    kazanim_satirlar = [
        (
            r["kazanim_ad"],
            r["konu_ad"],
            r["soru_sayisi"],
            r.get("dogru", ""),
            r.get("yanlis", ""),
            r.get("bos", ""),
            f"{r.get('basari_yuzde', '')}%",
        )
        for r in kazanim
    ]
    sonuc_satirlar = [
        (
            o["talebe"].ad_soyad,
            o["talebe"].talebe_no or "",
            o.get("dogru", ""),
            o.get("yanlis", ""),
            o.get("bos", ""),
            o.get("net", ""),
        )
        for o in ozet
    ]

    return coklu_rapor_xlsx(
        [
            ExcelSayfa(
                adi="Konu",
                baslik=f"{sinav.ad} — Konu Analizi",
                kolonlar=[
                    ExcelKolon("Konu", 28),
                    ExcelKolon("Soru", 8, tip="sayi"),
                    ExcelKolon("Doğru", 8, tip="sayi"),
                    ExcelKolon("Yanlış", 8, tip="sayi"),
                    ExcelKolon("Boş", 8, tip="sayi"),
                    ExcelKolon("Başarı", 10),
                ],
                satirlar=konu_satirlar,
            ),
            ExcelSayfa(
                adi="Kazanım",
                baslik=f"{sinav.ad} — Kazanım Analizi",
                kolonlar=[
                    ExcelKolon("Kazanım", 32),
                    ExcelKolon("Konu", 24),
                    ExcelKolon("Soru", 8, tip="sayi"),
                    ExcelKolon("Doğru", 8, tip="sayi"),
                    ExcelKolon("Yanlış", 8, tip="sayi"),
                    ExcelKolon("Boş", 8, tip="sayi"),
                    ExcelKolon("Başarı", 10),
                ],
                satirlar=kazanim_satirlar,
            ),
            ExcelSayfa(
                adi="Sonuçlar",
                baslik=f"{sinav.ad} — Talebe Sonuçları",
                kolonlar=[
                    ExcelKolon("Talebe", 26),
                    ExcelKolon("No", 10),
                    ExcelKolon("D", 6, tip="sayi"),
                    ExcelKolon("Y", 6, tip="sayi"),
                    ExcelKolon("B", 6, tip="sayi"),
                    ExcelKolon("Net", 8),
                ],
                satirlar=sonuc_satirlar,
            ),
        ]
    )


def sinav_sonuc_csv(sinav: KttSinav, user) -> str:
    """UTF-8 BOM ile talebe sonuç CSV metni."""
    import csv
    from io import StringIO

    ozet = sinav_sonuc_ozet(sinav, ktt_sonuc_talebeleri(user, sinav))
    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Talebe", "Talebe No", "Doğru", "Yanlış", "Boş", "Net", "Durum"])
    for row in ozet:
        talebe = row["talebe"]
        durum = "Tamam" if row["tamam"] else ("Kısmi" if row["kismi"] else "Eksik")
        writer.writerow(
            [
                talebe.ad_soyad,
                talebe.talebe_no or "",
                row.get("dogru", ""),
                row.get("yanlis", ""),
                row.get("bos", ""),
                row.get("net", ""),
                durum,
            ]
        )
    return buffer.getvalue()
