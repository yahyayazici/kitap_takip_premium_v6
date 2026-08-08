"""Öğretmen paneli görünümleri — örnek arayüz."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from config.branding import panel_branding_context
from takip.ogretmen_not_service import (
    hoca_degerlendirme_paneli,
    ogretmen_not_girisi_verisi,
    ogretmen_not_kaydet,
)
from takip.ogretmen_service import (
    kullanici_ogretmen_mi,
    ogretmen_dashboard_verisi,
    ogretmen_hocasi_for_user,
    ogretmen_program_verisi,
)
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

    from takip.dashboard_service import dashboard_kisayollari, dashboard_metrikleri

    ctx = ogretmen_dashboard_verisi(hoca)
    ctx["kisayollar"] = dashboard_kisayollari(request.user, hedef="ogretmen")
    ctx["metrikler"] = dashboard_metrikleri(
        request.user,
        hedef="ogretmen",
        baglam={
            "toplam_sinif": ctx.get("toplam_sinif", 0),
            "toplam_ogrenci": ctx.get("toplam_ogrenci", 0),
            "hafta_no": ctx.get("hafta_no"),
        },
    )
    return render(request, "ogretmen/dashboard.html", ctx)


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
            messages.success(request, "Sınıf notları ve yoklama kaydedildi.")
        url = reverse("ogretmen_not_girisi_sinif", kwargs={"sinif_id": sinif_id})
        ders_id = request.POST.get("ders_id")
        if ders_id:
            url = f"{url}?ders={ders_id}"
        return redirect(url)

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
    ctx.update(panel_branding_context())
    html_metni = render_to_string(
        "ogretmen/ders_programi_pdf.html",
        ctx,
        request=request,
    )
    pdf_verisi = html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})")
    return make_pdf_response(pdf_verisi, "haftalik-ders-programi.pdf")


@login_required
def ogretmen_degerlendirmeler(request):
    if not kullanici_ogretmen_mi(request.user):
        return redirect("dashboard")

    hoca = _hoca_yukle(request)
    if not hoca:
        return redirect("logout")

    sinif_id = request.GET.get("sinif")
    talebe_id = request.GET.get("talebe")
    try:
        sinif_id = int(sinif_id) if sinif_id else None
    except (TypeError, ValueError):
        sinif_id = None
    try:
        talebe_id = int(talebe_id) if talebe_id else None
    except (TypeError, ValueError):
        talebe_id = None

    ctx = hoca_degerlendirme_paneli(hoca, sinif_id=sinif_id, talebe_id=talebe_id)
    return render(request, "ogretmen/degerlendirmeler.html", ctx)


@login_required
def ogretmen_talebe_karne_pdf(request, talebe_id: int):
    if not kullanici_ogretmen_mi(request.user):
        return redirect("dashboard")

    messages.info(
        request,
        "Öğretmen panelinden karne PDF indirilemez. Kayıtları Değerlendirmeler sayfasından inceleyebilirsiniz.",
    )
    return redirect("ogretmen_degerlendirmeler")
