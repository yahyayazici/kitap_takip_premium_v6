"""Haftalık etüt planı — premium builder ve admin saat yönetimi."""

from __future__ import annotations

import json
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from takip.etut_plan_service import (
    DURUM_IKONLARI,
    admin_yonetim_baglami,
    builder_baglami,
    cakisma_kontrol,
    faaliyet_ata,
    faaliyet_durum_guncelle,
    faaliyet_sil,
    faaliyetler_gun_gruplu,
    gecen_haftayi_kopyala,
    gunu_tum_haftaya_kopyala,
    kurum_saat_islem_sonrasi,
    kurum_saat_kaynak_hoca,
    kurum_saatlerini_tum_gruplara_yay,
    mevcut_hafta_plani,
    ozel_havuz_karti_olustur,
    plan_duzenleyebilir,
    plan_olustur,
    plan_olusturabilir,
    plan_ozet,
    sablon_grup_uygula,
    saat_bloklari_otomatik_olustur,
    saat_bloklari_sirala,
    saat_bloku_kaydet,
    saat_bloku_sil,
    saat_satir_ekle,
    saat_yonetebilir,
    yetkili_etut_planlari,
)
from takip.models import (
    EtutGrupSaatBloku,
    EtutHaftaPlani,
    EtutHocasi,
    EtutPlanFaaliyet,
)
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.permissions.decorators import require_permission
from takip.permissions.scope import tum_talebe_kapsami_var
from takip.user_helpers import etut_hocasi_for_user


def _secili_hoca(request) -> EtutHocasi | None:
    hoca_id = request.GET.get("hoca") or request.POST.get("etut_hocasi_id")
    if hoca_id and tum_talebe_kapsami_var(request.user):
        return EtutHocasi.objects.filter(pk=hoca_id, aktif=True).first()
    return etut_hocasi_for_user(request.user)


def _json_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return {}
    return {}


def _plan_al(request, hoca: EtutHocasi) -> EtutHaftaPlani | None:
    plan_id = request.GET.get("plan") or request.POST.get("plan_id")
    if plan_id:
        return yetkili_etut_planlari(request.user).filter(pk=plan_id).first()
    return mevcut_hafta_plani(request.user, hoca)


