"""Öğrenci, optik şablon ve kullanıcı yönetimi."""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import Http404
from django.contrib.auth.models import User
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from okuma.forms import (
    KullaniciDuzenleForm,
    KullaniciOlusturForm,
    OgrenciForm,
    OgrenciTopluForm,
    SablonForm,
    SifreForm,
)
from okuma.erisim import erisim_gerekli, kullanici_yonetimi_acik
from okuma.models import Ogrenci, OptikSablon
from okuma.services.ogrenci_aktar import (
    etkilenen_denemeleri_hesapla,
    excel_ayristir,
    metni_ayristir,
    ogrencileri_kaydet,
)
from okuma.services.optik import dosyayi_ayristir, metni_coz

def _yonetici_ve_acik(u) -> bool:
    if not kullanici_yonetimi_acik():
        raise Http404("Kullanıcılar ana siteden yönetilir.")
    return u.is_active and u.is_superuser


yonetici_gerekli = user_passes_test(_yonetici_ve_acik)


def _ana_site_acik() -> bool:
    from okuma.services.ana_site import ana_site_acik

    return ana_site_acik()


# ── Öğrenciler ──────────────────────────────────────────────────────────────


@erisim_gerekli
def ogrenciler(request):
    qs = Ogrenci.objects.annotate(deneme_sayisi=Count("sonuclar"))
    q = request.GET.get("q", "").strip()
    sinif = request.GET.get("sinif", "")
    filtre = request.GET.get("filtre", "")
    if q:
        qs = qs.filter(Q(numara__startswith=q.lstrip("0") or q) | Q(ad_soyad__icontains=q))
    if sinif:
        seviye, _, sube = sinif.partition("-")
        qs = qs.filter(sinif_seviyesi=seviye, sube=sube)
    if filtre == "isimsiz":
        qs = qs.filter(ad_soyad="")
    elif filtre == "pasif":
        qs = qs.filter(aktif=False)
    else:
        qs = qs.filter(aktif=True)

    form = OgrenciForm(request.POST or None, initial={"aktif": True})
    if request.method == "POST" and form.is_valid():
        ogr = form.save()
        messages.success(request, f"{ogr.numara} · {ogr.ad_soyad} eklendi.")
        return redirect("ogrenciler")

    siniflar = (
        Ogrenci.objects.filter(aktif=True)
        .values("sinif_seviyesi", "sube")
        .annotate(adet=Count("id"))
        .order_by("sinif_seviyesi", "sube")
    )
    return render(
        request,
        "okuma/ogrenciler.html",
        {
            "ogrenciler": sorted(qs, key=lambda o: (o.sinif_seviyesi, o.sube, int(o.numara) if o.numara.isdigit() else 0)),
            "form": form,
            "q": q,
            "sinif": sinif,
            "filtre": filtre,
            "siniflar": siniflar,
            "toplam": Ogrenci.objects.filter(aktif=True).count(),
            "isimsiz": Ogrenci.objects.filter(aktif=True, ad_soyad="").count(),
            "ana_site": _ana_site_acik(),
            "bagli": Ogrenci.objects.filter(aktif=True).exclude(dis_kimlik="").count(),
        },
    )


@erisim_gerekli
@require_POST
def ogrenci_ana_siteden(request):
    from okuma.services.ana_site import ana_site_acik, talebeleri_esitle

    if not ana_site_acik():
        raise Http404
    sonuc = talebeleri_esitle()
    messages.success(
        request,
        f"Ana siteden {sonuc.eklenen} talebe eklendi, {sonuc.guncellenen} güncellendi."
        + (f" {sonuc.numarasiz} talebenin numarası yok." if sonuc.numarasiz else ""),
    )
    return redirect("ogrenciler")


@erisim_gerekli
def ogrenci_duzenle(request, pk):
    ogr = get_object_or_404(Ogrenci, pk=pk)
    form = OgrenciForm(request.POST or None, instance=ogr)
    if request.method == "POST" and form.is_valid():
        form.save()
        hesaplanan = etkilenen_denemeleri_hesapla([ogr.pk]) if {"sube", "numara"} & set(form.changed_data) else 0
        messages.success(
            request,
            f"{ogr.numara} · {ogr.ad_soyad} kaydedildi."
            + (f" {hesaplanan} denemenin sıralaması güncellendi." if hesaplanan else ""),
        )
        return redirect("ogrenciler")
    sonuclar = ogr.sonuclar.select_related("deneme").order_by("-deneme__tarih")
    return render(request, "okuma/ogrenci_form.html", {"form": form, "ogrenci": ogr, "sonuclar": sonuclar})


@erisim_gerekli
@require_POST
def ogrenci_sil(request, pk):
    ogr = get_object_or_404(Ogrenci, pk=pk)
    deneme_idler = list(ogr.sonuclar.values_list("deneme_id", flat=True))
    ad = str(ogr)
    ogr.delete()
    from okuma.models import Deneme
    from okuma.services.puanlama import deneme_hesapla

    for d in Deneme.objects.filter(pk__in=deneme_idler):
        deneme_hesapla(d)
    messages.success(request, f"{ad} silindi.")
    return redirect("ogrenciler")


