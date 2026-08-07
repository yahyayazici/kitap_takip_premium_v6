"""Talebe paneli görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from takip.talebe_panel_service import (
    kullanici_talebe_mi,
    talebe_dashboard_verisi,
    talebe_hesabi_for_user,
    talebe_okuma_soru_form_verisi,
    talebe_okuma_soru_kaydet,
    talebe_profil_verisi,
)


def _talebe_hesap(request):
    hesap = talebe_hesabi_for_user(request.user)
    if not hesap or not hesap.aktif:
        return None
    return hesap


@login_required
def talebe_dashboard(request):
    if not kullanici_talebe_mi(request.user):
        return redirect("dashboard")

    hesap = _talebe_hesap(request)
    if not hesap:
        return redirect("logout")

    return render(
        request,
        "talebe/dashboard.html",
        talebe_dashboard_verisi(hesap),
    )


@login_required
def talebe_profil(request):
    if not kullanici_talebe_mi(request.user):
        return redirect("dashboard")

    hesap = _talebe_hesap(request)
    if not hesap:
        return redirect("logout")

    return render(
        request,
        "talebe/profil.html",
        talebe_profil_verisi(hesap),
    )


@login_required
def talebe_gorevler(request):
    if not kullanici_talebe_mi(request.user):
        return redirect("dashboard")

    hesap = _talebe_hesap(request)
    if not hesap:
        return redirect("logout")

    return render(
        request,
        "talebe/gorevler.html",
        {"hesap": hesap, "talebe": hesap.talebe},
    )


@login_required
def talebe_okuma_soru(request):
    if not kullanici_talebe_mi(request.user):
        return redirect("dashboard")

    hesap = _talebe_hesap(request)
    if not hesap:
        return redirect("logout")

    ctx = talebe_okuma_soru_form_verisi(hesap)

    if request.method == "POST":
        if not ctx["girebilir"]:
            messages.error(request, "Bugün okuma/soru girişi yapılamaz.")
            return redirect("talebe_okuma_soru")

        ok, hatalar = talebe_okuma_soru_kaydet(request.user, hesap, request.POST)
        if hatalar:
            for h in hatalar:
                messages.error(request, h)
        elif ok:
            messages.success(request, "Günlük kayıt kaydedildi.")
            return redirect("talebe_okuma_soru")
        ctx = talebe_okuma_soru_form_verisi(hesap)

    return render(request, "talebe/okuma_soru.html", ctx)
