"""Ziyaret Araç Planlama — görünümler."""

from __future__ import annotations

import io
import re
import zipfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from takip.pdf_utils import html_to_pdf, make_pdf_response
from config.branding import panel_branding_context
from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.user_helpers import etut_mesul_for_user
from takip.ziyaret_arac_models import (
    ZiyaretAraci,
    ZiyaretPlani,
    ZiyaretPlaniTalebe,
    ZiyaretProgramAdimi,
)
from takip.ziyaret_arac_service import (
    arac_kart_verisi,
    genel_pdf_grid_meta,
    atanmamis_talebeler,
    etut_arac_duzenleyebilir,
    etut_arac_ekleyebilir,
    etut_hocalari_listesi,
    geri_al,
    geri_al_kaydet,
    kapasite_olustu_mesaji,
    kapasite_ozeti,
    otomatik_dagit,
    personel_surucu_adaylari,
    plan_kontrol,
    plan_queryset_yonetim,
    plan_yonetimi_var,
    planlama_ozeti,
    sinif_sube_listesi,
    talebe_ata,
    talebe_cikar,
    talebe_listeden_cikar,
    talebe_listesine_ekle,
    talebe_sabitle,
    toplu_talebe_adaylari,
    etut_hocasi_ata,
    etut_hocasi_cikar,
)


def _plan_or_404(pk: int) -> ZiyaretPlani:
    return get_object_or_404(plan_queryset_yonetim(), pk=pk)


def _arac_pdf_dosya_adi(sira: int, surucu_ad: str, tarih) -> str:
    slug = re.sub(r"[^\w\-]+", "_", surucu_ad.lower().replace(" ", "_"))[:40].strip("_")
    slug = slug or "arac"
    return f"{sira:02d}_{slug}_{tarih:%d_%m_%Y}.pdf"


def _json_ok(extra: dict | None = None) -> JsonResponse:
    data = {"ok": True}
    if extra:
        data.update(extra)
    return JsonResponse(data)


def _json_err(mesaj: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "mesaj": mesaj}, status=status)


def _plan_ozet_json(plan: ZiyaretPlani) -> dict:
    ozet = planlama_ozeti(plan)
    return {
        "talebe_sayisi": ozet.talebe_sayisi,
        "atanan": ozet.atanan,
        "atanmamis": ozet.atanmamis,
        "arac_sayisi": ozet.arac_sayisi,
        "toplam_kapasite": ozet.toplam_kapasite,
        "kapasite_olustu_mesaj": kapasite_olustu_mesaji(ozet.kapasite),
        "kapasite_mesaj": ozet.kapasite.mesaj,
        "kapasite_yeterli": ozet.kapasite.yeterli,
    }


@login_required
@require_permission("ziyaret_arac", "view")
def ziyaret_arac_listesi(request):
    if plan_yonetimi_var(request.user):
        planlar = ZiyaretPlani.objects.order_by("-tarih", "-id")
        return render(
            request,
            "ziyaret_arac_listesi.html",
            {"planlar": planlar, "yonetim": True},
        )

    hoca = etut_mesul_for_user(request.user)
    if not hoca:
        messages.error(request, "Bu modüle erişim yetkiniz yok.")
        return redirect("dashboard")

    planlar = ZiyaretPlani.objects.exclude(
        durum=ZiyaretPlani.Durum.ARSIV
    ).order_by("-tarih", "-id")
    return render(
        request,
        "ziyaret_arac_listesi.html",
        {
            "planlar": planlar,
            "yonetim": False,
            "hoca": hoca,
        },
    )


@login_required
@require_permission("ziyaret_arac", "create")
def ziyaret_arac_olustur(request):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "Plan oluşturma yetkiniz yok.")
        return redirect("ziyaret_arac_listesi")

    if request.method == "POST":
        ad = (request.POST.get("ad") or "").strip()
        tarih = request.POST.get("tarih")
        aciklama = (request.POST.get("aciklama") or "").strip()
        if not ad or not tarih:
            messages.error(request, "Plan adı ve tarih zorunludur.")
        else:
            plan = ZiyaretPlani.objects.create(
                ad=ad,
                tarih=tarih,
                aciklama=aciklama,
                durum=ZiyaretPlani.Durum.ARAC_TOPLANIYOR,
                olusturan=request.user,
            )
            messages.success(request, "Ziyaret planı oluşturuldu.")
            return redirect("ziyaret_arac_duzenle", pk=plan.pk)

    return render(request, "ziyaret_arac_form.html", {"plan": None})


