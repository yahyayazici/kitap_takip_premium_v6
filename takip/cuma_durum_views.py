"""Personel — Cuma WhatsApp durum stüdyosu."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from config.branding import panel_branding_context
from takip.cuma_durum_service import stuyo_baslangic_verisi


@login_required
def cuma_durum_panel(request):
    veri = stuyo_baslangic_verisi(request.user)
    return render(
        request,
        "cuma_durum_panel.html",
        {
            **panel_branding_context(),
            "stuyo_json": json.dumps(veri, ensure_ascii=False),
            "cuma_tarihi": veri["cuma_tarihi"],
            "personel_ad": veri["personel_ad"],
        },
    )


@login_required
@require_GET
def cuma_durum_api_havuz(request):
    return JsonResponse(stuyo_baslangic_verisi(request.user))
