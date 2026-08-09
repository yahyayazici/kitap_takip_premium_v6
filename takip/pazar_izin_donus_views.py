"""Pazar izin dönüşü yoklama panel ve rapor görünümleri."""

from __future__ import annotations

from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.timezone import localdate

from config.branding import panel_branding_context

from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit
from takip.filter_utils import get_int_list, get_str_list
from takip.models import EtutHocasi, SinifSube
from takip.pazar_izin_donus_models import PazarIzinDonusDurumu
from takip.pazar_izin_donus_service import (
    gun_ayari_kaydet,
    kayit_haritasi_tarih,
    oturum_getir,
    oturum_hazirla,
    pazar_izin_kaydedebilir,
    pazar_izin_tam_yetki,
    panel_talebeleri,
    rapor_filtrele,
    rapor_istatistik,
    rapor_kayitlari,
    satir_verisi,
    varsayilan_beklenen,
    yetkili_sinif_subeler,
    yoklama_kaydet,
    yoklama_kaydet_siniflara,
)
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.permissions.decorators import require_permission
from takip.permissions.scope import yetkili_talebeler
from takip.permissions.service import can


def _parse_tarih(value: str | None):
    if not value:
        return localdate()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return localdate()


def _parse_saat(value: str | None, fallback: time) -> time:
    if not value:
        return fallback
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return fallback


def _redirect_params(tarih, secili_sinif: str) -> str:
    return f"?tarih={tarih:%Y-%m-%d}&sinif_sube={secili_sinif}"


def _post_satirlari(
    request,
    talebe_ids: list[int],
    *,
    varsayilan_giris_tarihi,
) -> dict[int, dict]:
    satirlar: dict[int, dict] = {}
    for talebe_id in talebe_ids:
        prefix = f"s_{talebe_id}_"
        durum = request.POST.get(f"{prefix}durum", PazarIzinDonusDurumu.GELMEDI)
        giris_saat_raw = request.POST.get(f"{prefix}giris_saati", "").strip()
        aciklama = request.POST.get(f"{prefix}aciklama", "").strip()

        giris_tarih = None
        giris_saat = None
        if durum == PazarIzinDonusDurumu.GEC_GELDI and giris_saat_raw:
            giris_tarih = varsayilan_giris_tarihi
            giris_saat = _parse_saat(giris_saat_raw, time(0, 0))

        satirlar[talebe_id] = {
            "durum": durum,
            "giris_tarihi": giris_tarih,
            "giris_saati": giris_saat,
            "aciklama": aciklama,
        }
    return satirlar


def _filtre_from_request(request) -> dict:
    return {
        "baslangic": request.GET.get("baslangic", ""),
        "bitis": request.GET.get("bitis", ""),
        "sinif_sube": get_int_list(request.GET, "sinif_sube"),
        "etut_hocasi": get_int_list(request.GET, "etut_hocasi"),
        "talebe": get_int_list(request.GET, "talebe"),
        "durum": get_str_list(request.GET, "durum"),
        "donem": request.GET.get("donem", ""),
    }


def _filtreli_qs(user, filtre: dict):
    qs = rapor_kayitlari(user)
    return rapor_filtrele(
        qs,
        baslangic=filtre["baslangic"] or None,
        bitis=filtre["bitis"] or None,
        sinif_sube_ids=filtre["sinif_sube"] or None,
        etut_hocasi_ids=filtre["etut_hocasi"] or None,
        talebe_ids=filtre["talebe"] or None,
        durumlar=filtre["durum"] or None,
        donem=filtre["donem"] or None,
    )


