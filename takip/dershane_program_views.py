"""Dershane programı panel görünümleri."""

from __future__ import annotations

import json
from datetime import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from takip.dershane_program_models import DershaneProgramSablon, DershaneProgramSurum
from takip.dershane_program_service import (
    GUN_ADLARI,
    aktif_program,
    atama_kaydet,
    atama_surukle,
    dershane_program_duzenleyebilir,
    excel_yanit,
    gun_kopyala,
    panel_baglami,
    sablon_kaydet,
    sablon_yukle,
    saat_bloku_kaydet,
    saat_bloku_sil,
    saat_bloku_sirala,
    surum_geri_yukle,
    surum_olustur,
    varsayilan_program_olustur,
)
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.permissions.decorators import require_permission


def _program_al(user, request):
    program_id = request.GET.get("program") or request.POST.get("program")
    program = aktif_program(
        user,
        int(program_id) if program_id else None,
    )
    if not program:
        program = varsayilan_program_olustur(user)
    return program


def _gun_al(request) -> int:
    try:
        return max(0, min(6, int(request.GET.get("gun") or request.POST.get("gun") or 5)))
    except (TypeError, ValueError):
        return 5


def _filtre_al(request) -> dict[str, str]:
    return {
        key: value
        for key in ("sinif", "etut_grubu", "ders", "ogretmen", "atanmamis", "cakisma")
        if (value := (request.GET.get(key) or "").strip())
    }


def _redirect_panel(program, gun: int) -> redirect:
    url = f"{reverse('dershane_program_panel')}?program={program.pk}&gun={gun}"
    return redirect(url)


@login_required
@require_permission("dershane_programi", "view")
def dershane_program_panel(request):
    program = _program_al(request.user, request)
    gun = _gun_al(request)

    if request.method == "POST" and dershane_program_duzenleyebilir(request.user):
        action = request.POST.get("action", "")

        if action == "saat_ekle":
            try:
                saat_bloku_kaydet(
                    program,
                    gun=gun,
                    baslangic=time.fromisoformat(request.POST["baslangic"]),
                    bitis=time.fromisoformat(request.POST["bitis"]),
                    tur=request.POST.get("tur", "ders"),
                    aciklama=request.POST.get("aciklama", "").strip(),
                    blok_id=int(request.POST["blok_id"])
                    if request.POST.get("blok_id")
                    else None,
                )
                messages.success(request, "Saat bloğu kaydedildi.")
            except Exception as exc:
                messages.error(request, f"Saat bloğu kaydedilemedi: {exc}")

        elif action == "saat_sil":
            saat_bloku_sil(program, int(request.POST["blok_id"]))
            messages.success(request, "Saat bloğu silindi.")

        elif action == "saat_sirala":
            sira_listesi = [
                int(value)
                for value in request.POST.get("sira", "").split(",")
                if value.strip().isdigit()
            ]
            if sira_listesi:
                saat_bloku_sirala(program, gun, sira_listesi)
                messages.success(request, "Saat blokları sıralandı.")

        elif action == "atama_kaydet":
            _, hata = atama_kaydet(
                program,
                saat_bloku_id=int(request.POST["saat_bloku_id"]),
                etut_grubu_id=int(request.POST["etut_grubu_id"]),
                ders_id=int(request.POST["ders_id"]) if request.POST.get("ders_id") else None,
                ders_adi=request.POST.get("ders_adi", "").strip(),
                ogretmen_id=int(request.POST["ogretmen_id"])
                if request.POST.get("ogretmen_id")
                else None,
                ogretmen_adi=request.POST.get("ogretmen_adi", "").strip(),
            )
            if hata:
                messages.error(request, hata)
            else:
                messages.success(request, "Ders ataması kaydedildi.")

        elif action == "program_kaydet":
            surum_olustur(program, request.user)
            messages.success(request, "Program kaydedildi ve yeni sürüm oluşturuldu.")

        elif action == "sablon_kaydet":
            sablon_kaydet(
                program,
                request.user,
                ad=request.POST.get("sablon_ad", "").strip()
                or f"{program.ad} Şablonu",
                aciklama=request.POST.get("sablon_aciklama", "").strip(),
            )
            messages.success(request, "Şablon kaydedildi.")

        elif action == "sablon_yukle":
            sablon = get_object_or_404(
                DershaneProgramSablon,
                pk=int(request.POST["sablon_id"]),
            )
            sablon_yukle(program, sablon)
            messages.success(request, f"Şablon yüklendi: {sablon.ad}")

        elif action == "surum_yukle":
            surum = get_object_or_404(
                DershaneProgramSurum,
                pk=int(request.POST["surum_id"]),
                program=program,
            )
            surum_geri_yukle(program, surum)
            messages.success(request, f"Sürüm geri yüklendi: {surum.etiket}")

        elif action == "gun_kopyala":
            gun_kopyala(
                program,
                kaynak_gun=int(request.POST["kaynak_gun"]),
                hedef_gun=int(request.POST["hedef_gun"]),
                saat_bloklari=request.POST.get("kopya_saat") == "1",
                dersler=request.POST.get("kopya_ders") == "1",
                ogretmenler=request.POST.get("kopya_ogretmen") == "1",
            )
            messages.success(request, "Gün programı kopyalandı.")
            gun = int(request.POST["hedef_gun"])

        return _redirect_panel(program, gun)

    context = panel_baglami(
        request.user,
        program=program,
        gun=gun,
        filtre=_filtre_al(request),
    )
    return render(request, "dershane_program_panel.html", context)


