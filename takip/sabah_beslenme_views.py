"""Sabah Beslenmesi panelleri ve AJAX uçları."""

from __future__ import annotations

import json
from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST

from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.sabah_beslenme_models import SabahBeslenmeGunlukMenu, SabahBeslenmeSiparis
from takip.sabah_beslenme_service import (
    SabahBeslenmeHata,
    acik_borc_ozet,
    acik_borc_qs,
    borc_kapat,
    borc_kapatabilir,
    etut_siparis_satirlari,
    gun_ozeti,
    menu_al,
    menu_kaydet,
    menu_yonetebilir,
    odeme_turu_ayarla,
    rapor_gorebilir,
    rapor_satirlari,
    siparis_girebilir,
    siparis_json,
    siparis_kaydet,
    siparis_penceresi_acik,
    satis_satirlari,
    satis_yapabilir,
    teslim_et,
    teslim_geri_al,
)

MODUL = "sabah_beslenmesi"
URUN_ONERILERI = ("Simit", "Poğaça", "Açma", "Peynirli poğaça", "Çikolatalı poğaça")


def _parse_date(raw: str | None, default: date | None = None) -> date:
    default = default or localdate()
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return default


def _parse_time(raw: str | None, default: time | None = None) -> time:
    default = default or time(7, 30)
    if not raw:
        return default
    try:
        parts = raw.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, TypeError, IndexError):
        return default


def _parse_decimal(raw) -> Decimal:
    try:
        return Decimal(str(raw or "0").replace(",", "."))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SabahBeslenmeHata("Birim fiyat geçersiz.") from exc


def _json_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return {}
    return {}


def _json_hata(exc: Exception, status: int = 400):
    return JsonResponse({"ok": False, "hata": str(exc)}, status=status)


def _nav(request, aktif: str) -> dict:
    user = request.user
    return {
        "sb_nav_aktif": aktif,
        "sb_siparis_yetki": siparis_girebilir(user),
        "sb_satis_yetki": satis_yapabilir(user),
        "sb_menu_yetki": menu_yonetebilir(user),
        "sb_borc_yetki": borc_kapatabilir(user),
        "sb_rapor_yetki": rapor_gorebilir(user),
        "sb_urun_onerileri": URUN_ONERILERI,
    }


def _cevap_paketi(user, menu, siparis=None) -> dict:
    payload = {"ok": True, "ozet": gun_ozeti(menu)}
    if siparis is not None:
        payload["siparis"] = siparis_json(siparis)
    return payload


@login_required
@require_permission(MODUL, "view")
def sabah_beslenme_landing(request):
    if satis_yapabilir(request.user):
        return redirect("sabah_beslenme_satis")
    if borc_kapatabilir(request.user) and not siparis_girebilir(request.user):
        return redirect("sabah_beslenme_borclar")
    return redirect("sabah_beslenme_siparis")


@login_required
@require_permission(MODUL, "view")
def sabah_beslenme_siparis(request):
    if not siparis_girebilir(request.user) and not can(request.user, MODUL, "view"):
        messages.error(request, "Sipariş ekranına erişim yetkiniz yok.")
        return redirect("dashboard")

    tarih = _parse_date(request.GET.get("tarih"))
    menu = menu_al(tarih)
    ctx = _nav(request, "siparis")
    ctx.update(
        {
            "tarih": tarih,
            "onceki": (tarih - timedelta(days=1)).isoformat(),
            "sonraki": (tarih + timedelta(days=1)).isoformat(),
            "menu": menu,
            "pencere_acik": siparis_penceresi_acik(menu) if menu else False,
            "satirlar": etut_siparis_satirlari(request.user, menu) if menu else [],
            "menu_yonet": menu_yonetebilir(request.user),
        }
    )
    return render(request, "sabah_beslenme_siparis.html", ctx)


