"""Veli randevu — yönetim ayarları."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from takip.models import PersonelProfili
from takip.veli_randevu_forms import RandevuMusaitlikForm, RandevuPersonelAyarForm
from takip.veli_randevu_models import RandevuMusaitlik
from takip.veli_randevu_service import randevu_personel_ayar_getir

from .yonetim_views import yonetici_gerekli


@yonetici_gerekli
def randevu_personel_listesi(request):
    personeller = (
        PersonelProfili.objects.filter(aktif=True)
        .select_related("randevu_ayari")
        .order_by("ad_soyad")
    )
    for p in personeller:
        randevu_personel_ayar_getir(p)

    return render(
        request,
        "yonetim/randevu_personel_listesi.html",
        {"personeller": personeller},
    )


@yonetici_gerekli
def randevu_personel_ayar(request, pk):
    personel = get_object_or_404(PersonelProfili, pk=pk)
    ayar = randevu_personel_ayar_getir(personel)
    musaitlikler = personel.randevu_musaitlikleri.all()

    ayar_form = RandevuPersonelAyarForm(instance=ayar, prefix="ayar")
    musait_form = RandevuMusaitlikForm(prefix="musait")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "ayar":
            ayar_form = RandevuPersonelAyarForm(request.POST, instance=ayar, prefix="ayar")
            if ayar_form.is_valid():
                ayar_form.save()
                messages.success(request, "Randevu ayarları kaydedildi.")
                return redirect("yonetim:randevu_personel_ayar", pk=personel.pk)
        elif action == "musait_ekle":
            musait_form = RandevuMusaitlikForm(request.POST, prefix="musait")
            if musait_form.is_valid():
                kayit = musait_form.save(commit=False)
                kayit.personel = personel
                kayit.save()
                messages.success(request, "Müsaitlik eklendi.")
                return redirect("yonetim:randevu_personel_ayar", pk=personel.pk)
        elif action == "musait_sil":
            mid = request.POST.get("musait_id")
            if mid:
                RandevuMusaitlik.objects.filter(pk=mid, personel=personel).delete()
                messages.success(request, "Müsaitlik silindi.")
            return redirect("yonetim:randevu_personel_ayar", pk=personel.pk)

    return render(
        request,
        "yonetim/randevu_personel_ayar.html",
        {
            "personel": personel,
            "ayar": ayar,
            "ayar_form": ayar_form,
            "musait_form": musait_form,
            "musaitlikler": musaitlikler,
        },
    )
