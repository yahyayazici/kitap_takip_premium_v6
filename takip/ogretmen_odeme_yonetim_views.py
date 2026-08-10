"""Yönetim — öğretmen ödeme profili (saatlik ücret, branş)."""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from takip.hizli_kayit_service import ogretmen_pasif_et
from takip.models import EtutHocasi
from takip.ogretmen_odeme_models import OgretmenOdemeProfili
from takip.ogretmen_odeme_service import aktif_ogretmenler, ogretmen_profili
from takip.permissions.service import can
from takip.wave0_models import Brans
from takip.yonetim_views import yonetici_gerekli


class OgretmenOdemeProfilForm(forms.ModelForm):
    class Meta:
        model = OgretmenOdemeProfili
        fields = ["brans", "saatlik_ucret", "aktif"]
        widgets = {
            "brans": forms.Select(attrs={"class": "cs-input"}),
            "saatlik_ucret": forms.NumberInput(
                attrs={"class": "cs-input", "step": "0.01", "min": "0"}
            ),
            "aktif": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }


@yonetici_gerekli
def ogretmen_odeme_profil_listesi(request):
    if not can(request.user, "ogretmen_odeme", "view_financial"):
        return redirect("yonetim:dashboard")

    hocalar = list(aktif_ogretmenler())
    for hoca in hocalar:
        try:
            hoca.odeme_profili_kayit = hoca.odeme_profili
        except OgretmenOdemeProfili.DoesNotExist:
            hoca.odeme_profili_kayit = None

    return render(
        request,
        "yonetim/ogretmen_odeme_profil_listesi.html",
        {"hocalar": hocalar},
    )


@yonetici_gerekli
def ogretmen_odeme_profil_duzenle(request, pk: int):
    if not can(request.user, "ogretmen_odeme", "view_financial"):
        return redirect("yonetim:dashboard")

    hoca = get_object_or_404(
        EtutHocasi, pk=pk, aktif=True, personel_kaydi__isnull=True
    )
    profil = ogretmen_profili(hoca)
    form = OgretmenOdemeProfilForm(request.POST or None, instance=profil)

    if form.is_valid():
        form.save()
        messages.success(request, f"{hoca.ad_soyad} ödeme profili güncellendi.")
        return redirect("yonetim:ogretmen_odeme_profil_listesi")

    return render(
        request,
        "yonetim/ogretmen_odeme_profil_form.html",
        {
            "form": form,
            "hoca": hoca,
            "branslar": Brans.objects.filter(aktif=True).order_by("sira", "ad"),
        },
    )


@yonetici_gerekli
@require_POST
def ogretmen_odeme_profil_sil(request, pk: int):
    if not can(request.user, "ogretmen_odeme", "view_financial"):
        return redirect("yonetim:dashboard")

    hoca = get_object_or_404(
        EtutHocasi, pk=pk, aktif=True, personel_kaydi__isnull=True
    )
    ogretmen_pasif_et(hoca)
    messages.success(request, f"{hoca.ad_soyad} pasif edildi ve listeden kaldırıldı.")
    return redirect("yonetim:ogretmen_odeme_profil_listesi")
