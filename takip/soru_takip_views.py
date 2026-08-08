"""Günlük soru takip panel görünümleri."""

from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.text import slugify
from django.utils.timezone import localdate

from takip.models import GunlukSoruKaydi, Talebe
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.permissions.decorators import require_permission
from takip.permissions.scope import yetkili_talebeler
from takip.permissions.service import can
from takip.soru_takip_service import (
    aylik_ozet,
    gunluk_ozet,
    kayit_duzenleyebilir,
    kayit_kaydet,
    kayit_satirlari_form_verisi,
    kayit_silebilir,
    rapor_filtre_dict,
    rapor_istatistik,
    rapor_kayitlari,
    rapor_pdf_baglami,
    soru_takip_dersleri,
    yetkili_soru_kayitlari,
)


def _parse_tarih(deger: str | None):
    if not deger:
        return localdate()
    try:
        return datetime.strptime(deger, "%Y-%m-%d").date()
    except ValueError:
        return localdate()


def _rapor_export_tail(request) -> str:
    params = request.GET.copy()
    params.pop("format", None)
    qs = params.urlencode()
    return f"&{qs}" if qs else ""


@login_required
@require_permission("soru_takip", "view")
def soru_takip_panel(request):
    talebeler = yetkili_talebeler(request.user).select_related(
        "sinif_sube", "etut_hocasi"
    ).order_by("ad_soyad")

    talebe_id = request.GET.get("talebe") or request.POST.get("talebe_id")
    tarih = _parse_tarih(request.GET.get("tarih") or request.POST.get("tarih"))
    sinif_sube_id = request.GET.get("sinif_sube")

    if sinif_sube_id:
        talebeler = talebeler.filter(sinif_sube_id=sinif_sube_id)

    talebe = None
    if talebe_id:
        talebe = get_object_or_404(talebeler, pk=talebe_id)

    dersler = soru_takip_dersleri()
    kayit = None
    if talebe:
        kayit = GunlukSoruKaydi.objects.filter(talebe=talebe, tarih=tarih).first()

    if request.method == "POST" and talebe and can(request.user, "soru_takip", "edit"):
        kayit, hatalar = kayit_kaydet(
            request.user,
            talebe,
            tarih,
            dersler,
            request.POST,
            gunluk_not=request.POST.get("gunluk_not", "").strip(),
        )
        if hatalar:
            from takip.messages_util import hatalari_ozetle

            hatalari_ozetle(request, hatalar, tek_baslik="Soru kaydı hatalı")
        else:
            messages.success(request, "Günlük soru kaydı kaydedildi.")
            return redirect(
                f"{request.path}?talebe={talebe.id}&tarih={tarih:%Y-%m-%d}"
            )

    satirlar = kayit_satirlari_form_verisi(kayit, dersler)
    son_kayitlar = yetkili_soru_kayitlari(request.user)[:12]

    sinif_subeler = (
        talebeler.values_list("sinif_sube_id", "sinif_sube__sinif", "sinif_sube__sube")
        .distinct()
        .order_by("sinif_sube__sinif", "sinif_sube__sube")
    )

    context = {
        "talebeler": talebeler,
        "talebe": talebe,
        "tarih": tarih,
        "sinif_sube_id": sinif_sube_id or "",
        "sinif_subeler": sinif_subeler,
        "dersler": dersler,
        "satirlar": satirlar,
        "kayit": kayit,
        "gunluk_ozet": gunluk_ozet(kayit),
        "aylik_ozet": aylik_ozet(talebe, tarih) if talebe else None,
        "son_kayitlar": son_kayitlar,
        "duzenleyebilir": can(request.user, "soru_takip", "edit"),
        "silebilir": can(request.user, "soru_takip", "delete"),
    }
    return render(request, "soru_takip_panel.html", context)


@login_required
@require_permission("soru_takip", "view")
def soru_takip_detay(request, pk):
    kayit = get_object_or_404(yetkili_soru_kayitlari(request.user), pk=pk)
    satirlar = kayit_satirlari_form_verisi(kayit, soru_takip_dersleri())
    return render(
        request,
        "soru_takip_detay.html",
        {
            "kayit": kayit,
            "satirlar": satirlar,
            "duzenleyebilir": kayit_duzenleyebilir(request.user, kayit),
            "silebilir": kayit_silebilir(request.user, kayit),
        },
    )


