"""E-Kitap görünümleri — yalnızca ``ekitap.<domain>`` üzerinde çalışır (config.ekitap_urls).

İki ayrı erişim:
- Görüntüleme (akıllı tahta): yöneticinin belirlediği PIN.
- Yönetim (/yonetim/): EKITAP_YONETICI_SIFRE ortam değişkenindeki şifre.
Ana sitenin kullanıcı hesapları burada kullanılmaz.
"""

from __future__ import annotations

import re
from functools import wraps

from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from takip import ekitap_service as servis
from takip.ekitap_models import EKitap, EKitapAyar, EKitapBolum, EKitapSayfa

PIN_DENEME_LIMIT = 8
YONETICI_DENEME_LIMIT = 5
KILIT_SURESI = 15 * 60
MAKS_BOLUM = 8


# —— Yardımcılar ————————————————————————————————————————————————————————————


def _guvenli_sonraki(request, varsayilan: str) -> str:
    hedef = request.POST.get("next") or request.GET.get("next") or ""
    if hedef and url_has_allowed_host_and_scheme(hedef, allowed_hosts={request.get_host()}):
        return hedef
    return varsayilan


def pin_gerekli(view):
    @wraps(view)
    def sarmal(request, *args, **kwargs):
        if not servis.pin_gecerli_mi(request):
            if request.path.endswith(".webp"):
                return HttpResponse(status=403)
            return redirect(f"{reverse('ekitap:pin')}?next={request.get_full_path()}")
        return view(request, *args, **kwargs)

    return sarmal


def yonetici_gerekli(view):
    @wraps(view)
    def sarmal(request, *args, **kwargs):
        if not servis.yonetici_mi(request):
            return redirect(f"{reverse('ekitap:yonetim_giris')}?next={request.get_full_path()}")
        return view(request, *args, **kwargs)

    return sarmal


def _gorunur_kitaplar():
    return (
        EKitap.objects.filter(gorunur=True, bolumler__islem_durumu=EKitapBolum.IslemDurumu.HAZIR)
        .distinct()
        .order_by("sira", "-olusturulma")
    )


def _kapak(kitap: EKitap) -> EKitapSayfa | None:
    return (
        EKitapSayfa.objects.filter(
            bolum__kitap=kitap, bolum__islem_durumu=EKitapBolum.IslemDurumu.HAZIR
        )
        .order_by("bolum__sira", "bolum_id", "sira")
        .first()
    )


# —— Görüntüleme (tahta) ————————————————————————————————————————————————————


@require_GET
def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


@never_cache
def pin_giris(request):
    ayar = EKitapAyar.al()
    hata = ""
    if request.method == "POST":
        if servis.deneme_kilitli_mi(request, "pin", limit=PIN_DENEME_LIMIT, sure_sn=KILIT_SURESI):
            hata = "Çok fazla hatalı deneme. 15 dakika sonra tekrar deneyin."
        else:
            surum = servis.pin_dogru_mu((request.POST.get("pin") or "").strip())
            if surum is not None:
                servis.denemeleri_sifirla(request, "pin")
                request.session.cycle_key()
                request.session[servis.OTURUM_PIN] = surum
                return redirect(_guvenli_sonraki(request, reverse("ekitap:liste")))
            servis.hatali_deneme_kaydet(request, "pin", sure_sn=KILIT_SURESI)
            hata = "PIN hatalı."
    return render(
        request,
        "ekitap/pin.html",
        {"hata": hata, "pin_tanimli": bool(ayar.pin_hash), "next": request.GET.get("next", "")},
    )


@require_POST
def pin_cikis(request):
    request.session.pop(servis.OTURUM_PIN, None)
    return redirect("ekitap:pin")


@never_cache
@pin_gerekli
def liste(request):
    kitaplar = list(_gorunur_kitaplar().prefetch_related("bolumler"))
    for kitap in kitaplar:
        kitap.kapak = _kapak(kitap)
        hazir = [b for b in kitap.bolumler.all() if b.islem_durumu == EKitapBolum.IslemDurumu.HAZIR]
        kitap.bolum_adlari = [b.ad for b in hazir]
        kitap.sayfa_toplam = sum(b.sayfa_sayisi for b in hazir)
    return render(request, "ekitap/liste.html", {"kitaplar": kitaplar})


