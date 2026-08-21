"""Veli değerlendirme anketi — yönetim paneli."""

from __future__ import annotations

from django.contrib import messages
from django.db.models import Avg
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit
from takip.models import VeliAnketCevap
from takip.yonetim_views import yonetici_gerekli


@yonetici_gerekli
def veli_anketi_listesi(request):
    from django.shortcuts import render

    cevaplar = VeliAnketCevap.objects.all()
    ortalama = cevaplar.aggregate(ort=Avg("istifade_puani"))["ort"]

    return render(
        request,
        "yonetim/veli_anketi_listesi.html",
        {
            "cevaplar": cevaplar,
            "toplam": cevaplar.count(),
            "ortalama": round(ortalama, 1) if ortalama is not None else None,
        },
    )


@yonetici_gerekli
def veli_anketi_excel(request):
    cevaplar = VeliAnketCevap.objects.all()
    satirlar = [
        [
            c.olusturulma.strftime("%d.%m.%Y %H:%M"),
            c.sinif,
            c.genel_degerlendirme,
            c.konu_ihtiyaci_cevap,
            c.konusmaci_gorus,
            c.istifade_puani,
            c.onerilen_konular,
            c.oneriler,
        ]
        for c in cevaplar
    ]
    icerik = basit_rapor_xlsx(
        baslik="Veli Anket Cevapları",
        kolon_basliklari=[
            "Tarih",
            "Sınıf",
            "Genel Değerlendirme",
            "İhtiyaca Cevap Verdi mi",
            "Konuşmacı",
            "İstifade Puanı",
            "Önerilen Konular",
            "Diğer Öneriler",
        ],
        satirlar=satirlar,
        sayfa_adi="Anket",
    )
    return excel_http_yanit(icerik, "veli-anketi.xlsx")


@yonetici_gerekli
@require_POST
def veli_anketi_sil(request, pk):
    cevap = get_object_or_404(VeliAnketCevap, pk=pk)
    cevap.delete()
    messages.success(request, "Anket cevabı silindi.")
    return redirect("yonetim:veli_anketi_listesi")
