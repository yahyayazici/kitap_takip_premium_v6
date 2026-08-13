"""Namaz yoklama panel görünümleri."""

from __future__ import annotations

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.timezone import localdate

from config.branding import panel_branding_context

from takip.filter_utils import get_int_list, get_str_list
from takip.models import EtutHocasi, NamazVakti, SinifSube
from takip.namaz_yoklama_models import NamazYoklamaOturum
from takip.namaz_yoklama_service import (
    VAKIT_SIRASI,
    etut_gelmedi_bildirimleri,
    gelmedi_ozetleri,
    kayit_haritasi,
    namaz_tam_yetki,
    namaz_yoklama_kaydedebilir,
    panel_talebeleri,
    rapor_filtrele,
    rapor_istatistik,
    rapor_kayitlari,
    talebe_sinif_etiketi,
    talebeler_gruplu,
    yoklama_kaydet,
)
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user


def _parse_tarih(value: str | None):
    if not value:
        return localdate()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return localdate()


def _varsayilan_vakit() -> str:
    """Hocanın o anki namaz vakti — yoklama ekranına varsayılan odak."""
    saat = datetime.now().hour
    if saat < 10:
        return NamazVakti.SABAH
    if saat < 14:
        return NamazVakti.OGLE
    if saat < 17:
        return NamazVakti.IKINDI
    if saat < 20:
        return NamazVakti.AKSAM
    return NamazVakti.YATSI


def _odak_vakit(value: str | None) -> str:
    if value in VAKIT_SIRASI:
        return value
    return _varsayilan_vakit()


def _kayit_haritalari(tarih):
    oturumlar = {
        vakit: NamazYoklamaOturum.objects.filter(tarih=tarih, vakit=vakit).first()
        for vakit in VAKIT_SIRASI
    }
    return oturumlar, {v: kayit_haritasi(o) for v, o in oturumlar.items()}


def _post_durumlari(request, talebe_ids, vakit: str) -> dict[int, str]:
    durumlar: dict[int, str] = {}
    for talebe_id in talebe_ids:
        key = f"k_{talebe_id}_{vakit}"
        deger = request.POST.get(key, "").strip()
        if deger:
            durumlar[int(talebe_id)] = deger
    return durumlar


@login_required
@require_permission("namaz_yoklama", "view")
def namaz_yoklama_panel(request):
    if request.method == "POST" and namaz_yoklama_kaydedebilir(request.user):
        tarih = _parse_tarih(request.POST.get("tarih"))
        odak = _odak_vakit(request.POST.get("odak_vakit"))
        qs = panel_talebeleri(
            request.user,
            etudum=request.POST.get("etudum") == "1",
            sinif_sube_id=request.POST.get("sinif_sube") or None,
            etut_hocasi_id=request.POST.get("etut_hocasi") or None,
        )
        talebe_ids = list(qs.values_list("id", flat=True))
        # Tek vakit kaydı: o anki namazı bitirir, diğer vakitler bozulmaz
        kaydedilecek = [odak] if request.POST.get("sadece_odak") == "1" else list(VAKIT_SIRASI)
        for vakit in kaydedilecek:
            yoklama_kaydet(
                request.user,
                tarih,
                vakit,
                _post_durumlari(request, talebe_ids, vakit),
                talebe_ids,
            )
        label = dict(NamazVakti.choices).get(odak, odak)
        messages.success(request, f"{tarih:%d.%m.%Y} · {label} yoklaması kaydedildi.")
        params = f"?tarih={tarih:%Y-%m-%d}&vakit={odak}"
        if request.POST.get("etudum") == "1":
            params += "&etudum=1"
        sinif = request.POST.get("sinif_sube") or ""
        if sinif:
            params += f"&sinif_sube={sinif}"
        return redirect("namaz_yoklama_panel" + params)

    tarih = _parse_tarih(request.GET.get("tarih"))
    etudum = request.GET.get("etudum") == "1"
    odak = _odak_vakit(request.GET.get("vakit"))

    qs = panel_talebeleri(
        request.user,
        etudum=etudum,
        sinif_sube_id=request.GET.get("sinif_sube") or None,
        etut_hocasi_id=request.GET.get("etut_hocasi") or None,
    )
    oturumlar, haritalar = _kayit_haritalari(tarih)
    gruplar = talebeler_gruplu(qs)
    for grup in gruplar:
        for talebe in grup["talebeler"]:
            talebe.vakit_hucreleri = [
                {"vakit": v, "secili": haritalar[v].get(talebe.id, "")}
                for v in VAKIT_SIRASI
            ]
            talebe.odak_secili = haritalar[odak].get(talebe.id, "")

    return render(
        request,
        "namaz_yoklama_panel.html",
        {
            "tarih": tarih,
            "gruplar": gruplar,
            "vakitler": VAKIT_SIRASI,
            "vakit_basliklari": [
                (v, dict(NamazVakti.choices).get(v, v)) for v in VAKIT_SIRASI
            ],
            "odak_vakit": odak,
            "odak_vakit_label": dict(NamazVakti.choices).get(odak, odak),
            "haritalar": haritalar,
            "oturumlar": oturumlar,
            "herhangi_oturum_kayitli": any(oturumlar.values()),
            "gelmedi_ozetleri": gelmedi_ozetleri(request.user, tarih),
            "kaydedebilir": namaz_yoklama_kaydedebilir(request.user),
            "tam_yetki": namaz_tam_yetki(request.user),
            "etudum": etudum,
            "etut_hocasi_var": bool(etut_hocasi_for_user(request.user)),
            "talebe_sayisi": qs.count(),
            "sinif_subeler": SinifSube.objects.filter(aktif=True).order_by("sinif", "sube"),
            "etut_hocalari": EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad"),
            "etut_bildirimleri": etut_gelmedi_bildirimleri(request.user, tarih),
            "talebe_sinif_etiketi": talebe_sinif_etiketi,
            "secili_sinif": request.GET.get("sinif_sube", ""),
        },
    )