@login_required
@require_permission("pazar_izin_donus", "view")
def pazar_izin_donus_panel(request):
    siniflar = yetkili_sinif_subeler(request.user)
    secili_sinif = request.GET.get("sinif_sube") or request.POST.get("sinif_sube") or ""
    tarih = _parse_tarih(
        request.GET.get("tarih") or request.POST.get("tarih")
    )
    tum_kurum = secili_sinif == "tum"

    if not secili_sinif:
        secili_sinif = "tum"
        tum_kurum = True

    beklenen_tarih, beklenen_saat = varsayilan_beklenen(tarih)
    if not tum_kurum and secili_sinif:
        oturum = oturum_getir(secili_sinif, tarih)
        if oturum:
            beklenen_tarih = oturum.beklenen_giris_tarihi
            beklenen_saat = oturum.beklenen_giris_saati

    if request.method == "POST" and pazar_izin_kaydedebilir(request.user):
        islem = request.POST.get("islem", "kaydet")
        secili_sinif = request.POST.get("sinif_sube") or secili_sinif
        tum_kurum = secili_sinif == "tum"

        if islem == "toplu_saat":
            beklenen_tarih = _parse_tarih(request.POST.get("beklenen_giris_tarihi"))
            beklenen_saat = _parse_saat(
                request.POST.get("beklenen_giris_saati"), beklenen_saat
            )
            gun_ayari_kaydet(
                request.user,
                tarih,
                beklenen_tarih,
                beklenen_saat,
                tum_siniflara_uygula=pazar_izin_tam_yetki(request.user),
            )
            messages.success(
                request,
                f"İzin dönüş saati kaydedildi: {beklenen_tarih:%d.%m.%Y} {beklenen_saat:%H:%M}",
            )
            return redirect(request.path + _redirect_params(tarih, secili_sinif))

        if not secili_sinif:
            messages.error(request, "Lütfen sınıf veya tüm kurum seçin.")
            return redirect(request.path)

        beklenen_tarih = _parse_tarih(request.POST.get("beklenen_giris_tarihi"))
        beklenen_saat = _parse_saat(
            request.POST.get("beklenen_giris_saati"), beklenen_saat
        )
        qs = panel_talebeleri(request.user, secili_sinif)
        talebeler = list(qs)
        talebe_ids = [t.id for t in talebeler]
        satirlar = _post_satirlari(
            request,
            talebe_ids,
            varsayilan_giris_tarihi=beklenen_tarih,
        )

        if tum_kurum:
            yoklama_kaydet_siniflara(
                request.user,
                tarih,
                beklenen_tarih=beklenen_tarih,
                beklenen_saat=beklenen_saat,
                satirlar=satirlar,
                talebeler=talebeler,
            )
        else:
            oturum = oturum_hazirla(
                request.user, secili_sinif, tarih, beklenen_tarih, beklenen_saat
            )
            yoklama_kaydet(
                request.user,
                oturum,
                beklenen_tarih=beklenen_tarih,
                beklenen_saat=beklenen_saat,
                satirlar=satirlar,
                talebe_ids=talebe_ids,
            )

        messages.success(request, f"{tarih:%d.%m.%Y} yoklaması kaydedildi.")
        return redirect(request.path + _redirect_params(tarih, secili_sinif))

    qs = panel_talebeleri(request.user, secili_sinif)
    talebe_ids = list(qs.values_list("id", flat=True))
    harita = kayit_haritasi_tarih(tarih, talebe_ids)
    satirlar = [satir_verisi(t, harita.get(t.id)) for t in qs]

    return render(
        request,
        "pazar_izin_donus_panel.html",
        {
            "tarih": tarih,
            "sinif_subeler": siniflar,
            "secili_sinif": secili_sinif,
            "tum_kurum": tum_kurum,
            "satirlar": satirlar,
            "beklenen_giris_tarihi": beklenen_tarih,
            "beklenen_giris_saati": beklenen_saat,
            "durum_secenekleri": PazarIzinDonusDurumu.choices,
            "kaydedebilir": pazar_izin_kaydedebilir(request.user),
            "tam_yetki": pazar_izin_tam_yetki(request.user),
            "talebe_sayisi": qs.count(),
        },
    )


