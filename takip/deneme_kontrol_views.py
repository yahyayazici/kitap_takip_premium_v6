"""Etüt Hocası — Deneme Kontrol Merkezi görünümleri."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from takip.deneme_gelisim_service import talebe_deneme_gelisim_paketi
from takip.deneme_kontrol_service import (
    hoca_sinif_secenekleri,
    satirlari_sirala,
    sinif_deneme_kontrol_verisi,
)
from takip.models import SinifSube, Talebe
from takip.ogretmen_not_service import ogretmen_sinif_ogrencileri
from takip.ogretmen_service import kullanici_ogretmen_mi, ogretmen_hocasi_for_user


def _hoca_yukle(request):
    return ogretmen_hocasi_for_user(request.user)


def _secili_sinif(siniflar, sinif_id: int | None):
    if sinif_id:
        return next((s for s in siniflar if s.id == sinif_id), None)
    return siniflar[0] if siniflar else None


@login_required
def deneme_kontrol_merkezi(request, sinif_id: int | None = None):
    if not kullanici_ogretmen_mi(request.user):
        return redirect("dashboard")

    hoca = _hoca_yukle(request)
    if not hoca:
        return redirect("logout")

    siniflar = hoca_sinif_secenekleri(hoca)
    secili = _secili_sinif(siniflar, sinif_id)

    ctx = {
        "siniflar": siniflar,
        "secili": secili,
        "sirala": (request.GET.get("sirala") or "puan").strip(),
        "veri": None,
    }

    if secili:
        sinif = get_object_or_404(SinifSube, pk=secili.id)
        veri = sinif_deneme_kontrol_verisi(hoca, sinif)
        veri["satirlar"] = satirlari_sirala(veri["satirlar"], ctx["sirala"])
        ctx["veri"] = veri

    return render(request, "ogretmen/deneme_kontrol_merkezi.html", ctx)


@login_required
def deneme_kontrol_ogrenci_detay(request, sinif_id: int, talebe_id: int):
    if not kullanici_ogretmen_mi(request.user):
        return redirect("dashboard")

    hoca = _hoca_yukle(request)
    if not hoca:
        return redirect("logout")

    sinif = get_object_or_404(SinifSube, pk=sinif_id)
    ogrenciler = ogretmen_sinif_ogrencileri(hoca, sinif)
    talebe = next((t for t in ogrenciler if t.id == talebe_id), None)
    if not talebe:
        return redirect("ogretmen_deneme_kontrol_merkezi")

    ctx = {
        "sinif": sinif,
        "talebe": talebe,
        "deneme_gelisim": talebe_deneme_gelisim_paketi(talebe),
    }
    return render(request, "ogretmen/deneme_kontrol_ogrenci_detay.html", ctx)
