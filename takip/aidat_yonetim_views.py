"""Aidat — yönetim (tanım CRUD)."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from takip.forms import AidatTanimForm
from takip.models import AidatTanim
from takip.permissions.service import can

from .yonetim_views import yonetici_gerekli


@yonetici_gerekli
def aidat_tanim_listesi(request):
    if not can(request.user, "aidat", "view"):
        messages.error(request, "Aidat modülüne erişim yok.")
        return redirect("yonetim:dashboard")

    tanimlar = AidatTanim.objects.select_related("egitim_yili").order_by("-vade", "ad")
    return render(
        request,
        "yonetim/aidat_tanim_listesi.html",
        {
            "tanimlar": tanimlar,
            "duzenleyebilir": can(request.user, "aidat", "edit"),
        },
    )


@yonetici_gerekli
def aidat_tanim_ekle(request):
    if not can(request.user, "aidat", "edit"):
        messages.error(request, "Aidat tanımı ekleme yetkiniz yok.")
        return redirect("yonetim:aidat_tanim_listesi")

    form = AidatTanimForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Aidat tanımı eklendi.")
        return redirect("yonetim:aidat_tanim_listesi")

    return render(
        request,
        "yonetim/aidat_tanim_form.html",
        {"form": form, "baslik": "Yeni Aidat Tanımı"},
    )


@yonetici_gerekli
def aidat_tanim_duzenle(request, pk):
    if not can(request.user, "aidat", "edit"):
        messages.error(request, "Düzenleme yetkiniz yok.")
        return redirect("yonetim:aidat_tanim_listesi")

    tanim = get_object_or_404(AidatTanim, pk=pk)
    form = AidatTanimForm(request.POST or None, instance=tanim)
    if form.is_valid():
        form.save()
        messages.success(request, "Aidat tanımı güncellendi.")
        return redirect("yonetim:aidat_tanim_listesi")

    return render(
        request,
        "yonetim/aidat_tanim_form.html",
        {"form": form, "baslik": f"Düzenle — {tanim.ad}"},
    )
