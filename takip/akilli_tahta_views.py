"""Akıllı Tahta Dosya Merkezi — etüt hocası / yönetici paneli görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from takip.akilli_tahta_forms import AkilliTahtaDosyaForm
from takip.akilli_tahta_models import AkilliTahtaDosya, AkilliTahtaHedef
from takip.akilli_tahta_service import (
    AkilliTahtaHatasi,
    dosya_duzenlenebilir_mi,
    dosya_turunu_belirle,
    dosya_yukle,
    islem_kaydet,
    tam_yetkili,
)
from takip.dosya_guvenlik import dosya_ozeti
from takip.permissions.decorators import require_permission


@login_required
@require_permission("akilli_tahta", "view")
def liste(request):
    if tam_yetkili(request.user):
        dosyalar = AkilliTahtaDosya.objects.select_related("ders", "yukleyen")
    else:
        dosyalar = AkilliTahtaDosya.objects.filter(yukleyen=request.user).select_related(
            "ders", "yukleyen"
        )
    return render(
        request,
        "akilli_tahta/liste.html",
        {
            "dosyalar": dosyalar.order_by("-olusturulma"),
            "tam_yetkili": tam_yetkili(request.user),
        },
    )


@login_required
@require_permission("akilli_tahta", "create")
def yukle(request):
    if request.method == "POST":
        form = AkilliTahtaDosyaForm(request.POST, request.FILES)
        taslak = "taslak" in request.POST
        if form.is_valid():
            try:
                kayit = dosya_yukle(
                    kullanici=request.user,
                    dosya=form.cleaned_data["dosya"],
                    baslik=form.cleaned_data["baslik"],
                    icerik_turu=form.cleaned_data["icerik_turu"],
                    ders=form.cleaned_data.get("ders"),
                    aciklama=form.cleaned_data.get("aciklama", ""),
                    tum_siniflar=form.cleaned_data["tum_siniflar"],
                    hedef_seviyeler=form.cleaned_data.get("hedef_sinif_seviyeleri", []),
                    yayin_baslangic=form.cleaned_data["yayin_baslangic"],
                    yayin_bitis=form.cleaned_data.get("yayin_bitis"),
                    ust_sirada=form.cleaned_data.get("ust_sirada", False),
                    indirme_izni=form.cleaned_data.get("indirme_izni", True),
                    taslak=taslak,
                )
            except AkilliTahtaHatasi as hata:
                form.add_error("dosya", str(hata))
            else:
                if kayit.tum_siniflar:
                    hedef_metni = "tüm sınıf seviyeleri"
                else:
                    hedef_metni = ", ".join(
                        sorted(kayit.hedefler.values_list("sinif_seviyesi", flat=True))
                    )
                if taslak:
                    messages.success(request, f"“{kayit.baslik}” taslak olarak kaydedildi.")
                else:
                    messages.success(
                        request,
                        f"“{kayit.baslik}” yayımlandı. Gönderildiği sınıflar: {hedef_metni}.",
                    )
                return redirect("akilli_tahta:liste")
    else:
        form = AkilliTahtaDosyaForm()

    return render(request, "akilli_tahta/form.html", {"form": form, "duzenleme": False})


@login_required
@require_permission("akilli_tahta", "edit")
def duzenle(request, pk):
    kayit = get_object_or_404(AkilliTahtaDosya, pk=pk)
    if not dosya_duzenlenebilir_mi(request.user, kayit):
        messages.error(request, "Bu dosyayı düzenleme yetkiniz yok.")
        return redirect("akilli_tahta:liste")

    if request.method == "POST":
        form = AkilliTahtaDosyaForm(request.POST, request.FILES, instance=kayit)
        form.fields["dosya"].required = False
        if form.is_valid():
            guncel = form.save(commit=False)
            if request.FILES.get("dosya"):
                try:
                    uzanti, mime = dosya_turunu_belirle(form.cleaned_data["dosya"])
                except AkilliTahtaHatasi as hata:
                    form.add_error("dosya", str(hata))
                    return render(
                        request,
                        "akilli_tahta/form.html",
                        {"form": form, "duzenleme": True, "kayit": kayit},
                    )
                guncel.dosya_turu = uzanti
                guncel.mime = mime
                guncel.dosya_hash = dosya_ozeti(form.cleaned_data["dosya"])
                guncel.dosya_boyutu = form.cleaned_data["dosya"].size
            guncel.save()

            if not guncel.tum_siniflar:
                guncel.hedefler.all().delete()
                AkilliTahtaHedef.objects.bulk_create(
                    [
                        AkilliTahtaHedef(dosya=guncel, sinif_seviyesi=s)
                        for s in form.cleaned_data.get("hedef_sinif_seviyeleri", [])
                    ]
                )
            else:
                guncel.hedefler.all().delete()

            islem_kaydet(request.user, "dosya_duzenle", dosya=guncel, detay=guncel.baslik)
            messages.success(request, f"“{guncel.baslik}” güncellendi.")
            return redirect("akilli_tahta:liste")
    else:
        form = AkilliTahtaDosyaForm(instance=kayit)
        form.fields["dosya"].required = False

    return render(
        request,
        "akilli_tahta/form.html",
        {"form": form, "duzenleme": True, "kayit": kayit},
    )


@login_required
@require_POST
@require_permission("akilli_tahta", "edit")
def yayindan_kaldir(request, pk):
    kayit = get_object_or_404(AkilliTahtaDosya, pk=pk)
    if not dosya_duzenlenebilir_mi(request.user, kayit):
        messages.error(request, "Bu dosyayı yönetme yetkiniz yok.")
        return redirect("akilli_tahta:liste")
    kayit.durum = AkilliTahtaDosya.Durum.TASLAK
    kayit.save(update_fields=["durum", "guncellenme"])
    islem_kaydet(request.user, "yayindan_kaldir", dosya=kayit, detay=kayit.baslik)
    messages.success(request, f"“{kayit.baslik}” yayından kaldırıldı.")
    return redirect("akilli_tahta:liste")


@login_required
@require_POST
@require_permission("akilli_tahta", "edit")
def arsivle(request, pk):
    kayit = get_object_or_404(AkilliTahtaDosya, pk=pk)
    if not dosya_duzenlenebilir_mi(request.user, kayit):
        messages.error(request, "Bu dosyayı yönetme yetkiniz yok.")
        return redirect("akilli_tahta:liste")
    kayit.durum = AkilliTahtaDosya.Durum.ARSIVLENDI
    kayit.save(update_fields=["durum", "guncellenme"])
    islem_kaydet(request.user, "arsivle", dosya=kayit, detay=kayit.baslik)
    messages.success(request, f"“{kayit.baslik}” arşivlendi.")
    return redirect("akilli_tahta:liste")


@login_required
@require_POST
@require_permission("akilli_tahta", "edit")
def yayina_al(request, pk):
    kayit = get_object_or_404(AkilliTahtaDosya, pk=pk)
    if not dosya_duzenlenebilir_mi(request.user, kayit):
        messages.error(request, "Bu dosyayı yönetme yetkiniz yok.")
        return redirect("akilli_tahta:liste")
    kayit.durum = AkilliTahtaDosya.Durum.YAYINDA
    kayit.save(update_fields=["durum", "guncellenme"])
    islem_kaydet(request.user, "yayina_al", dosya=kayit, detay=kayit.baslik)
    messages.success(request, f"“{kayit.baslik}” yayına alındı.")
    return redirect("akilli_tahta:liste")
