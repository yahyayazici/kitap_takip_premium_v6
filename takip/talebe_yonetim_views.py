"""Talebe hesabı yönetimi."""

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from takip.forms import TalebeHesapForm
from takip.models import TalebeHesap

from .yonetim_views import yonetici_gerekli


@yonetici_gerekli
def talebe_hesap_listesi(request):
    hesaplar = TalebeHesap.objects.select_related("user", "talebe").order_by(
        "talebe__ad_soyad"
    )
    return render(
        request,
        "yonetim/talebe_hesap_listesi.html",
        {"hesaplar": hesaplar},
    )


@yonetici_gerekli
def talebe_hesap_ekle(request):
    form = TalebeHesapForm(request.POST or None)
    if form.is_valid():
        with transaction.atomic():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["talebe"].ad_soyad,
            )
            TalebeHesap.objects.create(
                user=user,
                talebe=form.cleaned_data["talebe"],
                aktif=form.cleaned_data.get("aktif", True),
            )
        messages.success(request, "Talebe hesabı oluşturuldu.")
        return redirect("yonetim:talebe_hesap_listesi")

    return render(
        request,
        "yonetim/talebe_hesap_form.html",
        {"form": form, "baslik": "Yeni Talebe Hesabı"},
    )


@yonetici_gerekli
def talebe_hesap_duzenle(request, pk):
    hesap = get_object_or_404(
        TalebeHesap.objects.select_related("user", "talebe"),
        pk=pk,
    )
    form = TalebeHesapForm(
        request.POST or None,
        instance=hesap,
        duzenleme=True,
    )
    if form.is_valid():
        hesap.talebe = form.cleaned_data["talebe"]
        hesap.aktif = form.cleaned_data.get("aktif", True)
        hesap.save()

        if form.cleaned_data.get("password"):
            hesap.user.set_password(form.cleaned_data["password"])
            hesap.user.save()

        messages.success(request, "Talebe hesabı güncellendi.")
        return redirect("yonetim:talebe_hesap_listesi")

    return render(
        request,
        "yonetim/talebe_hesap_form.html",
        {
            "form": form,
            "baslik": f"Düzenle — {hesap.talebe.ad_soyad}",
            "hesap": hesap,
        },
    )
