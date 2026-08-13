"""İletişim Merkezi — panel görünümleri."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from takip.iletisim_adapters import ktt_hazir_kuyruk, kaynak_paket_hazirla
from takip.iletisim_models import IletisimEki, IletisimOlay, IletisimPaketi
from takip.iletisim_service import (
    hazir_paketler,
    olay_gecmisi,
    olay_kaydet,
    paket_indir_yetkisi,
    paket_json,
    paket_mesaj_guncelle,
    paket_taslak_yap,
    paket_yetkisi_var,
    eki_public_indir_url,
    eki_pk_from_public_token,
    sablon_degiskenleri,
    taslak_paketler,
    yetkili_paketler,
)
from takip.permissions.decorators import require_permission


def _json_ok(data=None, **extra):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return JsonResponse(payload)


def _json_err(mesaj: str, status: int = 400):
    return JsonResponse({"ok": False, "mesaj": mesaj}, status=status)


@login_required
@require_permission("iletisim_merkezi", "view")
def iletisim_merkezi(request):
    q = (request.GET.get("q") or "").strip()
    hazir = list(hazir_paketler(request.user, limit=30))
    taslaklar = list(taslak_paketler(request.user, limit=20))
    gecmis = list(olay_gecmisi(request.user, limit=40))
    kuyruk = ktt_hazir_kuyruk(request.user, limit=12)

    if q:
        filtre = yetkili_paketler(request.user).filter(
            baslik__icontains=q
        ) | yetkili_paketler(request.user).filter(
            hedef_etiket__icontains=q
        ) | yetkili_paketler(request.user).filter(
            mesaj__icontains=q
        )
        hazir = list(filtre.filter(durum=IletisimPaketi.Durum.HAZIR)[:30])

    return render(
        request,
        "iletisim_merkezi.html",
        {
            "hazir_paketler": hazir,
            "taslak_paketler": taslaklar,
            "gecmis_olaylar": gecmis,
            "kuyruk": kuyruk,
            "arama": q,
            "sablon_yonetimi": request.user.is_superuser
            or __import__("takip.permissions.service", fromlist=["can"]).can(
                request.user, "iletisim_merkezi", "manage_templates"
            ),
        },
    )


@login_required
@require_permission("iletisim_merkezi", "share")
@require_GET
def iletisim_hazirla(request, modul: str, kaynak_id: int):
    try:
        paket = kaynak_paket_hazirla(request.user, modul, kaynak_id, request)
    except PermissionError as exc:
        messages.error(request, str(exc))
        return redirect("iletisim_merkezi")
    except ValueError as exc:
        messages.error(request, str(exc))
        if modul == "ktt":
            return redirect("ktt_detay", pk=kaynak_id)
        return redirect("iletisim_merkezi")
    return redirect("iletisim_paket_onizleme", pk=paket.pk)


@login_required
@require_permission("iletisim_merkezi", "view")
def iletisim_paket_onizleme(request, pk: int):
    paket = get_object_or_404(
        IletisimPaketi.objects.select_related("talebe", "sinif_sube", "sablon").prefetch_related(
            "ekler"
        ),
        pk=pk,
    )
    if not paket_yetkisi_var(request.user, paket):
        raise Http404
    first_ek = paket.ekler.first()
    pdf_public_url = eki_public_indir_url(request, first_ek) if first_ek else ""
    return render(
        request,
        "iletisim_paket_onizleme.html",
        {
            "paket": paket,
            "paket_json": json.dumps(paket_json(paket), ensure_ascii=False),
            "pdf_public_url": pdf_public_url,
            "paylas_yetkisi": __import__(
                "takip.permissions.service", fromlist=["can"]
            ).can(request.user, "iletisim_merkezi", "share"),
        },
    )


@login_required
@require_permission("iletisim_merkezi", "share")
@require_GET
def iletisim_share_bridge(request, pk: int):
    paket = get_object_or_404(
        IletisimPaketi.objects.prefetch_related("ekler"),
        pk=pk,
    )
    if not paket_yetkisi_var(request.user, paket):
        raise Http404
    eki = paket.ekler.first()
    if not eki:
        messages.error(request, "Paylaşılacak PDF eki yok.")
        return redirect("iletisim_paket_onizleme", pk=pk)
    return render(
        request,
        "iletisim_share_bridge.html",
        {
            "paket_id": paket.pk,
            "pdf_url": f"/iletisim/ek/{eki.pk}/indir/",
            "pdf_name": eki.dosya_adi,
        },
    )


@require_GET
def iletisim_ek_public_indir(request, token: str):
    try:
        eki_pk = eki_pk_from_public_token(token)
    except ValueError:
        raise Http404
    eki = get_object_or_404(IletisimEki.objects.select_related("paket"), pk=eki_pk)
    try:
        fh = eki.dosya.open("rb")
    except FileNotFoundError:
        raise Http404
    return FileResponse(fh, as_attachment=True, filename=eki.dosya_adi)


@login_required
@require_permission("iletisim_merkezi", "view")
@require_GET
def iletisim_ek_indir(request, pk: int):
    eki = get_object_or_404(IletisimEki.objects.select_related("paket"), pk=pk)
    if not paket_indir_yetkisi(request.user, eki.paket, eki):
        raise Http404
    olay_kaydet(eki.paket, IletisimOlay.OlayTur.FILE_DOWNLOADED, request.user, {"ek_id": eki.pk})
    try:
        fh = eki.dosya.open("rb")
    except FileNotFoundError:
        messages.error(request, "Dosya artık mevcut değil.")
        return redirect("iletisim_paket_onizleme", pk=eki.paket_id)
    return FileResponse(fh, as_attachment=True, filename=eki.dosya_adi)


@login_required
@require_permission("iletisim_merkezi", "share")
@require_POST
def iletisim_api_mesaj_guncelle(request, pk: int):
    paket = get_object_or_404(IletisimPaketi, pk=pk)
    try:
        paket_mesaj_guncelle(request.user, paket, request.POST.get("mesaj", ""))
    except (PermissionError, ValueError) as exc:
        return _json_err(str(exc))
    return _json_ok(paket=paket_json(paket))


@login_required
@require_permission("iletisim_merkezi", "share")
@require_POST
def iletisim_api_taslak(request, pk: int):
    paket = get_object_or_404(IletisimPaketi, pk=pk)
    try:
        paket_taslak_yap(request.user, paket)
    except PermissionError as exc:
        return _json_err(str(exc))
    return _json_ok(mesaj="Taslak kaydedildi.")


@login_required
@require_permission("iletisim_merkezi", "share")
@require_POST
def iletisim_api_olay(request, pk: int):
    paket = get_object_or_404(IletisimPaketi, pk=pk)
    if not paket_yetkisi_var(request.user, paket):
        return _json_err("Yetkisiz", 403)
    olay_tur = (request.POST.get("olay_tur") or "").strip()
    gecerli = {c.value for c in IletisimOlay.OlayTur}
    if olay_tur not in gecerli:
        return _json_err("Geçersiz olay türü.")
    olay_kaydet(paket, olay_tur, request.user)
    if olay_tur in {
        IletisimOlay.OlayTur.WHATSAPP_SHARE_OPENED,
        IletisimOlay.OlayTur.NATIVE_SHARE_OPENED,
    }:
        paket.durum = IletisimPaketi.Durum.PAYLASIM_BASLATILDI
        paket.save(update_fields=["durum", "guncellenme"])
    return _json_ok()


@login_required
@require_permission("iletisim_merkezi", "view")
@require_GET
def iletisim_api_paket(request, pk: int):
    paket = get_object_or_404(
        IletisimPaketi.objects.prefetch_related("ekler"), pk=pk
    )
    if not paket_yetkisi_var(request.user, paket):
        return _json_err("Yetkisiz", 403)
    return _json_ok(paket=paket_json(paket))


@login_required
@require_permission("iletisim_merkezi", "view")
def iletisim_yeni_mesaj(request):
    return render(
        request,
        "iletisim_yeni_mesaj.html",
        {
            "degiskenler": sablon_degiskenleri("manuel"),
        },
    )
