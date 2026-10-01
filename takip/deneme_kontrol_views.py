"""Etüt Hocası — Deneme Kontrol Merkezi görünümleri."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from takip.deneme_gelisim_service import talebe_deneme_gelisim_paketi
from takip.deneme_kontrol_service import (
    deneme_kontrol_hocalari,
    hoca_sinif_secenekleri,
    kazanim_ortalamalari,
    kazanimlari_derse_gore,
    satirlari_sirala,
    sinif_deneme_kontrol_verisi,
)
from takip.models import SinifSube
from takip.ogretmen_not_service import ogretmen_sinif_ogrencileri
from takip.ogretmen_service import kullanici_ogretmen_mi


def _hocalar(request):
    return deneme_kontrol_hocalari(request.user)


def _sinif_hocasi(hocalar, sinif_id: int):
    for hoca in hocalar:
        if hoca.sorumlu_sinif_subeler.filter(pk=sinif_id, aktif=True).exists():
            return hoca
    return None


def _erisim_yok(request):
    if kullanici_ogretmen_mi(request.user):
        return redirect("ogretmen_dashboard")
    return redirect("dashboard")


@login_required
def deneme_kontrol_merkezi(request, sinif_id: int | None = None):
    hocalar = _hocalar(request)
    if not hocalar:
        return _erisim_yok(request)

    sirala = (request.GET.get("sirala") or "puan").strip()
    siniflar = []
    gruplar = []
    gorulen: set[int] = set()
    for hoca in hocalar:
        for kart in hoca_sinif_secenekleri(hoca):
            if kart.id in gorulen:
                continue
            gorulen.add(kart.id)
            sinif = get_object_or_404(SinifSube, pk=kart.id)
            veri = sinif_deneme_kontrol_verisi(hoca, sinif)
            veri["satirlar"] = satirlari_sirala(veri["satirlar"], sirala)
            siniflar.append(kart)
            gruplar.append({"kart": kart, "veri": veri})
    gosterilen_id = sinif_id if any(kart.id == sinif_id for kart in siniflar) else None

    return render(
        request,
        "ogretmen/deneme_kontrol_merkezi.html",
        {
            "siniflar": siniflar,
            "gruplar": gruplar,
            "sirala": sirala,
            "gosterilen_id": gosterilen_id,
        },
    )


@login_required
def deneme_kontrol_ogrenci_detay(request, sinif_id: int, talebe_id: int):
    hocalar = _hocalar(request)
    if not hocalar:
        return _erisim_yok(request)
    hoca = _sinif_hocasi(hocalar, sinif_id)
    if not hoca:
        return redirect("ogretmen_deneme_kontrol_merkezi")

    sinif = get_object_or_404(SinifSube, pk=sinif_id)
    ogrenciler = ogretmen_sinif_ogrencileri(hoca, sinif)
    talebe = next((t for t in ogrenciler if t.id == talebe_id), None)
    if not talebe:
        return redirect("ogretmen_deneme_kontrol_merkezi")

    kazanimlar = kazanim_ortalamalari([talebe.id])
    ctx = {
        "sinif": sinif,
        "talebe": talebe,
        "deneme_gelisim": talebe_deneme_gelisim_paketi(talebe),
        "kazanimlar": kazanimlar,
        "kazanim_gruplari": kazanimlari_derse_gore(kazanimlar),
    }
    return render(request, "ogretmen/deneme_kontrol_ogrenci_detay.html", ctx)
