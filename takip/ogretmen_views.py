"""Öğretmen paneli görünümleri — örnek arayüz."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from takip.ogretmen_service import (
    kullanici_ogretmen_mi,
    ogretmen_dashboard_verisi,
    ogretmen_hocasi_for_user,
    ogretmen_program_verisi,
)
from takip.ogretmen_not_service import ogretmen_not_girisi_verisi, ogretmen_not_kaydet
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response


def _hoca_yukle(request):
    return ogretmen_hocasi_for_user(request.user)


@login_required
def ogretmen_dashboard(request):
    if not kullanici_ogretmen_mi(request.user):
        return redirect("dashboard")

    hoca = _hoca_yukle(request)
    if not hoca:
        return redirect("logout")

    return render(
        request,
        "ogretmen/dashboard.html",
        ogretmen_dashboard_verisi(hoca),
    )


@login_required
def ogretmen_not_girisi(request, sinif_id: int | None = None):
    if not kullanici_ogretmen_mi(request.user):
        return redirect("dashboard")

    hoca = _hoca_yukle(request)
    if not hoca:
        return redirect("logout")

    if request.method == "POST" and sinif_id:
        hatalar = ogretmen_not_kaydet(hoca, sinif_id, request.POST)
        if hatalar:
            for h in hatalar:
                messages.error(request, h)
        else:
            messages.success(request, "Sınıf notları kaydedildi.")
        return redirect("ogretmen_not_girisi_sinif", sinif_id=sinif_id)

    ders_id = request.GET.get("ders")
    try:
        ders_id = int(ders_id) if ders_id else None
    except (TypeError, ValueError):
        ders_id = None

    ctx = ogretmen_not_girisi_verisi(hoca, sinif_id=sinif_id, ders_id=ders_id)
    return render(request, "ogretmen/not_girisi.html", ctx)


@login_required
def ogretmen_ders_programi(request):
    if not kullanici_ogretmen_mi(request.user):
        return redirect("dashboard")

    hoca = _hoca_yukle(request)
    if not hoca:
        return redirect("logout")

    return render(
        request,
        "ogretmen/ders_programi.html",
        ogretmen_program_verisi(hoca),
    )


@login_required
def ogretmen_ders_programi_pdf(request):
    if not kullanici_ogretmen_mi(request.user):
        return redirect("dashboard")

    hoca = _hoca_yukle(request)
    if not hoca:
        return redirect("logout")

    ctx = ogretmen_program_verisi(hoca)
    html_metni = render_to_string(
        "ogretmen/ders_programi_pdf.html",
        ctx,
        request=request,
    )
    pdf_verisi = html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})")
    return make_pdf_response(pdf_verisi, "haftalik-ders-programi.pdf")
