"""Yapay zeka platformu API."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from takip.ai_permissions import (
    ai_erisim_var,
    kurum_ai_erisebilir,
    rehberlik_ai_erisebilir,
    talebe_ai_erisebilir,
    veli_takip_ai_erisebilir,
)
from takip.ai_service import (
    ai_durumu,
    deneme_zekasi_analizi,
    gelisim_zekasi_analizi,
    kurum_zekasi_ozet,
    mudahale_oneri_listesi,
    rehberlik_gorusme_ozeti,
    soru_takip_insight,
    veli_haftalik_ozet,
    veli_takip_zekasi_raporu,
)
from takip.deneme_service import deneme_sonuclari, yetkili_denemeler
from takip.models import DenemeSinavi, Talebe
from takip.rehberlik_models import OgrenciGorusmesi


def _json_hata(mesaj: str, status: int = 403) -> JsonResponse:
    return JsonResponse({"ok": False, "hata": mesaj}, status=status)


@login_required
@require_GET
def ai_analiz_api(request):
    if not ai_erisim_var(request.user):
        return _json_hata("AI platformu kullanılamıyor.", 403)

    tur = (request.GET.get("tur") or "").strip()
    yenile = request.GET.get("yenile") == "1"

    if tur == "gelisim_zekasi":
        talebe_id = request.GET.get("talebe_id")
        if not talebe_id:
            return _json_hata("talebe_id gerekli", 400)
        talebe = get_object_or_404(Talebe, pk=talebe_id)
        if not talebe_ai_erisebilir(request.user, talebe):
            return _json_hata("Bu talebe için erişim yok.", 403)
        sonuc = gelisim_zekasi_analizi(request.user, talebe, yenile=yenile)
        return JsonResponse({"ok": True, "analiz": sonuc.as_dict(), "durum": ai_durumu()})

    if tur == "veli_haftalik":
        talebe_id = request.GET.get("talebe_id")
        talebe = get_object_or_404(Talebe, pk=talebe_id)
        if not talebe_ai_erisebilir(request.user, talebe):
            return _json_hata("Erişim yok.", 403)
        sonuc = veli_haftalik_ozet(talebe, user=request.user, yenile=yenile)
        return JsonResponse({"ok": True, "analiz": sonuc.as_dict(), "durum": ai_durumu()})

    if tur == "deneme_analiz":
        deneme_id = request.GET.get("deneme_id")
        deneme = get_object_or_404(yetkili_denemeler(request.user), pk=deneme_id)
        sonuclar = list(deneme_sonuclari(request.user, deneme))
        sonuc = deneme_zekasi_analizi(request.user, deneme, sonuclar, yenile=yenile)
        return JsonResponse({"ok": True, "analiz": sonuc.as_dict(), "durum": ai_durumu()})

    if tur == "kurum_zekasi":
        if not kurum_ai_erisebilir(request.user):
            return _json_hata("Kurum zekası erişimi yok.", 403)
        sonuc = kurum_zekasi_ozet(request.user, yenile=yenile)
        meta = sonuc.meta or {}
        return JsonResponse(
            {
                "ok": True,
                "analiz": sonuc.as_dict(),
                "durum": ai_durumu(),
                "mudahale_adaylari": meta.get("risk_adaylari") or mudahale_oneri_listesi(request.user),
            }
        )

    if tur == "rehberlik_ozet":
        gorusme_id = request.GET.get("gorusme_id")
        if not rehberlik_ai_erisebilir(request.user):
            return _json_hata("Rehberlik AI erişimi yok.", 403)
        gorusme = get_object_or_404(OgrenciGorusmesi, pk=gorusme_id)
        if not talebe_ai_erisebilir(request.user, gorusme.talebe):
            return _json_hata("Erişim yok.", 403)
        sonuc = rehberlik_gorusme_ozeti(gorusme, user=request.user, yenile=yenile)
        return JsonResponse({"ok": True, "analiz": sonuc.as_dict(), "durum": ai_durumu()})

    if tur == "soru_takip":
        talebe = None
        talebe_id = request.GET.get("talebe_id")
        if talebe_id:
            talebe = get_object_or_404(Talebe, pk=talebe_id)
            if not talebe_ai_erisebilir(request.user, talebe):
                return _json_hata("Erişim yok.", 403)
        elif not kurum_ai_erisebilir(request.user):
            return _json_hata("Erişim yok.", 403)
        sonuc = soru_takip_insight(request.user, talebe, yenile=yenile)
        return JsonResponse({"ok": True, "analiz": sonuc.as_dict(), "durum": ai_durumu()})

    if tur == "mudahale_listesi":
        if not kurum_ai_erisebilir(request.user):
            return _json_hata("Erişim yok.", 403)
        return JsonResponse(
            {
                "ok": True,
                "adaylar": mudahale_oneri_listesi(request.user),
                "durum": ai_durumu(),
            }
        )

    if tur == "veli_takip":
        if not veli_takip_ai_erisebilir(request.user):
            return _json_hata("Veli takip AI erişimi yok.", 403)
        sonuc = veli_takip_zekasi_raporu(request.user, yenile=yenile)
        return JsonResponse({"ok": True, "analiz": sonuc.as_dict(), "durum": ai_durumu()})

    return _json_hata("Geçersiz tur.", 400)


@login_required
@require_GET
def ai_analiz_html(request):
    """Analiz kartını HTML parçası olarak döner (lazy load)."""
    if not ai_erisim_var(request.user):
        return HttpResponse("", status=403)

    tur = (request.GET.get("tur") or "").strip()
    yenile = request.GET.get("yenile") == "1"
    analiz = None

    if tur == "gelisim_zekasi":
        talebe = get_object_or_404(Talebe, pk=request.GET.get("talebe_id"))
        if not talebe_ai_erisebilir(request.user, talebe):
            return HttpResponse("", status=403)
        analiz = gelisim_zekasi_analizi(request.user, talebe, yenile=yenile)
    elif tur == "veli_haftalik":
        talebe = get_object_or_404(Talebe, pk=request.GET.get("talebe_id"))
        if not talebe_ai_erisebilir(request.user, talebe):
            return HttpResponse("", status=403)
        analiz = veli_haftalik_ozet(talebe, user=request.user, yenile=yenile)
    elif tur == "deneme_analiz":
        deneme = get_object_or_404(yetkili_denemeler(request.user), pk=request.GET.get("deneme_id"))
        sonuclar = list(deneme_sonuclari(request.user, deneme))
        analiz = deneme_zekasi_analizi(request.user, deneme, sonuclar, yenile=yenile)
    elif tur == "kurum_zekasi":
        if not kurum_ai_erisebilir(request.user):
            return HttpResponse("", status=403)
        analiz = kurum_zekasi_ozet(request.user, yenile=yenile)
    elif tur == "veli_takip":
        if not veli_takip_ai_erisebilir(request.user):
            return HttpResponse("", status=403)
        analiz = veli_takip_zekasi_raporu(request.user, yenile=yenile)
    elif tur == "rehberlik_ozet":
        gorusme = get_object_or_404(OgrenciGorusmesi, pk=request.GET.get("gorusme_id"))
        if not talebe_ai_erisebilir(request.user, gorusme.talebe):
            return HttpResponse("", status=403)
        analiz = rehberlik_gorusme_ozeti(gorusme, user=request.user, yenile=yenile)
    else:
        return HttpResponse("", status=400)

    return render(
        request,
        "includes/ai_analiz_card.html",
        {"analiz": analiz, "analiz_durumu": ai_durumu()},
    )