@login_required
@require_permission(MODUL, "view")
def sabah_beslenme_satis(request):
    if not (satis_yapabilir(request.user) or menu_yonetebilir(request.user) or borc_kapatabilir(request.user)):
        messages.error(request, "Satış ekranına erişim yetkiniz yok.")
        return redirect("sabah_beslenme_siparis")

    tarih = _parse_date(request.GET.get("tarih"))
    menu = menu_al(tarih)
    siparisler = satis_satirlari(request.user, menu) if menu else []
    etutler = sorted({(s.etut_hocasi_id or 0, s.etut_hocasi.ad_soyad if s.etut_hocasi_id else "—") for s in siparisler})
    ctx = _nav(request, "satis")
    ctx.update(
        {
            "tarih": tarih,
            "onceki": (tarih - timedelta(days=1)).isoformat(),
            "sonraki": (tarih + timedelta(days=1)).isoformat(),
            "menu": menu,
            "siparisler": siparisler,
            "siparis_json": [siparis_json(s) for s in siparisler],
            "ozet": gun_ozeti(menu),
            "etut_filtreleri": etutler,
            "satis_yapabilir": satis_yapabilir(request.user),
        }
    )
    return render(request, "sabah_beslenme_satis.html", ctx)


@login_required
@require_permission(MODUL, "view")
def sabah_beslenme_menu(request):
    if not menu_yonetebilir(request.user):
        messages.error(request, "Günlük menüyü yalnızca satış sorumlusu veya yönetici tanımlayabilir.")
        return redirect("sabah_beslenme_landing")

    tarih = _parse_date(request.POST.get("tarih") or request.GET.get("tarih"))
    menu = menu_al(tarih)

    if request.method == "POST":
        try:
            menu = menu_kaydet(
                request.user,
                tarih=_parse_date(request.POST.get("tarih"), tarih),
                urun=request.POST.get("urun") or "",
                birim_fiyat=_parse_decimal(request.POST.get("birim_fiyat")),
                siparis_son_saati=_parse_time(request.POST.get("siparis_son_saati")),
                durum=request.POST.get("durum") or SabahBeslenmeGunlukMenu.Durum.ACIK,
            )
            messages.success(request, f"{menu.tarih:%d.%m.%Y} menüsü kaydedildi.")
            return redirect(f"{request.path}?tarih={menu.tarih.isoformat()}")
        except SabahBeslenmeHata as exc:
            messages.error(request, str(exc))

    son_menuler = SabahBeslenmeGunlukMenu.objects.order_by("-tarih")[:14]
    ctx = _nav(request, "menu")
    ctx.update({"tarih": tarih, "menu": menu, "son_menuler": son_menuler})
    return render(request, "sabah_beslenme_menu.html", ctx)


@login_required
@require_permission(MODUL, "view")
def sabah_beslenme_rapor(request):
    if not rapor_gorebilir(request.user):
        messages.error(request, "Rapor yetkiniz yok.")
        return redirect("sabah_beslenme_landing")

    bugun = localdate()
    bas = _parse_date(request.GET.get("bas"), bugun - timedelta(days=6))
    bitis = _parse_date(request.GET.get("bitis"), bugun)
    if bitis < bas:
        bas, bitis = bitis, bas
    siparisler = rapor_satirlari(request.user, bas, bitis)
    teslim = [s for s in siparisler if s.teslim_edildi]
    pesin = sum((s.tutar for s in teslim if s.odeme_turu == SabahBeslenmeSiparis.OdemeTuru.PESIN), Decimal("0.00"))
    borc = sum((s.tutar for s in teslim if s.odeme_turu == SabahBeslenmeSiparis.OdemeTuru.BORC), Decimal("0.00"))
    ctx = _nav(request, "rapor")
    ctx.update(
        {
            "tarih": bugun,
            "bas": bas,
            "bitis": bitis,
            "siparisler": siparisler,
            "toplam_adet": sum(s.adet for s in siparisler),
            "teslim_adet": len(teslim),
            "pesin": pesin,
            "borc": borc,
        }
    )
    return render(request, "sabah_beslenme_rapor.html", ctx)