@login_required
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_duzenle(request, pk):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "Plan düzenleme yetkiniz yok.")
        return redirect("ziyaret_arac_listesi")

    plan = _plan_or_404(pk)
    if request.method == "POST":
        plan.ad = (request.POST.get("ad") or plan.ad).strip()
        plan.tarih = request.POST.get("tarih") or plan.tarih
        plan.aciklama = (request.POST.get("aciklama") or "").strip()
        plan.durum = request.POST.get("durum") or plan.durum
        plan.save()

        if request.POST.get("program_kaydet") == "1":
            ZiyaretProgramAdimi.objects.filter(plan=plan).delete()
            saatler = request.POST.getlist("program_saat")
            aciklamalar = request.POST.getlist("program_aciklama")
            for sira, (saat, aciklama) in enumerate(zip(saatler, aciklamalar, strict=False)):
                if saat and aciklama.strip():
                    ZiyaretProgramAdimi.objects.create(
                        plan=plan,
                        saat=saat,
                        aciklama=aciklama.strip(),
                        sira=sira,
                    )

        messages.success(request, "Plan güncellendi.")
        return redirect("ziyaret_arac_duzenle", pk=plan.pk)

    program = list(plan.program_adimlari.all())
    return render(
        request,
        "ziyaret_arac_form.html",
        {"plan": plan, "program": program},
    )


@login_required
@require_permission("ziyaret_arac", "view")
def ziyaret_arac_detay(request, pk):
    plan = _plan_or_404(pk)
    if plan_yonetimi_var(request.user):
        return redirect("ziyaret_arac_planlama", pk=plan.pk)
    return redirect("ziyaret_arac_etut", pk=plan.pk)


@login_required
@require_permission("ziyaret_arac", "view")
def ziyaret_arac_etut(request, pk):
    plan = _plan_or_404(pk)
    hoca = etut_mesul_for_user(request.user)
    if not hoca and not plan_yonetimi_var(request.user):
        messages.error(request, "Etüt hocası profili bulunamadı.")
        return redirect("dashboard")

    if request.method == "POST" and can(request.user, "ziyaret_arac", "create"):
        if not etut_arac_ekleyebilir(plan):
            messages.error(request, "Bu planda araç eklenemez.")
        else:
            surucu_ad = (request.POST.get("surucu_ad") or "").strip()
            kapasite = request.POST.get("kapasite")
            notlar = (request.POST.get("notlar") or "").strip()
            personel_id = request.POST.get("surucu_personel") or None
            if not surucu_ad or not kapasite:
                messages.error(request, "Araç sahibi ve kapasite zorunludur.")
            else:
                ZiyaretAraci.objects.create(
                    plan=plan,
                    surucu_ad=surucu_ad,
                    surucu_personel_id=personel_id or None,
                    kapasite=int(kapasite),
                    ekleyen=hoca,
                    notlar=notlar,
                )
                if plan.durum == ZiyaretPlani.Durum.TASLAK:
                    plan.durum = ZiyaretPlani.Durum.ARAC_TOPLANIYOR
                    plan.save(update_fields=["durum", "guncellenme"])
                oz = kapasite_ozeti(plan)
                messages.success(
                    request,
                    f"Araç eklendi. {kapasite_olustu_mesaji(oz)}",
                )

    araclar = plan.araclar.all()
    if hoca and not plan_yonetimi_var(request.user):
        araclar = araclar.filter(ekleyen=hoca)

    kapasite = kapasite_ozeti(plan)
    return render(
        request,
        "ziyaret_arac_etut.html",
        {
            "plan": plan,
            "araclar": araclar,
            "hoca": hoca,
            "kapasite": kapasite,
            "kapasite_olustu": kapasite_olustu_mesaji(kapasite),
            "arac_ekleyebilir": etut_arac_ekleyebilir(plan),
            "arac_ekle_yetkisi": can(request.user, "ziyaret_arac", "create"),
            "duzenleyebilir": etut_arac_duzenleyebilir(plan),
            "personel_adaylari": personel_surucu_adaylari(),
        },
    )


