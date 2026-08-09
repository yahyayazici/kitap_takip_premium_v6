"""Yazılı takip — personel: oluştur, puan gir, PDF."""

from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import localdate
from django.utils.text import slugify

from takip.forms import YaziliSinavPanelForm
from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.user_helpers import etut_hocasi_for_user
from takip.yazili_takip_service import (
    kamp_ozet_istatistik,
    sinav_sonuc_talebeleri,
    sinav_sonuclari_sirali,
    sonuc_giris_satirlari,
    sonuclari_toplu_kaydet,
    yazili_duzenleyebilir,
    yazili_olusturabilir,
    yazili_sinav_olustur,
    yazili_sinif_secenekleri,
    yazili_sinif_secimlerini_dogrula,
    yetkili_kamplar,
    yetkili_sinavlar,
)
from takip.models import YaziliSinav, YaziliSonuc


def _yazili_aktif_tur(request, *, form=None) -> str:
    """Sekme türü — GET, POST veya formdan."""
    allowed = {YaziliSinav.Tur.ORNEK, YaziliSinav.Tur.GERCEK}
    for source in (request.GET, request.POST):
        raw = (source.get("tur") or "").strip().lower()
        if raw in allowed:
            return raw
    if form is not None and getattr(form, "data", None):
        raw = (form.data.get("tur") or "").strip().lower()
        if raw in allowed:
            return raw
    return YaziliSinav.Tur.ORNEK


def _etut_etiket(user) -> str | None:
    hoca = etut_hocasi_for_user(user)
    if hoca:
        return hoca.ad_soyad
    from takip.models import PersonelProfili

    profil = (
        PersonelProfili.objects.filter(user=user)
        .select_related("etut_hocasi")
        .first()
    )
    if profil and profil.etut_hocasi:
        return profil.etut_hocasi.ad_soyad
    return None


@login_required
@require_permission("yazili_takip", "view")
def yazili_kamp_listesi(request):
    """Ana panel: yazılı oluştur + örnek/gerçek listeleri."""
    olusturabilir = yazili_olusturabilir(request.user)
    form = None
    tur = _yazili_aktif_tur(request)

    if request.method == "POST" and olusturabilir:
        form = YaziliSinavPanelForm(request.POST, aktif_tur=tur)
        tur = _yazili_aktif_tur(request, form=form)
        sinif_etiketleri, sinif_hata = yazili_sinif_secimlerini_dogrula(
            request.user,
            request.POST.getlist("sinif_subeler"),
        )
        if sinif_hata:
            messages.error(request, sinif_hata)
        elif form.is_valid():
            kayit_tur = form.cleaned_data["tur"]
            try:
                sinav = yazili_sinav_olustur(
                    request.user,
                    ders=form.cleaned_data["ders"],
                    sinav_tarihi=form.cleaned_data["sinav_tarihi"],
                    yazili_no=form.cleaned_data["yazili_no"],
                    tur=kayit_tur,
                    sinif_etiketleri=sinif_etiketleri,
                    ad=form.cleaned_data.get("ad") or "",
                    donem=int(form.cleaned_data.get("donem") or 1),
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"{sinav.ad} oluşturuldu.")
                return redirect("yazili_sonuc_gir", pk=sinav.pk)
    elif olusturabilir:
        form = YaziliSinavPanelForm(
            aktif_tur=tur,
            initial={
                "sinav_tarihi": localdate(),
                "yazili_no": 1,
                "tur": tur,
            },
        )

    sinavlar = list(yetkili_sinavlar(request.user).filter(tur=tur))
    kamplar = yetkili_kamplar(request.user)

    return render(
        request,
        "yazili_kamp_listesi.html",
        {
            "kamplar": kamplar,
            "sinavlar": sinavlar,
            "form": form,
            "olusturabilir": olusturabilir,
            "sinif_secenekleri": yazili_sinif_secenekleri(request.user),
            "aktif_tur": tur,
            "silme_yetkisi": can(request.user, "yazili_takip", "delete"),
            "pdf_yetkisi": can(request.user, "yazili_takip", "export_pdf"),
            "sonuc_girebilir": yazili_duzenleyebilir(request.user),
        },
    )


@login_required
@require_permission("yazili_takip", "delete")
def yazili_sinav_sil(request, pk):
    sinav = get_object_or_404(yetkili_sinavlar(request.user), pk=pk)
    if request.method != "POST":
        return redirect("yazili_kamp_listesi")
    ad = sinav.ad
    tur = sinav.tur
    sinav.delete()
    messages.success(request, f"{ad} silindi.")
    return redirect(f"{reverse('yazili_kamp_listesi')}?tur={tur}")