@login_required
@require_permission("namaz_yoklama", "view")
def namaz_yoklama_rapor(request):
    if request.GET.get("format") == "pdf" and can(request.user, "namaz_yoklama", "export_pdf"):
        return namaz_yoklama_pdf(request)

    filtre = {
        "vakit": get_str_list(request.GET, "vakit"),
        "baslangic": request.GET.get("baslangic", ""),
        "bitis": request.GET.get("bitis", ""),
        "sinif_sube": get_int_list(request.GET, "sinif_sube"),
        "etut_hocasi": get_int_list(request.GET, "etut_hocasi"),
        "talebe": get_int_list(request.GET, "talebe"),
        "durum": get_str_list(request.GET, "durum"),
        "donem": request.GET.get("donem", ""),
    }
    qs = rapor_kayitlari(request.user)
    qs = rapor_filtrele(
        qs,
        vakitler=filtre["vakit"] or None,
        baslangic=filtre["baslangic"] or None,
        bitis=filtre["bitis"] or None,
        sinif_sube_ids=filtre["sinif_sube"] or None,
        etut_hocasi_ids=filtre["etut_hocasi"] or None,
        talebe_ids=filtre["talebe"] or None,
        durumlar=filtre["durum"] or None,
        donem=filtre["donem"] or None,
    )

    from takip.permissions.scope import yetkili_talebeler

    export_params = request.GET.copy()
    export_params.pop("format", None)
    export_qs = export_params.urlencode()
    export_tail = f"&{export_qs}" if export_qs else ""

    return render(
        request,
        "namaz_yoklama_rapor.html",
        {
            "kayitlar": qs[:500],
            "istatistik": rapor_istatistik(qs),
            "filtre": filtre,
            "vakit_labels": dict(NamazVakti.choices),
            "sinif_subeler": SinifSube.objects.filter(aktif=True).order_by("sinif", "sube"),
            "etut_hocalari": EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad"),
            "talebeler": yetkili_talebeler(request.user, aktif_only=True).order_by("ad_soyad"),
            "pdf_yetkisi": can(request.user, "namaz_yoklama", "export_pdf"),
            "pdf_url": f"{request.path}?format=pdf{export_tail}",
        },
    )


@login_required
@require_permission("namaz_yoklama", "export_pdf")
def namaz_yoklama_pdf(request):
    qs = rapor_kayitlari(request.user)
    qs = rapor_filtrele(
        qs,
        vakitler=get_str_list(request.GET, "vakit") or None,
        baslangic=request.GET.get("baslangic") or None,
        bitis=request.GET.get("bitis") or None,
        sinif_sube_ids=get_int_list(request.GET, "sinif_sube") or None,
        etut_hocasi_ids=get_int_list(request.GET, "etut_hocasi") or None,
        talebe_ids=get_int_list(request.GET, "talebe") or None,
        durumlar=get_str_list(request.GET, "durum") or None,
        donem=request.GET.get("donem") or None,
    )

    html = render(
        request,
        "namaz_yoklama_pdf.html",
        {
            "kayitlar": list(qs[:800]),
            "istatistik": rapor_istatistik(qs),
            "filtre": request.GET,
            "vakit_labels": dict(NamazVakti.choices),
            **panel_branding_context(),
        },
    ).content.decode("utf-8")

    pdf_verisi = html_to_pdf(html)
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    return make_pdf_response(pdf_verisi, f"namaz_yoklama_{localdate():%Y%m%d}.pdf")