@erisim_gerekli
def ogrenci_toplu(request):
    form = OgrenciTopluForm(request.POST or None, request.FILES or None)
    sonuc = None
    if request.method == "POST" and form.is_valid():
        try:
            if form.cleaned_data.get("dosya"):
                satirlar, hatalar = excel_ayristir(form.cleaned_data["dosya"].read())
            else:
                satirlar, hatalar = metni_ayristir(form.cleaned_data["metin"])
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            sonuc = ogrencileri_kaydet(satirlar, form.cleaned_data.get("varsayilan_sinif", "").strip())
            sonuc.hatalar = hatalar + sonuc.hatalar
            hesaplanan = etkilenen_denemeleri_hesapla(sonuc.ogrenci_idler)
            messages.success(
                request,
                f"{sonuc.eklenen} öğrenci eklendi, {sonuc.guncellenen} güncellendi, {sonuc.degismeyen} aynı kaldı."
                + (f" {hesaplanan} denemenin sonuçları güncellendi." if hesaplanan else ""),
            )
            if not sonuc.hatalar:
                return redirect("ogrenciler")
    return render(request, "okuma/ogrenci_toplu.html", {"form": form, "sonuc": sonuc})


# ── Optik şablonlar ─────────────────────────────────────────────────────────


@erisim_gerekli
def sablonlar(request):
    from okuma.models import DenemeTuru

    return render(
        request,
        "okuma/sablonlar.html",
        {
            "sablonlar": OptikSablon.objects.annotate(deneme_sayisi=Count("optikyukleme__deneme", distinct=True)),
            "turler": DenemeTuru.objects.prefetch_related("dersler").annotate(deneme_sayisi=Count("denemeler")),
        },
    )


@erisim_gerekli
def sablon_form(request, pk=None):
    sablon = get_object_or_404(OptikSablon, pk=pk) if pk else None
    form = SablonForm(request.POST or None, instance=sablon)
    onizleme = None
    if request.method == "POST" and form.is_valid():
        if "onizle" in request.POST and request.FILES.get("ornek"):
            # Kaydetmeden, örnek dosyanın ilk satırlarının nasıl okunacağını göster.
            gecici = form.save(commit=False)
            soru = int(request.POST.get("soru_sayisi") or 90)
            veri = request.FILES["ornek"].read()
            onizleme = {"satirlar": dosyayi_ayristir(metni_coz(veri, gecici.kodlama), gecici, soru)[:8], "soru": soru}
        else:
            kayit = form.save()
            messages.success(request, f"“{kayit.ad}” şablonu kaydedildi.")
            return redirect("sablonlar")
    return render(request, "okuma/sablon_form.html", {"form": form, "sablon": sablon, "onizleme": onizleme})


@erisim_gerekli
@require_POST
def sablon_sil(request, pk):
    sablon = get_object_or_404(OptikSablon, pk=pk)
    try:
        sablon.delete()
        messages.success(request, "Şablon silindi.")
    except ProtectedError:
        messages.error(request, "Bu şablonla okunmuş dosyalar var; silinemez.")
    return redirect("sablonlar")


# ── Kullanıcılar ────────────────────────────────────────────────────────────


@erisim_gerekli
@yonetici_gerekli
def kullanicilar(request):
    return render(request, "okuma/kullanicilar.html", {"kullanicilar": User.objects.order_by("-is_active", "username")})


@erisim_gerekli
@yonetici_gerekli
def kullanici_olustur(request):
    form = KullaniciOlusturForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"{user.username} kullanıcısı oluşturuldu.")
        return redirect("kullanicilar")
    return render(request, "okuma/kullanici_form.html", {"form": form})


@erisim_gerekli
@yonetici_gerekli
def kullanici_duzenle(request, pk):
    kullanici = get_object_or_404(User, pk=pk)
    sifre_istegi = request.method == "POST" and "sifre" in request.POST
    form = KullaniciDuzenleForm(
        request.POST if request.method == "POST" and not sifre_istegi else None, instance=kullanici, prefix="b"
    )
    sifre_form = SifreForm(kullanici, request.POST if sifre_istegi else None, prefix="s")
    if sifre_istegi and sifre_form.is_valid():
        sifre_form.save()
        messages.success(request, f"{kullanici.username} şifresi değiştirildi.")
        return redirect("kullanicilar")
    if form.is_bound and form.is_valid():
        if kullanici == request.user and (not form.cleaned_data["is_active"] or not form.cleaned_data["is_superuser"]):
            messages.error(request, "Kendi yönetici yetkinizi ya da hesabınızı kapatamazsınız.")
        else:
            form.save()
            messages.success(request, f"{kullanici.username} güncellendi.")
            return redirect("kullanicilar")
    return render(
        request, "okuma/kullanici_form.html", {"form": form, "sifre_form": sifre_form, "kullanici": kullanici}
    )


# ── Deneme türleri ──────────────────────────────────────────────────────────


@erisim_gerekli
def deneme_turu(request, pk):
    from okuma.forms import DenemeTuruDersFormSet
    from okuma.models import DenemeTuru

    tur = get_object_or_404(DenemeTuru, pk=pk)
    formset = DenemeTuruDersFormSet(request.POST or None, queryset=tur.dersler.all())
    if request.method == "POST" and formset.is_valid():
        formset.save()
        messages.success(request, f"“{tur.ad}” güncellendi. Yeni denemeler bu yapıyla açılır; eskiler değişmez.")
        return redirect("sablonlar")
    return render(request, "okuma/deneme_turu.html", {"tur": tur, "formset": formset})
