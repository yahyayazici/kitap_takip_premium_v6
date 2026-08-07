"""Finans yönetim merkezi görünümleri."""

from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
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
    dosya_listesi_filtrele,
    finans_analiz,
    finans_dosya_olustur,
    finans_seed_verisi,
    finans_yonetebilir,
    odeme_plani_olustur,
    sag_panel_verisi,
    sinif_sube_secenekleri,
    tahsilat_ekle,
    yetkili_finans_dosyalari,
    yeni_yil_politikasi_kopyala,
)
from takip.models import Talebe
from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.wave0_models import EgitimYili


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
    sag = sag_panel_verisi(request.user, yetkili_finans_dosyalari(request.user).filter(egitim_yili=yil) if yil else yetkili_finans_dosyalari(request.user))
    grafik = aylik_tahsilat_grafik(request.user, qs)
    analiz = finans_analiz(request.user, qs)

    yeni_form = None
    if finans_yonetebilir(request.user) and request.method == "POST" and request.POST.get("action") == "yeni_kayit":
        yeni_form = FinansYeniKayitForm(request.POST)
        if yeni_form.is_valid():
            talebe = get_object_or_404(Talebe, pk=int(yeni_form.cleaned_data["talebe_id"]))
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

    if yeni_form is None and finans_yonetebilir(request.user):
        mevcut_ids = set(qs.values_list("talebe_id", flat=True))
        talebe_secenekleri = Talebe.objects.filter(aktif=True).exclude(id__in=mevcut_ids).order_by("ad_soyad")[:200]
        yeni_form = FinansYeniKayitForm()
        yeni_form.fields["talebe_id"].choices = [
            (str(t.pk), f"{t.ad_soyad} · {t.sinif_sube or t.sinif}") for t in talebe_secenekleri
        ]

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
            "yonetebilir": finans_yonetebilir(request.user),
            "tahsilat_girebilir": can(request.user, "aidat", "edit"),
            "yeni_form": yeni_form if finans_yonetebilir(request.user) else None,
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

    if can(request.user, "aidat", "edit"):
        if request.method == "POST":
            action = request.POST.get("action", "tahsilat")
            if action == "tahsilat":
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
            elif action == "odeme_plani" and finans_yonetebilir(request.user):
                pesinat = Decimal(request.POST.get("pesinat") or "0")
                taksit_sayisi = int(request.POST.get("taksit_sayisi") or 10)
                odeme_plani_olustur(
                    dosya,
                    pesinat=pesinat,
                    taksit_sayisi=taksit_sayisi,
                    ilk_vade=localdate().replace(day=10),
                )
                messages.success(request, "Ödeme planı güncellendi.")
                return redirect("finans_ogrenci", pk=dosya.pk)
        else:
            tahsilat_form = FinansTahsilatForm(initial={"tarih": localdate(), "tutar": dosya.kalan_tutar})

    return render(
        request,
        "finans/ogrenci.html",
        {
            "dosya": dosya,
            "talebe": talebe,
            "taksitler": taksitler,
            "tahsilatlar": tahsilatlar,
            "tahsilat_form": tahsilat_form,
            "yonetebilir": finans_yonetebilir(request.user),
            "tahsilat_girebilir": can(request.user, "aidat", "edit"),
        },
    )


@login_required
@require_permission("aidat", "edit")
def finans_politikalar(request):
    if not finans_yonetebilir(request.user):
        return HttpResponseForbidden("Politika yönetimi için yetkiniz yok.")

    finans_seed_verisi()
    yillar = EgitimYili.objects.order_by("-baslangic")
    secili_yil_id = request.GET.get("yil") or (aktif_egitim_yili().pk if aktif_egitim_yili() else None)
    secili_yil = get_object_or_404(EgitimYili, pk=secili_yil_id) if secili_yil_id else None

    if request.method == "POST":
        action = request.POST.get("action")
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
    qs = yetkili_finans_dosyalari(request.user)
    yil = aktif_egitim_yili()
    if yil:
        qs = qs.filter(egitim_yili=yil)

    return render(
        request,
        "finans/raporlar.html",
        {
            "dosya_sayisi": qs.count(),
            "ozet": dashboard_ozet(request.user, yil),
            "sinif_subeler": sinif_sube_secenekleri(),
            "durum_secenekleri": TalebeFinansDosyasi.Durum.choices,
        },
    )


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