@login_required
@require_permission("yazili_takip", "view")
def yazili_kamp_detay(request, pk):
    kamp = get_object_or_404(yetkili_kamplar(request.user), pk=pk)
    sinavlar = list(yetkili_sinavlar(request.user, kamp))

    sinav_id = request.GET.get("sinav")
    secili_sinav = None
    sonuc_satirlari = []

    if sinav_id:
        secili_sinav = get_object_or_404(
            yetkili_sinavlar(request.user, kamp),
            pk=sinav_id,
        )
    elif sinavlar:
        secili_sinav = sinavlar[0]

    if secili_sinav:
        sonuc_satirlari = sinav_sonuclari_sirali(request.user, secili_sinav)

    return render(
        request,
        "yazili_kamp_detay.html",
        {
            "kamp": kamp,
            "sinavlar": sinavlar,
            "secili_sinav": secili_sinav,
            "sonuc_satirlari": sonuc_satirlari,
            "istatistik": kamp_ozet_istatistik(request.user, kamp),
            "sonuc_girebilir": yazili_duzenleyebilir(request.user),
            "pdf_yetkisi": can(request.user, "yazili_takip", "export_pdf"),
        },
    )


@login_required
@require_permission("yazili_takip", "edit")
def yazili_sonuc_gir(request, pk):
    sinav = get_object_or_404(
        yetkili_sinavlar(request.user).select_related("kamp", "ders"),
        pk=pk,
    )
    talebeler = list(sinav_sonuc_talebeleri(request.user, sinav))

    if request.method == "POST":
        kaydedilen, hatalar = sonuclari_toplu_kaydet(
            request.user,
            sinav,
            talebeler,
            request.POST,
        )
        if hatalar:
            from takip.messages_util import hatalari_ozetle

            hatalari_ozetle(request, hatalar, tek_baslik="Puan kaydı hatalı")
        else:
            messages.success(
                request,
                f"{kaydedilen} öğrenci puanı kaydedildi.",
            )
            return redirect("yazili_sonuc_gir", pk=sinav.pk)

    return render(
        request,
        "yazili_sonuc_gir.html",
        {
            "sinav": sinav,
            "kamp": sinav.kamp,
            "satirlar": sonuc_giris_satirlari(request.user, sinav),
            "pdf_yetkisi": can(request.user, "yazili_takip", "export_pdf"),
        },
    )


@login_required
@require_permission("yazili_takip", "export_pdf")
def yazili_kamp_pdf(request, pk):
    kamp = get_object_or_404(yetkili_kamplar(request.user), pk=pk)
    sinavlar = list(yetkili_sinavlar(request.user, kamp))

    sinav_verileri = []
    for sinav in sinavlar:
        sinav_verileri.append(
            {
                "sinav": sinav,
                "satirlar": sinav_sonuclari_sirali(request.user, sinav),
            }
        )

    html = render(
        request,
        "yazili_kamp_pdf.html",
        {
            "kamp": kamp,
            "sinav_verileri": sinav_verileri,
            "istatistik": kamp_ozet_istatistik(request.user, kamp),
            "bugun": localdate(),
        },
    ).content.decode("utf-8")

    pdf_verisi = html_to_pdf(html)
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    return make_pdf_response(
        pdf_verisi,
        f"yazili_kamp_{kamp.pk}_{localdate():%Y%m%d}.pdf",
    )


