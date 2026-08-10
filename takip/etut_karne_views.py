"""Etüt hocası — haftalık eğitim değerlendirme karnesi arşivi."""

from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.timezone import localdate

from config.branding import panel_branding_context
from takip.models import EtutHocasi, Talebe
from takip.ogretmen_not_service import (
    etut_haftalik_karne_listesi,
    talebe_haftalik_karne_verisi,
)
from takip.ogretmen_service import aktif_hafta_baslangic
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.user_helpers import etut_hocasi_for_user


def _etut_hoca_yukle(user) -> EtutHocasi | None:
    """Personel etüt/sınıf mesulünün EtutHocasi kaydı."""
    if not user.is_authenticated:
        return None
    try:
        profil = user.personel_profili
    except Exception:
        profil = None
    if profil and profil.aktif and profil.etut_hocasi_id:
        hoca = profil.etut_hocasi
        if hoca and hoca.aktif:
            return hoca
    hoca = etut_hocasi_for_user(user)
    if hoca and hoca.aktif and getattr(hoca, "personel_kaydi", None):
        return hoca
    return None


def _hafta_parse(raw: str | None) -> date:
    raw = (raw or "").strip()
    if not raw:
        return aktif_hafta_baslangic()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return aktif_hafta_baslangic()


@login_required
def etut_haftalik_karneler(request):
    hoca = _etut_hoca_yukle(request.user)
    if not hoca:
        messages.error(request, "Bu sayfa yalnızca etüt / sınıf mesulleri içindir.")
        return redirect("dashboard")

    ctx = etut_haftalik_karne_listesi(hoca, _hafta_parse(request.GET.get("hafta")))
    return render(request, "etut/haftalik_karneler.html", ctx)


@login_required
def etut_talebe_haftalik_karne_pdf(request, talebe_id: int):
    hoca = _etut_hoca_yukle(request.user)
    if not hoca:
        messages.error(request, "Bu sayfa yalnızca etüt / sınıf mesulleri içindir.")
        return redirect("dashboard")

    talebe = get_object_or_404(
        Talebe, pk=talebe_id, etut_hocasi=hoca, aktif=True
    )
    hafta = _hafta_parse(request.GET.get("hafta"))
    ctx = talebe_haftalik_karne_verisi(talebe, hafta, sadece_veliye_acik=True)
    ctx.update(panel_branding_context())
    ctx["bugun"] = localdate()
    html_metni = render_to_string(
        "ogretmen_haftalik_egitim_karne_pdf.html",
        ctx,
        request=request,
    )
    pdf_verisi = html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(
            f"Karne PDF oluşturulamadı. (Motor: {pdf_engine_status()})"
        )
    ad = talebe.ad_soyad.replace(" ", "-")
    return make_pdf_response(pdf_verisi, f"{ad}-haftalik-egitim-karnesi.pdf")
