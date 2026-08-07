"""Yapay zeka asistanı API."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from takip.asistan_service import asistan_kullanilabilir, mesaj_isle


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

    message = str(payload.get("message", "")).strip()
    history = payload.get("history") or []
    if not isinstance(history, list):
        history = []

    yanit = mesaj_isle(request.user, message, history)
    return JsonResponse(yanit)
