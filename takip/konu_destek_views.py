"""Konu destek merkezi görünümleri — talebe, etüt hocası, API."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from takip.konu_destek_models import KonuEgitimVideosu, KonuKatalogu, KonuTestOturu
from takip.konu_destek_service import (
    etut_hocasi_konu_destek_raporu,
    konu_detay_verisi,
    konu_test_cevabi_kaydet,
    konu_test_oturumu_baslat,
    konu_test_oturumu_bitir,
    konu_test_sorulari,
    talebe_konu_destek_listesi,
    video_izleme_baslat,
    video_izleme_guncelle,
)
from takip.talebe_panel_service import kullanici_talebe_mi, talebe_hesabi_for_user
from takip.user_helpers import etut_hocasi_for_user


def _talebe_hesap(request):
    hesap = talebe_hesabi_for_user(request.user)
    if not hesap or not hesap.aktif:
        return None
    return hesap


@login_required
def talebe_konu_destek(request):
    if not kullanici_talebe_mi(request.user):
        return redirect("dashboard")

    hesap = _talebe_hesap(request)
    if not hesap:
        return redirect("logout")

    talebe = hesap.talebe
    return render(
        request,
        "talebe/konu_destek.html",
        {
            "hesap": hesap,
            "talebe": talebe,
            "konu_kartlari": talebe_konu_destek_listesi(talebe),
        },
    )


@login_required
def talebe_konu_destek_detay(request, konu_id: int):
    if not kullanici_talebe_mi(request.user):
        return redirect("dashboard")

    hesap = _talebe_hesap(request)
    if not hesap:
        return redirect("logout")

    veri = konu_detay_verisi(hesap.talebe, konu_id)
    if not veri:
        messages.error(request, "Konu bulunamadı.")
        return redirect("talebe_konu_destek")

    return render(
        request,
        "talebe/konu_destek_detay.html",
        {"hesap": hesap, "talebe": hesap.talebe, **veri},
    )


@login_required
def talebe_konu_video(request, konu_id: int, sira: int):
    if not kullanici_talebe_mi(request.user):
        return redirect("dashboard")

    hesap = _talebe_hesap(request)
    if not hesap:
        return redirect("logout")

    konu = get_object_or_404(KonuKatalogu, pk=konu_id, aktif=True)
    video = KonuEgitimVideosu.objects.filter(konu=konu, sira=sira, aktif=True).first()

    if not video:
        from takip.konu_destek_service import _konu_videolari

        sanal = [v for v in _konu_videolari(konu) if v.sira == sira]
        if not sanal:
            messages.error(request, "Video bulunamadı.")
            return redirect("talebe_konu_destek_detay", konu_id=konu_id)
        video = sanal[0]

    izleme = video_izleme_baslat(
        hesap.talebe,
        konu,
        video if video.pk else None,
        video.baslik,
    )

    return render(
        request,
        "talebe/konu_destek_video.html",
        {
            "hesap": hesap,
            "talebe": hesap.talebe,
            "konu": konu,
            "video": video,
            "izleme_id": izleme.pk,
        },
    )


@login_required
@require_POST
def talebe_konu_video_heartbeat(request):
    if not kullanici_talebe_mi(request.user):
        return JsonResponse({"ok": False}, status=403)

    hesap = _talebe_hesap(request)
    if not hesap:
        return JsonResponse({"ok": False}, status=403)

    try:
        veri = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        veri = request.POST

    izleme_id = int(veri.get("izleme_id") or 0)
    sure_sn = int(veri.get("sure_sn") or 0)
    tamamlandi = bool(veri.get("tamamlandi"))

    kayit = video_izleme_guncelle(izleme_id, hesap.talebe, sure_sn, tamamlandi)
    if not kayit:
        return JsonResponse({"ok": False}, status=404)
    return JsonResponse({"ok": True, "sure_sn": kayit.sure_sn, "tamamlandi": kayit.tamamlandi})


@login_required
def talebe_konu_test(request, konu_id: int):
    if not kullanici_talebe_mi(request.user):
        return redirect("dashboard")

    hesap = _talebe_hesap(request)
    if not hesap:
        return redirect("logout")

    konu = get_object_or_404(KonuKatalogu, pk=konu_id, aktif=True)
    sorular, test_kaynak = konu_test_sorulari(konu, talebe=hesap.talebe)
    if not sorular:
        messages.warning(request, "Bu konu için test soruları hazırlanamadı.")
        return redirect("talebe_konu_destek_detay", konu_id=konu_id)

    oturum_id = request.session.get(f"konu_test_{konu_id}")
    oturum = None
    if oturum_id:
        oturum = KonuTestOturu.objects.filter(
            pk=oturum_id, talebe=hesap.talebe, konu=konu, bitis__isnull=True
        ).first()

    if request.method == "POST":
        if not oturum:
            oturum = konu_test_oturumu_baslat(hesap.talebe, konu)
            if oturum:
                request.session[f"konu_test_{konu_id}"] = oturum.pk

        if not oturum:
            messages.error(request, "Test başlatılamadı.")
            return redirect("talebe_konu_destek_detay", konu_id=konu_id)

        if request.POST.get("islem") == "bitir":
            konu_test_oturumu_bitir(oturum)
            request.session.pop(f"konu_test_{konu_id}", None)
            messages.success(
                request,
                f"Test tamamlandı: {oturum.dogru_sayisi}/{oturum.toplam_soru} "
                f"(%{oturum.basari_yuzde})",
            )
            return redirect("talebe_konu_destek_detay", konu_id=konu_id)

        for soru in sorular:
            alan = f"soru_{soru.pk}"
            if alan in request.POST:
                konu_test_cevabi_kaydet(oturum, soru, request.POST.get(alan, ""))

        messages.success(request, "Cevaplar kaydedildi.")
        return redirect("talebe_konu_test", konu_id=konu_id)

    if not oturum:
        oturum = konu_test_oturumu_baslat(hesap.talebe, konu)
        if oturum:
            request.session[f"konu_test_{konu_id}"] = oturum.pk

    mevcut_cevaplar = {}
    if oturum:
        mevcut_cevaplar = {
            c.soru_id: c.secilen for c in oturum.cevaplar.select_related("soru")
        }

    ai_etiket = {
        "ai": "Yapay zeka · denetimli yeni nesil set",
        "kural": "Bağlam temelli soru seti",
        "havuz": "Hazır soru bankası",
    }.get(test_kaynak, "")

    return render(
        request,
        "talebe/konu_destek_test.html",
        {
            "hesap": hesap,
            "talebe": hesap.talebe,
            "konu": konu,
            "sorular": sorular,
            "oturum": oturum,
            "mevcut_cevaplar": mevcut_cevaplar,
            "test_kaynak": test_kaynak,
            "ai_etiket": ai_etiket,
        },
    )


@login_required
def etut_konu_destek_rapor(request):
    hoca = etut_hocasi_for_user(request.user)
    if not hoca and not request.user.is_superuser:
        messages.error(request, "Bu sayfa yalnızca etüt hocaları içindir.")
        return redirect("dashboard")

    if request.user.is_superuser and not hoca:
        from takip.models import EtutHocasi

        hoca = EtutHocasi.objects.filter(aktif=True).first()
        if not hoca:
            messages.warning(request, "Etüt hocası kaydı bulunamadı.")
            return redirect("dashboard")

    return render(
        request,
        "konu_destek/etut_rapor.html",
        etut_hocasi_konu_destek_raporu(hoca),
    )
