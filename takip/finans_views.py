"""Finans yönetim merkezi görünümleri."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.timezone import localdate

from takip.finans_forms import (
    FinansIndirimForm,
    FinansTahsilatForm,
    FinansYeniKayitForm,
)
from takip.finans_models import (
    FinansIndirim,
    FinansKampanya,
    FinansTaksit,
    FinansUcretPolitikasi,
    TalebeFinansDosyasi,
)
from takip.finans_service import (
    DEFAULT_UCRETLER,
    aktif_egitim_yili,
    aylik_tahsilat_grafik,
    dashboard_ozet,
    dosya_indirim_uygula,
    dosya_listesi_filtrele,
    dosyasiz_yetkili_talebeler,
    ensure_egitim_yili,
    finans_analiz,
    finans_dosya_olustur,
    finans_rapor_filtre_etiketi,
    finans_rapor_ozet,
    finans_rapor_satirlari,
    finans_rapor_sorgusu,
    finans_seed_verisi,
    finans_tahsilat_girebilir,
    finans_yonetebilir,
    odeme_plani_olustur,
    rapor_filtre_dict,
    sag_panel_verisi,
    sinif_sube_secenekleri,
    tahsilat_ekle,
    talebe_finans_yetkisi_var,
    toplu_finans_dosya_olustur,
    yetkili_finans_dosyalari,
    yeni_yil_politikasi_kopyala,
)
from takip.models import Talebe
from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.wave0_models import EgitimYili


def _parse_decimal(raw, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(raw or default).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


@login_required
@require_permission("aidat", "view")
def finans_panel(request):
    finans_seed_verisi()
    yil = aktif_egitim_yili()
    qs = yetkili_finans_dosyalari(request.user)
    if yil:
        qs = qs.filter(egitim_yili=yil)

    q = request.GET.get("q", "").strip()
    sinif_sube_id = request.GET.get("sinif", "").strip()
    durum = request.GET.get("durum", "").strip()
    qs = dosya_listesi_filtrele(
        qs,
        q=q or None,
        sinif_sube_id=sinif_sube_id or None,
        durum=durum or None,
    ).order_by("talebe__ad_soyad")

    ozet = dashboard_ozet(request.user, yil)
    sag = sag_panel_verisi(
        request.user,
        yetkili_finans_dosyalari(request.user).filter(egitim_yili=yil) if yil else yetkili_finans_dosyalari(request.user),
    )
    grafik = aylik_tahsilat_grafik(request.user, qs)
    analiz = finans_analiz(request.user, qs)

    yonetebilir = finans_yonetebilir(request.user)
    tahsilat_girebilir = finans_tahsilat_girebilir(request.user)
    dosyasiz = list(dosyasiz_yetkili_talebeler(request.user, yil)) if yil and yonetebilir else []

    yeni_form = None
    if yonetebilir and request.method == "POST":
        action = request.POST.get("action")
        if action == "yeni_kayit":
            yeni_form = FinansYeniKayitForm(request.POST)
            if yeni_form.is_valid():
                talebe = get_object_or_404(Talebe, pk=int(yeni_form.cleaned_data["talebe_id"]))
                if not talebe_finans_yetkisi_var(request.user, talebe):
                    return HttpResponseForbidden("Bu talebe için yetkiniz yok.")
                if not yil:
                    messages.error(request, "Aktif eğitim yılı bulunamadı.")
                else:
                    finans_dosya_olustur(
                        talebe,
                        yil,
                        indirim_tutari=yeni_form.cleaned_data.get("indirim_tutari") or Decimal("0"),
                        pesinat=yeni_form.cleaned_data.get("pesinat") or Decimal("0"),
                        taksit_sayisi=yeni_form.cleaned_data["taksit_sayisi"],
                        user=request.user,
                    )
                    messages.success(request, f"{talebe.ad_soyad} için finans dosyası oluşturuldu.")
                    dosya = TalebeFinansDosyasi.objects.filter(talebe=talebe, egitim_yili=yil).first()
                    if dosya:
                        return redirect("finans_ogrenci", pk=dosya.pk)
                    return redirect("finans_panel")
        elif action == "toplu_kayit":
            if not yil:
                messages.error(request, "Aktif eğitim yılı bulunamadı.")
                return redirect("finans_panel")
            raw_ids = request.POST.getlist("talebe_ids")
            if request.POST.get("hepsi") == "1":
                raw_ids = [str(t.pk) for t in dosyasiz]
            try:
                talebe_ids = [int(x) for x in raw_ids if str(x).isdigit()]
            except (TypeError, ValueError):
                talebe_ids = []
            if not talebe_ids:
                messages.error(request, "En az bir talebe seçin.")
                return redirect("finans_panel")
            sonuc = toplu_finans_dosya_olustur(
                request.user,
                yil,
                talebe_ids,
                pesinat=_parse_decimal(request.POST.get("pesinat")),
                taksit_sayisi=max(1, min(24, int(request.POST.get("taksit_sayisi") or 10))),
                ilk_vade=_parse_date(request.POST.get("ilk_vade")),
            )
            messages.success(
                request,
                (
                    f"Toplu aidat: {sonuc['olusturulan']} oluşturuldu"
                    + (f", {sonuc['atlanan']} atlandı" if sonuc["atlanan"] else "")
                    + (f", {sonuc['yetkisiz']} yetkisiz" if sonuc["yetkisiz"] else "")
                    + "."
                ),
            )
            return redirect("finans_panel")

    if yeni_form is None and yonetebilir:
        yeni_form = FinansYeniKayitForm()
        yeni_form.fields["talebe_id"].choices = [
            (str(t.pk), f"{t.ad_soyad} · {t.sinif_sube or t.sinif}") for t in dosyasiz[:200]
        ]

    kapsam = (
        "Admin · aidat / taksit tanımları"
        if yonetebilir
        else "Etüt grubunuz · tahsilat girişi ve takip"
    )

    return render(
        request,
        "finans/panel.html",
        {
            "dosyalar": qs[:150],
            "ozet": ozet,
            "sag": sag,
            "grafik": grafik,
            "analiz": analiz,
            "filtre_q": q,
            "filtre_sinif": sinif_sube_id,
            "filtre_durum": durum,
            "sinif_subeler": sinif_sube_secenekleri(),
            "durum_secenekleri": TalebeFinansDosyasi.Durum.choices,
            "yil": yil,
            "yonetebilir": yonetebilir,
            "tahsilat_girebilir": tahsilat_girebilir,
            "yeni_form": yeni_form if yonetebilir else None,
            "dosyasiz_talebeler": dosyasiz,
            "kapsam_etiket": kapsam,
        },
    )


@login_required
@require_permission("aidat", "view")
def finans_ogrenci(request, pk):
    dosya = get_object_or_404(
        yetkili_finans_dosyalari(request.user).select_related(
            "talebe",
            "talebe__sinif_sube",
            "talebe__etut_hocasi",
            "egitim_yili",
        ),
        pk=pk,
    )
    talebe = dosya.talebe
    taksitler = dosya.taksitler.all()
    tahsilatlar = dosya.tahsilatlar.select_related("kaydeden", "taksit").order_by("-tarih", "-id")
    tahsilat_form = None
    yonetebilir = finans_yonetebilir(request.user)
    tahsilat_girebilir = finans_tahsilat_girebilir(request.user)
    indirimler = FinansIndirim.objects.filter(aktif=True).order_by("sira", "ad") if yonetebilir else []

    if request.method == "POST":
        action = request.POST.get("action", "tahsilat")
        if action == "tahsilat" and tahsilat_girebilir:
            tahsilat_form = FinansTahsilatForm(request.POST)
            if tahsilat_form.is_valid():
                taksit = None
                taksit_id = tahsilat_form.cleaned_data.get("taksit_id")
                if taksit_id:
                    taksit = get_object_or_404(FinansTaksit, pk=taksit_id, dosya=dosya)
                tahsilat_ekle(
                    dosya,
                    tutar=tahsilat_form.cleaned_data["tutar"],
                    tarih=tahsilat_form.cleaned_data["tarih"],
                    yontem=tahsilat_form.cleaned_data["yontem"],
                    tur=tahsilat_form.cleaned_data["tur"],
                    aciklama=tahsilat_form.cleaned_data.get("aciklama") or "",
                    taksit=taksit,
                    user=request.user,
                )
                messages.success(request, "Tahsilat kaydedildi.")
                return redirect("finans_ogrenci", pk=dosya.pk)
        elif action == "odeme_plani" and yonetebilir:
            pesinat = _parse_decimal(request.POST.get("pesinat"))
            taksit_sayisi = max(1, min(24, int(request.POST.get("taksit_sayisi") or 10)))
            if dosya.tahsilatlar.filter(iptal=False).exists():
                messages.warning(request, "Tahsilat olduğu için plan yeniden yazılmadı.")
            else:
                odeme_plani_olustur(
                    dosya,
                    pesinat=pesinat,
                    taksit_sayisi=taksit_sayisi,
                    ilk_vade=localdate().replace(day=10),
                )
                messages.success(request, "Ödeme planı güncellendi.")
            return redirect("finans_ogrenci", pk=dosya.pk)
        elif action == "indirim" and yonetebilir:
            kod = (request.POST.get("indirim_kodu") or "").strip() or None
            raw_tutar = (request.POST.get("indirim_tutari") or "").strip()
            tutar = _parse_decimal(raw_tutar) if raw_tutar else None
            if not kod and tutar is None:
                messages.error(request, "İndirim seçin veya tutar girin.")
                return redirect("finans_ogrenci", pk=dosya.pk)
            _, notu = dosya_indirim_uygula(
                dosya,
                indirim_kodu=kod,
                indirim_tutari=tutar,
                user=request.user,
            )
            messages.success(request, notu)
            return redirect("finans_ogrenci", pk=dosya.pk)
        else:
            return HttpResponseForbidden("Bu işlem için yetkiniz yok.")
    elif tahsilat_girebilir:
        tahsilat_form = FinansTahsilatForm(
            initial={"tarih": localdate(), "tutar": dosya.kalan_tutar}
        )

    return render(
        request,
        "finans/ogrenci.html",
        {
            "dosya": dosya,
            "talebe": talebe,
            "taksitler": taksitler,
            "tahsilatlar": tahsilatlar,
            "tahsilat_form": tahsilat_form,
            "yonetebilir": yonetebilir,
            "tahsilat_girebilir": tahsilat_girebilir,
            "indirimler": indirimler,
        },
    )


@login_required
@require_permission("aidat", "edit")
def finans_politikalar(request):
    if not finans_yonetebilir(request.user):
        return HttpResponseForbidden("Politika yönetimi için yetkiniz yok.")

    finans_seed_verisi()
    yillar = EgitimYili.objects.order_by("-baslangic")
    aktif = aktif_egitim_yili() or ensure_egitim_yili()
    secili_yil_id = request.GET.get("yil") or str(aktif.pk)
    secili_yil = get_object_or_404(EgitimYili, pk=secili_yil_id)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "yil_olustur":
            ad = (request.POST.get("ad") or "").strip()
            try:
                bas = date.fromisoformat(request.POST.get("baslangic") or "")
                bit = date.fromisoformat(request.POST.get("bitis") or "")
            except ValueError:
                messages.error(request, "Geçerli başlangıç / bitiş tarihi girin.")
                return redirect("finans_politikalar")
            if not ad:
                ad = f"{bas.year}-{bit.year}"
            if bit < bas:
                messages.error(request, "Bitiş tarihi başlangıçtan önce olamaz.")
                return redirect("finans_politikalar")
            yil, created = EgitimYili.objects.get_or_create(
                ad=ad,
                defaults={"baslangic": bas, "bitis": bit, "aktif": True},
            )
            if created:
                EgitimYili.objects.exclude(pk=yil.pk).update(aktif=False)
                finans_seed_verisi()
                messages.success(request, f"{yil.ad} eğitim yılı oluşturuldu.")
            else:
                messages.info(request, f"{yil.ad} zaten tanımlı.")
            return redirect(f"{request.path}?yil={yil.pk}")
        if action == "kopyala" and secili_yil:
            hedef_id = request.POST.get("hedef_yil")
            hedef = get_object_or_404(EgitimYili, pk=hedef_id)
            adet = yeni_yil_politikasi_kopyala(secili_yil, hedef)
            messages.success(request, f"{adet} politika {hedef.ad} yılına kopyalandı.")
            return redirect(f"{request.path}?yil={hedef.pk}")
        elif action == "kaydet" and secili_yil:
            sinif = request.POST.get("sinif_seviyesi")
            tutar = Decimal(request.POST.get("tutar") or "0")
            politika, _ = FinansUcretPolitikasi.objects.get_or_create(
                egitim_yili=secili_yil,
                sinif_seviyesi=sinif,
                defaults={"tutar": tutar, "aktif": True},
            )
            politika.tutar = tutar
            politika.aktif = request.POST.get("aktif") == "on"
            politika.save()
            messages.success(request, "Politika güncellendi.")
            return redirect(f"{request.path}?yil={secili_yil.pk}")

    politikalar = []
    if secili_yil:
        mevcut = {p.sinif_seviyesi: p for p in FinansUcretPolitikasi.objects.filter(egitim_yili=secili_yil)}
        for kod, etiket in FinansUcretPolitikasi.SINIF_SECENEKLERI:
            p = mevcut.get(kod)
            politikalar.append(
                {
                    "sinif_seviyesi": kod,
                    "etiket": etiket,
                    "tutar": p.tutar if p else DEFAULT_UCRETLER.get(kod, Decimal("92000")),
                    "aktif": p.aktif if p else True,
                    "kayitli": bool(p),
                }
            )

    return render(
        request,
        "finans/politikalar.html",
        {
            "yillar": yillar,
            "secili_yil": secili_yil,
            "politikalar": politikalar,
            "sinif_secenekleri": FinansUcretPolitikasi.SINIF_SECENEKLERI,
        },
    )


@login_required
@require_permission("aidat", "edit")
def finans_indirimler(request):
    if not finans_yonetebilir(request.user):
        return HttpResponseForbidden("İndirim yönetimi için yetkiniz yok.")

    finans_seed_verisi()
    indirim = None
    form = None

    if request.method == "POST":
        pk = request.POST.get("pk")
        if pk:
            indirim = get_object_or_404(FinansIndirim, pk=pk)
            form = FinansIndirimForm(request.POST, instance=indirim)
        else:
            form = FinansIndirimForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "İndirim kaydedildi.")
            return redirect("finans_indirimler")

    edit_pk = request.GET.get("duzenle")
    if edit_pk:
        indirim = get_object_or_404(FinansIndirim, pk=edit_pk)
        form = FinansIndirimForm(instance=indirim)

    indirimler = FinansIndirim.objects.all()
    kampanyalar = FinansKampanya.objects.select_related("indirim").order_by("-baslangic")[:12]

    return render(
        request,
        "finans/indirimler.html",
        {
            "indirimler": indirimler,
            "kampanyalar": kampanyalar,
            "form": form,
            "duzenlenen": indirim,
        },
    )


@login_required
@require_permission("aidat", "view")
def finans_raporlar(request):
    finans_seed_verisi()
    yil = aktif_egitim_yili()
    filtre = rapor_filtre_dict(request)
    qs = finans_rapor_sorgusu(request.user, filtre)
    ozet = finans_rapor_ozet(qs, filtre)
    satirlar = finans_rapor_satirlari(qs[:500])

    return render(
        request,
        "finans/raporlar.html",
        {
            "yil": yil,
            "dosya_sayisi": ozet["dosya_sayisi"],
            "ozet": ozet,
            "satirlar": satirlar,
            "filtre": filtre,
            "filtre_q": filtre.get("q") or "",
            "filtre_sinif": filtre.get("sinif_sube_id") or "",
            "filtre_durum": filtre.get("durum") or "",
            "filtre_baslangic": filtre.get("baslangic").isoformat() if filtre.get("baslangic") else "",
            "filtre_bitis": filtre.get("bitis").isoformat() if filtre.get("bitis") else "",
            "filtre_etiketi": finans_rapor_filtre_etiketi(filtre),
            "sinif_subeler": sinif_sube_secenekleri(),
            "durum_secenekleri": TalebeFinansDosyasi.Durum.choices,
            "export_qs": request.GET.urlencode(),
        },
    )


def _finans_rapor_verisi(request):
    filtre = rapor_filtre_dict(request)
    qs = finans_rapor_sorgusu(request.user, filtre)
    ozet = finans_rapor_ozet(qs, filtre)
    satirlar = finans_rapor_satirlari(qs[:500])
    yil = aktif_egitim_yili()
    return filtre, qs, ozet, satirlar, yil


@login_required
@require_permission("aidat", "view")
def finans_rapor_pdf(request):
    from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response

    filtre, _, ozet, satirlar, yil = _finans_rapor_verisi(request)
    html = render_to_string(
        "finans/rapor_pdf.html",
        {
            "satirlar": satirlar,
            "ozet": ozet,
            "yil": yil,
            "filtre_etiketi": finans_rapor_filtre_etiketi(filtre),
            "olusturma_tarihi": localdate(),
        },
        request=request,
    )
    pdf_verisi = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})")
    return make_pdf_response(
        pdf_verisi,
        f"finans-rapor-{localdate():%Y%m%d}.pdf",
    )


@login_required
@require_permission("aidat", "view")
def finans_rapor_excel(request):
    from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit
    from takip.finans_service import _para_metin

    filtre, _, ozet, satirlar, yil = _finans_rapor_verisi(request)
    excel_satirlar = [
        [
            s["ad_soyad"].upper(),
            s["talebe_no"],
            s["sinif"],
            _para_metin(s["toplam_ucret"]),
            _para_metin(s["indirim_tutari"]),
            _para_metin(s["net_ucret"]),
            _para_metin(s["odenen_tutar"]),
            _para_metin(s["kalan_tutar"]),
            s["durum"],
        ]
        for s in satirlar
    ]
    excel_satirlar.append(
        [
            "TOPLAM",
            "",
            f"{ozet['dosya_sayisi']} kayıt",
            "",
            "",
            _para_metin(ozet["toplam_net"]),
            _para_metin(ozet["tahsil_edilen"]),
            _para_metin(ozet["bekleyen"]),
            "",
        ]
    )
    alt = finans_rapor_filtre_etiketi(filtre)
    if yil:
        alt = f"{yil.ad} · {alt}" if alt else yil.ad
    icerik = basit_rapor_xlsx(
        baslik="Finans Raporu",
        alt_baslik=alt or localdate().strftime("%d.%m.%Y"),
        kolon_basliklari=[
            "Ad-Soyad", "No", "Sınıf", "Toplam", "İndirim",
            "Net", "Ödenen", "Kalan", "Durum",
        ],
        satirlar=excel_satirlar,
        sayfa_adi="Finans",
        durum_kolonlari=[8],
        vurgu_kolonlari=[5, 6, 7],
        buyuk_harf_kolonlari=[0],
        genislikler=[26, 10, 10, 12, 12, 12, 12, 12, 14],
    )
    return excel_http_yanit(icerik, f"finans_rapor_{localdate():%Y%m%d}.xlsx")


@login_required
@require_permission("aidat", "view")
def finans_ayarlar(request):
    if not finans_yonetebilir(request.user):
        return HttpResponseForbidden("Finans ayarları için yetkiniz yok.")
    return render(request, "finans/ayarlar.html", {"yil": aktif_egitim_yili()})


@login_required
@require_permission("aidat", "view")
def aidat_listesi_yonlendir(request):
    return redirect("finans_panel")