@login_required
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_planlama(request, pk):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "Planlama ekranına erişim yetkiniz yok.")
        return redirect("ziyaret_arac_listesi")

    plan = _plan_or_404(pk)
    if plan.durum == ZiyaretPlani.Durum.TASLAK:
        plan.durum = ZiyaretPlani.Durum.DAGITIM
        plan.save(update_fields=["durum", "guncellenme"])

    return render(
        request,
        "ziyaret_arac_planlama.html",
        {
            "plan": plan,
            "ozet": planlama_ozeti(plan),
            "atanmamis": atanmamis_talebeler(plan),
            "arac_kartlari": arac_kart_verisi(plan),
            "etut_hocalari": etut_hocalari_listesi(),
            "sinif_subeler": sinif_sube_listesi(),
            "kontrol": plan_kontrol(plan),
            "kapasite_olustu": kapasite_olustu_mesaji(planlama_ozeti(plan).kapasite),
            "arac_sil_yetkisi": can(request.user, "ziyaret_arac", "edit"),
        },
    )


@login_required
@require_permission("ziyaret_arac", "view")
def ziyaret_arac_onizleme(request, pk):
    plan = _plan_or_404(pk)
    if not plan_yonetimi_var(request.user):
        messages.error(request, "Önizleme yetkiniz yok.")
        return redirect("ziyaret_arac_etut", pk=plan.pk)

    ozet = planlama_ozeti(plan)
    return render(
        request,
        "ziyaret_arac_onizleme.html",
        {
            "plan": plan,
            "arac_kartlari": arac_kart_verisi(plan),
            "ozet": ozet,
            "kontrol": plan_kontrol(plan),
            "kapasite_olustu": kapasite_olustu_mesaji(ozet.kapasite),
        },
    )


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_api_ata(request, pk):
    if not plan_yonetimi_var(request.user):
        return _json_err("Yetkisiz", 403)

    plan = _plan_or_404(pk)
    tur = request.POST.get("tur")
    arac_id = request.POST.get("arac_id")
    if not arac_id:
        return _json_err("Araç seçilmedi.")

    geri_al_kaydet(plan.pk, request.session)

    if tur == "talebe":
        talebe_id = request.POST.get("talebe_id")
        if not talebe_id:
            return _json_err("Talebe seçilmedi.")
        override = request.POST.get("override") == "1"
        ok, mesaj = talebe_ata(plan, int(talebe_id), int(arac_id), override=override)
        if not ok:
            return _json_err(mesaj)
        response_mesaj = "Talebe atandı."
    elif tur == "etut_hocasi":
        etut_id = request.POST.get("etut_hocasi_id")
        if not etut_id:
            return _json_err("Etüt hocası seçilmedi.")
        ok, response_mesaj = etut_hocasi_ata(plan, int(etut_id), int(arac_id))
        if not ok:
            return _json_err(response_mesaj)
    else:
        return _json_err("Geçersiz tür.")

    plan = _plan_or_404(pk)
    return _json_ok(
        {
            "mesaj": response_mesaj,
            "ozet": _plan_ozet_json(plan),
            "arac_kartlari": _arac_kartlari_json(plan),
            "atanmamis": _atanmamis_json(plan),
        }
    )


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_api_cikar(request, pk):
    if not plan_yonetimi_var(request.user):
        return _json_err("Yetkisiz", 403)

    plan = _plan_or_404(pk)
    geri_al_kaydet(plan.pk, request.session)
    tur = request.POST.get("tur")

    if tur == "talebe":
        talebe_id = request.POST.get("talebe_id")
        if talebe_id:
            talebe_cikar(plan, int(talebe_id))
    elif tur == "etut_hocasi":
        etut_id = request.POST.get("etut_hocasi_id")
        if etut_id:
            etut_hocasi_cikar(plan, int(etut_id))
    else:
        return _json_err("Geçersiz tür.")

    plan = _plan_or_404(pk)
    return _json_ok(
        {
            "ozet": _plan_ozet_json(plan),
            "arac_kartlari": _arac_kartlari_json(plan),
            "atanmamis": _atanmamis_json(plan),
        }
    )


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_api_otomatik(request, pk):
    if not plan_yonetimi_var(request.user):
        return _json_err("Yetkisiz", 403)

    plan = _plan_or_404(pk)
    geri_al_kaydet(plan.pk, request.session)
    yeniden = request.POST.get("yeniden") == "1"
    atanan, kalan = otomatik_dagit(plan, yeniden=yeniden)
    plan = _plan_or_404(pk)
    return _json_ok(
        {
            "mesaj": f"{atanan} talebe dağıtıldı. {kalan} talebe atanmadı.",
            "ozet": _plan_ozet_json(plan),
            "arac_kartlari": _arac_kartlari_json(plan),
            "atanmamis": _atanmamis_json(plan),
        }
    )


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_api_geri_al(request, pk):
    if not plan_yonetimi_var(request.user):
        return _json_err("Yetkisiz", 403)

    if not geri_al(pk, request.session):
        return _json_err("Geri alınacak işlem yok.")

    plan = _plan_or_404(pk)
    return _json_ok(
        {
            "mesaj": "Son işlem geri alındı.",
            "ozet": _plan_ozet_json(plan),
            "arac_kartlari": _arac_kartlari_json(plan),
            "atanmamis": _atanmamis_json(plan),
        }
    )


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_api_sabitle(request, pk):
    if not plan_yonetimi_var(request.user):
        return _json_err("Yetkisiz", 403)

    plan = _plan_or_404(pk)
    talebe_id = int(request.POST.get("talebe_id", 0))
    sabit = request.POST.get("sabit") == "1"
    arac_id = request.POST.get("arac_id")
    talebe_sabitle(
        plan,
        talebe_id,
        sabit=sabit,
        arac_id=int(arac_id) if arac_id else None,
    )
    return _json_ok({"mesaj": "Sabitleme güncellendi."})


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_talebe_ekle(request, pk):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "Yetkisiz.")
        return redirect("ziyaret_arac_listesi")

    plan = _plan_or_404(pk)
    ids = [int(x) for x in request.POST.getlist("talebe_ids") if x.isdigit()]
    if not ids:
        sinif_ids = [int(x) for x in request.POST.getlist("sinif_sube_ids") if x.isdigit()]
        etut_ids = [int(x) for x in request.POST.getlist("etut_hocasi_ids") if x.isdigit()]
        adaylar = toplu_talebe_adaylari(
            sinif_sube_ids=sinif_ids or None,
            etut_hocasi_ids=etut_ids or None,
        )
        ids = [t.id for t in adaylar]

    adet = talebe_listesine_ekle(plan, ids)
    messages.success(request, f"{adet} talebe ziyaret listesine eklendi.")
    return redirect("ziyaret_arac_planlama", pk=plan.pk)


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_talebe_cikar(request, pk, talebe_id):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "Yetkisiz.")
        return redirect("ziyaret_arac_listesi")

    plan = _plan_or_404(pk)
    talebe_listeden_cikar(plan, talebe_id)
    messages.success(request, "Talebe ziyaret listesinden çıkarıldı.")
    return redirect("ziyaret_arac_planlama", pk=plan.pk)


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_arac_kaydet(request, pk):
    if not plan_yonetimi_var(request.user):
        return _json_err("Yetkisiz", 403)

    plan = _plan_or_404(pk)
    arac_id = request.POST.get("arac_id")
    surucu_ad = (request.POST.get("surucu_ad") or "").strip()
    kapasite = request.POST.get("kapasite")
    notlar = (request.POST.get("notlar") or "").strip()

    if arac_id:
        arac = get_object_or_404(ZiyaretAraci, pk=arac_id, plan=plan)
        arac.surucu_ad = surucu_ad or arac.surucu_ad
        if kapasite:
            arac.kapasite = int(kapasite)
        arac.notlar = notlar
        arac.save()
    else:
        if not surucu_ad or not kapasite:
            return _json_err("Araç sahibi ve kapasite zorunlu.")
        ZiyaretAraci.objects.create(
            plan=plan,
            surucu_ad=surucu_ad,
            kapasite=int(kapasite),
            notlar=notlar,
        )

    plan = _plan_or_404(pk)
    return _json_ok(
        {
            "ozet": _plan_ozet_json(plan),
            "arac_kartlari": _arac_kartlari_json(plan),
        }
    )


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_arac_sil(request, pk, arac_id):
    if not plan_yonetimi_var(request.user):
        return _json_err("Yetkisiz", 403)

    plan = _plan_or_404(pk)
    arac = get_object_or_404(ZiyaretAraci, pk=arac_id, plan=plan)
    geri_al_kaydet(plan.pk, request.session)
    arac.delete()
    plan = _plan_or_404(pk)
    return _json_ok(
        {
            "mesaj": "Araç silindi.",
            "ozet": _plan_ozet_json(plan),
            "arac_kartlari": _arac_kartlari_json(plan),
            "atanmamis": _atanmamis_json(plan),
        }
    )


