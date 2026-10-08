"""Sınav okuma alanı. Ana panel oturumundan ayrı, kendi şifresiyle açılır."""

from __future__ import annotations

import hmac
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from sinav_okuma.kayit import sonuclari_yaz
from sinav_okuma.models import OptikForm, OptikFormAlani, Sinav
from sinav_okuma.okuma import (
    OptikHata,
    alan_metni,
    anahtar_temizle,
    dagilim_coz,
    dagilim_metni,
    form_alanlarini_coz,
    harita_from_form,
    kazanim_listesi,
    kazanim_metni,
    optik_oku,
    satirlari_puanla,
)

OTURUM = "sinav_okuma_yonetici"
_MAKS_DOSYA = 2_000_000


def _sifre_tanimli() -> bool:
    return bool(getattr(settings, "SINAV_YONETICI_SIFRE", "") or "")


def _sifre_dogru(gelen: str) -> bool:
    beklenen = getattr(settings, "SINAV_YONETICI_SIFRE", "") or ""
    if not beklenen or not gelen:
        return False
    return hmac.compare_digest(gelen.encode("utf-8"), beklenen.encode("utf-8"))


def _sonraki(request) -> str:
    hedef = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if not hedef.startswith("/") or hedef.startswith("//"):
        return reverse("sinav_okuma:sinav_listesi")
    return hedef


def yonetici_gerekli(view):
    @wraps(view)
    def sarmal(request, *args, **kwargs):
        if not request.session.get(OTURUM):
            giris = reverse("sinav_okuma:giris")
            return redirect(f"{giris}?next={request.get_full_path()}")
        return view(request, *args, **kwargs)

    return sarmal


@never_cache
def giris(request):
    if request.session.get(OTURUM):
        return redirect("sinav_okuma:sinav_listesi")
    hata = ""
    tanimli = _sifre_tanimli()
    if request.method == "POST" and tanimli:
        if _sifre_dogru(request.POST.get("sifre") or ""):
            request.session.cycle_key()
            request.session[OTURUM] = True
            return redirect(_sonraki(request))
        hata = "Şifre hatalı."
    return render(
        request,
        "sinav_okuma/giris.html",
        {"hata": hata, "sifre_tanimli": tanimli, "next": request.GET.get("next", "")},
    )


@require_POST
def cikis(request):
    request.session.pop(OTURUM, None)
    return redirect("sinav_okuma:giris")


@yonetici_gerekli
def sinav_listesi(request):
    if request.method == "POST":
        ad = (request.POST.get("ad") or "").strip()
        try:
            tarih = datetime.strptime(request.POST.get("tarih") or "", "%Y-%m-%d").date()
        except ValueError:
            tarih = None
        if not ad:
            messages.error(request, "Sınavın adını yazın.")
        elif tarih is None:
            messages.error(request, "Sınav tarihini seçin.")
        else:
            sinav = Sinav.objects.create(ad=ad[:200], tarih=tarih)
            messages.success(request, f"«{sinav.ad}» oluşturuldu.")
            return redirect("sinav_okuma:sinav_detay", pk=sinav.pk)
    sinavlar = Sinav.objects.select_related("form")
    return render(request, "sinav_okuma/sinav_listesi.html", {"sinavlar": sinavlar})


@yonetici_gerekli
def sinav_detay(request, pk):
    sinav = get_object_or_404(Sinav.objects.select_related("form"), pk=pk)
    if request.method == "POST":
        _tanimi_kaydet(request, sinav)
        return redirect("sinav_okuma:sinav_detay", pk=sinav.pk)
    satirlar = list(sinav.satirlar.all())
    return render(
        request,
        "sinav_okuma/sinav_detay.html",
        {
            "sinav": sinav,
            "formlar": OptikForm.objects.all(),
            "satirlar": satirlar,
            "puanlanan": sum(1 for s in satirlar if s.puanlandi),
        },
    )


def _tanimi_kaydet(request, sinav: Sinav) -> None:
    form = get_object_or_404(OptikForm, pk=request.POST.get("form_id") or 0)
    try:
        harita = harita_from_form(form)
        dagilim = dagilim_coz(request.POST.get("dagilim", ""), harita.sik_sayisi)
        anahtar_a = anahtar_temizle(
            request.POST.get("anahtar_a", ""),
            harita.sik_sayisi,
            kitapcik="A",
        )
        ham_b = request.POST.get("anahtar_b", "")
        anahtar_b = ""
        if "".join(ham_b.split()):
            anahtar_b = anahtar_temizle(ham_b, harita.sik_sayisi, kitapcik="B")
        kazanimlar = kazanim_listesi(request.POST.get("kazanimlar", ""), harita.sik_sayisi)
    except OptikHata as exc:
        messages.error(request, str(exc))
        return
    sinav.form = form
    sinav.anahtar_a = anahtar_a
    sinav.anahtar_b = anahtar_b
    sinav.dagilim = dagilim_metni(dagilim)
    sinav.kazanimlar = kazanim_metni(kazanimlar)
    sinav.save(update_fields=["form", "anahtar_a", "anahtar_b", "dagilim", "kazanimlar", "guncellenme"])
    messages.success(request, f"Tanım kaydedildi: {form.ad}.")


