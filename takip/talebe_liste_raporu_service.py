"""Talebe liste raporu — sınıf bazlı ve kurum geneli PDF verisi."""

from __future__ import annotations

import re
from typing import Iterable

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

from config.branding import PANEL_ORG, PANEL_SHORT

from .models import SinifSube, Talebe
from .namaz_yoklama_service import talebeler_gruplu
from .pdf_utils import html_to_pdf, make_pdf_response, pdf_error_response, pdf_engine_status


def _sinif_grup_sira(etiket: str) -> tuple:
    parcalar = etiket.split("-", 1)
    sinif = parcalar[0] if parcalar else etiket
    sube = parcalar[1] if len(parcalar) > 1 else ""
    rakamlar = re.sub(r"\D", "", sinif)
    numara = int(rakamlar) if rakamlar else 99
    return (numara, sinif.casefold(), sube.casefold())


def _sinif_baslik(etiket: str) -> str:
    return f"{etiket.upper()} SINIFI"


def _pdf_yogunluk_sinifi(toplam: int, rapor_turu: str) -> str:
    if rapor_turu == "sinif":
        if toplam <= 32:
            return "yogunluk-normal"
        if toplam <= 48:
            return "yogunluk-sik"
        if toplam <= 64:
            return "yogunluk-xs"
        return "yogunluk-xxs"

    if toplam <= 55:
        return "yogunluk-normal"
    if toplam <= 90:
        return "yogunluk-sik"
    if toplam <= 130:
        return "yogunluk-xs"
    return "yogunluk-xxs"


def _rapor_talebe_qs(kaynak: QuerySet[Talebe]) -> QuerySet[Talebe]:
    return (
        kaynak.filter(aktif=True)
        .select_related("sinif_sube")
        .order_by("ad_soyad")
    )


def sinif_rapor_verisi(
    talebe_qs: QuerySet[Talebe],
    sinif_sube_id: int,
) -> dict | None:
    sinif = SinifSube.objects.filter(pk=sinif_sube_id, aktif=True).first()
    if sinif is None:
        return None

    talebeler = list(
        _rapor_talebe_qs(talebe_qs)
        .filter(sinif_sube_id=sinif_sube_id)
        .values_list("ad_soyad", flat=True)
    )
    etiket = f"{sinif.sinif}-{sinif.sube}".upper()

    return {
        "rapor_turu": "sinif",
        "baslik": f"{etiket} SINIFI TALEBE LİSTESİ",
        "talebeler": talebeler,
        "bolumler": [],
        "toplam": len(talebeler),
        "yogunluk": _pdf_yogunluk_sinifi(len(talebeler), "sinif"),
    }


def kurum_rapor_verisi(talebe_qs: QuerySet[Talebe]) -> dict:
    bolumler = []
    for grup in talebeler_gruplu(_rapor_talebe_qs(talebe_qs)):
        etiket = grup["sinif"]
        isimler = sorted(
            (talebe.ad_soyad for talebe in grup["talebeler"]),
            key=str.casefold,
        )
        bolumler.append(
            {
                "baslik": _sinif_baslik(etiket),
                "talebeler": isimler,
            }
        )

    bolumler.sort(key=lambda b: _sinif_grup_sira(b["baslik"].replace(" SINIFI", "")))
    toplam = sum(len(b["talebeler"]) for b in bolumler)

    return {
        "rapor_turu": "kurum",
        "baslik": "KURUM GENELİ TALEBE LİSTESİ",
        "talebeler": [],
        "bolumler": bolumler,
        "toplam": toplam,
        "yogunluk": _pdf_yogunluk_sinifi(toplam, "kurum"),
    }


def erisilebilir_siniflar(talebe_qs: QuerySet[Talebe]) -> Iterable[SinifSube]:
    sinif_idleri = (
        _rapor_talebe_qs(talebe_qs)
        .exclude(sinif_sube_id__isnull=True)
        .values_list("sinif_sube_id", flat=True)
        .distinct()
    )
    return SinifSube.objects.filter(id__in=sinif_idleri, aktif=True).order_by(
        "sinif",
        "sube",
    )


def sinif_etiketi_goster(sinif: SinifSube) -> str:
    return f"{sinif.sinif}-{sinif.sube}"


