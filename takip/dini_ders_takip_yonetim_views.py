"""Dini ders takip — yönetim (seviye, alan, konu)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from takip.dini_ders_excel import (
    alan_excel_ice_aktar,
    alan_sablon_xlsx,
    konu_excel_ice_aktar,
    konu_sablon_xlsx,
)
from takip.excel_rapor import excel_http_yanit
from takip.forms import (
    DiniDersKonuForm,
    DiniDersSeviyesiYonetimForm,
    DiniDersTakipAlaniForm,
)
from takip.models import DiniDersKonu, DiniDersSeviyesi, DiniDersTakipAlani
from takip.permissions.service import can

from .yonetim_views import yonetici_gerekli


def _excel_sonuc_mesajlari(request, sonuc) -> None:
    for mesaj in sonuc.bilgi:
        messages.success(request, mesaj)
    if sonuc.atlanan and not sonuc.hatalar:
        messages.warning(request, f"{sonuc.atlanan} satır atlandı.")
    if sonuc.hatalar:
        for hata in sonuc.hatalar[:12]:
            messages.error(request, hata)
        if len(sonuc.hatalar) > 12:
            messages.error(
                request,
                f"… ve {len(sonuc.hatalar) - 12} hata daha.",
            )
    if not sonuc.eklenen and not sonuc.guncellenen and not sonuc.hatalar:
        messages.warning(request, "İşlenecek satır bulunamadı.")


def _yonetim_yetki(request, islem: str = "view"):
    if not can(request.user, "dini_ders_takip", islem):
        messages.error(request, "Dini ders takip modülüne erişim yok.")
        return False
    return True


@yonetici_gerekli
def dini_ders_seviye_listesi(request):
    if not _yonetim_yetki(request):
        return redirect("yonetim:dashboard")

    seviyeler = DiniDersSeviyesi.objects.prefetch_related("hocalar").order_by(
        "sira", "ad"
    )
    return render(
        request,
        "yonetim/dini_ders_seviye_listesi.html",
        {
            "seviyeler": seviyeler,
            "duzenleyebilir": can(request.user, "dini_ders_takip", "edit"),
            "aktif_sekme": "seviye",
        },
    )


@yonetici_gerekli
def dini_ders_seviye_duzenle(request, pk):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:dini_ders_seviye_listesi")

    seviye = get_object_or_404(DiniDersSeviyesi, pk=pk)
    form = DiniDersSeviyesiYonetimForm(request.POST or None, instance=seviye)
    if form.is_valid():
        form.save()
        messages.success(request, "Seviye güncellendi.")
        return redirect("yonetim:dini_ders_seviye_listesi")

    return render(
        request,
        "yonetim/dini_ders_seviye_form.html",
        {"form": form, "baslik": f"Düzenle — {seviye.ad}", "aktif_sekme": "seviye"},
    )


@yonetici_gerekli
def dini_ders_alan_listesi(request):
    if not _yonetim_yetki(request):
        return redirect("yonetim:dashboard")

    if request.method == "POST" and request.FILES.get("excel_dosyasi"):
        if not _yonetim_yetki(request, "edit"):
            return redirect("yonetim:dini_ders_alan_listesi")
        try:
            sonuc = alan_excel_ice_aktar(request.FILES["excel_dosyasi"])
        except ImportError:
            messages.error(
                request,
                "Excel yükleme için openpyxl paketi gerekli.",
            )
            return redirect("yonetim:dini_ders_alan_listesi")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"Excel okunamadı: {exc}")
            return redirect("yonetim:dini_ders_alan_listesi")
        _excel_sonuc_mesajlari(request, sonuc)
        return redirect("yonetim:dini_ders_alan_listesi")

    alanlar = DiniDersTakipAlani.objects.order_by("sira", "ad")
    return render(
        request,
        "yonetim/dini_ders_alan_listesi.html",
        {
            "alanlar": alanlar,
            "duzenleyebilir": can(request.user, "dini_ders_takip", "edit"),
            "aktif_sekme": "alan",
        },
    )


@yonetici_gerekli
def dini_ders_alan_excel_sablon(request):
    if not _yonetim_yetki(request):
        return redirect("yonetim:dashboard")
    try:
        icerik = alan_sablon_xlsx()
    except ImportError:
        messages.error(request, "Excel şablonu için openpyxl paketi gerekli.")
        return redirect("yonetim:dini_ders_alan_listesi")
    return excel_http_yanit(icerik, "dini-ders-takip-alanlari-sablon.xlsx")


@yonetici_gerekli
def dini_ders_alan_ekle(request):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:dini_ders_alan_listesi")

    form = DiniDersTakipAlaniForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Takip alanı eklendi.")
        return redirect("yonetim:dini_ders_alan_listesi")

    return render(
        request,
        "yonetim/dini_ders_alan_form.html",
        {"form": form, "baslik": "Yeni Takip Alanı", "aktif_sekme": "alan"},
    )


@yonetici_gerekli
def dini_ders_alan_duzenle(request, pk):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:dini_ders_alan_listesi")

    alan = get_object_or_404(DiniDersTakipAlani, pk=pk)
    form = DiniDersTakipAlaniForm(request.POST or None, instance=alan)
    if form.is_valid():
        form.save()
        messages.success(request, "Takip alanı güncellendi.")
        return redirect("yonetim:dini_ders_alan_listesi")

    return render(
        request,
        "yonetim/dini_ders_alan_form.html",
        {"form": form, "baslik": f"Düzenle — {alan.ad}", "aktif_sekme": "alan"},
    )


@yonetici_gerekli
def dini_ders_konu_listesi(request):
    if not _yonetim_yetki(request):
        return redirect("yonetim:dashboard")

    if request.method == "POST" and request.FILES.get("excel_dosyasi"):
        if not _yonetim_yetki(request, "edit"):
            return redirect("yonetim:dini_ders_konu_listesi")
        try:
            sonuc = konu_excel_ice_aktar(request.FILES["excel_dosyasi"])
        except ImportError:
            messages.error(
                request,
                "Excel yükleme için openpyxl paketi gerekli.",
            )
            return redirect("yonetim:dini_ders_konu_listesi")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"Excel okunamadı: {exc}")
            return redirect("yonetim:dini_ders_konu_listesi")
        _excel_sonuc_mesajlari(request, sonuc)
        return redirect("yonetim:dini_ders_konu_listesi")

    konular = DiniDersKonu.objects.select_related("alan", "seviye").order_by(
        "seviye__sira", "alan__sira", "sira", "ad"
    )
    return render(
        request,
        "yonetim/dini_ders_konu_listesi.html",
        {
            "konular": konular,
            "duzenleyebilir": can(request.user, "dini_ders_takip", "edit"),
            "aktif_sekme": "konu",
        },
    )


@yonetici_gerekli
def dini_ders_konu_excel_sablon(request):
    if not _yonetim_yetki(request):
        return redirect("yonetim:dashboard")
    try:
        icerik = konu_sablon_xlsx()
    except ImportError:
        messages.error(request, "Excel şablonu için openpyxl paketi gerekli.")
        return redirect("yonetim:dini_ders_konu_listesi")
    return excel_http_yanit(icerik, "dini-ders-konu-listeleri-sablon.xlsx")


@yonetici_gerekli
def dini_ders_konu_ekle(request):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:dini_ders_konu_listesi")

    form = DiniDersKonuForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Konu eklendi.")
        return redirect("yonetim:dini_ders_konu_listesi")

    return render(
        request,
        "yonetim/dini_ders_konu_form.html",
        {"form": form, "baslik": "Yeni Konu", "aktif_sekme": "konu"},
    )


@yonetici_gerekli
def dini_ders_konu_duzenle(request, pk):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:dini_ders_konu_listesi")

    konu = get_object_or_404(DiniDersKonu, pk=pk)
    form = DiniDersKonuForm(request.POST or None, instance=konu)
    if form.is_valid():
        form.save()
        messages.success(request, "Konu güncellendi.")
        return redirect("yonetim:dini_ders_konu_listesi")

    return render(
        request,
        "yonetim/dini_ders_konu_form.html",
        {"form": form, "baslik": f"Düzenle — {konu.ad}", "aktif_sekme": "konu"},
    )
