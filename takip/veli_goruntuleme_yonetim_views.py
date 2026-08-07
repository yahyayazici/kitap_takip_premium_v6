"""Veli paneli görüntüleme kontrol paneli."""

from django.shortcuts import get_object_or_404, render

from takip.models import VeliHesap
from takip.veli_goruntuleme_service import (
    panel_istatistikleri,
    veli_goruntuleme_detay,
    veli_goruntuleme_panel_listesi,
)

from .yonetim_views import yonetici_gerekli


@yonetici_gerekli
def veli_goruntuleme_paneli(request):
    sadece_eksik = request.GET.get("filtre") == "eksik"
    tum_ozetler = veli_goruntuleme_panel_listesi()
    ozetler = (
        [o for o in tum_ozetler if o.durum in {"eksik", "hic_giris"}]
        if sadece_eksik
        else tum_ozetler
    )
    return render(
        request,
        "yonetim/veli_goruntuleme_paneli.html",
        {
            "ozetler": ozetler,
            "istatistik": panel_istatistikleri(tum_ozetler),
            "sadece_eksik": sadece_eksik,
        },
    )


@yonetici_gerekli
def veli_goruntuleme_detay_view(request, pk: int):
    veli = get_object_or_404(
        VeliHesap.objects.select_related("user").prefetch_related(
            "talebe_baglantilari__talebe"
        ),
        pk=pk,
    )
    detay = veli_goruntuleme_detay(veli)
    return render(
        request,
        "yonetim/veli_goruntuleme_detay.html",
        {"detay": detay, "veli": veli},
    )
