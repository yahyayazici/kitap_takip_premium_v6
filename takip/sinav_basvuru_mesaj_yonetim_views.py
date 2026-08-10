"""Sınav başvurusu mesaj anları — yönetim."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from takip.forms import SinavBasvuruMesajSablonForm
from takip.models import SinavBasvuruMesajSablon
from takip.whatsapp_service import whatsapp_yapilandirilmis
from takip.yonetim_views import yonetici_gerekli


@yonetici_gerekli
def mesaj_an_listesi(request):
    sablonlar = SinavBasvuruMesajSablon.objects.order_by("sira", "an_kodu")
    return render(
        request,
        "yonetim/sinav_basvuru_mesaj_an_listesi.html",
        {
            "sablonlar": sablonlar,
            "whatsapp_aktif": whatsapp_yapilandirilmis(),
        },
    )


@yonetici_gerekli
@require_http_methods(["GET", "POST"])
def mesaj_an_duzenle(request, pk):
    sablon = get_object_or_404(SinavBasvuruMesajSablon, pk=pk)
    form = SinavBasvuruMesajSablonForm(request.POST or None, instance=sablon)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"“{sablon.baslik}” güncellendi.")
        return redirect("yonetim:sinav_basvuru_mesaj_an_listesi")

    return render(
        request,
        "yonetim/sinav_basvuru_mesaj_an_form.html",
        {
            "form": form,
            "sablon": sablon,
            "whatsapp_aktif": whatsapp_yapilandirilmis(),
        },
    )


@yonetici_gerekli
@require_POST
def mesaj_an_toggle(request, pk):
    sablon = get_object_or_404(SinavBasvuruMesajSablon, pk=pk)
    sablon.aktif = not sablon.aktif
    sablon.save(update_fields=["aktif", "guncellenme"])
    messages.success(
        request,
        f"“{sablon.baslik}” {'aktif' if sablon.aktif else 'pasif'} yapıldı.",
    )
    return redirect("yonetim:sinav_basvuru_mesaj_an_listesi")
