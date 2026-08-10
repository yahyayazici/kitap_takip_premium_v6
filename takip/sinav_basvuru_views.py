"""Public sınav başvuru formu — giriş gerektirmez."""

from __future__ import annotations

import logging

from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from config.branding import SINAV_BASVURU_BASLIK
from takip.forms import SinavBasvuruForm
from takip.models import SinavBasvuruMesajSablon
from takip.sinav_basvuru_mesaj_service import basvuru_mesaji_gonder

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def sinav_basvuru_form(request):
    form = SinavBasvuruForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        basvuru = form.save(commit=False)
        basvuru.sinav_adi = SINAV_BASVURU_BASLIK
        basvuru.save()
        try:
            basvuru_mesaji_gonder(
                basvuru,
                SinavBasvuruMesajSablon.AnKodu.BASVURU_ALINDI,
                sadece_aktif=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Başvuru alındı mesajı gönderilemedi")
        return redirect(reverse("sinav_basvuru_tesekkur"))

    return render(
        request,
        "sinav_basvuru/form.html",
        {
            "form": form,
            "sinav_basvuru_baslik": SINAV_BASVURU_BASLIK,
        },
    )


@require_http_methods(["GET"])
def sinav_basvuru_tesekkur(request):
    return render(
        request,
        "sinav_basvuru/tesekkur.html",
        {"sinav_basvuru_baslik": SINAV_BASVURU_BASLIK},
    )
