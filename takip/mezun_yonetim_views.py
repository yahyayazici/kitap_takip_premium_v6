"""Mezun — yönetim (mezuniyet işlemi)."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from takip.forms import MezuniyetIslemForm
from takip.mezun_service import mezun_yap
from takip.models import Talebe
from takip.permissions.scope import yetkili_talebeler
from takip.permissions.service import can

from .yonetim_views import yonetici_gerekli


@yonetici_gerekli
def mezuniyet_islemi(request):
    if not can(request.user, "mezun", "create"):
        messages.error(request, "Mezuniyet işlemi yetkiniz yok.")
        return redirect("yonetim:dashboard")

    form = MezuniyetIslemForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        talebe = form.cleaned_data["talebe"]
        if talebe.durum == Talebe.Durum.MEZUN:
            messages.warning(request, "Bu talebe zaten mezun.")
            return redirect("yonetim:mezuniyet_islemi")

        mezun_yap(
            talebe,
            mezuniyet_yili=form.cleaned_data.get("mezuniyet_yili"),
            mezuniyet_tarihi=form.cleaned_data.get("mezuniyet_tarihi"),
            donem=form.cleaned_data.get("donem"),
            lgs_puani=form.cleaned_data.get("lgs_puani"),
            lgs_sira=form.cleaned_data.get("lgs_sira"),
            lgs_yuzdelik=form.cleaned_data.get("lgs_yuzdelik"),
            yerlestigi_lise=form.cleaned_data.get("yerlestigi_lise") or "",
            lise_yerlesme_yili=form.cleaned_data.get("lise_yerlesme_yili"),
            universite=form.cleaned_data.get("universite") or "",
            bolum=form.cleaned_data.get("bolum") or "",
            yks_puani=form.cleaned_data.get("yks_puani"),
            yks_sira=form.cleaned_data.get("yks_sira"),
            iletisim_telefon=form.cleaned_data.get("iletisim_telefon") or "",
            iletisim_eposta=form.cleaned_data.get("iletisim_eposta") or "",
            iletisim_adres=form.cleaned_data.get("iletisim_adres") or "",
            notlar=form.cleaned_data.get("notlar") or "",
        )
        messages.success(request, f"{talebe.ad_soyad} mezun olarak kaydedildi.")
        return redirect("mezun_detay", pk=talebe.mezun_profili.pk)

    aktif_talebeler = (
        yetkili_talebeler(request.user, aktif_only=True)
        .exclude(durum=Talebe.Durum.MEZUN)
        .order_by("ad_soyad")
    )

    return render(
        request,
        "yonetim/mezuniyet_islemi.html",
        {
            "form": form,
            "aktif_talebeler": aktif_talebeler,
        },
    )


@yonetici_gerekli
def mezun_profil_duzenle(request, pk):
    if not can(request.user, "mezun", "edit"):
        messages.error(request, "Düzenleme yetkiniz yok.")
        return redirect("yonetim:dashboard")

    from takip.mezun_service import yetkili_mezun_profilleri

    profil = get_object_or_404(yetkili_mezun_profilleri(request.user), pk=pk)
    form = MezuniyetIslemForm(
        request.user,
        request.POST or None,
        instance=profil,
        duzenleme=True,
    )
    if request.method == "POST" and form.is_valid():
        profil = form.save()
        messages.success(request, "Mezun profili güncellendi.")
        return redirect("mezun_detay", pk=profil.pk)

    return render(
        request,
        "yonetim/mezuniyet_islemi.html",
        {
            "form": form,
            "profil": profil,
            "baslik": f"Düzenle — {profil.talebe.ad_soyad}",
        },
    )
