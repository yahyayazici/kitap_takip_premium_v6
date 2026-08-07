"""Yazılı takip — personel görüntüleme."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate

from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.yazili_takip_service import (
    kamp_ozet_istatistik,
    sinav_sonuclari_sirali,
    sonuc_giris_satirlari,
    sonuclari_toplu_kaydet,
    yazili_duzenleyebilir,
    yetkili_kamplar,
    yetkili_sinavlar,
)
from takip.models import YaziliSinav


@login_required
@require_permission("yazili_takip", "view")
def yazili_kamp_listesi(request):
    kamplar = yetkili_kamplar(request.user)
    return render(
        request,
        "yazili_kamp_listesi.html",
        {"kamplar": kamplar},
    )


@login_required
@require_permission("yazili_takip", "view")
def yazili_kamp_detay(request, pk):
    kamp = get_object_or_404(yetkili_kamplar(request.user), pk=pk)
    sinavlar = list(yetkili_sinavlar(request.user, kamp))

    sinav_id = request.GET.get("sinav")
    secili_sinav = None
    sonuc_satirlari = []

    if sinav_id:
        secili_sinav = get_object_or_404(
            yetkili_sinavlar(request.user, kamp),
            pk=sinav_id,
        )
    elif sinavlar:
        secili_sinav = sinavlar[0]

    if secili_sinav:
        sonuc_satirlari = sinav_sonuclari_sirali(request.user, secili_sinav)

    return render(
        request,
        "yazili_kamp_detay.html",
        {
            "kamp": kamp,
            "sinavlar": sinavlar,
            "secili_sinav": secili_sinav,
            "sonuc_satirlari": sonuc_satirlari,
            "istatistik": kamp_ozet_istatistik(request.user, kamp),
            "sonuc_girebilir": yazili_duzenleyebilir(request.user),
            "pdf_yetkisi": can(request.user, "yazili_takip", "export_pdf"),
        },
    )


@login_required
@require_permission("yazili_takip", "edit")
def yazili_sonuc_gir(request, pk):
    sinav = get_object_or_404(
        YaziliSinav.objects.select_related("kamp"),
        pk=pk,
        kamp__aktif=True,
    )
    if not can(request.user, "yazili_takip", "view"):
        return redirect("yazili_kamp_listesi")

    from takip.yazili_takip_service import sinav_sonuc_talebeleri

    talebeler = list(sinav_sonuc_talebeleri(request.user, sinav))
    toplam_soru = int(sinav.soru_sayisi or 0)

    if toplam_soru <= 0:
        messages.error(request, "Sınav soru sayısı geçersiz.")
        return redirect("yazili_kamp_detay", pk=sinav.kamp_id)

    if request.method == "POST":
        kaydedilen, hatalar = sonuclari_toplu_kaydet(
            request.user,
            sinav,
            talebeler,
            request.POST,
        )
        for hata in hatalar:
            messages.error(request, hata)
        if not hatalar:
            messages.success(
                request,
                f"{kaydedilen} öğrenci sonucu kaydedildi.",
            )
            return redirect("yazili_sonuc_gir", pk=sinav.pk)

    return render(
        request,
        "yazili_sonuc_gir.html",
        {
            "sinav": sinav,
            "kamp": sinav.kamp,
            "satirlar": sonuc_giris_satirlari(request.user, sinav),
            "toplam_soru": toplam_soru,
        },
    )


@login_required
@require_permission("yazili_takip", "export_pdf")
def yazili_kamp_pdf(request, pk):
    kamp = get_object_or_404(yetkili_kamplar(request.user), pk=pk)
    sinavlar = list(yetkili_sinavlar(request.user, kamp))

    sinav_verileri = []
    for sinav in sinavlar:
        sinav_verileri.append(
            {
                "sinav": sinav,
                "satirlar": sinav_sonuclari_sirali(request.user, sinav),
            }
        )

    html = render(
        request,
        "yazili_kamp_pdf.html",
        {
            "kamp": kamp,
            "sinav_verileri": sinav_verileri,
            "istatistik": kamp_ozet_istatistik(request.user, kamp),
            "bugun": localdate(),
        },
    ).content.decode("utf-8")

    pdf_verisi = html_to_pdf(html)
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    return make_pdf_response(
        pdf_verisi,
        f"yazili_kamp_{kamp.pk}_{localdate():%Y%m%d}.pdf",
    )
