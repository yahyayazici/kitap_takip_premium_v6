"""Sınav başvuruları — yönetim paneli."""

from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit
from takip.models import SinavBasvuru, SinavBasvuruMesajLog, SinavBasvuruMesajSablon
from takip.sinav_basvuru_mesaj_service import (
    basvuru_mesaji_gonder,
    basvurularda_mesaj_gonder,
    durum_icin_mesaj_an,
)
from takip.whatsapp_service import telefon_normalize, whatsapp_yapilandirilmis
from takip.yonetim_views import yonetici_gerekli

# Yönetimden manuel tetiklenebilen anlar
MANUEL_ANLAR = (
    SinavBasvuruMesajSablon.AnKodu.SINAV_DAVETI,
    SinavBasvuruMesajSablon.AnKodu.SONUC_BILDIRIMI,
    SinavBasvuruMesajSablon.AnKodu.BASVURU_ALINDI,
    SinavBasvuruMesajSablon.AnKodu.KABUL,
    SinavBasvuruMesajSablon.AnKodu.RED,
)


def _filtreli_basvurular(request):
    basvurular = SinavBasvuru.objects.all()
    durum = request.GET.get("durum", "").strip()
    arama = request.GET.get("q", "").strip()

    if durum in SinavBasvuru.Durum.values:
        basvurular = basvurular.filter(durum=durum)

    if arama:
        basvurular = basvurular.filter(
            Q(ad_soyad__icontains=arama)
            | Q(baba_telefon__icontains=arama)
            | Q(anne_telefon__icontains=arama)
            | Q(baba_adi__icontains=arama)
            | Q(anne_adi__icontains=arama)
            | Q(il__icontains=arama)
            | Q(ilce__icontains=arama)
        )
    return basvurular, durum, arama


@yonetici_gerekli
def sinav_basvuru_listesi(request):
    basvurular, durum, arama = _filtreli_basvurular(request)
    manuel_sablonlar = SinavBasvuruMesajSablon.objects.filter(
        an_kodu__in=MANUEL_ANLAR
    ).order_by("sira")

    return render(
        request,
        "yonetim/sinav_basvuru_listesi.html",
        {
            "basvurular": basvurular,
            "durum_filtre": durum,
            "arama": arama,
            "durum_secenekleri": SinavBasvuru.Durum.choices,
            "manuel_sablonlar": manuel_sablonlar,
            "whatsapp_aktif": whatsapp_yapilandirilmis(),
        },
    )


@yonetici_gerekli
def sinav_basvuru_excel(request):
    basvurular, _, _ = _filtreli_basvurular(request)
    satirlar = []
    for b in basvurular:
        satirlar.append(
            [
                b.ad_soyad,
                b.baba_adi,
                b.baba_telefon,
                telefon_normalize(b.baba_telefon),
                b.anne_adi,
                b.anne_telefon,
                telefon_normalize(b.anne_telefon),
                b.il,
                b.ilce,
                b.dogum_tarihi.strftime("%d.%m.%Y") if b.dogum_tarihi else "",
                b.sinav_adi,
                b.get_durum_display(),
                b.olusturulma.strftime("%d.%m.%Y %H:%M") if b.olusturulma else "",
            ]
        )

    icerik = basit_rapor_xlsx(
        baslik="Sınav Başvuruları",
        alt_baslik="WhatsApp / SMS kampanya listesi",
        kolon_basliklari=[
            "Ad soyad",
            "Baba adı",
            "Baba tel",
            "Baba tel (90…)",
            "Anne adı",
            "Anne tel",
            "Anne tel (90…)",
            "İl",
            "İlçe",
            "Doğum tarihi",
            "Sınav",
            "Durum",
            "Başvuru zamanı",
        ],
        satirlar=satirlar,
        durum_kolonlari=[11],
        vurgu_kolonlari=[0],
        genislikler=[18, 14, 14, 14, 14, 14, 14, 10, 12, 12, 22, 12, 16],
    )
    return excel_http_yanit(icerik, "sinav-basvurulari.xlsx")


