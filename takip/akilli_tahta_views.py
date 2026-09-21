"""Akıllı Tahta Dosya Merkezi — etüt hocası / yönetici paneli görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
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
    tam = tam_yetkili(request.user)
    if tam:
        dosyalar = AkilliTahtaDosya.objects.select_related("ders", "yukleyen")
    else:
        dosyalar = AkilliTahtaDosya.objects.filter(yukleyen=request.user).select_related(
            "ders", "yukleyen"
        )

    sinif = request.GET.get("sinif", "").strip()
    ders_id = request.GET.get("ders", "").strip()
    dosya_turu = request.GET.get("dosya_turu", "").strip()
    yukleyen_id = request.GET.get("yukleyen", "").strip()
    baslangic = request.GET.get("baslangic", "").strip()
    bitis = request.GET.get("bitis", "").strip()

    if tam:
        if sinif:
            dosyalar = dosyalar.filter(hedefler__sinif_seviyesi=sinif)
        if ders_id:
            dosyalar = dosyalar.filter(ders_id=ders_id)
        if dosya_turu:
            dosyalar = dosyalar.filter(dosya_turu=dosya_turu)
        if yukleyen_id:
            dosyalar = dosyalar.filter(yukleyen_id=yukleyen_id)
        if baslangic:
            dosyalar = dosyalar.filter(olusturulma__date__gte=baslangic)
        if bitis:
            dosyalar = dosyalar.filter(olusturulma__date__lte=bitis)

    from takip.wave0_models import Ders

    baglam = {
        "dosyalar": dosyalar.order_by("-olusturulma").distinct(),
        "tam_yetkili": tam,
        "sinif_secenekleri": AkilliTahtaDosya._meta.get_field("dosya_turu").choices,
    }
    if tam:
        from takip.akilli_tahta_models import SinifSeviyesi

        baglam.update(
            {
                "sinif_seviyeleri": SinifSeviyesi.choices,
                "dersler": Ders.objects.filter(aktif=True),
                "yukleyenler": (
                    User.objects.filter(
                        pk__in=AkilliTahtaDosya.objects.values_list("yukleyen_id", flat=True)
                    )
                ),
                "secili": {
                    "sinif": sinif,
                    "ders": ders_id,
                    "dosya_turu": dosya_turu,
                    "yukleyen": yukleyen_id,
                    "baslangic": baslangic,
                    "bitis": bitis,
                },
            }
        )
    return render(request, "akilli_tahta/liste.html", baglam)


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
