"""Akademik müdahale panel görünümleri."""

from __future__ import annotations

import csv
import json
from io import StringIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import localdate

from takip.akademik_mudahale_service import (
    aktif_mudahale_turleri,
    ek_alanlari_topla,
    mudahale_duzenleyebilir,
    mudahale_olusturabilir,
    mudahale_silebilir,
    mudahale_sinif_secenekleri,
    mudahaleleri_filtrele,
    rapor_istatistikleri,
    talebe_panel_verisi,
    yetkili_mudahaleler,
)
from takip.filter_utils import get_int_list
from takip.forms import AkademikMudahaleForm
from takip.models import AkademikMudahale, MudahaleTuru
from takip.permissions.decorators import require_permission
from takip.permissions.scope import yetkili_talebeler
from takip.permissions.service import can


def _form_kaydet(request, form, tur: MudahaleTuru, instance=None):
    mudahale = form.save(commit=False)
    if not mudahale.tarih:
        mudahale.tarih = localdate()
    mudahale.olusturan = request.user
    mudahale.ek_alanlar = ek_alanlari_topla(request.POST, tur)
    mudahale.save()
    return mudahale


def _mudahale_panel_form(user, data=None, instance=None):
    initial = {"tarih": localdate(), "veliye_goster": True}
    kwargs = {}
    if not data and not instance:
        kwargs["initial"] = initial
    form = AkademikMudahaleForm(user, data, instance=instance, **kwargs)
    form.fields.pop("tarih", None)
    form.fields.pop("veliye_goster", None)
    return form


@login_required
@require_permission("akademik_mudahale", "view")
def mudahale_listesi(request):
    olusturabilir = mudahale_olusturabilir(request.user)
    form = None
    turler = aktif_mudahale_turleri()
    tur_semalari = {str(t.id): t.form_semasi or [] for t in turler}

    if request.method == "POST" and olusturabilir:
        form = _mudahale_panel_form(request.user, request.POST)
        if form.is_valid():
            tur = form.cleaned_data["mudahale_turu"]
            mudahale = _form_kaydet(request, form, tur)
            messages.success(request, "Müdahale kaydı eklendi.")
            url = reverse("akademik_mudahale_listesi")
            sinif_q = request.GET.get("sinif_sube", "")
            if sinif_q:
                url = f"{url}?sinif_sube={sinif_q}"
            return redirect(url)
    elif olusturabilir:
        form = _mudahale_panel_form(request.user)

    kayitlar = yetkili_mudahaleler(request.user).order_by("-tarih", "-id")
    sinif_sube_id = request.GET.get("sinif_sube", "")
    kayitlar = mudahaleleri_filtrele(kayitlar, sinif_sube_id=sinif_sube_id or None)[:100]

    return render(
        request,
        "akademik_mudahale_listesi.html",
        {
            "kayitlar": kayitlar,
            "form": form,
            "turler": turler,
            "tur_semalari_json": json.dumps(tur_semalari),
            "talebeler_json": json.dumps(talebe_panel_verisi(request.user)),
            "sinif_subeler": mudahale_sinif_secenekleri(request.user),
            "olusturabilir": olusturabilir,
            "filtre_sinif": sinif_sube_id,
        },
    )


@login_required
@require_permission("akademik_mudahale", "create")
def mudahale_ekle(request):
    return redirect("akademik_mudahale_listesi")


@login_required
@require_permission("akademik_mudahale", "view")
def mudahale_detay(request, pk):
    mudahale = get_object_or_404(yetkili_mudahaleler(request.user), pk=pk)
    return render(
        request,
        "akademik_mudahale_detay.html",
        {
            "mudahale": mudahale,
            "duzenleyebilir": mudahale_duzenleyebilir(request.user, mudahale),
            "silebilir": mudahale_silebilir(request.user, mudahale),
        },
    )


@login_required
@require_permission("akademik_mudahale", "edit")
def mudahale_duzenle(request, pk):
    mudahale = get_object_or_404(yetkili_mudahaleler(request.user), pk=pk)
    if not mudahale_duzenleyebilir(request.user, mudahale):
        messages.error(request, "Düzenleme yetkiniz yok.")
        return redirect("akademik_mudahale_listesi")

    form = AkademikMudahaleForm(
        request.user,
        request.POST or None,
        instance=mudahale,
    )

    if request.method == "POST" and form.is_valid():
        tur = form.cleaned_data["mudahale_turu"]
        _form_kaydet(request, form, tur, instance=mudahale)
        messages.success(request, "Kayıt güncellendi.")
        return redirect("akademik_mudahale_detay", pk=mudahale.pk)

    turler = aktif_mudahale_turleri()
    tur_semalari = {str(t.id): t.form_semasi or [] for t in turler}

    return render(
        request,
        "akademik_mudahale_form.html",
        {
            "form": form,
            "baslik": "Akademik Müdahale Düzenle",
            "mudahale": mudahale,
            "turler": turler,
            "secili_tur": mudahale.mudahale_turu,
            "tur_semalari_json": json.dumps(tur_semalari),
            "mevcut_ek_json": json.dumps(mudahale.ek_alanlar or {}),
        },
    )


@login_required
@require_permission("akademik_mudahale", "delete")
def mudahale_sil(request, pk):
    mudahale = get_object_or_404(yetkili_mudahaleler(request.user), pk=pk)
    if not mudahale_silebilir(request.user, mudahale):
        messages.error(request, "Silme yetkiniz yok.")
        return redirect("akademik_mudahale_listesi")

    talebe_id = mudahale.talebe_id
    mudahale.delete()
    messages.success(request, "Kayıt silindi.")
    return redirect("akademik_mudahale_listesi")


