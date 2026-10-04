"""Etüt Hocası — Deneme Kontrol Merkezi görünümleri."""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from takip.deneme_gelisim_service import talebe_deneme_gelisim_paketi
from takip.deneme_kontrol_service import (
    deneme_kontrol_hocalari,
    hoca_sinif_secenekleri,
    kazanim_ortalamalari,
    kazanimlari_derse_gore,
    satirlari_sirala,
    seviye_etiketi,
    sinif_deneme_kontrol_verisi,
    siniflar_deneme_kontrol_verisi,
)
from takip.models import SinifSube
from takip.ogretmen_not_service import ogretmen_sinif_ogrencileri
from takip.permissions.service import can
from takip.ogretmen_service import kullanici_ogretmen_mi


def _hocalar(request):
    return deneme_kontrol_hocalari(request.user)


def _sinif_hocasi(hocalar, sinif_id: int):
    for hoca in hocalar:
        if hoca.sorumlu_sinif_subeler.filter(pk=sinif_id, aktif=True).exists():
            return hoca
    return None


def _seviye_gruplari(gruplar: list[dict], sirala: str) -> list[dict]:
    """Tümü: aynı sınıf seviyesindeki şubeler tek özet olur."""
    kovalar: dict[str, list[dict]] = {}
    for grup in gruplar:
        kovalar.setdefault(grup["sinif"].sinif, []).append(grup)

    sonuc = []
    for seviye, uyeler in kovalar.items():
        if len(uyeler) == 1:
            sonuc.append(uyeler[0])
            continue
        sinif_listesi = [uye["sinif"] for uye in uyeler]
        ogrenciler = []
        gorulen: set[int] = set()
        for uye in uyeler:
            for talebe in ogretmen_sinif_ogrencileri(uye["hoca"], uye["sinif"]):
                if talebe.id in gorulen:
                    continue
                gorulen.add(talebe.id)
                ogrenciler.append(talebe)
        veri = siniflar_deneme_kontrol_verisi(ogrenciler, sinif_listesi)
        veri["satirlar"] = satirlari_sirala(veri["satirlar"], sirala)
        kart = SimpleNamespace(
            id=None,
            etiket=seviye_etiketi(seviye),
            ogrenci_sayisi=len(ogrenciler),
        )
        sonuc.append(
            {
                "kart": kart,
                "veri": veri,
                "uyeler": [
                    {
                        "id": uye["sinif"].id,
                        "etiket": uye["kart"].etiket,
                        "sube": uye["sinif"].sube,
                    }
                    for uye in uyeler
                ],
            }
        )
    return sonuc


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
    ekran = (request.GET.get("ekran") or "").strip()
    cisa_acik = can(request.user, "deneme", "export_pdf")
    if ekran not in ("kazanim", "cisa") or (ekran == "cisa" and not cisa_acik):
        ekran = "yukselis"
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
            gruplar.append({"kart": kart, "veri": veri, "hoca": hoca, "sinif": sinif})
    gosterilen_id = sinif_id if any(kart.id == sinif_id for kart in siniflar) else None
    if not gosterilen_id and len(siniflar) > 1:
        gruplar = _seviye_gruplari(gruplar, sirala)
    if ekran == "cisa":
        from takip.cisa_service import cisa_sinif_denemeleri

        for grup in gruplar:
            talebeler = sorted(
                (satir.talebe for satir in grup["veri"]["satirlar"]),
                key=lambda talebe: talebe.ad_soyad or "",
            )
            grup["cisa_talebeler"] = talebeler
            grup["cisa_denemeler"] = cisa_sinif_denemeleri([t.id for t in talebeler])
            uyeler = grup.get("uyeler") or []
            if uyeler:
                grup["cisa_sinif_idleri"] = ",".join(str(uye["id"]) for uye in uyeler)

    return render(
        request,
        "ogretmen/deneme_kontrol_merkezi.html",
        {
            "siniflar": siniflar,
            "gruplar": gruplar,
            "sirala": sirala,
            "gosterilen_id": gosterilen_id,
            "ekran": ekran,
            "ekran_sorgu": f"?ekran={ekran}" if ekran in ("kazanim", "cisa") else "",
            "cisa_acik": cisa_acik,
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