@never_cache
@pin_gerekli
def okuyucu(request, kitap_id: int):
    yonetici = servis.yonetici_mi(request)
    kitap = get_object_or_404(EKitap, pk=kitap_id)
    if not kitap.gorunur and not yonetici:
        raise Http404
    bolumler = list(
        kitap.hazir_bolumler().prefetch_related(
            Prefetch("sayfalar", queryset=EKitapSayfa.objects.order_by("sira"))
        )
    )
    if not bolumler:
        raise Http404
    veri = [
        {
            "id": b.pk,
            "ad": b.ad,
            "sayfalar": [
                {
                    "src": reverse("ekitap:sayfa", args=[s.pk]),
                    "kucuk": reverse("ekitap:sayfa_kucuk", args=[s.pk]),
                    "w": s.genislik,
                    "h": s.yukseklik,
                }
                for s in b.sayfalar.all()
            ],
        }
        for b in bolumler
    ]
    return render(
        request,
        "ekitap/okuyucu.html",
        {
            "kitap": kitap,
            "bolumler": bolumler,
            "veri": veri,
            "yonetici_onizleme": yonetici and not kitap.gorunur,
        },
    )


def _sayfa_dosyasi(request, sayfa_id: int, alan: str):
    sayfa = get_object_or_404(EKitapSayfa.objects.select_related("bolum__kitap"), pk=sayfa_id)
    if not sayfa.bolum.kitap.gorunur and not servis.yonetici_mi(request):
        raise Http404
    dosya = getattr(sayfa, alan)
    if not dosya:
        raise Http404
    try:
        yanit = FileResponse(dosya.storage.open(dosya.name, "rb"), content_type="image/webp")
    except FileNotFoundError as exc:
        raise Http404 from exc
    # Görsel adresi sayfa kaydına özgüdür; PDF değişince yeni kayıt/adres oluşur.
    yanit["Cache-Control"] = "private, max-age=604800"
    return yanit


@require_GET
@pin_gerekli
def sayfa_gorseli(request, sayfa_id: int):
    return _sayfa_dosyasi(request, sayfa_id, "gorsel")


@require_GET
@pin_gerekli
def sayfa_kucuk(request, sayfa_id: int):
    return _sayfa_dosyasi(request, sayfa_id, "kucuk")


# —— Yönetim ———————————————————————————————————————————————————————————————


@never_cache
def yonetim_giris(request):
    hata = ""
    tanimli = servis.yonetici_sifresi_tanimli_mi()
    if request.method == "POST" and tanimli:
        if servis.deneme_kilitli_mi(request, "yonetici", limit=YONETICI_DENEME_LIMIT, sure_sn=KILIT_SURESI):
            hata = "Çok fazla hatalı deneme. 15 dakika sonra tekrar deneyin."
        elif servis.yonetici_sifresi_dogru_mu(request.POST.get("sifre") or ""):
            servis.denemeleri_sifirla(request, "yonetici")
            request.session.cycle_key()
            request.session[servis.OTURUM_YONETICI] = True
            return redirect(_guvenli_sonraki(request, reverse("ekitap:yonetim")))
        else:
            servis.hatali_deneme_kaydet(request, "yonetici", sure_sn=KILIT_SURESI)
            hata = "Şifre hatalı."
    return render(
        request,
        "ekitap/yonetim/giris.html",
        {"hata": hata, "sifre_tanimli": tanimli, "next": request.GET.get("next", "")},
    )


@require_POST
def yonetim_cikis(request):
    request.session.pop(servis.OTURUM_YONETICI, None)
    return redirect("ekitap:yonetim_giris")


