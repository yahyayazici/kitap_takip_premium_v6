"""Nehari hoca günlük ödev paneli."""

from __future__ import annotations

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST

from takip.nehari_odev_service import (
    NehariOdevHata,
    isaret_kaydet,
    metin_kaydet,
    nehari_panosu,
    sinif_secenekleri,
)
from takip.permissions.decorators import require_permission
from takip.permissions.service import can


def _tarih(deger: str | None):
    if not deger:
        return None
    try:
        return datetime.strptime(deger, "%Y-%m-%d").date()
    except ValueError:
        return None


def _donus(request, tarih):
    qs = request.GET.copy()
    qs["tarih"] = tarih.isoformat()
    return redirect(f"{request.path}?{qs.urlencode()}")


@login_required
@require_permission("nehari_odev", "view")
def nehari_odev_panel(request):
    tarih = _tarih(request.POST.get("tarih") if request.method == "POST" else request.GET.get("tarih"))
    tarih = tarih or localdate()
    duzenler = can(request.user, "nehari_odev", "edit")

    if request.method == "POST" and request.POST.get("islem") == "metin":
        if not duzenler:
            messages.error(request, "Günün ödevini düzenleme yetkiniz yok.")
            return redirect(request.path)
        try:
            metin_kaydet(request.user, tarih, request.POST.get("metin", ""))
        except NehariOdevHata as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Günün ödevi kaydedildi. Liste bu metinle açılır.")
        return _donus(request, tarih)

    sinif = (request.GET.get("sinif") or "").strip()
    q = (request.GET.get("q") or "").strip()
    durum = (request.GET.get("durum") or "").strip()
    if durum not in {"yapildi", "bekleyen"}:
        durum = ""
    satirlar, ozet, metin = nehari_panosu(
        request.user, tarih, sinif=sinif, q=q, durum=durum
    )
    return render(
        request,
        "nehari_odev_panel.html",
        {
            "secili_tarih": tarih,
            "bugun": tarih == localdate(),
            "satirlar": satirlar,
            "ozet": ozet,
            "odev_metni": metin,
            "sinif_secenekleri": sinif_secenekleri(request.user),
            "filtre_sinif": sinif,
            "filtre_q": q,
            "filtre_durum": durum,
            "duzenleyebilir": duzenler,
        },
    )


@login_required
@require_permission("nehari_odev", "edit")
@require_POST
def nehari_odev_isaret(request):
    tarih = _tarih(request.POST.get("tarih")) or localdate()
    json_ister = "application/json" in request.headers.get("Accept", "")
    talebe_id = request.POST.get("talebe_id", "")
    if not str(talebe_id).isdigit():
        if json_ister:
            return JsonResponse({"ok": False, "mesaj": "Talebe seçilmedi."}, status=400)
        messages.error(request, "Talebe seçilmedi.")
        return redirect("nehari_odev_panel")
    try:
        kayit = isaret_kaydet(
            request.user,
            tarih,
            int(talebe_id),
            request.POST.get("yapildi") == "1",
        )
    except NehariOdevHata as exc:
        if json_ister:
            return JsonResponse({"ok": False, "mesaj": str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect("nehari_odev_panel")

    if json_ister:
        return JsonResponse(
            {
                "ok": True,
                "yapildi": kayit.yapildi,
                "etiket": "Yapıldı" if kayit.yapildi else "Yapılmadı",
            }
        )
    return redirect(f"{reverse('nehari_odev_panel')}?tarih={tarih.isoformat()}")
