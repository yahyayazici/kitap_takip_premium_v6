"""Bildirim merkezi — liste, okundu, JSON API."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from takip.bildirim_models import Bildirim
from takip.bildirim_service import (
    bildirim_listesi,
    bildirim_okundu,
    okunmamis_sayisi,
    tumunu_okundu,
)


def _wants_json(request) -> bool:
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )


@login_required
def bildirim_merkezi(request):
    return render(
        request,
        "bildirim_merkezi.html",
        {
            "bildirimler": bildirim_listesi(request.user, limit=50),
            "okunmamis": okunmamis_sayisi(request.user),
        },
    )


@login_required
def bildirim_api_liste(request):
    return JsonResponse(
        {
            "ok": True,
            "okunmamis": okunmamis_sayisi(request.user),
            "bildirimler": bildirim_listesi(request.user, limit=15),
        }
    )


@login_required
@require_POST
def bildirim_api_okundu(request, pk):
    ok = bildirim_okundu(request.user, pk)
    return JsonResponse({"ok": ok, "okunmamis": okunmamis_sayisi(request.user)})


@login_required
@require_http_methods(["POST"])
def bildirim_api_tumunu_okundu(request):
    n = tumunu_okundu(request.user)
    if _wants_json(request):
        return JsonResponse({"ok": True, "isaretlenen": n, "okunmamis": 0})
    return redirect("bildirim_merkezi")


@login_required
def bildirim_okundu_yonlendir(request, pk):
    bildirim_okundu(request.user, pk)
    b = Bildirim.objects.filter(pk=pk, alici=request.user).first()
    if b and b.link:
        return redirect(b.link)
    return redirect("bildirim_merkezi")