@login_required
@require_permission("akademik_mudahale", "view")
def mudahale_rapor(request):
    if request.GET.get("format") == "excel" and can(
        request.user, "akademik_mudahale", "export_excel"
    ):
        return mudahale_excel(request)

    qs = yetkili_mudahaleler(request.user).order_by("-tarih", "-id")
    filtre = {
        "talebe": get_int_list(request.GET, "talebe"),
        "sinif_sube": get_int_list(request.GET, "sinif_sube"),
        "ders": get_int_list(request.GET, "ders"),
        "tur": get_int_list(request.GET, "tur"),
        "konu": request.GET.get("konu") or "",
        "olusturan": get_int_list(request.GET, "olusturan"),
        "baslangic": request.GET.get("baslangic") or "",
        "bitis": request.GET.get("bitis") or "",
    }
    qs = mudahaleleri_filtrele(
        qs,
        talebe_ids=filtre["talebe"] or None,
        sinif_sube_ids=filtre["sinif_sube"] or None,
        ders_ids=filtre["ders"] or None,
        tur_ids=filtre["tur"] or None,
        konu=filtre["konu"] or None,
        olusturan_ids=filtre["olusturan"] or None,
        baslangic=filtre["baslangic"] or None,
        bitis=filtre["bitis"] or None,
    )

    from takip.models import Ders, SinifSube

    olusturanlar = User.objects.filter(
        id__in=yetkili_mudahaleler(request.user)
        .exclude(olusturan__isnull=True)
        .values_list("olusturan_id", flat=True)
        .distinct()
    ).order_by("first_name", "username")

    return render(
        request,
        "akademik_mudahale_rapor.html",
        {
            "kayitlar": qs[:200],
            "istatistik": rapor_istatistikleri(qs),
            "talebeler": yetkili_talebeler(request.user).order_by("ad_soyad"),
            "turler": aktif_mudahale_turleri(),
            "dersler": Ders.objects.filter(aktif=True).order_by("sira", "ad"),
            "sinif_subeler": SinifSube.objects.filter(aktif=True).order_by(
                "sinif", "sube"
            ),
            "olusturanlar": olusturanlar,
            "filtre": filtre,
            "excel_yetkisi": can(request.user, "akademik_mudahale", "export_excel"),
            "pdf_yetkisi": can(request.user, "akademik_mudahale", "export_pdf")
            or can(request.user, "akademik_mudahale", "export_excel")
            or can(request.user, "akademik_mudahale", "view"),
        },
    )


def _mudahale_rapor_queryset(request):
    qs = yetkili_mudahaleler(request.user).order_by("-tarih", "-id")
    return mudahaleleri_filtrele(
        qs,
        talebe_ids=get_int_list(request.GET, "talebe") or None,
        sinif_sube_ids=get_int_list(request.GET, "sinif_sube") or None,
        ders_ids=get_int_list(request.GET, "ders") or None,
        tur_ids=get_int_list(request.GET, "tur") or None,
        konu=request.GET.get("konu"),
        olusturan_ids=get_int_list(request.GET, "olusturan") or None,
        baslangic=request.GET.get("baslangic"),
        bitis=request.GET.get("bitis"),
    )


@login_required
@require_permission("akademik_mudahale", "view")
def mudahale_pdf(request):
    from django.template.loader import render_to_string
    from django.utils.timezone import localdate

    from takip.pdf_utils import (
        coz_pdf_sayfa,
        html_to_pdf,
        make_pdf_response,
        pdf_engine_status,
        pdf_error_response,
    )

    qs = _mudahale_rapor_queryset(request)[:500]
    pdf_sayfa = coz_pdf_sayfa(request, default="a4_landscape")
    html = render_to_string(
        "akademik_mudahale_rapor_pdf.html",
        {
            "kayitlar": qs,
            "istatistik": rapor_istatistikleri(qs),
            "alt_baslik": localdate().strftime("%d.%m.%Y"),
            "pdf_sayfa": pdf_sayfa,
        },
        request=request,
    )
    pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf:
        return pdf_error_response(
            f"PDF üretilemedi ({pdf_engine_status()})."
        )
    return make_pdf_response(
        pdf, f"akademik_mudahale_{localdate():%Y%m%d}.pdf"
    )


@login_required
@require_permission("akademik_mudahale", "export_excel")
def mudahale_excel(request):
    from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit
    from django.utils.timezone import localdate

    qs = _mudahale_rapor_queryset(request)

    satirlar = [
        [
            kayit.tarih.strftime("%d.%m.%Y"),
            (kayit.talebe.ad_soyad or "").upper(),
            str(kayit.talebe.sinif_sube or ""),
            kayit.ders.ad if kayit.ders_id else "",
            kayit.konu,
            kayit.mudahale_turu.ad,
            kayit.sure_dakika,
            (
                kayit.olusturan.get_full_name() or kayit.olusturan.username
                if kayit.olusturan
                else ""
            ),
            "Evet" if kayit.veliye_goster else "Hayır",
            (kayit.degerlendirme_notu or "").replace("\n", " ")[:200],
        ]
        for kayit in qs[:1000]
    ]
    icerik = basit_rapor_xlsx(
        baslik="Akademik Müdahale Raporu",
        alt_baslik=localdate().strftime("%d.%m.%Y"),
        kolon_basliklari=[
            "Tarih", "Ad-Soyad", "Sınıf", "Ders", "Konu",
            "Müdahale Türü", "Süre (dk)", "Personel", "Veliye Göster", "Not",
        ],
        satirlar=satirlar,
        sayfa_adi="Müdahale",
        ortala_kolonlari=[0, 2, 6, 8],
        genislikler=[12, 26, 10, 14, 18, 16, 10, 18, 12, 30],
    )
    return excel_http_yanit(icerik, f"akademik_mudahale_{localdate():%Y%m%d}.xlsx")