@login_required
@require_permission("pazar_izin_donus", "view")
def pazar_izin_donus_rapor(request):
    if request.GET.get("format") == "pdf" and can(
        request.user, "pazar_izin_donus", "export_pdf"
    ):
        return pazar_izin_donus_pdf(request)
    if request.GET.get("format") == "excel" and can(
        request.user, "pazar_izin_donus", "export_excel"
    ):
        return pazar_izin_donus_excel(request)

    filtre = _filtre_from_request(request)
    qs = _filtreli_qs(request.user, filtre)

    export_params = request.GET.copy()
    export_params.pop("format", None)
    export_qs = export_params.urlencode()
    export_tail = f"&{export_qs}" if export_qs else ""

    return render(
        request,
        "pazar_izin_donus_rapor.html",
        {
            "kayitlar": qs[:500],
            "istatistik": rapor_istatistik(qs),
            "filtre": filtre,
            "durum_labels": dict(PazarIzinDonusDurumu.choices),
            "sinif_subeler": SinifSube.objects.filter(aktif=True).order_by(
                "sinif", "sube"
            ),
            "etut_hocalari": EtutHocasi.objects.filter(aktif=True).order_by(
                "ad_soyad"
            ),
            "talebeler": yetkili_talebeler(
                request.user, aktif_only=True
            ).order_by("ad_soyad"),
            "pdf_yetkisi": can(request.user, "pazar_izin_donus", "export_pdf"),
            "excel_yetkisi": can(request.user, "pazar_izin_donus", "export_excel"),
            "pdf_url": f"{request.path}?format=pdf{export_tail}",
            "excel_url": f"{request.path}?format=excel{export_tail}",
        },
    )


@login_required
@require_permission("pazar_izin_donus", "export_pdf")
def pazar_izin_donus_pdf(request):
    filtre = _filtre_from_request(request)
    qs = _filtreli_qs(request.user, filtre)

    html = render(
        request,
        "pazar_izin_donus_pdf.html",
        {
            "kayitlar": list(qs[:800]),
            "istatistik": rapor_istatistik(qs),
            "filtre": filtre,
            "durum_labels": dict(PazarIzinDonusDurumu.choices),
            **panel_branding_context(),
        },
    ).content.decode("utf-8")

    pdf_verisi = html_to_pdf(html)
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    return make_pdf_response(
        pdf_verisi, f"pazar_izin_donus_{localdate():%Y%m%d}.pdf"
    )


@login_required
@require_permission("pazar_izin_donus", "export_excel")
def pazar_izin_donus_excel(request):
    filtre = _filtre_from_request(request)
    qs = _filtreli_qs(request.user, filtre)
    durum_labels = dict(PazarIzinDonusDurumu.choices)

    satirlar = []
    for k in qs[:2000]:
        sinif = "—"
        if k.talebe.sinif_sube_id:
            ss = k.talebe.sinif_sube
            sinif = f"{ss.sinif}-{ss.sube}"
        giris = "—"
        if k.giris_saati:
            tarih_etiket = k.giris_tarihi or k.oturum.tarih
            giris = f"{tarih_etiket:%d.%m.%Y} {k.giris_saati:%H:%M}"
        satirlar.append(
            (
                k.oturum.tarih.strftime("%d.%m.%Y"),
                sinif,
                k.talebe.ad_soyad,
                k.talebe.etut_hocasi.ad_soyad if k.talebe.etut_hocasi_id else "—",
                durum_labels.get(k.durum, k.durum),
                giris,
                k.gecikme_dk if k.durum == PazarIzinDonusDurumu.GEC_GELDI else "—",
                k.aciklama or "—",
            )
        )

    icerik = basit_rapor_xlsx(
        baslik="Pazar İzin Dönüşü Yoklama Raporu",
        alt_baslik=f"Toplam {len(satirlar)} kayıt",
        kolon_basliklari=[
            "Tarih",
            "Sınıf",
            "Talebe",
            "Etüt Hocası",
            "Durum",
            "Giriş",
            "Gecikme (dk)",
            "Açıklama",
        ],
        satirlar=satirlar,
        durum_kolonlari=[4],
        genislikler=[12, 10, 28, 22, 14, 12, 12, 24],
    )
    return excel_http_yanit(
        icerik, f"pazar-izin-donus_{localdate():%Y%m%d}.xlsx"
    )