@never_cache
@yonetici_gerekli
def yonetim(request):
    kitaplar = list(EKitap.objects.prefetch_related("bolumler").order_by("sira", "-olusturulma"))
    for kitap in kitaplar:
        kitap.kapak = _kapak(kitap)
    isleniyor = any(
        b.islem_durumu == EKitapBolum.IslemDurumu.BEKLIYOR for k in kitaplar for b in k.bolumler.all()
    )
    ayar = EKitapAyar.al()
    return render(
        request,
        "ekitap/yonetim/panel.html",
        {
            "kitaplar": kitaplar,
            "gorunur_sayisi": sum(1 for k in kitaplar if k.gorunur),
            "toplam_sayfa": sum(
                b.sayfa_sayisi for k in kitaplar for b in k.bolumler.all()
                if b.islem_durumu == EKitapBolum.IslemDurumu.HAZIR
            ),
            "isleniyor": isleniyor,
            "pin_tanimli": bool(ayar.pin_hash),
            "goruntuleme_adresi": request.build_absolute_uri(reverse("ekitap:liste")),
        },
    )


@require_POST
@yonetici_gerekli
def yonetim_pin(request):
    pin = (request.POST.get("pin") or "").strip()
    tekrar = (request.POST.get("pin_tekrar") or "").strip()
    if not re.fullmatch(r"\d{4,12}", pin):
        messages.error(request, "PIN 4–12 haneli rakamlardan oluşmalı.")
    elif pin != tekrar:
        messages.error(request, "PIN'ler eşleşmiyor.")
    else:
        servis.pin_belirle(pin)
        messages.success(request, "PIN kaydedildi. Açık tahtalar yeni PIN'i isteyecek.")
    return redirect("ekitap:yonetim")


def _yeni_bolum_satirlari(request) -> tuple[list[tuple[str, object]], list[str]]:
    """Formdaki 'yeni_ad_N' + 'yeni_pdf_N' çiftlerini okur."""
    satirlar: list[tuple[str, object]] = []
    hatalar: list[str] = []
    for i in range(MAKS_BOLUM):
        dosya = request.FILES.get(f"yeni_pdf_{i}")
        ad = (request.POST.get(f"yeni_ad_{i}") or "").strip()
        if not dosya:
            if ad:
                hatalar.append(f"“{ad}” bölümü için PDF seçilmedi.")
            continue
        if not ad:
            ad = re.sub(r"\.pdf$", "", dosya.name, flags=re.I)[:80]
        hata = servis.pdf_dogrula(dosya)
        if hata:
            hatalar.append(hata)
        else:
            satirlar.append((ad[:80], dosya))
    return satirlar, hatalar


@never_cache
@yonetici_gerekli
def kitap_yeni(request):
    hatalar: list[str] = []
    ad = ""
    if request.method == "POST":
        ad = (request.POST.get("ad") or "").strip()
        satirlar, hatalar = _yeni_bolum_satirlari(request)
        if not satirlar and not hatalar:
            hatalar.append("En az bir PDF yükleyin.")
        if not ad:
            hatalar.insert(0, "Kitap adı gerekli.")
        if not hatalar:
            with transaction.atomic():
                kitap = EKitap.objects.create(
                    ad=ad[:160], gorunur=request.POST.get("gorunur") == "on"
                )
                ids = [
                    EKitapBolum.objects.create(kitap=kitap, ad=bad, sira=i, pdf=dosya).pk
                    for i, (bad, dosya) in enumerate(satirlar)
                ]
                servis.bolumleri_isle(ids)
            messages.success(request, f"“{kitap.ad}” eklendi. PDF sayfaları hazırlanıyor.")
            return redirect("ekitap:yonetim")
    return render(
        request,
        "ekitap/yonetim/kitap_form.html",
        {"hatalar": hatalar, "ad": ad, "yeni": True, "satir_sayisi": range(MAKS_BOLUM)},
    )


