"""İletişim Merkezi — PDF üretimi (mevcut rapor şablonlarını yeniden kullanır)."""

from __future__ import annotations

from django.template.loader import render_to_string
from django.utils.timezone import now

from takip.ktt_models import KttSinav
from takip.pdf_utils import coz_pdf_sayfa, html_to_pdf, pdf_engine_status


def _ktt_sonuc_ozeti(sonuclar_list):
    adet = len(sonuclar_list)
    if not adet:
        return {
            "ogrenci_sayisi": 0,
            "ortalama_net": 0,
            "ortalama_puan": 0,
            "en_yuksek_puan": 0,
        }
    toplam_net = sum(float(s.net or 0) for s in sonuclar_list)
    toplam_puan = sum(float(s.puan or 0) for s in sonuclar_list)
    en_yuksek = max(float(s.puan or 0) for s in sonuclar_list)
    return {
        "ogrenci_sayisi": adet,
        "ortalama_net": round(toplam_net / adet, 2),
        "ortalama_puan": round(toplam_puan / adet, 2),
        "en_yuksek_puan": round(en_yuksek, 2),
    }


def ktt_pdf_bytes(request, ktt: KttSinav) -> tuple[bytes | None, str]:
    """ktt_detay_pdf ile aynı çıktı — iletişim ekleri için."""
    sonuclar = ktt.sonuclar.select_related("talebe").order_by("-puan", "-net", "talebe__ad_soyad")
    sonuclar_list = list(sonuclar)
    if not sonuclar_list:
        return None, ""
    ozet = _ktt_sonuc_ozeti(sonuclar_list)
    pdf_sayfa = coz_pdf_sayfa(request)
    adet = len(sonuclar_list)
    split_at = (adet + 1) // 2
    sonuc_split = adet > 24

    html = render_to_string(
        "ktt_detay_pdf.html",
        {
            "ktt": ktt,
            "sonuclar": sonuclar_list,
            "sonuclar_sol": sonuclar_list[:split_at],
            "sonuclar_sag": sonuclar_list[split_at:],
            "sonuc_split": sonuc_split,
            "split_at": split_at,
            "analiz_goster": False,
            "ozet": ozet,
            "olusturma_tarihi": now(),
            "pdf_sayfa": pdf_sayfa,
        },
        request=request,
    )
    pdf_verisi = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        raise RuntimeError(f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})")
    ad = (ktt.ad or "").strip() or f"KTT {ktt.pk}"
    return pdf_verisi, f"{ad}.pdf"
