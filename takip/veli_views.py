"""Veli paneli görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.timezone import localdate

from config.branding import panel_branding_context
from takip.duyuru_service import veli_duyurulari
from takip.ogretmen_not_service import talebe_karne_verisi
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.veli_goruntuleme_service import (
    dini_ders_goruntulendi,
    duyurular_goruntulendi,
    sayfa_goruntulendi,
    sinav_sayfasi_goruntulendi,
)
from takip.veli_randevu_forms import VeliRandevuOlusturForm
from takip.veli_randevu_models import VeliRandevu
from takip.veli_randevu_service import (
    musait_slotlar,
    randevu_olustur,
    veli_icin_personeller,
    veli_randevulari,
)
from takip.veli_service import (
    aktif_sohbet_mevzulari,
    dini_ders_mufredat_detay,
    kullanici_veli_mi,
    talebe_haftalik_notlar,
    talebe_kpi_ozeti,
    talebe_namaz_30_gun,
    talebe_sinif_goster,
    talebe_soru_detay,
    talebe_veli_mudahaleleri,
    talebe_veli_ozeti,
    talebe_yakinlik,
    talebe_yoklama_30_gun,
    veli_dashboard_verisi,
    veli_hesabi_for_user,
    veli_talebe_getir,
    veli_talebeleri,
)


def _veli_hesap(request):
    hesap = veli_hesabi_for_user(request.user)
    if not hesap or not hesap.aktif:
        return None
    return hesap


def _veli_talebe_yukle(request, talebe_id: int):
    veli = _veli_hesap(request)
    if not veli:
        return None, None
    talebe = veli_talebe_getir(veli, talebe_id)
    if not talebe:
        raise Http404
    return veli, talebe


def _talebe_sayfa(request, veli, talebe, template, aktif_sekme, extra=None):
    context = {
        "veli": veli,
        "talebe": talebe,
        "talebeler": list(veli_talebeleri(veli)),
        "aktif_sekme": aktif_sekme,
        "kpi": talebe_kpi_ozeti(talebe),
        "sinif_goster": talebe_sinif_goster(talebe),
        "yakinlik": talebe_yakinlik(veli, talebe),
    }
    if extra:
        context.update(extra)
    return render(request, template, context)


@login_required
def veli_dashboard(request):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")

    veli = _veli_hesap(request)
    if not veli:
        return redirect("logout")

    context = veli_dashboard_verisi(veli)
    if len(context["talebeler"]) == 1:
        return redirect(
            "veli_talebe_dashboard",
            talebe_id=context["talebeler"][0].pk,
        )

    sayfa_goruntulendi(veli, "veli_dashboard")
    from takip.dashboard_service import dashboard_kisayollari

    context["kisayollar"] = dashboard_kisayollari(hedef="veli")
    return render(request, "veli/dashboard.html", context)


@login_required
def veli_talebe_detay(request, talebe_id: int):
    return redirect("veli_talebe_dashboard", talebe_id=talebe_id)


@login_required
def veli_talebe_dashboard(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    duyurular = list(veli_duyurulari()[:8])
    sayfa_goruntulendi(veli, "veli_talebe_dashboard", talebe=talebe)
    duyurular_goruntulendi(veli, duyurular, sayfa="veli_talebe_dashboard")
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_dashboard.html",
        "dashboard",
        {"duyurular": duyurular},
    )


@login_required
def veli_talebe_profil(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    ozet = talebe_veli_ozeti(talebe, sinav_verisi=False)
    sayfa_goruntulendi(veli, "veli_talebe_profil", talebe=talebe)
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_profil.html",
        "profil",
        {
            "haftalik_soru": ozet["haftalik_soru"],
            "aylik_soru": ozet["aylik_soru"],
            "dini_ders_ozet": ozet["dini_ders_ozet"],
            "mudahaleler": ozet["mudahaleler"][:5],
        },
    )


@login_required
def veli_talebe_sinavlar(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    ozet = talebe_veli_ozeti(talebe, sinav_verisi=True)
    tab = request.GET.get("tab", "ktt")
    if tab not in {"ktt", "deneme", "ogretmen", "yazili"}:
        tab = "ktt"
    sinav_sayfasi_goruntulendi(
        veli,
        talebe,
        tab,
        ktt_sonuclari=ozet["ktt_sonuclari"],
        deneme_sonuclari=ozet["deneme_sonuclari"],
        yazili_sonuclari=ozet["yazili_sonuclari"],
    )
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_sinavlar.html",
        "sinavlar",
        {
            "sinav_tab": tab,
            "ktt_sonuclari": ozet["ktt_sonuclari"],
            "deneme_sonuclari": ozet["deneme_sonuclari"],
            "deneme_performans": ozet["deneme_performans"],
            "yazili_sonuclari": ozet["yazili_sonuclari"],
            "ogretmen_notlari": ozet["ogretmen_notlari"],
        },
    )


@login_required
def veli_talebe_degerlendirme_karne_pdf(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    _veli, talebe = _veli_talebe_yukle(request, talebe_id)
    ctx = talebe_karne_verisi(talebe, sadece_veliye_acik=True)
    ctx.update(panel_branding_context())
    ctx["bugun"] = localdate()
    html_metni = render_to_string(
        "ogretmen_degerlendirme_karne_pdf.html",
        ctx,
        request=request,
    )
    pdf_verisi = html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        messages.error(
            request,
            f"Karne PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )
        return redirect("veli_talebe_sinavlar", talebe_id=talebe.id)
    ad = talebe.ad_soyad.replace(" ", "-")
    return make_pdf_response(pdf_verisi, f"{ad}-degerlendirme-karnesi.pdf")


@login_required
def veli_talebe_dini_ders(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    mufredat = dini_ders_mufredat_detay(talebe)
    alan_id = request.GET.get("alan")
    secili_alan = None
    if mufredat and alan_id:
        secili_alan = next(
            (a for a in mufredat["alanlar"] if str(a["id"]) == str(alan_id)),
            None,
        )
    if mufredat and not secili_alan and mufredat["alanlar"]:
        secili_alan = mufredat["alanlar"][0]

    alan_id = secili_alan["id"] if secili_alan else None
    dini_ders_goruntulendi(veli, talebe, alan_id=alan_id)

    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_dini_ders.html",
        "dini_ders",
        {
            "mufredat": mufredat,
            "secili_alan": secili_alan,
        },
    )


@login_required
def veli_talebe_aidat(request, talebe_id: int):
    return redirect("veli_talebe_dashboard", talebe_id=talebe_id)


@login_required
def veli_talebe_soru(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    sayfa_goruntulendi(veli, "veli_talebe_soru", talebe=talebe)
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_soru.html",
        "soru",
        {"soru": talebe_soru_detay(talebe)},
    )


@login_required
def veli_talebe_ders_notlari(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    hafta = request.GET.get("hafta")
    hafta_bas = None
    if hafta:
        from datetime import date

        try:
            hafta_bas = date.fromisoformat(hafta)
        except ValueError:
            hafta_bas = None
    data = talebe_haftalik_notlar(talebe, hafta_baslangic=hafta_bas)
    sayfa_goruntulendi(veli, "veli_talebe_ders_notlari", talebe=talebe)
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_ders_notlari.html",
        "ders_notlari",
        data,
    )


@login_required
def veli_talebe_yoklama(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    sayfa_goruntulendi(veli, "veli_talebe_yoklama", talebe=talebe)
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_yoklama.html",
        "yoklama",
        {"yoklama": talebe_yoklama_30_gun(talebe)},
    )


@login_required
def veli_talebe_namaz(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    sayfa_goruntulendi(veli, "veli_talebe_namaz", talebe=talebe)
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_namaz.html",
        "namaz",
        {"namaz": talebe_namaz_30_gun(talebe)},
    )


@login_required
def veli_talebe_mudahale(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    sayfa_goruntulendi(veli, "veli_talebe_mudahale", talebe=talebe)
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_mudahale.html",
        "mudahale",
        {"mudahaleler": talebe_veli_mudahaleleri(talebe)},
    )


@login_required
def veli_talebe_sohbet(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    sayfa_goruntulendi(veli, "veli_talebe_sohbet", talebe=talebe)
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_sohbet.html",
        "sohbet",
        {"mevzular": aktif_sohbet_mevzulari()},
    )


@login_required
def veli_talebe_randevu(request, talebe_id: int):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")
    veli, talebe = _veli_talebe_yukle(request, talebe_id)
    personeller = veli_icin_personeller(talebe)
    randevular = veli_randevulari(veli, talebe)[:20]

    secili_personel_id = request.GET.get("personel") or request.POST.get("personel_id")
    slotlar = []
    secili_personel = None
    if secili_personel_id:
        secili_personel = personeller.filter(pk=secili_personel_id).first()
        if secili_personel:
            slotlar = musait_slotlar(secili_personel)

    if request.method == "POST" and request.POST.get("action") == "iptal":
        rid = request.POST.get("randevu_id")
        randevu = get_object_or_404(VeliRandevu, pk=rid, veli=veli, talebe=talebe)
        if randevu.durum == VeliRandevu.Durum.PLANLANDI:
            randevu.durum = VeliRandevu.Durum.IPTAL_VELI
            randevu.save(update_fields=["durum", "guncellenme"])
            messages.success(request, "Randevunuz iptal edildi.")
        return redirect("veli_talebe_randevu", talebe_id=talebe.pk)

    form = VeliRandevuOlusturForm()
    form.fields["personel_id"].queryset = personeller
    form.fields["slot"].choices = [("", "— Önce personel seçin —")] + [
        (s["value"], s["etiket"]) for s in slotlar
    ]
    if secili_personel:
        form.initial["personel_id"] = secili_personel.pk

    if request.method == "POST" and request.POST.get("action") == "olustur":
        form = VeliRandevuOlusturForm(request.POST)
        form.fields["personel_id"].queryset = personeller
        personel = personeller.filter(pk=request.POST.get("personel_id")).first()
        if personel:
            slotlar = musait_slotlar(personel)
        form.fields["slot"].choices = [("", "— Saat seçin —")] + [
            (s["value"], s["etiket"]) for s in slotlar
        ]
        if form.is_valid():
            tarih_str, saat_str = form.cleaned_data["slot"].split("|")
            from datetime import date, time

            try:
                randevu_olustur(
                    veli=veli,
                    talebe=talebe,
                    personel=form.cleaned_data["personel_id"],
                    tarih=date.fromisoformat(tarih_str),
                    baslangic=time.fromisoformat(saat_str),
                    konu=form.cleaned_data.get("konu") or "",
                )
                messages.success(request, "Randevunuz oluşturuldu.")
                return redirect("veli_talebe_randevu", talebe_id=talebe.pk)
            except ValueError as exc:
                messages.error(request, str(exc))

    sayfa_goruntulendi(veli, "veli_talebe_randevu", talebe=talebe)
    return _talebe_sayfa(
        request,
        veli,
        talebe,
        "veli/talebe_randevu.html",
        "randevu",
        {
            "form": form,
            "randevular": randevular,
            "secili_personel": secili_personel,
            "slot_sayisi": len(slotlar),
        },
    )


@login_required
def veli_duyurular(request):
    if not kullanici_veli_mi(request.user):
        return redirect("dashboard")

    veli = _veli_hesap(request)
    if not veli:
        return redirect("logout")

    duyurular = list(veli_duyurulari())
    duyurular_goruntulendi(veli, duyurular, sayfa="veli_duyurular")

    return render(
        request,
        "veli/duyurular.html",
        {
            "veli": veli,
            "duyurular": duyurular,
        },
    )