@login_required
@require_permission(MODUL, "view")
def sabah_beslenme_borclar(request):
    if not borc_kapatabilir(request.user) and not satis_yapabilir(request.user):
        messages.error(request, "Borç listesini görme yetkiniz yok.")
        return redirect("sabah_beslenme_landing")

    qs = acik_borc_qs(request.user)
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(talebe__ad_soyad__icontains=q)
    ctx = _nav(request, "borclar")
    ctx.update(
        {
            "tarih": localdate(),
            "siparisler": list(qs),
            "ozet": acik_borc_ozet(request.user),
            "q": q,
            "kapatabilir": borc_kapatabilir(request.user),
        }
    )
    return render(request, "sabah_beslenme_borclar.html", ctx)


@login_required
@require_POST
def sabah_beslenme_api_siparis(request):
    if not siparis_girebilir(request.user):
        return _json_hata("Sipariş yetkiniz yok.", 403)
    payload = _json_body(request) or request.POST
    tarih = _parse_date(payload.get("tarih"))
    menu = menu_al(tarih)
    if not menu:
        return _json_hata("Bu tarih için menü yok.")
    try:
        adet = int(payload.get("adet"))
        talebe_id = int(payload.get("talebe_id"))
        siparis = siparis_kaydet(request.user, menu=menu, talebe_id=talebe_id, adet=adet)
    except (TypeError, ValueError):
        return _json_hata("Adet veya talebe bilgisi geçersiz.")
    except SabahBeslenmeHata as exc:
        return _json_hata(exc)
    return JsonResponse(_cevap_paketi(request.user, menu, siparis))


@login_required
@require_POST
def sabah_beslenme_api_teslim(request, pk: int):
    if not satis_yapabilir(request.user):
        return _json_hata("Satış yetkiniz yok.", 403)
    payload = _json_body(request) or request.POST
    geri = str(payload.get("undo") or payload.get("geri") or "").lower() in {"1", "true", "evet"}
    try:
        siparis = teslim_geri_al(request.user, pk) if geri else teslim_et(request.user, pk)
    except SabahBeslenmeHata as exc:
        return _json_hata(exc)
    return JsonResponse(_cevap_paketi(request.user, siparis.menu, siparis))


@login_required
@require_POST
def sabah_beslenme_api_odeme(request, pk: int):
    if not satis_yapabilir(request.user):
        return _json_hata("Ödeme tercihi yetkiniz yok.", 403)
    payload = _json_body(request) or request.POST
    try:
        siparis = odeme_turu_ayarla(request.user, pk, str(payload.get("odeme_turu") or ""))
    except SabahBeslenmeHata as exc:
        return _json_hata(exc)
    return JsonResponse(_cevap_paketi(request.user, siparis.menu, siparis))


@login_required
@require_POST
def sabah_beslenme_api_borc_kapat(request, pk: int):
    if not borc_kapatabilir(request.user):
        return _json_hata("Borç kapatma yetkiniz yok.", 403)
    try:
        siparis = borc_kapat(request.user, pk)
    except SabahBeslenmeHata as exc:
        return _json_hata(exc)
    return JsonResponse({"ok": True, "siparis": siparis_json(siparis), "ozet": acik_borc_ozet(request.user)})


@login_required
def sabah_beslenme_api_satis_verisi(request):
    if not (satis_yapabilir(request.user) or menu_yonetebilir(request.user) or borc_kapatabilir(request.user)):
        return _json_hata("Yetki yok.", 403)
    tarih = _parse_date(request.GET.get("tarih"))
    menu = menu_al(tarih)
    siparisler = satis_satirlari(request.user, menu) if menu else []
    return JsonResponse(
        {
            "ok": True,
            "ozet": gun_ozeti(menu),
            "siparisler": [siparis_json(s) for s in siparisler],
            "menu": (
                {
                    "urun": menu.urun,
                    "birim_fiyat": f"{menu.birim_fiyat:.2f}",
                    "durum": menu.get_durum_display(),
                }
                if menu
                else None
            ),
        }
    )