@yonetici_gerekli
@require_POST
def sinav_basvuru_toplu_mesaj(request):
    an_kodu = request.POST.get("an_kodu", "").strip()
    ids = request.POST.getlist("basvuru_ids")
    if an_kodu not in SinavBasvuruMesajSablon.AnKodu.values:
        messages.error(request, "Geçersiz mesaj anı.")
        return redirect("yonetim:sinav_basvuru_listesi")

    qs = SinavBasvuru.objects.filter(pk__in=ids)
    if not qs.exists():
        messages.error(request, "Mesaj için başvuru seçin.")
        return redirect("yonetim:sinav_basvuru_listesi")

    # Yönetimden manuel gönderimde aktif kontrolü: pasif an da gönderilebilir
    # (admin bilerek seçti); yine de şablon yoksa sessizce çıkar.
    ozet = basvurularda_mesaj_gonder(qs, an_kodu, sadece_aktif=False)
    messages.success(
        request,
        (
            f"Mesaj işlemi: {ozet['toplam']} deneme — "
            f"{ozet['gonderildi']} gönderildi, "
            f"{ozet['hata']} hata, "
            f"{ozet['atlandi']} atlandı."
        ),
    )
    return redirect("yonetim:sinav_basvuru_listesi")


@yonetici_gerekli
@require_http_methods(["GET", "POST"])
def sinav_basvuru_detay(request, pk):
    basvuru = get_object_or_404(SinavBasvuru, pk=pk)
    onceki_durum = basvuru.durum

    if request.method == "POST":
        action = request.POST.get("action", "kaydet").strip()
        if action == "mesaj_gonder":
            an_kodu = request.POST.get("an_kodu", "").strip()
            if an_kodu in SinavBasvuruMesajSablon.AnKodu.values:
                loglar = basvuru_mesaji_gonder(
                    basvuru, an_kodu, sadece_aktif=False
                )
                ok = sum(
                    1
                    for log in loglar
                    if log.durum == SinavBasvuruMesajLog.Durum.GONDERILDI
                )
                messages.success(
                    request,
                    f"Mesaj: {ok}/{len(loglar)} gönderildi.",
                )
            else:
                messages.error(request, "Geçersiz mesaj anı.")
            return redirect("yonetim:sinav_basvuru_detay", pk=basvuru.pk)

        yeni_durum = request.POST.get("durum", "").strip()
        notlar = request.POST.get("notlar", "").strip()
        if yeni_durum in SinavBasvuru.Durum.values:
            basvuru.durum = yeni_durum
        basvuru.notlar = notlar
        basvuru.save(update_fields=["durum", "notlar", "guncellenme"])

        if basvuru.durum != onceki_durum:
            an = durum_icin_mesaj_an(basvuru.durum)
            if an:
                try:
                    basvuru_mesaji_gonder(basvuru, an, sadece_aktif=True)
                except Exception:  # noqa: BLE001
                    messages.warning(
                        request,
                        "Durum kaydedildi; WhatsApp mesajı gönderilemedi.",
                    )

        messages.success(request, "Başvuru güncellendi.")
        return redirect("yonetim:sinav_basvuru_detay", pk=basvuru.pk)

    loglar = basvuru.mesaj_loglari.select_related("sablon").all()[:40]
    manuel_sablonlar = SinavBasvuruMesajSablon.objects.filter(
        an_kodu__in=MANUEL_ANLAR
    ).order_by("sira")

    return render(
        request,
        "yonetim/sinav_basvuru_detay.html",
        {
            "basvuru": basvuru,
            "durum_secenekleri": SinavBasvuru.Durum.choices,
            "mesaj_loglari": loglar,
            "manuel_sablonlar": manuel_sablonlar,
            "whatsapp_aktif": whatsapp_yapilandirilmis(),
        },
    )


@yonetici_gerekli
@require_POST
def sinav_basvuru_sil(request, pk):
    basvuru = get_object_or_404(SinavBasvuru, pk=pk)
    ad = basvuru.ad_soyad
    basvuru.delete()
    messages.success(request, f"{ad} başvurusu silindi.")
    return redirect("yonetim:sinav_basvuru_listesi")