@login_required
@require_permission("yazili_takip", "export_pdf")
def yazili_sinav_sirali_pdf(request, pk):
    """Tek sınav — SN / ad soyad / puan sıralı PDF."""
    sinav = get_object_or_404(
        yetkili_sinavlar(request.user).select_related("kamp"),
        pk=pk,
    )
    satirlar = sinav_sonuclari_sirali(request.user, sinav)
    istatistik = YaziliSonuc.objects.filter(sinav=sinav).aggregate(
        ortalama=Avg("puan"),
        en_yuksek=Max("puan"),
    )
    from config.branding import PANEL_NAME, PANEL_ORG, PANEL_SHORT

    html = render(
        request,
        "yazili_sinav_sirali_pdf.html",
        {
            "sinav": sinav,
            "satirlar": satirlar,
            "toplam_talebe": len(satirlar),
            "sinif_ortalamasi": istatistik["ortalama"] or Decimal("0.00"),
            "en_yuksek_puan": istatistik["en_yuksek"] or Decimal("0.00"),
            "etut_hocasi": _etut_etiket(request.user),
            "bugun": localdate(),
            "panel_org": PANEL_ORG,
            "panel_name": PANEL_NAME,
            "panel_short": PANEL_SHORT,
        },
    ).content.decode("utf-8")

    pdf_verisi = html_to_pdf(
        html,
        base_url=request.build_absolute_uri("/"),
    )
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    safe = slugify(f"{sinav.ders_ad}_{sinav.yazili_no}_{sinav.tur}") or f"yazili_{sinav.pk}"
    return make_pdf_response(
        pdf_verisi,
        f"yazili_sirali_{safe}_{localdate():%Y%m%d}.pdf",
    )


@login_required
@require_permission("yazili_takip", "export_pdf")
def yazili_sinav_bireysel_pdf(request, pk, talebe_id=None):
    """Bireysel karne — tek talebe veya tüm sonuçlar (çok sayfa)."""
    sinav = get_object_or_404(
        yetkili_sinavlar(request.user).select_related("kamp", "ders"),
        pk=pk,
    )
    satirlar = sinav_sonuclari_sirali(request.user, sinav)
    if not satirlar:
        messages.error(request, "Bu yazılıya ait sonuç bulunamadı.")
        return redirect("yazili_sonuc_gir", pk=sinav.pk)

    if talebe_id is not None:
        satirlar = [s for s in satirlar if s["sonuc"].talebe_id == int(talebe_id)]
        if not satirlar:
            messages.error(request, "Talebe sonucu bulunamadı.")
            return redirect("yazili_sonuc_gir", pk=sinav.pk)

    istatistik = YaziliSonuc.objects.filter(sinav=sinav).aggregate(
        ortalama=Avg("puan"),
        en_yuksek=Max("puan"),
    )
    tum = sinav_sonuclari_sirali(request.user, sinav)

    html = render(
        request,
        "yazili_sinav_bireysel_pdf.html",
        {
            "sinav": sinav,
            "satirlar": satirlar,
            "toplam_talebe": len(tum),
            "sinif_ortalamasi": istatistik["ortalama"] or Decimal("0.00"),
            "en_yuksek_puan": istatistik["en_yuksek"] or Decimal("0.00"),
            "etut_hocasi": _etut_etiket(request.user),
            "bugun": localdate(),
        },
    ).content.decode("utf-8")

    pdf_verisi = html_to_pdf(
        html,
        base_url=request.build_absolute_uri("/"),
    )
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    safe = slugify(sinav.ad) or f"yazili_{sinav.pk}"
    suffix = f"_t{talebe_id}" if talebe_id else "_tum"
    return make_pdf_response(
        pdf_verisi,
        f"yazili_bireysel_{safe}{suffix}_{localdate():%Y%m%d}.pdf",
    )


@login_required
@require_permission("yazili_takip", "view")
def yazili_sinav_excel_sablon(request, pk):
    """Boş puan giriş şablonu (Excel)."""
    from io import BytesIO

    from django.http import HttpResponse

    try:
        from openpyxl import Workbook
    except ImportError:
        messages.error(
            request,
            "Excel şablonu için openpyxl gerekli. Sunucuda 'pip install openpyxl' çalıştırın.",
        )
        return redirect("yazili_kamp_listesi")

    sinav = get_object_or_404(
        yetkili_sinavlar(request.user).select_related("kamp"),
        pk=pk,
    )
    talebeler = list(sinav_sonuc_talebeleri(request.user, sinav))

    wb = Workbook()
    ws = wb.active
    ws.title = "Sonuclar"
    ws.append(
        [
            "talebe_id",
            "sn",
            "ad_soyad",
            "sinif",
            "ders",
            "yazili_no",
            "tur",
            "puan",
        ]
    )
    for i, t in enumerate(talebeler, start=1):
        sinif = str(t.sinif_sube) if t.sinif_sube_id else (t.sinif or "")
        ws.append(
            [
                t.pk,
                i,
                t.ad_soyad,
                sinif,
                sinav.ders_ad,
                sinav.yazili_no,
                sinav.tur,
                "",
            ]
        )

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = (
        f'attachment; filename="yazili_sablon_{sinav.pk}.xlsx"'
    )
    return resp