@login_required
@require_POST
@require_permission("ziyaret_arac", "edit")
def ziyaret_arac_hazir(request, pk):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "Yetkisiz.")
        return redirect("ziyaret_arac_listesi")

    plan = _plan_or_404(pk)
    kontrol = plan_kontrol(plan)
    if kontrol.hatalar:
        for hata in kontrol.hatalar:
            messages.error(request, hata)
        return redirect("ziyaret_arac_onizleme", pk=plan.pk)

    for uyari in kontrol.uyarilar:
        messages.warning(request, uyari)

    plan.durum = ZiyaretPlani.Durum.HAZIR
    plan.save(update_fields=["durum", "guncellenme"])
    messages.success(request, "Plan hazır durumuna alındı.")
    return redirect("ziyaret_arac_onizleme", pk=plan.pk)


@login_required
@require_GET
@require_permission("ziyaret_arac", "export_pdf")
def ziyaret_arac_pdf_genel(request, pk):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "PDF yetkiniz yok.")
        return redirect("ziyaret_arac_listesi")

    plan = _plan_or_404(pk)
    kartlar = arac_kart_verisi(plan)
    html = render(
        request,
        "ziyaret_arac_pdf_genel.html",
        {
            **panel_branding_context(),
            "plan": plan,
            "arac_kartlari": kartlar,
            "pdf_grid": genel_pdf_grid_meta(kartlar),
        },
    ).content.decode("utf-8")
    pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    dosya = f"ziyaret_arac_plani_{plan.tarih:%Y%m%d}.pdf"
    return make_pdf_response(pdf, dosya)


