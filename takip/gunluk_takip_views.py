"""Günlük takip panel görünümleri."""

from __future__ import annotations

from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate

from takip.forms import GunlukTakipKaydiForm
from takip.gunluk_takip_service import (
    etut_yoklama_kaydet,
    etut_yoklama_ozet,
    etut_yoklama_satirlari,
    gunluk_kayitlari_filtrele,
    gunluk_takip_duzenleyebilir,
    yetkili_gunluk_kayitlari,
)
from takip.models import GunlukTakipKaydi
from takip.permissions.decorators import require_permission


def _parse_tarih(deger: str | None) -> date | None:
    if not deger:
        return None
    try:
        return datetime.strptime(deger, "%Y-%m-%d").date()
    except ValueError:
        return None


@login_required
@require_permission("gunluk_takip", "view")
def gunluk_takip_etut(request):
    """Eski URL — ana panele yönlendir."""
    tarih = request.GET.get("tarih", "").strip()
    if request.method == "POST":
        tarih = request.POST.get("tarih", tarih).strip()
    if tarih:
        return redirect(f"/gunluk-takip/?tarih={tarih}")
    return redirect("gunluk_takip_panel")


@login_required
@require_permission("gunluk_takip", "view")
def gunluk_takip_panel(request):
    duzenleyebilir = gunluk_takip_duzenleyebilir(request.user)

    tarih_str = request.GET.get("tarih", "").strip()
    if request.method == "POST":
        tarih_str = request.POST.get("tarih", tarih_str).strip()

    secili_tarih = _parse_tarih(tarih_str) or localdate()
    satirlar = etut_yoklama_satirlari(request.user, secili_tarih)
    ozet = etut_yoklama_ozet(satirlar)

    if request.method == "POST" and duzenleyebilir:
        devamsiz_ids = {
            int(x)
            for x in request.POST.getlist("devamsiz")
            if str(x).isdigit()
        }
        adet = etut_yoklama_kaydet(request.user, secili_tarih, devamsiz_ids)
        messages.success(
            request,
            f"{secili_tarih:%d.%m.%Y} etüt yoklaması kaydedildi. "
            f"{adet - len(devamsiz_ids)} katıldı, {len(devamsiz_ids)} devamsız.",
        )
        return redirect(f"{request.path}?tarih={secili_tarih:%Y-%m-%d}")

    qs = yetkili_gunluk_kayitlari(request.user).order_by("-tarih", "talebe__ad_soyad")
    q = request.GET.get("q", "").strip()
    liste_tarih = request.GET.get("liste_tarih", "").strip() or secili_tarih.isoformat()
    devam = request.GET.get("devam", "").strip()
    qs = gunluk_kayitlari_filtrele(
        qs,
        q=q or None,
        tarih=liste_tarih or None,
        devam=devam or None,
    )

    return render(
        request,
        "gunluk_takip_panel.html",
        {
            "satirlar": satirlar,
            "ozet": ozet,
            "secili_tarih": secili_tarih,
            "kayitlar": qs[:200],
            "filtre_q": q,
            "filtre_tarih": liste_tarih,
            "filtre_devam": devam,
            "devam_secenekleri": GunlukTakipKaydi.DevamDurumu.choices,
            "duzenleyebilir": duzenleyebilir,
        },
    )


@login_required
@require_permission("gunluk_takip", "view")
def gunluk_takip_detay(request, pk):
    kayit = get_object_or_404(yetkili_gunluk_kayitlari(request.user), pk=pk)
    return render(
        request,
        "gunluk_takip_detay.html",
        {
            "kayit": kayit,
            "duzenleyebilir": gunluk_takip_duzenleyebilir(request.user),
        },
    )


@login_required
@require_permission("gunluk_takip", "edit")
def gunluk_takip_duzenle(request, pk):
    kayit = get_object_or_404(yetkili_gunluk_kayitlari(request.user), pk=pk)
    form = GunlukTakipKaydiForm(
        request.user,
        request.POST or None,
        instance=kayit,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Kayıt güncellendi.")
        return redirect("gunluk_takip_detay", pk=kayit.pk)

    return render(
        request,
        "gunluk_takip_form.html",
        {
            "form": form,
            "kayit": kayit,
            "baslik": "Günlük Takip Düzenle",
        },
    )
