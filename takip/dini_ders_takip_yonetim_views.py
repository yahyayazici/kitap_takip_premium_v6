"""Dini ders takip — yönetim (seviye, alan, konu)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from takip.dini_ders_excel import (
    alan_excel_ice_aktar,
    alan_sablon_xlsx,
    konu_excel_ice_aktar,
    konu_sablon_xlsx,
)
from takip.excel_rapor import excel_http_yanit
from takip.forms import (
    DiniAlanPlaniForm,
    DiniDersKonuForm,
    DiniDersSeviyesiYonetimForm,
    DiniDersTakipAlaniForm,
    DiniIlerlemeEsikForm,
)
from takip.models import (
    DiniAlanPlani,
    DiniDersKonu,
    DiniDersSeviyesi,
    DiniDersTakipAlani,
    DiniIlerlemeEsik,
    DiniKonuHedefTarihi,
    EgitimYili,
)
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


def _konu_hedef_tarihi_kaydet(konu: DiniDersKonu, hedef_tarih) -> None:
    if hedef_tarih:
        DiniKonuHedefTarihi.objects.update_or_create(
            konu=konu,
            defaults={"hedef_tarih": hedef_tarih},
        )
    else:
        DiniKonuHedefTarihi.objects.filter(konu=konu).delete()


@yonetici_gerekli
def dini_ders_konu_ekle(request):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:dini_ders_konu_listesi")

    form = DiniDersKonuForm(request.POST or None)
    if form.is_valid():
        konu = form.save()
        _konu_hedef_tarihi_kaydet(konu, form.cleaned_data.get("hedef_tarih"))
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
        konu = form.save()
        _konu_hedef_tarihi_kaydet(konu, form.cleaned_data.get("hedef_tarih"))
        messages.success(request, "Konu güncellendi.")
        return redirect("yonetim:dini_ders_konu_listesi")

    return render(
        request,
        "yonetim/dini_ders_konu_form.html",
        {"form": form, "baslik": f"Düzenle — {konu.ad}", "aktif_sekme": "konu"},
    )


def _aktif_egitim_yili() -> EgitimYili | None:
    return EgitimYili.objects.filter(aktif=True).order_by("-baslangic").first()


@yonetici_gerekli
def dini_ders_plani_listesi(request):
    if not _yonetim_yetki(request):
        return redirect("yonetim:dashboard")

    yil = _aktif_egitim_yili()
    seviye_id = request.GET.get("seviye")
    seviyeler = DiniDersSeviyesi.objects.filter(aktif=True).order_by("sira", "ad")
    seviye = seviyeler.filter(pk=seviye_id).first() if seviye_id else seviyeler.first()

    planlar = []
    if yil and seviye:
        alanlar = DiniDersTakipAlani.objects.filter(aktif=True).order_by("sira", "ad")
        mevcut = {
            p.alan_id: p
            for p in DiniAlanPlani.objects.filter(
                egitim_yili=yil, seviye=seviye
            ).select_related("alan")
        }
        for alan in alanlar:
            konu_sayisi = DiniDersKonu.objects.filter(
                seviye=seviye, alan=alan, aktif=True
            ).count()
            if not konu_sayisi:
                continue
            plan = mevcut.get(alan.id)
            planlar.append(
                {
                    "alan": alan,
                    "konu_sayisi": konu_sayisi,
                    "plan": plan,
                    "d1_hedef": plan.birinci_donem_hedef if plan else 0,
                    "yil_hedef": plan.yil_sonu_hedef if plan else konu_sayisi,
                }
            )

    esik = DiniIlerlemeEsik.objects.filter(egitim_yili=yil).first() if yil else None
    esik_form = DiniIlerlemeEsikForm(
        request.POST or None,
        instance=esik,
        prefix="esik",
        initial={"egitim_yili": yil} if yil and not esik else None,
    )
    if (
        request.method == "POST"
        and request.POST.get("form_type") == "esik"
        and _yonetim_yetki(request, "edit")
    ):
        if esik_form.is_valid():
            esik_form.save()
            messages.success(request, "İlerleme eşikleri güncellendi.")
            return redirect("yonetim:dini_ders_plani_listesi")

    return render(
        request,
        "yonetim/dini_ders_plani_listesi.html",
        {
            "yil": yil,
            "seviyeler": seviyeler,
            "seviye": seviye,
            "planlar": planlar,
            "duzenleyebilir": can(request.user, "dini_ders_takip", "edit"),
            "aktif_sekme": "plan",
            "esik_form": esik_form,
        },
    )


@yonetici_gerekli
def dini_ders_plani_ekle(request):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:dini_ders_plani_listesi")

    yil = _aktif_egitim_yili()
    initial = {"egitim_yili": yil} if yil else {}
    if request.GET.get("seviye"):
        initial["seviye"] = request.GET.get("seviye")
    if request.GET.get("alan"):
        initial["alan"] = request.GET.get("alan")

    form = DiniAlanPlaniForm(request.POST or None, initial=initial)
    if form.is_valid():
        plan = form.save()
        messages.success(request, "İlerleme planı kaydedildi.")
        return redirect(
            f"{reverse('yonetim:dini_ders_plani_listesi')}?seviye={plan.seviye_id}"
        )

    return render(
        request,
        "yonetim/dini_ders_plani_form.html",
        {"form": form, "baslik": "Yeni İlerleme Planı", "aktif_sekme": "plan"},
    )


@yonetici_gerekli
def dini_ders_plani_duzenle(request, pk):
    if not _yonetim_yetki(request, "edit"):
        return redirect("yonetim:dini_ders_plani_listesi")

    plan = get_object_or_404(DiniAlanPlani, pk=pk)
    form = DiniAlanPlaniForm(request.POST or None, instance=plan)
    if form.is_valid():
        plan = form.save()
        messages.success(request, "İlerleme planı güncellendi.")
        return redirect(
            f"{reverse('yonetim:dini_ders_plani_listesi')}?seviye={plan.seviye_id}"
        )

    return render(
        request,
        "yonetim/dini_ders_plani_form.html",
        {
            "form": form,
            "baslik": f"Plan — {plan}",
            "aktif_sekme": "plan",
        },
    )
