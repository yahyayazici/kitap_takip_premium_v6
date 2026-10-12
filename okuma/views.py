import io

import openpyxl
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from okuma.erisim import erisim_gerekli, erisimi_var, yetki_yok
from okuma.forms import AnahtarForm, DenemeDuzenleForm, DenemeForm, OptikForm, SatirForm, SoruForm
from okuma.models import Deneme, Ogrenci, OptikSablon, OptikSatir, Soru, Sonuc
from okuma.services import analiz
from okuma.services.anahtar_excel import AnahtarHatasi, anahtar_elle, anahtar_yukle
from okuma.services.yapi import yapiyi_kur
from okuma.services.optik import numara_normalize, optik_yukle
from okuma.services.puanlama import deneme_hesapla


def _yeniden_hesapla(request, deneme: Deneme):
    if not deneme.testler.exists():
        return
    try:
        adet = deneme_hesapla(deneme)
        messages.success(request, f"Sonuçlar yeniden hesaplandı ({adet} öğrenci).")
    except ValueError as exc:
        messages.error(request, str(exc))


def _katilmayanlar(deneme: Deneme):
    """Denemenin sınıf düzeyindeki aktif öğrencilerden sonucu olmayanlar."""
    return (
        Ogrenci.objects.filter(aktif=True, sinif_seviyesi=deneme.sinif_seviyesi)
        .exclude(sonuclar__deneme=deneme)
        .order_by("sube", "ad_soyad")
    )


def deneme_listesi(request):
    if not request.user.is_authenticated:
        # Yönlendirme yerine giriş formunu doğrudan göster: kök adres her zaman 200 döner.
        return LoginView.as_view(template_name="okuma/giris.html", next_page="deneme_listesi")(request)
    if not erisimi_var(request.user):
        return yetki_yok(request)
    denemeler = Deneme.objects.annotate(
        ogrenci_sayisi=Count("sonuclar", distinct=True),
        ortalama_net=Avg("sonuclar__net"),
    )
    return render(
        request,
        "okuma/deneme_listesi.html",
        {
            "denemeler": denemeler,
            "ogrenci_sayisi": Ogrenci.objects.filter(aktif=True).count(),
            "isimsiz_sayisi": Ogrenci.objects.filter(aktif=True, ad_soyad="").count(),
        },
    )


