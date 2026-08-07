"""Yönetim — öğretmen ödeme profili (saatlik ücret, branş)."""

from __future__ import annotations

from django.contrib.auth.models import User
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from takip.models import EtutHocasi
from takip.ogretmen_odeme_models import OgretmenOdemeProfili
from takip.ogretmen_odeme_service import ogretmen_profili
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

    hocalar = EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad")
    for hoca in hocalar:
        hoca.odeme_profili_kayit = ogretmen_profili(hoca)

    return render(
        request,
        "yonetim/ogretmen_odeme_profil_listesi.html",
        {"hocalar": hocalar},
    )


@yonetici_gerekli
def ogretmen_odeme_profil_duzenle(request, pk: int):
    if not can(request.user, "ogretmen_odeme", "view_financial"):
        return redirect("yonetim:dashboard")

    hoca = get_object_or_404(EtutHocasi, pk=pk, aktif=True)
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

    hoca = get_object_or_404(EtutHocasi, pk=pk, aktif=True)
    profil = ogretmen_profili(hoca)
    profil.aktif = False
    profil.save(update_fields=["aktif"])

    hoca.aktif = False
    hoca.save(update_fields=["aktif"])

    personel = getattr(hoca, "personel_kaydi", None)
    if personel:
        personel.aktif = False
        personel.save(update_fields=["aktif"])

    if hoca.user_id:
        User.objects.filter(pk=hoca.user_id).update(is_active=False)

    messages.success(request, f"{hoca.ad_soyad} pasif edildi ve listeden kaldırıldı.")
    return redirect("yonetim:ogretmen_odeme_profil_listesi")