@yonetici_gerekli
@require_POST
def sinav_oku(request, pk):
    sinav = get_object_or_404(Sinav.objects.select_related("form"), pk=pk)
    dosya = request.FILES.get("optik_dosya")
    if not dosya:
        messages.error(request, "Optik dosyası seçin (.dat).")
        return redirect("sinav_okuma:sinav_detay", pk=pk)
    if dosya.size > _MAKS_DOSYA:
        messages.error(request, "Optik dosyası 2 MB sınırını aşıyor.")
        return redirect("sinav_okuma:sinav_detay", pk=pk)
    if sinav.form_id is None or not (sinav.anahtar_a or "").strip():
        messages.error(request, "Önce optik formunu ve cevap anahtarını kaydedin.")
        return redirect("sinav_okuma:sinav_detay", pk=pk)
    try:
        harita = harita_from_form(sinav.form)
        optik = optik_oku(dosya.read(), harita)
        dagilim = dagilim_coz(sinav.dagilim, optik.cevap_sayisi)
        kazanimlar = kazanim_listesi(sinav.kazanimlar, optik.cevap_sayisi)
        puanlar = satirlari_puanla(
            optik, dagilim, sinav.anahtar_a, sinav.anahtar_b or "", kazanimlar
        )
    except OptikHata as exc:
        messages.error(request, str(exc))
        return redirect("sinav_okuma:sinav_detay", pk=pk)
    adet = sonuclari_yaz(
        sinav,
        puanlar,
        dosya_adi=dosya.name or "",
        notlar=list(optik.uyarilar),
    )
    messages.success(request, f"{adet} satır okundu ve bu sınava yazıldı.")
    return redirect("sinav_okuma:sinav_detay", pk=pk)


@yonetici_gerekli
@require_POST
def sinav_sil(request, pk):
    sinav = get_object_or_404(Sinav, pk=pk)
    ad = sinav.ad
    sinav.delete()
    messages.success(request, f"«{ad}» silindi.")
    return redirect("sinav_okuma:sinav_listesi")


@yonetici_gerekli
def form_listesi(request):
    formlar = OptikForm.objects.prefetch_related("alanlar")
    return render(request, "sinav_okuma/form_listesi.html", {"formlar": formlar})


@yonetici_gerekli
def form_kaydet(request, pk=None):
    kayit = get_object_or_404(OptikForm, pk=pk) if pk else None
    if request.method == "POST" and request.POST.get("aksiyon") == "sil" and kayit:
        if kayit.sinavlar.exists():
            messages.error(request, "Bu formu kullanan sınav var. Silinmez.")
            return redirect("sinav_okuma:form_kaydet", pk=kayit.pk)
        kayit.delete()
        messages.success(request, "Optik form silindi.")
        return redirect("sinav_okuma:form_listesi")

    posted = {
        "ad": (request.POST.get("ad") or (kayit.ad if kayit else "")).strip(),
        "aciklama": request.POST.get("aciklama") if request.method == "POST" else (kayit.aciklama if kayit else ""),
        "satir_uzunluk": request.POST.get("satir_uzunluk") if request.method == "POST" else (kayit.satir_uzunluk if kayit else ""),
        "kodlama": request.POST.get("kodlama") if request.method == "POST" else (kayit.kodlama if kayit else "cp1254"),
        "alanlar": (
            request.POST.get("alanlar")
            if request.method == "POST"
            else (alan_metni(harita_from_form(kayit).alanlar) if kayit else "")
        ),
    }
    if request.method == "POST" and request.POST.get("aksiyon") != "sil":
        try:
            uzunluk = int(posted["satir_uzunluk"] or 0)
        except ValueError:
            uzunluk = 0
        kodlama = posted["kodlama"] if posted["kodlama"] in {"cp1254", "utf-8"} else "cp1254"
        try:
            if not posted["ad"]:
                raise OptikHata("Formun adını yazın.")
            if OptikForm.objects.exclude(pk=getattr(kayit, "pk", None)).filter(ad=posted["ad"]).exists():
                raise OptikHata("Bu adda bir form zaten var.")
            alanlar = form_alanlarini_coz(posted["alanlar"], uzunluk)
        except OptikHata as exc:
            messages.error(request, str(exc))
        else:
            with transaction.atomic():
                if kayit is None:
                    kayit = OptikForm.objects.create(
                        ad=posted["ad"],
                        aciklama=(posted["aciklama"] or "").strip(),
                        satir_uzunluk=uzunluk,
                        kodlama=kodlama,
                    )
                else:
                    kayit.ad = posted["ad"]
                    kayit.aciklama = (posted["aciklama"] or "").strip()
                    kayit.satir_uzunluk = uzunluk
                    kayit.kodlama = kodlama
                    kayit.save()
                    kayit.alanlar.all().delete()
                OptikFormAlani.objects.bulk_create(
                    [
                        OptikFormAlani(
                            form=kayit,
                            tur=alan.tur,
                            baslangic=alan.baslangic,
                            bitis=alan.bitis,
                            sira=sira,
                        )
                        for sira, alan in enumerate(alanlar)
                    ]
                )
            messages.success(request, f"«{kayit.ad}» kaydedildi.")
            return redirect("sinav_okuma:form_listesi")

    return render(
        request,
        "sinav_okuma/form_form.html",
        {"kayit": kayit, "posted": posted},
    )