@login_required
@require_permission("etut_plani", "view")
def etut_plan_panel(request):
    hoca = _secili_hoca(request)
    if not hoca:
        messages.info(request, "Etüt hocası profili bulunamadı.")
        if saat_yonetebilir(request.user):
            return redirect("etut_plan_yonetim")
        return render(request, "etut_plan_panel.html", {"hoca": None})

    plan = _plan_al(request, hoca)
    if not plan and plan_olusturabilir(request.user, hoca):
        plan = plan_olustur(request.user, hoca)

    context = builder_baglami(request.user, hoca=hoca, plan=plan)
    hocalar = []
    if tum_talebe_kapsami_var(request.user):
        hocalar = list(EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad"))
    context["hocalar"] = hocalar
    context["cakismalar"] = cakisma_kontrol(hoca)
    context["durum_ikonlari"] = DURUM_IKONLARI
    context["durum_secenekleri"] = EtutPlanFaaliyet.UygulamaDurumu.choices

    return render(request, "etut_plan_builder.html", context)


@login_required
@require_permission("etut_plani", "view")
def etut_plan_detay(request, pk):
    plan = get_object_or_404(yetkili_etut_planlari(request.user), pk=pk)
    return redirect(f"/etut-plani/?hoca={plan.etut_hocasi_id}")


@login_required
@require_permission("etut_plani", "create")
def etut_plan_olustur(request):
    hoca = _secili_hoca(request)
    if not hoca:
        messages.error(request, "Etüt hocası bulunamadı.")
        return redirect("etut_plan_panel")
    if not plan_olusturabilir(request.user, hoca):
        messages.error(request, "Plan oluşturma yetkiniz yok.")
        return redirect("etut_plan_panel")
    plan_olustur(request.user, hoca)
    messages.success(request, "Haftalık etüt planı hazır.")
    return redirect(f"/etut-plani/?hoca={hoca.pk}")


@login_required
@require_permission("etut_plani", "view")
def etut_plan_arsiv(request):
    planlar = (
        yetkili_etut_planlari(request.user)
        .filter(durum=EtutHaftaPlani.Durum.TAMAMLANDI)
        .order_by("-hafta_baslangic")[:52]
    )
    return render(request, "etut_plan_arsiv.html", {"planlar": planlar})


@login_required
@require_permission("etut_plani", "edit")
def etut_plan_yonetim(request):
    if not saat_yonetebilir(request.user):
        messages.error(request, "Saat yönetimi yalnızca admin içindir.")
        return redirect("etut_plan_panel")

    hoca = kurum_saat_kaynak_hoca()
    if request.method == "POST":
        aksiyon = request.POST.get("aksiyon")
        hoca = kurum_saat_kaynak_hoca()
        if not hoca:
            messages.error(request, "Aktif etüt hocası bulunamadı.")
            return redirect("etut_plan_yonetim")

        def _senkron_mesaj(ek: str = "") -> None:
            grup = kurum_saat_islem_sonrasi(hoca)
            if grup:
                messages.info(
                    request,
                    f"Kurum saatleri {grup} etüt grubuna otomatik yansıtıldı.",
                )
            if ek:
                messages.success(request, ek)

        if aksiyon == "otomatik_olustur":
            adet = saat_bloklari_otomatik_olustur(
                hoca,
                temizle=bool(request.POST.get("temizle")),
            )
            _senkron_mesaj(f"{adet} saat bloğu oluşturuldu.")
        elif aksiyon == "tum_haftaya_uygula":
            adet = gunu_tum_haftaya_kopyala(
                hoca,
                kaynak_gun=int(request.POST.get("kaynak_gun", 0)),
            )
            _senkron_mesaj(f"Pazartesi şablonu {adet} hücreye kopyalandı.")
        elif aksiyon == "sablon_uygula":
            tip = request.POST.get("sablon_tip", "hafta_ici")
            adet = sablon_grup_uygula(hoca, tip)
            _senkron_mesaj(f"Şablon uygulandı ({adet} yeni blok).")
        elif aksiyon == "tum_gruplara_yay":
            grup = kurum_saatlerini_tum_gruplara_yay(hoca)
            messages.success(
                request,
                f"Kurum saatleri {grup} gruba senkronize edildi.",
            )
        elif aksiyon == "saat_satir_ekle":
            try:
                bas = datetime.strptime(request.POST.get("baslangic", ""), "%H:%M").time()
                bit = datetime.strptime(request.POST.get("bitis", ""), "%H:%M").time()
                adet = saat_satir_ekle(hoca, baslangic=bas, bitis=bit)
                _senkron_mesaj(f"{adet} yeni saat hücresi eklendi.")
            except (ValueError, TypeError):
                messages.error(request, "Geçersiz saat bilgisi.")
        elif aksiyon == "saat_kaydet":
            try:
                bas = datetime.strptime(request.POST.get("baslangic", ""), "%H:%M").time()
                bit = datetime.strptime(request.POST.get("bitis", ""), "%H:%M").time()
                blok_id = request.POST.get("blok_id") or None
                if blok_id:
                    blok_id = int(blok_id)
                saat_bloku_kaydet(
                    hoca,
                    blok_id=blok_id,
                    gun=int(request.POST.get("gun", 0)),
                    baslangic=bas,
                    bitis=bit,
                )
                _senkron_mesaj("Saat bloğu kaydedildi.")
            except (ValueError, TypeError):
                messages.error(request, "Geçersiz saat bilgisi.")
        elif aksiyon == "saat_sil":
            saat_bloku_sil(hoca, int(request.POST.get("blok_id")))
            _senkron_mesaj("Saat bloğu silindi.")
        elif aksiyon == "havuz_kaydet":
            from takip.models import EtutFaaliyetHavuzu

            kart_id = request.POST.get("kart_id")
            if kart_id:
                kart = get_object_or_404(EtutFaaliyetHavuzu, pk=kart_id, ozel=False)
            else:
                kart = EtutFaaliyetHavuzu(ozel=False)
            kart.baslik = request.POST.get("baslik", "").strip()
            kart.aciklama = request.POST.get("aciklama", "").strip()
            kart.varsayilan_hedef = request.POST.get("hedef", "").strip()
            kart.renk = request.POST.get("renk", "#eff6ff")
            kart.aktif = request.POST.get("aktif") == "1"
            kart.save()
            messages.success(request, "Havuz kartı kaydedildi.")

        return redirect("/etut-plani/yonetim/")

    context = admin_yonetim_baglami(request.user)
    context["cakismalar"] = cakisma_kontrol(hoca) if hoca else []
    context["aktif_sekme"] = request.GET.get("sekme", "sablon")
    return render(request, "etut_plan_admin.html", context)


@login_required
@require_POST
@require_permission("etut_plani", "edit")
def etut_plan_faaliyet_ata(request):
    payload = _json_body(request)
    hoca = _secili_hoca(request) or get_object_or_404(
        EtutHocasi, pk=payload.get("hoca_id"), aktif=True
    )
    plan = _plan_al(request, hoca) or plan_olustur(request.user, hoca)
    if not plan_duzenleyebilir(request.user, plan):
        return JsonResponse({"ok": False, "hata": "Yetki yok."}, status=403)

    try:
        faaliyet = faaliyet_ata(
            plan,
            saat_bloku_id=int(payload["saat_bloku_id"]),
            havuz_id=int(payload["havuz_id"]) if payload.get("havuz_id") else None,
            baslik=str(payload.get("baslik") or ""),
            aciklama=str(payload.get("aciklama") or ""),
            hedef=str(payload.get("hedef") or ""),
            renk=str(payload.get("renk") or ""),
        )
    except (KeyError, ValueError, EtutGrupSaatBloku.DoesNotExist) as exc:
        return JsonResponse({"ok": False, "hata": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "faaliyet": {
                "id": faaliyet.pk,
                "baslik": faaliyet.baslik,
                "hedef": faaliyet.hedef,
                "renk": faaliyet.renk,
                "durum": faaliyet.uygulama_durumu,
            },
        }
    )


@login_required
@require_POST
@require_permission("etut_plani", "edit")
def etut_plan_faaliyet_sil(request):
    payload = _json_body(request)
    plan = get_object_or_404(yetkili_etut_planlari(request.user), pk=payload.get("plan_id"))
    if not plan_duzenleyebilir(request.user, plan):
        return JsonResponse({"ok": False, "hata": "Yetki yok."}, status=403)
    faaliyet_sil(plan, int(payload.get("faaliyet_id")))
    return JsonResponse({"ok": True})


@login_required
@require_POST
@require_permission("etut_plani", "edit")
def etut_plan_durum_guncelle(request):
    payload = _json_body(request)
    plan = get_object_or_404(yetkili_etut_planlari(request.user), pk=payload.get("plan_id"))
    if not plan_duzenleyebilir(request.user, plan):
        return JsonResponse({"ok": False, "hata": "Yetki yok."}, status=403)
    faaliyet = faaliyet_durum_guncelle(
        plan,
        int(payload.get("faaliyet_id")),
        str(payload.get("durum")),
        notu=str(payload.get("notu") or ""),
    )
    if not faaliyet:
        return JsonResponse({"ok": False, "hata": "Geçersiz durum."}, status=400)
    return JsonResponse({"ok": True, "durum": faaliyet.uygulama_durumu})


@login_required
@require_POST
@require_permission("etut_plani", "edit")
def etut_plan_havuz_ekle(request):
    payload = _json_body(request)
    hoca = _secili_hoca(request) or get_object_or_404(
        EtutHocasi, pk=payload.get("hoca_id"), aktif=True
    )
    baslik = str(payload.get("baslik") or "").strip()
    if not baslik:
        return JsonResponse({"ok": False, "hata": "Başlık gerekli."}, status=400)
    kart = ozel_havuz_karti_olustur(
        request.user,
        hoca,
        baslik=baslik,
        aciklama=str(payload.get("aciklama") or ""),
        hedef=str(payload.get("hedef") or ""),
        renk=str(payload.get("renk") or "#eff6ff"),
    )
    return JsonResponse(
        {
            "ok": True,
            "kart": {
                "id": kart.pk,
                "baslik": kart.baslik,
                "hedef": kart.varsayilan_hedef,
                "renk": kart.renk,
            },
        }
    )


@login_required
@require_POST
@require_permission("etut_plani", "edit")
def etut_plan_kopyala(request):
    payload = _json_body(request)
    plan = get_object_or_404(yetkili_etut_planlari(request.user), pk=payload.get("plan_id"))
    if not plan_duzenleyebilir(request.user, plan):
        return JsonResponse({"ok": False, "hata": "Yetki yok."}, status=403)
    adet = gecen_haftayi_kopyala(plan)
    return JsonResponse({"ok": True, "kopya": adet})


@login_required
@require_POST
@require_permission("etut_plani", "edit")
def etut_plan_saat_sirala(request):
    if not saat_yonetebilir(request.user):
        return JsonResponse({"ok": False, "hata": "Yetki yok."}, status=403)
    payload = _json_body(request)
    hoca = get_object_or_404(EtutHocasi, pk=payload.get("hoca_id"), aktif=True)
    saat_bloklari_sirala(
        hoca,
        int(payload.get("gun", 0)),
        [int(x) for x in payload.get("blok_ids") or []],
    )
    return JsonResponse({"ok": True})


@login_required
@require_GET
@require_permission("etut_plani", "export_pdf")
def etut_plan_pdf(request):
    hoca = _secili_hoca(request)
    if not hoca:
        messages.error(request, "Etüt hocası bulunamadı.")
        return redirect("etut_plan_panel")
    plan = _plan_al(request, hoca) or mevcut_hafta_plani(request.user, hoca)
    if not plan:
        messages.error(request, "Plan bulunamadı.")
        return redirect("etut_plan_panel")
    if pdf_engine_status() != "ok":
        return pdf_error_response(request)

    context = builder_baglami(request.user, hoca=hoca, plan=plan)
    context["gun_gruplari"] = faaliyetler_gun_gruplu(plan)
    html = render_to_string("etut_plan_pdf.html", context, request=request)
    pdf = html_to_pdf(html)
    dosya = f"etut_plani_{hoca.ad_soyad.replace(' ', '_')}_{plan.hafta_baslangic:%Y%m%d}.pdf"
    return make_pdf_response(pdf, dosya)