@login_required
@require_permission("dershane_programi", "edit")
@require_POST
def dershane_program_atama_surukle(request):
    if not dershane_program_duzenleyebilir(request.user):
        return JsonResponse({"error": "Yetkiniz yok."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Geçersiz istek."}, status=400)

    program = _program_al(request.user, request)
    try:
        saat_bloku_id = int(payload.get("saat_bloku_id"))
        ders_id = int(payload.get("ders_id"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Eksik parametre."}, status=400)

    grup_ids = payload.get("grup_ids") or []
    if grup_ids and not isinstance(grup_ids, list):
        grup_ids = []

    sonuclar = atama_surukle(
        program,
        saat_bloku_id=saat_bloku_id,
        ders_id=ders_id,
        grup_ids=[int(g) for g in grup_ids if str(g).isdigit()],
        sinif_seviye=str(payload.get("sinif_seviye") or "").strip() or None,
        tum_gruplar=bool(payload.get("tum_gruplar")),
    )
    return JsonResponse({"sonuclar": sonuclar})


@login_required
@require_permission("dershane_programi", "view")
def dershane_program_goruntule(request, mod):
    from takip.dershane_program_service import gorunum_baglami

    program = _program_al(request.user, request)
    gun = _gun_al(request)
    context = gorunum_baglami(
        request.user,
        program=program,
        gun=gun,
        mod=mod,
        filtre=_filtre_al(request),
    )
    return render(request, "dershane_program_goruntule.html", context)


@login_required
@require_GET
@require_permission("dershane_programi", "view")
def dershane_program_pdf(request):
    from takip.dershane_program_service import gorunum_baglami, tum_haftalik_pdf_baglami

    program = _program_al(request.user, request)
    gun_param = (request.GET.get("gun") or "").strip().lower()
    tum = request.GET.get("tum") == "1" or gun_param in {"all", "hepsi", "tum"}

    if pdf_engine_status() == "none":
        return pdf_error_response(
            f"PDF motoru bulunamadı. (Motor: {pdf_engine_status()})"
        )

    if tum:
        context = tum_haftalik_pdf_baglami(request.user, program=program)
        dosya = f"dershane_{program.pk}_haftalik_tum.pdf"
    else:
        gun = _gun_al(request)
        mod = (request.GET.get("mod") or "genel").strip().lower()
        if mod not in {"genel", "sinif", "etut", "ogretmen"}:
            mod = "genel"
        filtre = _filtre_al(request)
        context = gorunum_baglami(
            request.user,
            program=program,
            gun=gun,
            mod=mod,
            filtre=filtre,
        )
        parcalar = [f"dershane_{program.pk}", mod, f"gun{gun}"]
        if filtre.get("etut_grubu"):
            parcalar.append(f"etut{filtre['etut_grubu']}")
        elif filtre.get("sinif"):
            parcalar.append(f"sinif{filtre['sinif']}")
        dosya = "_".join(parcalar) + ".pdf"

    html = render_to_string(
        "dershane_program_pdf.html",
        context,
        request=request,
    )
    pdf = html_to_pdf(html, base_url="/")
    if not pdf:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})"
        )
    return make_pdf_response(pdf, dosya)


@login_required
@require_GET
@require_permission("dershane_programi", "view")
def dershane_program_excel(request):
    program = _program_al(request.user, request)
    gun_param = (request.GET.get("gun") or "").strip().lower()
    tum = request.GET.get("tum") == "1" or gun_param in {"all", "hepsi", "tum"}

    if tum:
        gun = None
        filtre: dict[str, str] = {}
        mod = "genel"
    elif gun_param.isdigit():
        gun = max(0, min(6, int(gun_param)))
        mod = (request.GET.get("mod") or "genel").strip().lower()
        filtre = _filtre_al(request)
        if mod == "etut" and not filtre.get("etut_grubu"):
            ilk = program.etut_gruplari.order_by("sira", "id").first()
            if ilk:
                filtre["etut_grubu"] = str(ilk.pk)
        if mod == "sinif" and not filtre.get("sinif"):
            seviye = (
                program.etut_gruplari.exclude(sinif_seviye="")
                .order_by("sinif_seviye")
                .values_list("sinif_seviye", flat=True)
                .first()
            )
            if seviye:
                filtre["sinif"] = str(seviye)
    elif (
        "gun" not in request.GET
        and (request.GET.get("mod") or "genel") == "genel"
        and not _filtre_al(request)
    ):
        gun = None
        filtre = {}
        mod = "genel"
    else:
        gun = _gun_al(request)
        mod = (request.GET.get("mod") or "genel").strip().lower()
        filtre = _filtre_al(request)

    dosya, icerik = excel_yanit(program, gun, filtre=filtre, mod=mod)
    response = HttpResponse(
        icerik,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = f'attachment; filename="{dosya}"'
    return response


@login_required
@require_GET
@require_permission("dershane_programi", "view")
def dershane_program_paylas(request):
    program = _program_al(request.user, request)
    url = request.build_absolute_uri(
        f"{reverse('dershane_program_goruntule', kwargs={'mod': 'genel'})}?program={program.pk}"
    )
    return JsonResponse({"url": url, "gunler": list(GUN_ADLARI)})
