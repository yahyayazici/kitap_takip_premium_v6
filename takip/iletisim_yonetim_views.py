"""İletişim Merkezi — yönetim (şablon) görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from takip.iletisim_models import IletisimSablon
from takip.iletisim_service import kurum_ayarlari, sablon_degiskenleri, sablon_render
from takip.permissions.decorators import require_permission
from takip.yonetim_views import yonetici_gerekli


@login_required
@yonetici_gerekli
@require_permission("iletisim_merkezi", "manage_templates")
def iletisim_sablon_listesi(request):
    sablonlar = IletisimSablon.objects.order_by("sira", "ad")
    return render(
        request,
        "yonetim/iletisim_sablon_listesi.html",
        {"sablonlar": sablonlar, "ayar": kurum_ayarlari()},
    )


@login_required
@yonetici_gerekli
@require_permission("iletisim_merkezi", "manage_templates")
def iletisim_sablon_ekle(request):
    return _iletisim_sablon_form(request, None)


@login_required
@yonetici_gerekli
@require_permission("iletisim_merkezi", "manage_templates")
def iletisim_sablon_duzenle(request, pk: int):
    return _iletisim_sablon_form(request, pk)


def _ornek_onizleme(metin: str) -> str:
    return sablon_render(
        metin,
        {
            "talebe_adi": "Ahmet Yılmaz",
            "veli_adi": "Mehmet Yılmaz",
            "sinif": "7-A",
            "grup": "7-A",
            "ders": "Türkçe",
            "konu": "Sözcükte Anlam",
            "ktt_adi": "Türkçe KTT-4",
            "deneme_adi": "Deneme 4",
            "kitap_adi": "80 Günde Devriâlem",
            "puan": "87,5",
            "tarih": "14 Ağustos 2026",
            "kurum": "Çinili Saray Proje",
        },
    ).metin


def _iletisim_sablon_form(request, pk: int | None):
    sablon = get_object_or_404(IletisimSablon, pk=pk) if pk else None
    modul = (request.GET.get("modul") or "ktt").strip()
    icerik = sablon.icerik if sablon else ""

    if request.method == "POST":
        kod = (request.POST.get("kod") or "").strip()
        ad = (request.POST.get("ad") or "").strip()
        kategori = request.POST.get("kategori") or IletisimSablon.Kategori.AKADEMIK
        icerik = (request.POST.get("icerik") or "").strip()
        if not kod or not ad or not icerik:
            messages.error(request, "Kod, ad ve mesaj zorunludur.")
        else:
            kayit = sablon or IletisimSablon()
            kayit.kod = kod
            kayit.ad = ad
            kayit.kategori = kategori
            kayit.icerik = icerik
            kayit.aktif = request.POST.get("aktif") == "1"
            kayit.varsayilan = request.POST.get("varsayilan") == "1"
            kayit.sira = int(request.POST.get("sira") or 50)
            kayit.kaynak_moduller = request.POST.getlist("kaynak_moduller")
            if not sablon:
                kayit.olusturan = request.user
            kayit.save()
            messages.success(request, "Şablon kaydedildi.")
            return redirect("yonetim:iletisim_sablon_listesi")
        onizleme = _ornek_onizleme(icerik)
    else:
        onizleme = _ornek_onizleme(icerik) if icerik else ""

    return render(
        request,
        "yonetim/iletisim_sablon_form.html",
        {
            "sablon": sablon,
            "modul": modul,
            "degiskenler": sablon_degiskenleri(modul),
            "onizleme": onizleme,
            "kategoriler": IletisimSablon.Kategori.choices,
            "ayar": kurum_ayarlari(),
            "modul_secenekleri": [
                ("ktt", "KTT"),
                ("deneme", "Deneme"),
                ("kitap", "Kitap"),
                ("karne", "Karne"),
                ("dini_egitim", "Dinî Eğitim"),
                ("program", "Program"),
                ("yazili", "Yazılı"),
                ("duyuru", "Duyuru"),
            ],
            "secili_moduller": sablon.kaynak_moduller if sablon else [],
        },
    )


@login_required
@yonetici_gerekli
@require_permission("iletisim_merkezi", "manage_templates")
@require_POST
def iletisim_kurum_ayar_kaydet(request):
    ayar = kurum_ayarlari()
    ayar.varsayilan_hitap = (request.POST.get("varsayilan_hitap") or "").strip()
    ayar.varsayilan_kapanis = (request.POST.get("varsayilan_kapanis") or "").strip()
    ayar.kurum_imza = (request.POST.get("kurum_imza") or "").strip()
    ayar.save()
    messages.success(request, "Kurumsal iletişim ayarları güncellendi.")
    return redirect("yonetim:iletisim_sablon_listesi")
