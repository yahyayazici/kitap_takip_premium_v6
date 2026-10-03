"""ÇİSA raporu — deneme seçimi ve PDF."""

from __future__ import annotations

import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from takip.cisa_service import cisa_deneme_listesi, cisa_rapor
from takip.deneme_models import DenemeSinavi
from takip.pdf_utils import (
    html_to_pdf,
    make_pdf_response,
    pdf_engine_status,
    pdf_error_response,
)
from takip.permissions.decorators import require_permission
from takip.permissions.scope import yetkili_talebeler


def _talebe(request, talebe_id: int):
    return get_object_or_404(
        yetkili_talebeler(request.user, aktif_only=True).select_related("sinif_sube"),
        id=talebe_id,
    )


def _pdf_adi(ad_soyad: str) -> str:
    ad = re.sub(r'[\\/:*?"<>|\r\n]+', " ", (ad_soyad or "").strip())
    ad = re.sub(r"\s+", " ", ad).strip() or "Talebe"
    return f"{ad} CISA.pdf"


@login_required
@require_permission("deneme", "export_pdf")
def cisa_denemeler(request):
    """Denemeler sekmesinden giriş. Önce talebe, sonra hangi denemeler."""
    talebeler = (
        yetkili_talebeler(request.user, aktif_only=True)
        .filter(deneme_sonuclari__deneme__durum=DenemeSinavi.Durum.AKTIF)
        .distinct()
        .order_by("ad_soyad")
    )
    talebe = None
    denemeler = []
    ham = request.GET.get("talebe", "")
    if str(ham).isdigit():
        talebe = (
            talebeler.filter(id=int(ham)).select_related("sinif_sube").first()
        )
        if talebe is not None:
            denemeler = cisa_deneme_listesi(talebe)
    return render(
        request,
        "cisa_denemeler.html",
        {
            "talebeler": talebeler,
            "talebe": talebe,
            "denemeler": denemeler,
        },
    )


@login_required
@require_permission("deneme", "export_pdf")
def cisa_sec(request, talebe_id: int):
    talebe = _talebe(request, talebe_id)
    return render(
        request,
        "cisa_sec.html",
        {
            "talebe": talebe,
            "denemeler": cisa_deneme_listesi(talebe),
        },
    )


@login_required
@require_permission("deneme", "export_pdf")
@require_POST
def cisa_pdf(request, talebe_id: int):
    talebe = _talebe(request, talebe_id)
    secilen = []
    for ham in request.POST.getlist("deneme"):
        if str(ham).isdigit():
            secilen.append(int(ham))
    rapor = cisa_rapor(talebe, secilen)
    if rapor is None:
        messages.warning(request, "Rapora girecek deneme seç.")
        return redirect("cisa_sec", talebe_id=talebe.id)

    html = render(
        request,
        "cisa_pdf.html",
        {"rapor": rapor, "olusturma_tarihi": now()},
    ).content.decode("utf-8")
    pdf_verisi = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )
    return make_pdf_response(pdf_verisi, _pdf_adi(talebe.ad_soyad))