@login_required
@require_GET
@require_permission("ziyaret_arac", "export_pdf")
def ziyaret_arac_pdf_program(request, pk):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "PDF yetkiniz yok.")
        return redirect("ziyaret_arac_listesi")

    plan = _plan_or_404(pk)
    kapasite = kapasite_ozeti(plan)
    html = render(
        request,
        "ziyaret_arac_pdf_program.html",
        {
            **panel_branding_context(),
            "plan": plan,
            "program": plan.program_adimlari.all(),
            "kapasite": kapasite,
            "kapasite_olustu": kapasite_olustu_mesaji(kapasite),
        },
    ).content.decode("utf-8")
    pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    dosya = f"ziyaret_program_{plan.tarih:%Y%m%d}.pdf"
    return make_pdf_response(pdf, dosya)


@login_required
@require_GET
@require_permission("ziyaret_arac", "export_pdf")
def ziyaret_arac_pdf_arac(request, pk, arac_id):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "PDF yetkiniz yok.")
        return redirect("ziyaret_arac_listesi")

    plan = _plan_or_404(pk)
    arac = get_object_or_404(ZiyaretAraci, pk=arac_id, plan=plan)
    kart = next((k for k in arac_kart_verisi(plan) if k["arac"].pk == arac.pk), None)
    html = render(
        request,
        "ziyaret_arac_pdf_arac.html",
        {
            **panel_branding_context(),
            "plan": plan,
            "kart": kart,
            "program": plan.program_adimlari.all(),
        },
    ).content.decode("utf-8")
    pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    dosya = _arac_pdf_dosya_adi(1, arac.surucu_ad, plan.tarih)
    return make_pdf_response(pdf, dosya)


