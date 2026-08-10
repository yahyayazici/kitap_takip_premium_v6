"""Sınav başvuruları — yönetim paneli."""

from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from takip.models import SinavBasvuru
from takip.yonetim_views import yonetici_gerekli


@yonetici_gerekli
def sinav_basvuru_listesi(request):
    basvurular = SinavBasvuru.objects.all()
    durum = request.GET.get("durum", "").strip()
    arama = request.GET.get("q", "").strip()

    if durum in SinavBasvuru.Durum.values:
        basvurular = basvurular.filter(durum=durum)

    if arama:
        basvurular = basvurular.filter(
            Q(ad_soyad__icontains=arama)
            | Q(baba_telefon__icontains=arama)
            | Q(anne_telefon__icontains=arama)
            | Q(baba_adi__icontains=arama)
            | Q(anne_adi__icontains=arama)
            | Q(il__icontains=arama)
            | Q(ilce__icontains=arama)
        )

    return render(
        request,
        "yonetim/sinav_basvuru_listesi.html",
        {
            "basvurular": basvurular,
            "durum_filtre": durum,
            "arama": arama,
            "durum_secenekleri": SinavBasvuru.Durum.choices,
        },
    )


@yonetici_gerekli
@require_http_methods(["GET", "POST"])
def sinav_basvuru_detay(request, pk):
    basvuru = get_object_or_404(SinavBasvuru, pk=pk)

    if request.method == "POST":
        yeni_durum = request.POST.get("durum", "").strip()
        notlar = request.POST.get("notlar", "").strip()
        if yeni_durum in SinavBasvuru.Durum.values:
            basvuru.durum = yeni_durum
        basvuru.notlar = notlar
        basvuru.save(update_fields=["durum", "notlar", "guncellenme"])
        messages.success(request, "Başvuru güncellendi.")
        return redirect("yonetim:sinav_basvuru_detay", pk=basvuru.pk)

    return render(
        request,
        "yonetim/sinav_basvuru_detay.html",
        {
            "basvuru": basvuru,
            "durum_secenekleri": SinavBasvuru.Durum.choices,
        },
    )


@yonetici_gerekli
@require_POST
def sinav_basvuru_sil(request, pk):
    basvuru = get_object_or_404(SinavBasvuru, pk=pk)
    ad = basvuru.ad_soyad
    basvuru.delete()
    messages.success(request, f"{ad} başvurusu silindi.")
    return redirect("yonetim:sinav_basvuru_listesi")
