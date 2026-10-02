"""Yapay zeka asistanı API."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from takip.ai_gateway import kota_asildi_mi
from takip.asistan_service import asistan_kullanilabilir, mesaj_isle

logger = logging.getLogger(__name__)


@login_required
@require_POST
def asistan_chat_api(request):
    if not asistan_kullanilabilir(request.user):
        return JsonResponse(
            {"error": "Asistan şu an kullanılamıyor."},
            status=403,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Geçersiz istek."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Geçersiz istek."}, status=400)

    message = str(payload.get("message", "")).strip()
    max_karakter = int(getattr(settings, "AI_SOHBET_MESAJ_MAX_KARAKTER", 2000))
    if len(message) > max_karakter:
        return JsonResponse(
            {"error": f"Mesaj çok uzun. En fazla {max_karakter} karakter yazabilirsiniz."},
            status=400,
        )
    history = payload.get("history") or []
    if not isinstance(history, list):
        history = []

    if message:
        uid = request.user.pk
        if kota_asildi_mi(
            f"sohbet-dk:{uid}",
            limit=int(getattr(settings, "AI_SOHBET_DAKIKA_LIMIT", 10)),
            sure_sn=60,
        ):
            return JsonResponse(
                {"error": "Çok sık mesaj gönderdiniz. Lütfen bir dakika bekleyip tekrar deneyin."},
                status=429,
            )
        if kota_asildi_mi(
            f"sohbet-gun:{uid}",
            limit=int(getattr(settings, "AI_SOHBET_GUNLUK_LIMIT", 150)),
            sure_sn=86400,
        ):
            return JsonResponse(
                {"error": "Bugünkü asistan mesaj sınırına ulaştınız. Yarın tekrar deneyebilirsiniz."},
                status=429,
            )

    try:
        yanit = mesaj_isle(request.user, message, history)
    except Exception:  # noqa: BLE001
        logger.exception("Asistan yanıtı üretilemedi")
        return JsonResponse(
            {"error": "Yanıt hazırlanırken beklenmeyen bir hata oluştu. Lütfen tekrar deneyin."},
            status=500,
        )
    return JsonResponse(yanit)
