"""Deneme — yönetim (oluşturma, Excel, önizleme)."""

from __future__ import annotations

import csv
from io import StringIO

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from takip.deneme_excel import (
    deneme_excel_onizle,
    deneme_sonuclari_aktar,
    session_key,
    DenemeImportOnizleme,
)
from takip.deneme_service import BRANS_ETIKETLERI, deneme_sonuclari, deneme_yukleyebilir
from takip.forms import DenemeSinaviForm
from takip.models import DenemeSinavi, Talebe
from takip.permissions.service import can

from .yonetim_views import yonetici_gerekli


def _onizleme_yukle(request, deneme_id: int) -> DenemeImportOnizleme | None:
    data = request.session.get(session_key(deneme_id))
    if not data:
        return None
    return DenemeImportOnizleme.from_session(data)


def _onizleme_kaydet(request, deneme_id: int, onizleme: DenemeImportOnizleme) -> None:
    request.session[session_key(deneme_id)] = onizleme.to_session()
    request.session.modified = True


@yonetici_gerekli
def deneme_listesi(request):
    if not can(request.user, "deneme", "view"):
        messages.error(request, "Deneme modülüne erişim yok.")
        return redirect("yonetim:dashboard")

    denemeler = DenemeSinavi.objects.annotate(
        sonuc_sayisi=Count("sonuclar"),
    ).order_by("-sinav_tarihi", "-id")
    return render(
        request,
        "yonetim/deneme_listesi.html",
        {
            "denemeler": denemeler,
            "yukleyebilir": deneme_yukleyebilir(request.user),
        },
    )


@yonetici_gerekli
def deneme_ekle(request):
    if not deneme_yukleyebilir(request.user):
        messages.error(request, "Deneme oluşturma yetkiniz yok.")
        return redirect("yonetim:deneme_listesi")

    form = DenemeSinaviForm(request.POST or None)
    if form.is_valid():
        deneme = form.save(commit=False)
        deneme.olusturan = request.user
        deneme.save()
        messages.success(request, "Deneme oluşturuldu. Excel yükleyebilirsiniz.")
        return redirect("yonetim:deneme_detay", pk=deneme.pk)

    return render(
        request,
        "yonetim/deneme_form.html",
        {"form": form, "baslik": "Yeni Deneme"},
    )


@yonetici_gerekli
def deneme_detay(request, pk):
    if not can(request.user, "deneme", "view"):
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    sonuclar = deneme_sonuclari(request.user, deneme) if deneme.durum == "aktif" else []

    if request.method == "POST" and request.FILES.get("excel"):
        if not deneme_yukleyebilir(request.user):
            messages.error(request, "Excel yükleme yetkiniz yok.")
            return redirect("yonetim:deneme_detay", pk=pk)
        if deneme.durum == DenemeSinavi.Durum.AKTIF:
            messages.error(request, "Aktif denemeye tekrar Excel yüklenemez.")
            return redirect("yonetim:deneme_detay", pk=pk)

        onizleme = deneme_excel_onizle(request.FILES["excel"])
        if onizleme.hatalar and not onizleme.satirlar:
            for h in onizleme.hatalar:
                messages.error(request, h)
            return redirect("yonetim:deneme_detay", pk=pk)

        _onizleme_kaydet(request, pk, onizleme)
        return redirect("yonetim:deneme_onizleme", pk=pk)

    return render(
        request,
        "yonetim/deneme_detay.html",
        {
            "deneme": deneme,
            "sonuclar": sonuclar,
            "brans_etiketleri": BRANS_ETIKETLERI,
            "yukleyebilir": deneme_yukleyebilir(request.user),
        },
    )


@yonetici_gerekli
def deneme_onizleme(request, pk):
    if not deneme_yukleyebilir(request.user):
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    onizleme = _onizleme_yukle(request, pk)
    if not onizleme:
        messages.error(request, "Önizleme verisi bulunamadı. Excel'i tekrar yükleyin.")
        return redirect("yonetim:deneme_detay", pk=pk)

    if request.method == "POST":
        aksiyon = request.POST.get("aksiyon")
        if aksiyon == "eslestir":
            satir_no = int(request.POST.get("satir_no", 0))
            talebe_id = request.POST.get("talebe_id")
            for satir in onizleme.satirlar:
                if satir.satir_no == satir_no and talebe_id:
                    satir.talebe_id = int(talebe_id)
                    satir.eslesme = "manuel"
            _onizleme_kaydet(request, pk, onizleme)
            messages.success(request, "Eşleştirme kaydedildi.")
            return redirect("yonetim:deneme_onizleme", pk=pk)

        if aksiyon == "aktar":
            adet, hatalar = deneme_sonuclari_aktar(deneme, onizleme, request.user)
            for h in hatalar:
                messages.error(request, h)
            if adet:
                request.session.pop(session_key(pk), None)
                messages.success(request, f"{adet} öğrenci sonucu aktarıldı.")
                return redirect("yonetim:deneme_detay", pk=pk)

    talebeler = Talebe.objects.filter(aktif=True).order_by("ad_soyad")
    eslesmeyen = [s for s in onizleme.satirlar if not s.talebe_id]

    return render(
        request,
        "yonetim/deneme_onizleme.html",
        {
            "deneme": deneme,
            "onizleme": onizleme,
            "eslesmeyen": eslesmeyen,
            "talebeler": talebeler,
        },
    )


@yonetici_gerekli
def deneme_rapor(request):
    if not can(request.user, "deneme", "view"):
        return redirect("yonetim:deneme_listesi")

    if request.GET.get("format") == "excel" and can(request.user, "deneme", "export_excel"):
        return deneme_excel_export(request)

    deneme_id = request.GET.get("deneme")
    sinif_id = request.GET.get("sinif_sube")
    sonuclar = []
    if deneme_id:
        deneme = get_object_or_404(DenemeSinavi, pk=deneme_id)
        sonuclar = deneme_sonuclari(request.user, deneme)
        if sinif_id:
            sonuclar = sonuclar.filter(talebe__sinif_sube_id=sinif_id)

    return render(
        request,
        "yonetim/deneme_rapor.html",
        {
            "denemeler": DenemeSinavi.objects.filter(durum="aktif").order_by("-sinav_tarihi"),
            "sonuclar": sonuclar[:300],
            "filtre": {"deneme": deneme_id or "", "sinif_sube": sinif_id or ""},
        },
    )


@yonetici_gerekli
def deneme_excel_export(request):
    deneme_id = request.GET.get("deneme")
    if not deneme_id:
        return redirect("yonetim:deneme_rapor")

    deneme = get_object_or_404(DenemeSinavi, pk=deneme_id)
    sonuclar = deneme_sonuclari(request.user, deneme)

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "Sıra",
            "Talebe",
            "Sınıf",
            "Toplam Net",
            "Puan",
        ]
    )
    for sira, sonuc in enumerate(sonuclar, start=1):
        writer.writerow(
            [
                sira,
                sonuc.talebe.ad_soyad,
                str(sonuc.talebe.sinif_sube or ""),
                str(sonuc.toplam_net).replace(".", ","),
                str(sonuc.puan).replace(".", ","),
            ]
        )

    response = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="deneme_{deneme.pk}_siralama.csv"'
    return response
