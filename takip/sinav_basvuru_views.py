"""Public sınav başvuru formu — giriş gerektirmez."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from config.branding import (
    SINAV_BASVURU_ANA_BASLIK,
    SINAV_BASVURU_BASLIK,
    SINAV_BASVURU_UST_BASLIK,
)
from takip.forms import SinavBasvuruForm
from takip.models import SinavBasvuruMesajSablon
from takip.push_bildirim_service import push_bildirim_aktif
from takip.sinav_basvuru_mesaj_service import basvuru_mesaji_gonder
from takip.sinav_bildirim_service import (
    AN_KAYIT,
    abonelik_kaydet,
    basvuru_bildirim_url,
    bildirim_gonder,
    tokendan_basvuru,
)

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
        return redirect(basvuru_bildirim_url(basvuru))

    return render(
        request,
        "sinav_basvuru/form.html",
        {
            "form": form,
            "sinav_basvuru_baslik": SINAV_BASVURU_BASLIK,
            "sinav_ust_baslik": SINAV_BASVURU_UST_BASLIK,
            "sinav_ana_baslik": SINAV_BASVURU_ANA_BASLIK,
        },
    )


@require_http_methods(["GET"])
def sinav_basvuru_tesekkur(request):
    token = request.GET.get("t", "").strip()
    basvuru = tokendan_basvuru(token) if token else None
    bildirim = None
    if basvuru and push_bildirim_aktif():
        bildirim = {
            "vapid_key": settings.VAPID_PUBLIC_KEY,
            "abone_url": reverse("sinav_basvuru_bildirim_abone", args=[token]),
            "manifest_url": reverse("sinav_basvuru_bildirim_manifest", args=[token]),
        }
    return render(
        request,
        "sinav_basvuru/tesekkur.html",
        {
            "basvuru": basvuru,
            "bildirim": bildirim,
            "sinav_basvuru_baslik": SINAV_BASVURU_BASLIK,
            "sinav_ust_baslik": SINAV_BASVURU_UST_BASLIK,
            "sinav_ana_baslik": SINAV_BASVURU_ANA_BASLIK,
        },
    )


@require_POST
def sinav_basvuru_bildirim_abone(request, token):
    basvuru = tokendan_basvuru(token)
    if not basvuru:
        return JsonResponse({"ok": False, "hata": "Başvuru bulunamadı."}, status=404)
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "hata": "Geçersiz istek."}, status=400)
    abonelik = abonelik_kaydet(
        basvuru, data, user_agent=request.META.get("HTTP_USER_AGENT", "")
    )
    if not abonelik:
        return JsonResponse({"ok": False, "hata": "Eksik abonelik bilgisi."}, status=400)
    try:
        bildirim_gonder(basvuru, AN_KAYIT)
    except Exception:  # noqa: BLE001
        logger.exception("Kayıt bildirimi gönderilemedi")
    return JsonResponse({"ok": True})


@require_GET
def sinav_basvuru_bildirim_manifest(request, token):
    if not tokendan_basvuru(token):
        raise Http404
    response = JsonResponse(
        {
            "id": "/sinav-basvuru/",
            "name": "Çinili Saray Sınav",
            "short_name": "Çinili Saray",
            "start_url": f"{reverse('sinav_basvuru_tesekkur')}?t={token}",
            "scope": "/sinav-basvuru/",
            "display": "standalone",
            "theme_color": "#f7f4ef",
            "background_color": "#f7f4ef",
            "lang": "tr",
            "icons": [
                {"src": "/pwa/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/pwa/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        },
        json_dumps_params={"ensure_ascii": False},
        content_type="application/manifest+json",
    )
    response["Cache-Control"] = "no-store"
    return response