@login_required
@require_permission("soru_takip", "delete")
def soru_takip_sil(request, pk):
    kayit = get_object_or_404(yetkili_soru_kayitlari(request.user), pk=pk)
    if not kayit_silebilir(request.user, kayit):
        messages.error(request, "Silme yetkiniz yok.")
        return redirect("soru_takip_panel")

    talebe_id = kayit.talebe_id
    tarih = kayit.tarih
    kayit.delete()
    messages.success(request, "Kayıt silindi.")
    from django.urls import reverse

    return redirect(
        f"{reverse('soru_takip_panel')}?talebe={talebe_id}&tarih={tarih:%Y-%m-%d}"
    )


@login_required
@require_permission("soru_takip", "view")
def soru_takip_rapor(request):
    if request.GET.get("format") == "excel" and can(
        request.user, "soru_takip", "export_excel"
    ):
        return soru_takip_excel(request)
    if request.GET.get("format") == "pdf" and can(request.user, "soru_takip", "export_pdf"):
        return soru_takip_pdf(request)

    filtre = rapor_filtre_dict(request)
    kayitlar, baslangic, bitis, donem_baslik = rapor_kayitlari(request.user, filtre)
    export_tail = _rapor_export_tail(request)

    return render(
        request,
        "soru_takip_rapor.html",
        {
            "kayitlar": kayitlar[:200],
            "talebeler": yetkili_talebeler(request.user).order_by("ad_soyad"),
            "dersler": soru_takip_dersleri(),
            "filtre": filtre,
            "donem_baslik": donem_baslik,
            "baslangic": baslangic,
            "bitis": bitis,
            "istatistik": rapor_istatistik(
                kayitlar,
                ders_id=filtre.get("ders") or None,
            ),
            "pdf_yetki": can(request.user, "soru_takip", "export_pdf"),
            "excel_yetki": can(request.user, "soru_takip", "export_excel"),
            "export_tail": export_tail,
        },
    )


@login_required
@require_permission("soru_takip", "export_pdf")
def soru_takip_pdf(request):
    filtre = rapor_filtre_dict(request)
    baglam = rapor_pdf_baglami(request.user, filtre, limit=300)
    baglam["olusturma_tarihi"] = localdate()

    html = render_to_string(
        "soru_takip_rapor_pdf.html",
        baglam,
        request=request,
    )
    pdf_verisi = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    if baglam.get("talebe"):
        dosya = slugify(baglam["talebe"].ad_soyad) or f"talebe_{baglam['talebe'].pk}"
    else:
        dosya = "kurum"
    donem = filtre.get("donem") or "rapor"
    return make_pdf_response(
        pdf_verisi,
        f"soru-takip-{dosya}-{donem}-{localdate():%Y%m%d}.pdf",
    )


@login_required
@require_permission("soru_takip", "export_excel")
def soru_takip_excel(request):
    from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit

    filtre = rapor_filtre_dict(request)
    kayitlar, _, _, _ = rapor_kayitlari(request.user, filtre)

    satirlar = []
    for kayit in kayitlar[:500]:
        for satir in kayit.ders_satirlari.select_related("ders"):
            satirlar.append(
                [
                    kayit.tarih.strftime("%d.%m.%Y"),
                    (kayit.talebe.ad_soyad or "").upper(),
                    str(kayit.talebe.sinif_sube or kayit.talebe.sinif or ""),
                    satir.ders.ad,
                    satir.toplam_soru,
                    satir.dogru,
                    satir.yanlis,
                    satir.bos,
                    str(satir.net).replace(".", ","),
                    (kayit.gunluk_not or "").replace("\n", " ")[:120],
                ]
            )

    icerik = basit_rapor_xlsx(
        baslik="Soru Takip Raporu",
        alt_baslik=localdate().strftime("%d.%m.%Y"),
        kolon_basliklari=[
            "Tarih", "Ad-Soyad", "Sınıf", "Ders", "Toplam",
            "Doğru", "Yanlış", "Boş", "Net", "Not",
        ],
        satirlar=satirlar,
        sayfa_adi="Soru Takip",
        vurgu_kolonlari=[8],
        ortala_kolonlari=[0, 2, 4, 5, 6, 7],
        genislikler=[12, 26, 10, 14, 10, 9, 9, 9, 9, 28],
    )
    return excel_http_yanit(icerik, f"soru_takip_rapor_{localdate():%Y%m%d}.xlsx")
