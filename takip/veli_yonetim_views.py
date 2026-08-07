"""Veli hesabı yönetimi."""

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from takip.forms import VeliHesapForm
from takip.models import VeliHesap, VeliTalebeBaglantisi

from .yonetim_views import yonetici_gerekli


@yonetici_gerekli
def veli_hesap_listesi(request):
    hesaplar = VeliHesap.objects.select_related("user").prefetch_related(
        "talebe_baglantilari__talebe"
    ).order_by("ad_soyad")
    return render(
        request,
        "yonetim/veli_hesap_listesi.html",
        {"hesaplar": hesaplar},
    )


@yonetici_gerekli
def veli_hesap_ekle(request):
    form = VeliHesapForm(request.POST or None)
    if form.is_valid():
        with transaction.atomic():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["ad_soyad"],
            )
            veli = VeliHesap.objects.create(
                user=user,
                ad_soyad=form.cleaned_data["ad_soyad"],
                telefon=form.cleaned_data.get("telefon", ""),
                aktif=True,
            )
            for talebe in form.cleaned_data["talebeler"]:
                VeliTalebeBaglantisi.objects.create(
                    veli=veli,
                    talebe=talebe,
                    yakinlik=form.cleaned_data.get("yakinlik") or "veli",
                )
        messages.success(request, "Veli hesabı oluşturuldu.")
        return redirect("yonetim:veli_hesap_listesi")

    return render(
        request,
        "yonetim/veli_hesap_form.html",
        {"form": form, "baslik": "Yeni Veli Hesabı"},
    )


@yonetici_gerekli
def veli_hesap_duzenle(request, pk):
    veli = get_object_or_404(VeliHesap.objects.select_related("user"), pk=pk)
    form = VeliHesapForm(
        request.POST or None,
        instance=veli,
        duzenleme=True,
    )
    if form.is_valid():
        veli.ad_soyad = form.cleaned_data["ad_soyad"]
        veli.telefon = form.cleaned_data.get("telefon", "")
        veli.aktif = form.cleaned_data.get("aktif", True)
        veli.save()

        if form.cleaned_data.get("password"):
            veli.user.set_password(form.cleaned_data["password"])
            veli.user.save()

        secili = set(form.cleaned_data["talebeler"].values_list("id", flat=True))
        mevcut = {
            b.talebe_id: b
            for b in veli.talebe_baglantilari.select_related("talebe")
        }
        for tid in secili - set(mevcut):
            VeliTalebeBaglantisi.objects.create(
                veli=veli,
                talebe_id=tid,
                yakinlik=form.cleaned_data.get("yakinlik") or "veli",
            )
        for tid, bag in mevcut.items():
            if tid not in secili:
                bag.delete()

        messages.success(request, "Veli hesabı güncellendi.")
        return redirect("yonetim:veli_hesap_listesi")

    return render(
        request,
        "yonetim/veli_hesap_form.html",
        {"form": form, "baslik": f"Düzenle — {veli.ad_soyad}", "veli": veli},
    )
