"""KTT akıllı takip — etüt paneli görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from takip.konu_destek_service import ders_adindan_brans
from takip.ktt_akilli_service import (
    bekleyen_eslestirmeler,
    etut_bugun_dikkat,
    etut_mudahale_kaydet,
    grup_ortak_eksikler,
    yonetim_ktt_ozet,
)
from takip.ktt_konu_normalize_service import eslestirme_onayla, konu_oneri_listesi
from takip.models import Ders, KttSinav, TalebeKonuEksigi
from takip.permissions.decorators import require_permission
from takip.user_helpers import etut_hocasi_for_user

from .yonetim_views import yonetici_gerekli


@login_required
@require_permission("ktt", "view")
def ktt_akilli_ozet(request):
    hoca = etut_hocasi_for_user(request.user)
    if not hoca:
        messages.info(request, "Etüt hocası kaydı bulunamadı; özet sınırlı gösterilir.")
        dikkat = []
        ortak = []
    else:
        dikkat = etut_bugun_dikkat(hoca)
        ortak = grup_ortak_eksikler(hoca)

    qs = TalebeKonuEksigi.objects.filter(
        kaynak=TalebeKonuEksigi.Kaynak.KTT,
        mudahale_durumu="bekliyor",
        cozuldu=False,
    )
    if hoca:
        qs = qs.filter(talebe__etut_hocasi=hoca)
    bekleyen_eksikler = qs.select_related("talebe", "konu").order_by("-oncelik", "-tespit_tarihi")[:20]

    return render(
        request,
        "ktt_akilli_ozet.html",
        {
            "dikkat": dikkat,
            "ortak_eksikler": ortak,
            "bekleyen_eksikler": bekleyen_eksikler,
            "eslestirmeler": bekleyen_eslestirmeler(15),
        },
    )


@login_required
@require_permission("ktt", "view")
def ktt_konu_oneri(request):
    arama = request.GET.get("q", "")
    sinif = request.GET.get("sinif", "7")
    ders_id = request.GET.get("ders")
    brans = request.GET.get("brans")
    if ders_id and not brans:
        ders = Ders.objects.filter(pk=ders_id).first()
        if ders:
            brans = ders_adindan_brans(ders.ad)
    if not brans:
        return JsonResponse({"oneriler": []})
    oneriler = konu_oneri_listesi(sinif, brans, arama)
    return JsonResponse({"oneriler": oneriler})


@login_required
@require_permission("ktt", "edit")
@require_POST
def ktt_mudahale_calisildi(request, eksik_id):
    hoca = etut_hocasi_for_user(request.user)
    if not hoca:
        messages.error(request, "Etüt hocası kaydı bulunamadı.")
        return redirect("ktt_akilli_ozet")

    eksik = get_object_or_404(
        TalebeKonuEksigi.objects.select_related("talebe", "konu"),
        pk=eksik_id,
        kaynak=TalebeKonuEksigi.Kaynak.KTT,
    )
    if eksik.talebe.etut_hocasi_id != hoca.id and not request.user.is_superuser:
        messages.error(request, "Bu talebe için müdahale kaydı oluşturamazsınız.")
        return redirect("ktt_akilli_ozet")

    etut_mudahale_kaydet(eksik, hoca, request.user)
    messages.success(
        request,
        f"{eksik.talebe.ad_soyad} — {eksik.konu.konu_ad} çalışıldı olarak işaretlendi.",
    )
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    if next_url:
        return redirect(next_url)
    return redirect("ktt_akilli_ozet")


@login_required
@require_permission("ktt", "edit")
@require_POST
def ktt_eslestirme_onayla(request, pk):
    eslestirme_onayla(pk, request.user)
    messages.success(request, "Konu eşleştirmesi onaylandı ve alias kaydedildi.")
    return redirect(request.POST.get("next") or "ktt_akilli_ozet")


@yonetici_gerekli
def yonetim_ktt_akilli_ozet(request):
    return render(
        request,
        "yonetim/ktt_akilli_ozet.html",
        {
            "ozet": yonetim_ktt_ozet(),
            "eslestirmeler": bekleyen_eslestirmeler(50),
        },
    )
