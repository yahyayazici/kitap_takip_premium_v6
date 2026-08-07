"""Öğretmen ödeme panel görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from config.branding import panel_branding_context
from takip.forms import OgretmenOdemeDonemForm
from takip.models import SinifSube
from takip.ogretmen_odeme_models import OgretmenOdemeDonemi
from takip.ogretmen_odeme_service import (
    aktif_ogretmenler,
    donem_detay_verisi,
    donem_kaydet,
    donem_matris_verisi,
    donem_olustur,
    donem_qs,
    ogretmen_odeme_finans_gorebilir,
    ogretmen_odeme_girebilir,
    ogretmen_odeme_silebilir,
    rapor_excel_yanit,
    rapor_filtreleri,
    rapor_istatistik,
    rapor_ozet_satirlari,
)
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.wave0_models import Brans


def _ortak_sayfa_verisi(user):
    return {
        "finans_goster": ogretmen_odeme_finans_gorebilir(user),
        "girebilir": ogretmen_odeme_girebilir(user),
        "silebilir": ogretmen_odeme_silebilir(user),
        "siniflar": SinifSube.objects.filter(aktif=True).order_by("sinif", "sube"),
        "branslar": Brans.objects.filter(aktif=True).order_by("sira", "ad"),
        "ogretmenler": aktif_ogretmenler(),
    }


@login_required
@require_permission("ogretmen_odeme", "view")
def ogretmen_odeme_listesi(request):
    olustur_form = None
    if ogretmen_odeme_girebilir(request.user):
        if request.method == "POST" and request.POST.get("islem") == "olustur":
            olustur_form = OgretmenOdemeDonemForm(request.POST)
            if olustur_form.is_valid():
                donem = donem_olustur(
                    etut_hocasi=olustur_form.cleaned_data["etut_hocasi"],
                    baslangic=olustur_form.cleaned_data["baslangic"],
                    bitis=olustur_form.cleaned_data["bitis"],
                    user=request.user,
                    notlar=olustur_form.cleaned_data.get("notlar", ""),
                )
                messages.success(request, "Ödeme dönemi oluşturuldu.")
                return redirect("ogretmen_odeme_detay", pk=donem.pk)
        else:
            olustur_form = OgretmenOdemeDonemForm()

    donemler = donem_qs()[:100]
    ctx = {
        "donemler": donemler,
        "olustur_form": olustur_form,
        **_ortak_sayfa_verisi(request.user),
    }
    return render(request, "ogretmen_odeme_listesi.html", ctx)


@login_required
@require_permission("ogretmen_odeme", "view")
def ogretmen_odeme_detay(request, pk: int):
    donem = get_object_or_404(donem_qs(), pk=pk)
    if request.method == "POST" and ogretmen_odeme_girebilir(request.user):
        donem_kaydet(donem, request.POST, request.user)
        messages.success(request, "Ders saatleri kaydedildi.")
        return redirect("ogretmen_odeme_detay", pk=donem.pk)

    detay = donem_matris_verisi(donem)
    ctx = {
        **detay,
        **_ortak_sayfa_verisi(request.user),
    }
    return render(request, "ogretmen_odeme_detay.html", ctx)


@login_required
@require_permission("ogretmen_odeme", "export_pdf")
def ogretmen_odeme_pdf(request, pk: int):
    donem = get_object_or_404(donem_qs(), pk=pk)
    finans = ogretmen_odeme_finans_gorebilir(request.user)
    detay = donem_detay_verisi(donem)
    html_metni = render_to_string(
        "ogretmen_odeme_pdf.html",
        {
            **detay,
            "finans_goster": finans,
            **panel_branding_context(),
        },
        request=request,
    )
    pdf_verisi = html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})")
    return make_pdf_response(pdf_verisi, f"ogretmen-odeme-{donem.pk}.pdf")


@login_required
@require_permission("ogretmen_odeme", "view")
def ogretmen_odeme_rapor(request):
    finans = ogretmen_odeme_finans_gorebilir(request.user)
    filtre = rapor_filtreleri(request.GET)
    satirlar = rapor_ozet_satirlari(filtre, finans=finans)
    istatistik = rapor_istatistik(satirlar, finans=finans)

    if request.GET.get("format") == "excel" and can(request.user, "ogretmen_odeme", "export_excel"):
        buffer = rapor_excel_yanit(satirlar, finans=finans)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="ogretmen-odeme-raporu.xlsx"'
        return response

    if request.GET.get("format") == "pdf" and can(request.user, "ogretmen_odeme", "export_pdf"):
        html_metni = render_to_string(
            "ogretmen_odeme_rapor_pdf.html",
            {
                "satirlar": satirlar,
                "istatistik": istatistik,
                "filtre": filtre,
                "finans_goster": finans,
            },
            request=request,
        )
        pdf_verisi = html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))
        if not pdf_verisi:
            return pdf_error_response(f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})")
        return make_pdf_response(pdf_verisi, "ogretmen-odeme-raporu.pdf")

    ctx = {
        "satirlar": satirlar,
        "istatistik": istatistik,
        "filtre": filtre,
        **_ortak_sayfa_verisi(request.user),
    }
    return render(request, "ogretmen_odeme_rapor.html", ctx)


@login_required
@require_permission("ogretmen_odeme", "delete")
def ogretmen_odeme_sil(request, pk: int):
    donem = get_object_or_404(OgretmenOdemeDonemi, pk=pk)
    if request.method == "POST":
        donem.delete()
        messages.success(request, "Ödeme dönemi silindi.")
    return redirect("ogretmen_odeme_listesi")
