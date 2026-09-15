"""Etüt hocası — haftalık eğitim değerlendirme karnesi arşivi."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
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


def _liste_url(hafta_raw: str | None) -> str:
    url = reverse("etut_haftalik_karneler")
    raw = (hafta_raw or "").strip()
    if raw:
        return f"{url}?{urlencode({'hafta': raw})}"
    return url


def _karne_pdf_adi(ad_soyad: str, sira: int | None = None) -> str:
    slug = re.sub(r"[\s_]+", "-", (ad_soyad or "").strip()) or "talebe"
    slug = re.sub(r"[^\w.-]+", "", slug, flags=re.UNICODE)
    ad = f"{slug}-haftalik-egitim-karnesi.pdf"
    if sira is None:
        return ad
    return f"{sira:02d}-{ad}"


def _talebe_karne_pdf(request, talebe: Talebe, hafta: date) -> bytes | None:
    ctx = talebe_haftalik_karne_verisi(talebe, hafta, sadece_veliye_acik=True)
    ctx.update(panel_branding_context())
    ctx["bugun"] = localdate()
    html_metni = render_to_string(
        "ogretmen_haftalik_egitim_karne_pdf.html",
        ctx,
        request=request,
    )
    return html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))


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
    pdf_verisi = _talebe_karne_pdf(request, talebe, hafta)
    if not pdf_verisi:
        return pdf_error_response(
            f"Karne PDF oluşturulamadı. (Motor: {pdf_engine_status()})"
        )
    return make_pdf_response(pdf_verisi, _karne_pdf_adi(talebe.ad_soyad))


@login_required
def etut_haftalik_karneler_pdf(request):
    hoca = _etut_hoca_yukle(request.user)
    if not hoca:
        messages.error(request, "Bu sayfa yalnızca etüt / sınıf mesulleri içindir.")
        return redirect("dashboard")

    hafta_raw = request.GET.get("hafta")
    hafta = _hafta_parse(hafta_raw)
    ctx = etut_haftalik_karne_listesi(hoca, hafta)
    satirlar = ctx["satirlar"]
    if not satirlar:
        messages.error(request, "İndirilecek talebe yok.")
        return redirect(_liste_url(hafta_raw))

    buffer = io.BytesIO()
    yazilan = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as arsiv:
        for sira, satir in enumerate(satirlar, start=1):
            pdf_verisi = _talebe_karne_pdf(request, satir["talebe"], hafta)
            if not pdf_verisi:
                continue
            arsiv.writestr(_karne_pdf_adi(satir["talebe"].ad_soyad, sira), pdf_verisi)
            yazilan += 1

    if not yazilan:
        return pdf_error_response(
            f"Karne PDF oluşturulamadı. (Motor: {pdf_engine_status()})"
        )

    dosya = f"haftalik-egitim-karneleri-{hafta:%Y-%m-%d}.zip"
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{dosya}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response