@login_required
@require_GET
@require_permission("ziyaret_arac", "export_pdf")
def ziyaret_arac_pdf_tum_araclar(request, pk):
    if not plan_yonetimi_var(request.user):
        messages.error(request, "PDF yetkiniz yok.")
        return redirect("ziyaret_arac_listesi")

    plan = _plan_or_404(pk)
    araclar = list(plan.araclar.all().order_by("surucu_ad", "id"))
    if not araclar:
        messages.error(request, "Henüz araç yok — ZIP oluşturulamadı.")
        return redirect("ziyaret_arac_planlama", pk=plan.pk)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for sira, arac in enumerate(araclar, start=1):
            kart = next(
                (k for k in arac_kart_verisi(plan) if k["arac"].pk == arac.pk),
                None,
            )
            html = render(
                request,
                "ziyaret_arac_pdf_arac.html",
                {
                    **panel_branding_context(),
                    "plan": plan,
                    "kart": kart,
                    "program": plan.program_adimlari.all(),
                },
            ).content.decode("utf-8")
            pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
            zf.writestr(_arac_pdf_dosya_adi(sira, arac.surucu_ad, plan.tarih), pdf)

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = (
        f'attachment; filename="ziyaret_arac_pdfleri_{plan.tarih:%Y%m%d}.zip"'
    )
    return response


@login_required
@require_GET
@require_permission("ziyaret_arac", "view")
def ziyaret_arac_talebe_ara(request, pk):
    if not plan_yonetimi_var(request.user):
        return _json_err("Yetkisiz", 403)

    q = request.GET.get("q", "")
    sinif_id = request.GET.get("sinif_sube")
    sinif_ids = [int(sinif_id)] if sinif_id and sinif_id.isdigit() else None
    adaylar = toplu_talebe_adaylari(sinif_sube_ids=sinif_ids, q=q)
    plan = _plan_or_404(pk)
    listede = set(
        plan.plan_talebeleri.filter(aktif=True).values_list("talebe_id", flat=True)
    )
    return JsonResponse(
        {
            "ok": True,
            "talebeler": [
                {
                    "id": t.id,
                    "ad": t.ad_soyad,
                    "sinif": str(t.sinif_sube) if t.sinif_sube_id else "—",
                    "listed": t.id in listede,
                }
                for t in adaylar[:80]
            ],
        }
    )


def _atanmamis_json(plan: ZiyaretPlani) -> list[dict]:
    return [
        {
            "id": t.id,
            "ad": t.ad_soyad,
            "sinif": str(t.sinif_sube) if t.sinif_sube_id else "—",
        }
        for t in atanmamis_talebeler(plan)
    ]


def _arac_kartlari_json(plan: ZiyaretPlani) -> list[dict]:
    kartlar = []
    for k in arac_kart_verisi(plan):
        arac = k["arac"]
        kartlar.append(
            {
                "id": arac.id,
                "surucu_ad": arac.surucu_ad,
                "kapasite": k["kapasite"],
                "dolu": k["dolu"],
                "kalan": k["kalan"],
                "dolu_mu": k["dolu_mu"],
                "ekleyen": arac.ekleyen.ad_soyad if arac.ekleyen_id else "—",
                "talebeler": [
                    {"id": t.id, "ad": t.ad_soyad}
                    for t in k["talebeler"]
                ],
                "etut_hocalari": [
                    {"id": h.id, "ad": h.ad_soyad}
                    for h in k["etut_hocalari"]
                ],
            }
        )
    return kartlar
