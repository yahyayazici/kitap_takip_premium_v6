"""Yazılı takip — yönetim (kamp ve sınav CRUD)."""

from __future__ import annotations

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from takip.forms import YaziliKampForm, YaziliSinavForm
from takip.models import YaziliKamp, YaziliSinav
from takip.permissions.service import can
from takip.yazili_takip_service import sinav_sonuclari_sirali

from .yonetim_views import yonetici_gerekli


def _yonetim_yetki(request, islem: str = "view"):
    if not can(request.user, "yazili_takip", islem):
        messages.error(request, "Yazılı takip modülüne erişim yok.")
        return False
    return True


@yonetici_gerekli
def yazili_kamp_listesi(request):
    if not _yonetim_yetki(request):
        return redirect("yonetim:dashboard")

    kamplar = YaziliKamp.objects.annotate(
        sinav_sayisi=Count("sinavlar"),
        sonuc_sayisi=Count("sinavlar__sonuclar"),
    ).order_by("-baslangic", "-id")

    return render(
        request,
        "yonetim/yazili_kamp_listesi.html",
        {
            "kamplar": kamplar,
            "duzenleyebilir": can(request.user, "yazili_takip", "edit"),
            "olusturabilir": can(request.user, "yazili_takip", "create"),
        },
    )


@yonetici_gerekli
def yazili_kamp_ekle(request):
    if not _yonetim_yetki(request, "create"):
        return redirect("yonetim:yazili_kamp_listesi")

    form = YaziliKampForm(request.POST or None)
    if form.is_valid():
        kamp = form.save(commit=False)
        kamp.olusturan = request.user
        kamp.save()
        messages.success(request, "Yazılı kamp oluşturuldu.")
        return redirect("yonetim:yazili_kamp_detay", pk=kamp.pk)

    return render(
        request,
        "yonetim/yazili_kamp_form.html",
        {"form": form, "baslik": "Yeni Yazılı Kamp"},
    )


@yonetici_gerekli
def yazili_kamp_duzenle(request, pk):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:yazili_kamp_listesi")

    kamp = get_object_or_404(YaziliKamp, pk=pk)
    form = YaziliKampForm(request.POST or None, instance=kamp)
    if form.is_valid():
        form.save()
        messages.success(request, "Kamp güncellendi.")
        return redirect("yonetim:yazili_kamp_detay", pk=kamp.pk)

    return render(
        request,
        "yonetim/yazili_kamp_form.html",
        {"form": form, "baslik": f"Düzenle — {kamp.ad}", "kamp": kamp},
    )


@yonetici_gerekli
def yazili_kamp_detay(request, pk):
    if not _yonetim_yetki(request):
        return redirect("yonetim:yazili_kamp_listesi")

    kamp = get_object_or_404(YaziliKamp, pk=pk)
    sinavlar = YaziliSinav.objects.filter(kamp=kamp).order_by("sinav_tarihi", "id")

    return render(
        request,
        "yonetim/yazili_kamp_detay.html",
        {
            "kamp": kamp,
            "sinavlar": sinavlar,
            "duzenleyebilir": can(request.user, "yazili_takip", "edit"),
            "olusturabilir": can(request.user, "yazili_takip", "create"),
        },
    )


@yonetici_gerekli
def yazili_kamp_sil(request, pk):
    if not can(request.user, "yazili_takip", "delete"):
        messages.error(request, "Silme yetkiniz yok.")
        return redirect("yonetim:yazili_kamp_listesi")

    kamp = get_object_or_404(YaziliKamp, pk=pk)
    if request.method == "POST":
        ad = kamp.ad
        kamp.delete()
        messages.success(request, f"{ad} silindi.")
        return redirect("yonetim:yazili_kamp_listesi")

    return redirect("yonetim:yazili_kamp_detay", pk=pk)


@yonetici_gerekli
def yazili_sinav_ekle(request, kamp_pk):
    if not _yonetim_yetki(request, "create"):
        return redirect("yonetim:yazili_kamp_detay", pk=kamp_pk)

    kamp = get_object_or_404(YaziliKamp, pk=kamp_pk)
    form = YaziliSinavForm(request.POST or None, initial={"kamp": kamp})
    if form.is_valid():
        sinav = form.save(commit=False)
        sinav.kamp = kamp
        sinav.olusturan = request.user
        sinav.save()
        messages.success(request, "Sınav eklendi.")
        return redirect("yonetim:yazili_sinav_detay", pk=sinav.pk)

    return render(
        request,
        "yonetim/yazili_sinav_form.html",
        {"form": form, "baslik": f"Yeni Sınav — {kamp.ad}", "kamp": kamp},
    )


@yonetici_gerekli
def yazili_sinav_duzenle(request, pk):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:yazili_kamp_listesi")

    sinav = get_object_or_404(YaziliSinav.objects.select_related("kamp"), pk=pk)
    form = YaziliSinavForm(request.POST or None, instance=sinav)
    if form.is_valid():
        form.save()
        messages.success(request, "Sınav güncellendi.")
        return redirect("yonetim:yazili_sinav_detay", pk=sinav.pk)

    return render(
        request,
        "yonetim/yazili_sinav_form.html",
        {
            "form": form,
            "baslik": f"Düzenle — {sinav.ad}",
            "kamp": sinav.kamp,
            "sinav": sinav,
        },
    )


@yonetici_gerekli
def yazili_sinav_detay(request, pk):
    if not _yonetim_yetki(request):
        return redirect("yonetim:yazili_kamp_listesi")

    sinav = get_object_or_404(
        YaziliSinav.objects.select_related("kamp"),
        pk=pk,
    )
    sonuc_satirlari = sinav_sonuclari_sirali(request.user, sinav)

    return render(
        request,
        "yonetim/yazili_sinav_detay.html",
        {
            "sinav": sinav,
            "kamp": sinav.kamp,
            "sonuc_satirlari": sonuc_satirlari,
            "duzenleyebilir": can(request.user, "yazili_takip", "edit"),
        },
    )


@yonetici_gerekli
def yazili_sinav_sil(request, pk):
    if not can(request.user, "yazili_takip", "delete"):
        messages.error(request, "Silme yetkiniz yok.")
        return redirect("yonetim:yazili_kamp_listesi")

    sinav = get_object_or_404(YaziliSinav.objects.select_related("kamp"), pk=pk)
    kamp_pk = sinav.kamp_id
    if request.method == "POST":
        ad = sinav.ad
        sinav.delete()
        messages.success(request, f"{ad} silindi.")
        return redirect("yonetim:yazili_kamp_detay", pk=kamp_pk)

    return redirect("yonetim:yazili_sinav_detay", pk=pk)
