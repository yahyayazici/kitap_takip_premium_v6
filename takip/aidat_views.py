"""Aidat panel görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate

from takip.aidat_service import (
    aidat_kayitlari_filtrele,
    aidat_tahsilat_ekle,
    aidat_tahsilat_girebilir,
    aktif_egitim_yillari,
    yetkili_aidat_kayitlari,
)
from takip.forms import AidatTahsilatForm
from takip.permissions.decorators import require_permission


@login_required
@require_permission("aidat", "view")
def aidat_listesi(request):
    qs = yetkili_aidat_kayitlari(request.user).order_by("-tanim__vade", "talebe__ad_soyad")
    q = request.GET.get("q", "").strip()
    durum = request.GET.get("durum", "").strip()
    yil = request.GET.get("yil", "").strip()
    qs = aidat_kayitlari_filtrele(
        qs,
        q=q or None,
        durum=durum or None,
        egitim_yili_id=yil or None,
    )

    return render(
        request,
        "aidat_listesi.html",
        {
            "kayitlar": qs[:200],
            "filtre_q": q,
            "filtre_durum": durum,
            "filtre_yil": yil,
            "egitim_yillari": aktif_egitim_yillari(),
            "tahsilat_girebilir": aidat_tahsilat_girebilir(request.user),
        },
    )


@login_required
@require_permission("aidat", "view")
def aidat_detay(request, pk):
    kayit = get_object_or_404(yetkili_aidat_kayitlari(request.user), pk=pk)
    tahsilat_form = None

    if aidat_tahsilat_girebilir(request.user):
        if request.method == "POST":
            tahsilat_form = AidatTahsilatForm(request.POST)
            if tahsilat_form.is_valid():
                aidat_tahsilat_ekle(
                    kayit,
                    tutar=tahsilat_form.cleaned_data["tutar"],
                    tarih=tahsilat_form.cleaned_data["tarih"],
                    aciklama=tahsilat_form.cleaned_data.get("aciklama") or "",
                    kaydeden=request.user,
                )
                messages.success(request, "Tahsilat kaydedildi.")
                return redirect("aidat_detay", pk=kayit.pk)
        else:
            tahsilat_form = AidatTahsilatForm(
                initial={"tarih": localdate(), "tutar": kayit.borc_tutari}
            )

    tahsilatlar = kayit.tahsilatlar.select_related("kaydeden").order_by("-tarih", "-id")

    return render(
        request,
        "aidat_detay.html",
        {
            "kayit": kayit,
            "tahsilatlar": tahsilatlar,
            "tahsilat_form": tahsilat_form,
            "tahsilat_girebilir": aidat_tahsilat_girebilir(request.user),
        },
    )
