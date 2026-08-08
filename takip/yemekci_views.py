"""Yemekçilik paneli — sınıf döngüsü UI ve API."""

from __future__ import annotations

import json
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.text import slugify
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST

from config.branding import PANEL_SHORT
from takip.panel_permissions import yemekcilik_modulu_erisimi_var, yonetim_erisimi_var
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status
from takip.yemekci_service import (
    aralik_uret,
    ayarlari_al,
    gorevli_degistir,
    gun_atama_sil,
    kayit_ekle,
    kayit_sil,
    kayitlari_sirala,
    panel_baglami,
)
from takip.yemekci_sinif_models import SINIF_ETIKET, SINIF_RENKLERI


def _erisim(request) -> bool:
    if not yemekcilik_modulu_erisimi_var(request.user):
        messages.error(request, "Yemekçilik modülüne erişim yetkiniz yok.")
        return False
    return True


def _parse_date(raw: str | None, default: date | None = None) -> date:
    default = default or localdate()
    if not raw:
        return default
    try:
        y, m, d = raw.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return default


def _json_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return {}
    return {}


@login_required
def yemekcilik_panel(request):
    if not _erisim(request):
        return redirect("dashboard")

    sekme = (request.GET.get("sekme") or "bugun").strip()
    if sekme not in {"bugun", "takvim", "siralama", "toplu"}:
        sekme = "bugun"

    tarih = _parse_date(request.GET.get("tarih"))
    yil = int(request.GET.get("yil") or tarih.year)
    ay = int(request.GET.get("ay") or tarih.month)

    toplu_satirlar = None
    if sekme == "toplu" and request.method == "POST" and request.POST.get("action") == "toplu_hesapla":
        bas = _parse_date(request.POST.get("baslangic"), tarih)
        sure = int(request.POST.get("sure") or 15)
        hafta_sonu = request.POST.get("hafta_sonu_cikar") == "1"
        bitis = bas + timedelta(days=max(sure - 1, 0))
        # süre gün sayısı çalışma günü değil takvim — aralik_uret workdays filtreler
        # bitiş: bas'tan sure kadar workday üretmek için geniş aralık
        bitis = bas + timedelta(days=sure * 2)
        gunler_hedef = sure
        satirlar = aralik_uret(
            bas,
            bitis,
            hafta_sonu_cikar=hafta_sonu,
            kaydet=request.POST.get("kaydet") == "1",
            user=request.user,
        )
        toplu_satirlar = satirlar[:gunler_hedef]
        ayar = ayarlari_al()
        if ayar.hafta_sonu_cikar != hafta_sonu:
            ayar.hafta_sonu_cikar = hafta_sonu
            ayar.save(update_fields=["hafta_sonu_cikar", "guncellenme"])

    ctx = panel_baglami(tarih=tarih, sekme=sekme, ay=ay, yil=yil)
    ctx.update(
        {
            "yonetim_modulu": yonetim_erisimi_var(request.user),
            "duzenleyebilir": yonetim_erisimi_var(request.user) or request.user.is_staff,
            "toplu_satirlar": toplu_satirlar,
            "toplu_baslangic": request.POST.get("baslangic") or tarih.isoformat(),
            "toplu_sure": request.POST.get("sure") or "15",
            "toplu_hafta_sonu": request.POST.get("hafta_sonu_cikar", "1") == "1"
            if request.method == "POST"
            else ayarlari_al().hafta_sonu_cikar,
            "onceki": (tarih - timedelta(days=1)).isoformat(),
            "sonraki": (tarih + timedelta(days=1)).isoformat(),
            "siniflar": ["5", "6", "7", "8"],
        }
    )
    return render(request, "yemekcilik_panel.html", ctx)


@login_required
def yemekcilik_pdf(request, pk=None):
    """Toplu aralık PDF — query: baslangic, sure, hafta_sonu_cikar, boyut=a4|a3."""
    if not _erisim(request):
        return redirect("dashboard")

    bas = _parse_date(request.GET.get("baslangic"))
    sure = int(request.GET.get("sure") or 15)
    hafta_sonu = request.GET.get("hafta_sonu_cikar", "1") == "1"
    boyut = (request.GET.get("boyut") or "a4").lower()
    if boyut not in {"a4", "a3"}:
        boyut = "a4"
    bitis = bas + timedelta(days=sure * 2)
    satirlar = aralik_uret(bas, bitis, hafta_sonu_cikar=hafta_sonu)[:sure]

    html_metni = render_to_string(
        "yemekcilik_pdf.html",
        {
            "baslangic": bas,
            "sure": sure,
            "satirlar": satirlar,
            "boyut": boyut,
            "sinif_etiket": SINIF_ETIKET,
            "sinif_renkleri": SINIF_RENKLERI,
            "panel_short": PANEL_SHORT,
        },
        request=request,
    )
    pdf_verisi = html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        messages.error(request, f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})")
        return redirect("yemekcilik_panel")
    return make_pdf_response(
        pdf_verisi,
        f"yemekcilik-{bas.isoformat()}-{sure}gun-{boyut}.pdf",
    )


@login_required
@require_POST
def yemekcilik_api_kayit_ekle(request):
    if not _erisim(request):
        return JsonResponse({"ok": False, "hata": "Yetki yok."}, status=403)
    payload = _json_body(request) or request.POST
    try:
        kayit = kayit_ekle(str(payload.get("sinif")), int(payload.get("talebe_id")))
    except Exception as exc:
        return JsonResponse({"ok": False, "hata": str(exc)}, status=400)
    return JsonResponse({"ok": True, "kayit_id": kayit.pk})


@login_required
@require_POST
def yemekcilik_api_kayit_sil(request):
    if not _erisim(request):
        return JsonResponse({"ok": False, "hata": "Yetki yok."}, status=403)
    payload = _json_body(request) or request.POST
    try:
        kayit_sil(int(payload.get("kayit_id")))
    except Exception as exc:
        return JsonResponse({"ok": False, "hata": str(exc)}, status=400)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def yemekcilik_api_sirala(request):
    if not _erisim(request):
        return JsonResponse({"ok": False, "hata": "Yetki yok."}, status=403)
    payload = _json_body(request)
    sinif = str(payload.get("sinif") or "")
    ids = [int(x) for x in (payload.get("kayit_ids") or [])]
    if not kayitlari_sirala(sinif, ids):
        return JsonResponse({"ok": False, "hata": "Sıra kaydedilemedi."}, status=400)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def yemekcilik_api_gorevli(request):
    if not _erisim(request):
        return JsonResponse({"ok": False, "hata": "Yetki yok."}, status=403)
    payload = _json_body(request) or request.POST
    tarih = _parse_date(payload.get("tarih"))
    sinif = str(payload.get("sinif") or "")
    if payload.get("reset") in {"1", 1, True, "true"}:
        gun_atama_sil(tarih, sinif)
        return JsonResponse({"ok": True})
    try:
        gorevli_degistir(tarih, sinif, int(payload.get("talebe_id")), user=request.user)
    except Exception as exc:
        return JsonResponse({"ok": False, "hata": str(exc)}, status=400)
    return JsonResponse({"ok": True})