def siniflar_rapor_verisi(
    talebe_qs: QuerySet[Talebe],
    sinif_sube_ids: list[int],
) -> dict | None:
    if not sinif_sube_ids:
        return None

    bolumler = []
    for sinif_sube_id in sinif_sube_ids:
        parca = sinif_rapor_verisi(talebe_qs, sinif_sube_id)
        if parca and parca["talebeler"]:
            bolumler.append(
                {
                    "baslik": parca["baslik"].replace(" TALEBE LİSTESİ", " SINIFI"),
                    "talebeler": parca["talebeler"],
                }
            )

    if not bolumler:
        return None

    bolumler.sort(key=lambda b: _sinif_grup_sira(b["baslik"].replace(" SINIFI", "")))
    toplam = sum(len(b["talebeler"]) for b in bolumler)
    baslik = (
        bolumler[0]["baslik"].replace(" SINIFI", "")
        if len(bolumler) == 1
        else f"{len(bolumler)} SINIF TALEBE LİSTESİ"
    )

    return {
        "rapor_turu": "sinif",
        "baslik": baslik.upper() + (" TALEBE LİSTESİ" if len(bolumler) == 1 else ""),
        "talebeler": bolumler[0]["talebeler"] if len(bolumler) == 1 else [],
        "bolumler": bolumler if len(bolumler) > 1 else [],
        "toplam": toplam,
        "yogunluk": _pdf_yogunluk_sinifi(toplam, "kurum"),
    }


def talebe_liste_raporu_pdf_yanit(
    request: HttpRequest,
    *,
    rapor_turu: str,
    sinif_sube_id: int | None,
    sinif_sube_ids: list[int] | None = None,
    talebe_qs: QuerySet[Talebe],
) -> HttpResponse:
    idler = sinif_sube_ids or ([sinif_sube_id] if sinif_sube_id else [])

    if rapor_turu == "sinif":
        if not idler:
            return pdf_error_response("En az bir sınıf seçin.", status=400)
        if len(idler) == 1:
            veri = sinif_rapor_verisi(talebe_qs, idler[0])
        else:
            veri = siniflar_rapor_verisi(talebe_qs, idler)
        if veri is None:
            return pdf_error_response("Seçilen sınıflar bulunamadı.", status=404)
        if not veri["talebeler"] and not veri["bolumler"]:
            return pdf_error_response("Seçilen sınıflarda raporlanacak aktif talebe yok.", status=404)
        dosya_adi = f"{veri['baslik'].lower().replace(' ', '-')}.pdf"
    elif rapor_turu == "kurum":
        veri = kurum_rapor_verisi(talebe_qs)
        if not veri["bolumler"]:
            return pdf_error_response("Raporlanacak talebe bulunamadı.", status=404)
        dosya_adi = "kurum-geneli-talebe-listesi.pdf"
    else:
        return pdf_error_response("Geçersiz rapor türü.", status=400)

    html_metni = render_to_string(
        "talebe_liste_raporu_pdf.html",
        {
            **veri,
            "panel_org": PANEL_ORG,
            "panel_short": PANEL_SHORT,
            "tarih": timezone.localdate(),
        },
        request=request,
    )

    pdf_verisi = html_to_pdf(
        html_metni,
        base_url=request.build_absolute_uri("/"),
    )
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    return make_pdf_response(pdf_verisi, dosya_adi)


def talebe_liste_excel_yanit(
    *,
    talebe_qs: QuerySet[Talebe],
    baslik: str = "Talebe Listesi",
    dosya_adi: str = "talebe-listesi.xlsx",
) -> HttpResponse:
    """Yetkili talebe listesini ortak Excel tasarımıyla indirir."""
    from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit

    qs = (
        talebe_qs.select_related("sinif_sube", "etut_hocasi", "dini_ders_hocasi")
        .order_by("sinif_sube__sinif", "sinif_sube__sube", "ad_soyad")
    )
    satirlar: list[list] = []
    for t in qs:
        sinif = ""
        sube = ""
        if t.sinif_sube_id:
            sinif = t.sinif_sube.sinif
            sube = t.sinif_sube.sube
        else:
            sinif = getattr(t, "sinif", "") or ""
            sube = getattr(t, "sube", "") or ""
        satirlar.append(
            [
                t.ad_soyad,
                t.talebe_no or "",
                sinif,
                sube,
                t.etut_hocasi.ad_soyad if t.etut_hocasi_id else "",
                t.dini_ders_hocasi.ad_soyad if t.dini_ders_hocasi_id else "",
                "Aktif" if t.aktif else "Pasif",
            ]
        )

    icerik = basit_rapor_xlsx(
        baslik=baslik,
        alt_baslik=f"{len(satirlar)} talebe",
        kolon_basliklari=[
            "Ad Soyad",
            "Talebe No",
            "Sınıf",
            "Şube",
            "Etüt Hocası",
            "Dini Ders Hocası",
            "Durum",
        ],
        satirlar=satirlar,
        sayfa_adi="Talebeler",
        durum_kolonlari=[6],
        vurgu_kolonlari=[0],
        ortala_kolonlari=[1, 2, 3, 6],
        genislikler=[26, 12, 10, 10, 22, 22, 10],
    )
    return excel_http_yanit(icerik, dosya_adi)
