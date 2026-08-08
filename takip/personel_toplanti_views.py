"""Personel toplantıları — yönetim görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import localdate

from config.branding import panel_branding_context
from takip.forms import (
    PersonelToplantiGundemForm,
    PersonelToplantiKararForm,
    PersonelToplantiYapilacakForm,
    PersonelToplantisiForm,
)
from takip.idareci_views import _idareci_erisim
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_error_response
from takip.personel_toplanti_models import (
    PersonelToplantiGundemMadde,
    PersonelToplantiKarar,
    PersonelToplantisi,
)
from takip.personel_toplanti_service import (
    idareci_toplanti_ozet,
    karar_sira_ver,
    karar_vazife_senkron,
    pdf_baglam,
    sonraki_toplanti_no,
    toplanti_tamamla,
    tutanak_pdf_kaydet,
)
from takip.yonetim_views import yonetici_gerekli

GundemFormSet = modelformset_factory(
    PersonelToplantiGundemMadde,
    form=PersonelToplantiGundemForm,
    extra=2,
    can_delete=True,
)

YapilacakFormSet = modelformset_factory(
    PersonelToplantiKarar,
    form=PersonelToplantiYapilacakForm,
    extra=2,
    can_delete=True,
)


def _toplanti_qs():
    return PersonelToplantisi.objects.select_related(
        "olusturan",
    ).prefetch_related("gundem_maddeleri", "kararlar__sorumlu", "katilimci_personeller")


def _formset_kaydet(formset, toplanti, *, metin_alanlari: tuple[str, ...]):
    """Boş satırları atlayarak formset kaydet."""
    kayitlar = formset.save(commit=False)
    for obj in formset.deleted_objects:
        obj.delete()
    sira = 1
    for obj in kayitlar:
        if not any((getattr(obj, alan, "") or "").strip() for alan in metin_alanlari):
            if obj.pk:
                obj.delete()
            continue
        obj.toplanti = toplanti
        obj.sira = sira
        if hasattr(obj, "tur") and not getattr(obj, "tur", None):
            from takip.personel_toplanti_models import PersonelToplantiKarar

            obj.tur = PersonelToplantiKarar.Tur.YAPILACAK
        obj.save()
        sira += 1
        yield obj


@yonetici_gerekli
def toplanti_listesi(request):
    if not _idareci_erisim(request.user):
        messages.error(request, "Personel toplantıları modülüne erişim yok.")
        return redirect("yonetim:dashboard")

    durum = request.GET.get("durum", "")
    qs = _toplanti_qs().order_by("-tarih", "-id")
    if durum:
        qs = qs.filter(durum=durum)
    arsiv = request.GET.get("arsiv") == "1"
    if arsiv:
        qs = qs.filter(arsivlandi=True)

    return render(
        request,
        "yonetim/personel_toplanti_listesi.html",
        {
            "toplantilar": qs[:150],
            "durum": durum,
            "arsiv": arsiv,
            "durumlar": PersonelToplantisi.Durum.choices,
            "ozet": idareci_toplanti_ozet(),
        },
    )


@yonetici_gerekli
def toplanti_ekle(request):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    form = PersonelToplantisiForm(
        request.POST or None,
        olusturma=True,
        initial={"tarih": localdate()},
    )
    if form.is_valid():
        toplanti = form.save(commit=False)
        toplanti.toplanti_no = sonraki_toplanti_no()
        toplanti.durum = PersonelToplantisi.Durum.TASLAK
        toplanti.olusturan = request.user
        toplanti.save()
        messages.success(request, f"{toplanti.toplanti_no} oluşturuldu.")
        return redirect("yonetim:personel_toplanti_detay", pk=toplanti.pk)

    return render(
        request,
        "yonetim/personel_toplanti_form.html",
        {"form": form, "baslik": "Yeni personel toplantısı"},
    )


@yonetici_gerekli
def toplanti_detay(request, pk: int):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    toplanti = get_object_or_404(_toplanti_qs(), pk=pk)
    form = PersonelToplantisiForm(request.POST or None, instance=toplanti)
    gundem_formset = GundemFormSet(
        request.POST or None,
        prefix="gundem",
        queryset=toplanti.gundem_maddeleri.order_by("sira", "id"),
    )
    yapilacak_qs = toplanti.kararlar.filter(
        tur__in=(PersonelToplantiKarar.Tur.YAPILACAK, PersonelToplantiKarar.Tur.TAKIP)
    ).order_by("sira", "id")
    yapilacak_formset = YapilacakFormSet(
        request.POST or None,
        prefix="yapilacak",
        queryset=yapilacak_qs,
    )

    if request.method == "POST":
        aksiyon = request.POST.get("aksiyon", "kaydet")
        if form.is_valid() and gundem_formset.is_valid() and yapilacak_formset.is_valid():
            form.save()
            list(_formset_kaydet(gundem_formset, toplanti, metin_alanlari=("madde", "gorusulen")))
            for karar in _formset_kaydet(
                yapilacak_formset, toplanti, metin_alanlari=("metin",)
            ):
                if karar.tur not in (
                    PersonelToplantiKarar.Tur.YAPILACAK,
                    PersonelToplantiKarar.Tur.TAKIP,
                ):
                    karar.tur = PersonelToplantiKarar.Tur.YAPILACAK
                    karar.save(update_fields=["tur", "guncellenme"])
                karar_vazife_senkron(karar, atayan=request.user)
            messages.success(request, "Toplantı kaydedildi.")
            if aksiyon == "tamamla":
                toplanti_tamamla(toplanti, atayan=request.user)
                messages.info(request, "Toplantı tamamlandı ve arşive alındı.")
                return redirect(
                    f"{reverse('yonetim:personel_toplanti_pdf', kwargs={'pk': pk})}?kaydet=1"
                )
            return redirect("yonetim:personel_toplanti_detay", pk=pk)

    return render(
        request,
        "yonetim/personel_toplanti_detay.html",
        {
            "toplanti": toplanti,
            "form": form,
            "gundem_formset": gundem_formset,
            "yapilacak_formset": yapilacak_formset,
        },
    )


@yonetici_gerekli
def toplanti_karar_ekle(request, pk: int):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    toplanti = get_object_or_404(PersonelToplantisi, pk=pk)
    if request.method == "POST":
        form = PersonelToplantiKararForm(request.POST)
        if form.is_valid():
            karar = form.save(commit=False)
            karar.toplanti = toplanti
            karar.sira = karar_sira_ver(toplanti)
            karar.save()
            karar_vazife_senkron(karar, atayan=request.user)
            messages.success(request, "Kayıt eklendi.")
    return redirect("yonetim:personel_toplanti_detay", pk=pk)


@yonetici_gerekli
def toplanti_pdf(request, pk: int):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    toplanti = get_object_or_404(_toplanti_qs(), pk=pk)
    html = render_to_string(
        "personel_toplanti_pdf.html",
        pdf_baglam(request.user, toplanti),
        request=request,
    )
    pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf:
        return pdf_error_response("PDF oluşturulamadı.")

    if request.GET.get("kaydet") == "1":
        tutanak_pdf_kaydet(toplanti, pdf)

    filename = f"{toplanti.toplanti_no.replace('/', '-')}_rapor.pdf"
    return make_pdf_response(pdf, filename)


@yonetici_gerekli
def toplanti_arsiv_pdf(request, pk: int):
    """Arşivlenmiş kayıtlı PDF — tasarım tamamlanma anında sabitlenir."""
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    toplanti = get_object_or_404(_toplanti_qs(), pk=pk)
    if toplanti.tutanak_pdf:
        from django.http import FileResponse

        fname = f"{toplanti.toplanti_no.replace('/', '-')}_rapor.pdf"
        return FileResponse(
            toplanti.tutanak_pdf.open("rb"),
            content_type="application/pdf",
            filename=fname,
            as_attachment=False,
        )
    return redirect(f"{reverse('yonetim:personel_toplanti_pdf', kwargs={'pk': pk})}?kaydet=1")


@yonetici_gerekli
def toplanti_arsiv(request):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    toplantilar = (
        _toplanti_qs()
        .filter(arsivlandi=True)
        .order_by("-tarih")[:200]
    )
    return render(
        request,
        "yonetim/personel_toplanti_arsiv.html",
        {"toplantilar": toplantilar, **panel_branding_context()},
    )