@erisim_gerekli
def deneme_olustur(request):
    form = DenemeForm(request.POST or None, initial={"tarih": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        deneme = form.save(commit=False)
        deneme.olusturan = request.user
        deneme.sinif_seviyesi = deneme.tur.sinif_seviyesi
        deneme.save()
        yapiyi_kur(deneme)
        messages.success(request, f"Deneme oluşturuldu ({deneme.tur}). Şimdi cevap anahtarını girin.")
        return redirect("deneme_detay", pk=deneme.pk)
    return render(request, "okuma/deneme_form.html", {"form": form})


@erisim_gerekli
def deneme_duzenle(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    form = DenemeDuzenleForm(request.POST or None, instance=deneme)
    if request.method == "POST" and form.is_valid():
        form.save()
        _yeniden_hesapla(request, deneme)
        return redirect("deneme_detay", pk=deneme.pk)
    return render(request, "okuma/deneme_form.html", {"form": form, "deneme": deneme})


@erisim_gerekli
@require_POST
def deneme_sil(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    ad = deneme.ad
    deneme.delete()
    messages.success(request, f"“{ad}” silindi.")
    return redirect("deneme_listesi")


@erisim_gerekli
def deneme_detay(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    testler = deneme.testler.annotate(
        kazanimli=Count("sorular", filter=Q(sorular__kazanimlar__isnull=False), distinct=True),
        iptal=Count("sorular", filter=Q(sorular__iptal=True), distinct=True),
        soru_var=Count("sorular", distinct=True),
    )
    satirlar = OptikSatir.objects.filter(yukleme__deneme=deneme)
    durumlar = {d: satirlar.filter(durum=d).count() for d in OptikSatir.Durum.values}
    return render(
        request,
        "okuma/deneme_detay.html",
        {
            "deneme": deneme,
            "testler": testler,
            "anahtar_tamam": bool(testler) and all(t.soru_var == t.soru_sayisi for t in testler),
            "yuklemeler": deneme.yuklemeler.annotate(satir_sayisi=Count("satirlar")),
            "durumlar": durumlar,
            "satir_toplam": satirlar.count(),
            "sonuc_sayisi": deneme.sonuclar.count(),
            "katilmayan_sayisi": _katilmayanlar(deneme).count() if deneme.sonuclar.exists() else 0,
            "anahtar_form": AnahtarForm(),
            "optik_form": OptikForm(
                initial={
                    "sablon": deneme.sablon or OptikSablon.objects.first(),
                    # Öğrenci listesi girildiyse kayıtsız numara büyük ihtimalle yanlış kodlamadır.
                    "otomatik_ogrenci": not Ogrenci.objects.exclude(ad_soyad="").exists(),
                }
            ),
        },
    )


@erisim_gerekli
@require_POST
def anahtar_yukle_view(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    form = AnahtarForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            ozet = anahtar_yukle(deneme, form.cleaned_data["dosya"].read())
        except AnahtarHatasi as exc:
            messages.error(request, f"Excel okunamadı: {exc}")
        else:
            messages.success(
                request,
                f"{ozet.test_sayisi} test, {ozet.soru_sayisi} soru, {ozet.kazanim_sayisi} kazanım yüklendi. "
                f"Kitapçıklar: {', '.join(ozet.kitapciklar)}.",
            )
            _yeniden_hesapla(request, deneme)
    return redirect("deneme_detay", pk=pk)


@erisim_gerekli
@require_POST
def optik_yukle_view(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    form = OptikForm(request.POST, request.FILES)
    if form.is_valid():
        dosya = form.cleaned_data["dosya"]
        try:
            yukleme = optik_yukle(
                deneme,
                form.cleaned_data["sablon"],
                dosya.name,
                dosya.read(),
                kullanici=request.user,
                otomatik_ogrenci=form.cleaned_data["otomatik_ogrenci"],
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("deneme_detay", pk=pk)
        hata = yukleme.satirlar.filter(durum=OptikSatir.Durum.HATA).count()
        messages.success(request, f"{yukleme.satirlar.count()} satır okundu.")
        if hata:
            messages.warning(request, f"{hata} satır hatalı; düzeltmeden hesaba katılmaz.")
        _yeniden_hesapla(request, deneme)
    return redirect("deneme_detay", pk=pk)


@erisim_gerekli
@require_POST
def yukleme_sil(request, pk, yukleme_pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    deneme.yuklemeler.filter(pk=yukleme_pk).delete()
    messages.success(request, "Yükleme silindi.")
    _yeniden_hesapla(request, deneme)
    return redirect("deneme_detay", pk=pk)


@erisim_gerekli
def satirlar(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    qs = OptikSatir.objects.filter(yukleme__deneme=deneme).select_related("ogrenci", "yukleme")
    durum = request.GET.get("durum")
    if durum:
        qs = qs.filter(durum=durum)
    return render(
        request,
        "okuma/satirlar.html",
        {"deneme": deneme, "satirlar": qs, "durum": durum, "durumlar": OptikSatir.Durum.choices},
    )


@erisim_gerekli
@require_POST
def satir_duzenle(request, satir_pk):
    satir = get_object_or_404(OptikSatir.objects.select_related("yukleme__deneme"), pk=satir_pk)
    deneme = satir.yukleme.deneme
    form = SatirForm(request.POST)
    if form.is_valid():
        numara = numara_normalize(form.cleaned_data["numara"])
        kitapcik = form.cleaned_data["kitapcik"].strip().upper()
        hatalar = []
        if not numara.isdigit():
            hatalar.append("Numara geçersiz")
        if kitapcik not in deneme.kitapcik_listesi:
            hatalar.append("Kitapçık geçersiz")
        cakisan = (
            OptikSatir.objects.filter(yukleme__deneme=deneme, numara=numara, dahil=True).exclude(pk=satir.pk).exists()
        )
        if cakisan and form.cleaned_data["dahil"]:
            hatalar.append("Bu numara başka bir satırda da hesaba katılıyor")
        satir.numara, satir.kitapcik = numara, kitapcik
        if not hatalar:
            satir.ogrenci, _ = Ogrenci.objects.get_or_create(
                numara=numara, defaults={"sinif_seviyesi": deneme.sinif_seviyesi, "ad_soyad": satir.ad_soyad}
            )
            satir.durum = OptikSatir.Durum.TAMAM
            satir.mesaj = "Elle düzeltildi"
            satir.dahil = form.cleaned_data["dahil"]
        else:
            satir.durum = OptikSatir.Durum.HATA
            satir.mesaj = "; ".join(hatalar)
            satir.dahil = False
        satir.save()
        if hatalar:
            messages.error(request, f"Satır {satir.satir_no}: {satir.mesaj}")
        else:
            messages.success(request, f"Satır {satir.satir_no} güncellendi.")
            _yeniden_hesapla(request, deneme)
    geri = request.POST.get("geri", "")
    if url_has_allowed_host_and_scheme(geri, allowed_hosts={request.get_host()}):
        return redirect(geri)
    return redirect("satirlar", pk=deneme.pk)


@erisim_gerekli
@require_POST
def hesapla(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    _yeniden_hesapla(request, deneme)
    return redirect("deneme_detay", pk=pk)


@erisim_gerekli
def sonuclar(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    sube = request.GET.get("sube") or ""
    qs = deneme.sonuclar.select_related("ogrenci").prefetch_related("test_sonuclari").order_by("sira_kurum")
    if sube:
        qs = qs.filter(sube=sube)
    testler = list(deneme.testler.all())
    subeler = deneme.sonuclar.exclude(sube="").values_list("sube", flat=True).distinct().order_by("sube")
    dersler, sube_tablosu = analiz.sube_ozeti(deneme)
    katilmayanlar = _katilmayanlar(deneme)
    return render(
        request,
        "okuma/sonuclar.html",
        {
            "deneme": deneme,
            "sonuclar": qs,
            "testler": testler,
            "subeler": subeler,
            "sube": sube,
            "dersler": dersler,
            "sube_tablosu": sube_tablosu,
            "katilmayanlar": katilmayanlar,
        },
    )


@erisim_gerekli
def sonuclar_excel(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    testler = list(deneme.testler.all())
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sonuçlar"
    baslik = ["Sıra", "Şube sırası", "Numara", "Ad soyad", "Şube", "Kitapçık"]
    for t in testler:
        baslik += [f"{t.ders} D", f"{t.ders} Y", f"{t.ders} Net"]
    baslik += ["Doğru", "Yanlış", "Boş", "Net", "Puan", "Yüzdelik"]
    ws.append(baslik)
    for s in deneme.sonuclar.select_related("ogrenci").prefetch_related("test_sonuclari").order_by("sira_kurum"):
        satir = [s.sira_kurum, s.sira_sube, s.ogrenci.numara, s.ogrenci.ad_soyad, s.sube, s.kitapcik]
        ts_map = {ts.test_id: ts for ts in s.test_sonuclari.all()}
        for t in testler:
            ts = ts_map.get(t.pk)
            satir += [ts.dogru, ts.yanlis, float(ts.net)] if ts else ["", "", ""]
        satir += [s.dogru, s.yanlis, s.bos, float(s.net), float(s.puan) if s.puan is not None else "", float(s.yuzdelik or 0)]
        ws.append(satir)
    for kolon in ws.columns:
        ws.column_dimensions[kolon[0].column_letter].width = max(8, min(28, max(len(str(c.value or "")) for c in kolon) + 2))
    ws.freeze_panes = "E2"
    cikti = io.BytesIO()
    wb.save(cikti)
    yanit = HttpResponse(
        cikti.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    yanit["Content-Disposition"] = f'attachment; filename="deneme-{deneme.pk}-sonuclar.xlsx"'
    return yanit


def _karne_ortak(deneme: Deneme) -> dict:
    """Bir denemenin bütün karnelerinde ortak olan (bir kez hesaplanan) veriler."""
    dersler, sube_tablosu = analiz.sube_ozeti(deneme)
    return {
        "kurum_kazanim": {k.kazanim.pk: k.oran for k in analiz.kazanim_raporu(deneme)},
        "sube_tablosu": sube_tablosu,
        "harita": analiz.harita_kur(deneme),
    }


def _karne_verisi(deneme: Deneme, sonuc: Sonuc, ortak: dict) -> dict:
    kazanimlar = analiz.ogrenci_kazanimlari(sonuc)
    sube_tablosu = ortak["sube_tablosu"]
    kurum_ort = sube_tablosu[-1]
    sube_ort = next((s for s in sube_tablosu if s["ad"] == (sonuc.sube or "—")), None)
    test_satirlari = [
        (ts, kurum_ort["netler"][i], sube_ort["netler"][i] if sube_ort else None)
        for i, ts in enumerate(sonuc.test_sonuclari.all())
    ]
    harita = ortak["harita"]
    soru_satirlari = []
    for t in harita.testler:
        sorular = []
        for s in [x for x in harita.sorular if x.test_id == t.pk]:
            c = sonuc.cevaplar_a[s.a_index]
            durum = "iptal" if s.iptal else ("bos" if c == " " else ("dogru" if c in s.dogrular else "yanlis"))
            sorular.append({"cevap": c.strip() or "–", "anahtar": "/".join(sorted(s.dogrular)) or "X", "durum": durum})
        soru_satirlari.append((t, sorular))
    return {
        "sonuc": sonuc,
        "kazanimlar": [(k, ortak["kurum_kazanim"].get(k.kazanim.pk)) for k in kazanimlar],
        "eksikler": [k for k in kazanimlar if k.eksik],
        "test_satirlari": test_satirlari,
        "kurum_ort": kurum_ort,
        "soru_satirlari": soru_satirlari,
    }


@erisim_gerekli
def karne(request, pk, sonuc_pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    sonuc = get_object_or_404(
        Sonuc.objects.select_related("ogrenci").prefetch_related("test_sonuclari__test"), pk=sonuc_pk, deneme=deneme
    )
    return render(request, "okuma/karne.html", {"deneme": deneme, **_karne_verisi(deneme, sonuc, _karne_ortak(deneme))})


@erisim_gerekli
def karneler(request, pk):
    """Bir şubenin (ya da tüm denemenin) karneleri tek sayfada; her biri ayrı kâğıda basılır."""
    deneme = get_object_or_404(Deneme, pk=pk)
    sube = request.GET.get("sube")
    qs = deneme.sonuclar.select_related("ogrenci").prefetch_related("test_sonuclari__test")
    if sube is not None:
        qs = qs.filter(sube=sube)
    sirala = request.GET.get("sira", "ad")
    sonuclar = sorted(
        qs,
        key=(lambda s: s.sira_kurum or 0) if sirala == "sira" else (lambda s: (s.ogrenci.ad_soyad or "~", s.ogrenci.numara)),
    )
    ortak = _karne_ortak(deneme)
    return render(
        request,
        "okuma/karneler.html",
        {
            "deneme": deneme,
            "karneler": [_karne_verisi(deneme, s, ortak) for s in sonuclar],
            "sube": sube,
            "subeler": deneme.sonuclar.values_list("sube", flat=True).distinct().order_by("sube"),
        },
    )


@erisim_gerekli
def anahtar(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    if request.method == "POST":
        test = get_object_or_404(deneme.testler, pk=request.POST.get("test"))
        try:
            anahtar_elle(test, request.POST.get("a_cevaplar", ""), request.POST.get("b_sirasi", ""))
        except AnahtarHatasi as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"{test.ders} anahtarı kaydedildi.")
            _yeniden_hesapla(request, deneme)
        return redirect(f"{reverse('anahtar', args=[deneme.pk])}#test-{test.pk}")

    testler = []
    eksik_b = False
    for t in deneme.testler.prefetch_related("sorular__kitapcik_siralari", "sorular__kazanimlar"):
        sorular = sorted(t.sorular.all(), key=lambda x: x.no)
        b = [next((ks.no for ks in s.kitapcik_siralari.all() if ks.kitapcik == "B"), None) for s in sorular]
        b_tam = bool(sorular) and all(b)
        eksik_b |= bool(sorular) and not b_tam and "B" in deneme.kitapcik_listesi
        testler.append({
            "test": t,
            "sorular": sorular,
            "a_metin": "".join("X" if s.iptal else (s.dogru or "?") for s in sorular),
            "b_metin": " ".join(str(x) for x in b) if b_tam else "",
            "kazanimli": sum(1 for s in sorular if s.kazanimlar.all()),
        })
    return render(request, "okuma/anahtar.html", {"deneme": deneme, "testler": testler, "eksik_b": eksik_b})


@erisim_gerekli
def kazanim_raporu(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    satirlar = analiz.kazanim_raporu(deneme)
    subeler = sorted({s for k in satirlar for s in k.sube_oranlari})
    tablo = [(k, [(k.sube_oranlari.get(s), analiz.isi_rengi(k.sube_oranlari.get(s))) for s in subeler]) for k in satirlar]
    return render(
        request,
        "okuma/kazanim.html",
        {"deneme": deneme, "tablo": tablo, "subeler": subeler, "esik": analiz.EKSIK_ESIK},
    )


@erisim_gerekli
def madde_analizi(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    satirlar, kr20 = analiz.madde_analizi(deneme)
    sorular = {(s.test.ders, s.no): s for s in Soru.objects.filter(test__deneme=deneme).select_related("test")}
    tablo = [(m, sorular.get((m.test, m.no))) for m in satirlar]
    return render(
        request,
        "okuma/madde.html",
        {"deneme": deneme, "tablo": tablo, "kr20": kr20, "secenekler": "ABCDE"},
    )


@erisim_gerekli
@require_POST
def soru_guncelle(request, soru_pk):
    soru = get_object_or_404(Soru.objects.select_related("test__deneme"), pk=soru_pk)
    deneme = soru.test.deneme
    form = SoruForm(request.POST, instance=soru)
    if form.is_valid():
        form.save()
        durum = "iptal" if soru.iptal else f"cevap {soru.dogru}{('/' + soru.ek_dogrular) if soru.ek_dogrular else ''}"
        messages.info(request, f"{soru.test.ders} {soru.no}. soru güncellendi ({durum}).")
        _yeniden_hesapla(request, deneme)
    else:
        messages.error(request, "Soru güncellenemedi.")
    return redirect(f"{reverse('madde_analizi', args=[deneme.pk])}#soru-{soru.pk}")