@never_cache
@yonetici_gerekli
def kitap_duzenle(request, kitap_id: int):
    kitap = get_object_or_404(EKitap, pk=kitap_id)
    hatalar: list[str] = []
    if request.method == "POST":
        ad = (request.POST.get("ad") or "").strip()
        if not ad:
            hatalar.append("Kitap adı gerekli.")
        degisen: list[tuple[EKitapBolum, str, int, object]] = []
        for bolum in kitap.bolumler.all():
            bad = (request.POST.get(f"ad_{bolum.pk}") or "").strip() or bolum.ad
            try:
                sira = int(request.POST.get(f"sira_{bolum.pk}") or bolum.sira)
            except ValueError:
                sira = bolum.sira
            yeni_pdf = request.FILES.get(f"pdf_{bolum.pk}")
            if yeni_pdf:
                hata = servis.pdf_dogrula(yeni_pdf)
                if hata:
                    hatalar.append(hata)
            degisen.append((bolum, bad[:80], sira, yeni_pdf))
        yeni_satirlar, yeni_hatalar = _yeni_bolum_satirlari(request)
        hatalar += yeni_hatalar
        if not hatalar:
            isle: list[int] = []
            with transaction.atomic():
                kitap.ad = ad[:160]
                kitap.gorunur = request.POST.get("gorunur") == "on"
                kitap.save()
                for bolum, bad, sira, yeni_pdf in degisen:
                    bolum.ad, bolum.sira = bad, sira
                    if yeni_pdf:
                        eski = bolum.pdf.name
                        bolum.pdf = yeni_pdf
                        bolum.save()
                        if eski and eski != bolum.pdf.name:
                            bolum.pdf.storage.delete(eski)
                        isle.append(bolum.pk)
                    else:
                        bolum.save(update_fields=["ad", "sira", "guncellenme"])
                son_sira = max([s for _, _, s, _ in degisen], default=-1)
                for i, (bad, dosya) in enumerate(yeni_satirlar, start=son_sira + 1):
                    isle.append(EKitapBolum.objects.create(kitap=kitap, ad=bad, sira=i, pdf=dosya).pk)
                servis.bolumleri_isle(isle)
            messages.success(
                request,
                "Değişiklikler kaydedildi." + (" Yeni PDF sayfaları hazırlanıyor." if isle else ""),
            )
            return redirect("ekitap:yonetim")
    return render(
        request,
        "ekitap/yonetim/kitap_form.html",
        {
            "kitap": kitap,
            "bolumler": kitap.bolumler.all(),
            "hatalar": hatalar,
            "ad": kitap.ad,
            "yeni": False,
            "satir_sayisi": range(MAKS_BOLUM),
        },
    )


@require_POST
@yonetici_gerekli
def kitap_gorunurluk(request, kitap_id: int):
    kitap = get_object_or_404(EKitap, pk=kitap_id)
    kitap.gorunur = not kitap.gorunur
    kitap.save(update_fields=["gorunur", "guncellenme"])
    messages.success(request, f"“{kitap.ad}” {'gösteriliyor' if kitap.gorunur else 'gizlendi'}.")
    return redirect("ekitap:yonetim")


@require_POST
@yonetici_gerekli
def kitap_sil(request, kitap_id: int):
    kitap = get_object_or_404(EKitap, pk=kitap_id)
    ad = kitap.ad
    servis.kitap_sil(kitap)
    messages.success(request, f"“{ad}” silindi.")
    return redirect("ekitap:yonetim")


@require_POST
@yonetici_gerekli
def bolum_sil(request, bolum_id: int):
    bolum = get_object_or_404(EKitapBolum, pk=bolum_id)
    kitap_id = bolum.kitap_id
    servis.bolum_dosyalarini_sil(bolum)
    bolum.delete()
    messages.success(request, "Bölüm silindi.")
    return redirect("ekitap:kitap_duzenle", kitap_id=kitap_id)


@require_POST
@yonetici_gerekli
def bolum_yeniden_isle(request, bolum_id: int):
    bolum = get_object_or_404(EKitapBolum, pk=bolum_id)
    servis.bolumleri_isle([bolum.pk])
    messages.success(request, f"“{bolum.ad}” yeniden işleniyor.")
    return redirect("ekitap:yonetim")
