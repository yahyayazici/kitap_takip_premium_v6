"""Çok denemeli raporlar: ortalama listesi, kazanım yüzde analizi, sınıf konu analizi, gelişim raporu."""

from django.shortcuts import render

from okuma.erisim import erisim_gerekli
from okuma.models import Deneme, Sonuc
from okuma.services import raporlar as r
from okuma.services.excel import excel_yaniti

RAPORLAR = [
    ("rapor_ortalama", "Ortalama listesi", "Seçilen denemelerde öğrencilerin ders ders ortalama doğru, yanlış, net ve puanı; puana göre sıralı."),
    ("rapor_kazanim", "Konu kazanım yüzde analizi", "Seçtiğiniz başarı aralığında kalan öğrenciler, konu konu. Etüt gruplarını buradan kurun."),
    ("rapor_sinif_konu", "Sınıf konu analizi", "Her konunun şube şube başarı yüzdesi."),
    ("rapor_gelisim", "Gelişim raporu", "Katılım, şube karşılaştırması, en başarılı 10, eğilim ve risk altındaki öğrenciler."),
]


def _secim(request) -> dict:
    """Ortak seçim paneli: sınıf → denemeler → şube."""
    tum = Deneme.objects.exclude(sonuclar__isnull=True).distinct().order_by("-tarih", "-pk")
    siniflar = sorted({d.sinif_seviyesi for d in tum})
    sinif = request.GET.get("sinif") or (siniflar[-1] if siniflar else "")
    sinif_denemeleri = [d for d in tum if d.sinif_seviyesi == sinif]
    secili_idler = request.GET.getlist("d")
    denemeler = [d for d in r.secili_denemeler(secili_idler) if d.sinif_seviyesi == sinif]
    sube = request.GET.get("sube", "")
    subeler = (
        Sonuc.objects.filter(deneme__in=sinif_denemeleri).exclude(sube="").values_list("sube", flat=True).distinct().order_by("sube")
    )
    return {
        "siniflar": siniflar,
        "sinif": sinif,
        "sinif_denemeleri": sinif_denemeleri,
        "secili_idler": {str(d.pk) for d in denemeler},
        "denemeler": denemeler,
        "sube": sube,
        "subeler": list(subeler),
        "sorgu": request.GET.urlencode(),
    }


def _excel_mi(request) -> bool:
    return request.GET.get("format") == "xlsx"


@erisim_gerekli
def raporlar(request):
    return render(request, "okuma/raporlar.html", {"raporlar": RAPORLAR})


@erisim_gerekli
def rapor_ortalama(request):
    ctx = _secim(request)
    ctx["rapor"] = "rapor_ortalama"
    if ctx["denemeler"]:
        satirlar, ortalama = r.ortalama_listesi(ctx["denemeler"], ctx["sube"] or None)
        ctx.update(satirlar=satirlar, ortalama=ortalama, dersler=r.ders_listesi(ctx["denemeler"]))
        if _excel_mi(request):
            basliklar = ["Sıra", "Ad soyad", "Numara", "Şube", "Deneme"]
            for _, ad in ctx["dersler"]:
                basliklar += [f"{ad} D", f"{ad} Y", f"{ad} N"]
            basliklar += ["Toplam D", "Toplam Y", "Toplam N", "Puan"]
            veri = []
            for s in satirlar:
                satir = [s.sira, s.ogrenci.ad_soyad, s.ogrenci.numara, f"{ctx['sinif']}{s.sube}", s.deneme_sayisi]
                for k, _ in ctx["dersler"]:
                    satir += list(s.dersler.get(k, ("", "", "")))
                satir += [s.dogru, s.yanlis, s.net, s.puan if s.puan is not None else ""]
                veri.append(satir)
            return excel_yaniti("ortalama-listesi", [("Ortalama listesi", basliklar, veri)])
    return render(request, "okuma/rapor_ortalama.html", ctx)


@erisim_gerekli
def rapor_kazanim(request):
    ctx = _secim(request)
    ctx["rapor"] = "rapor_kazanim"

    def sayi(ad, varsayilan):
        try:
            return max(0.0, min(100.0, float(request.GET.get(ad, varsayilan))))
        except ValueError:
            return varsayilan

    alt, ust = sayi("alt", 0), sayi("ust", 50)
    ders = request.GET.get("ders", "")
    ctx.update(alt=alt, ust=ust, ders=ders)
    if ctx["denemeler"]:
        ctx["dersler"] = r.ders_listesi(ctx["denemeler"])
        gruplar = r.kazanim_yuzde_analizi(ctx["denemeler"], ctx["sube"] or None, alt, ust, ders or None)
        ctx["gruplar"] = gruplar
        if _excel_mi(request):
            veri = [
                [g["kayit"].ders_adi, str(g["kayit"].kazanim), o["ogrenci"].ad_soyad, o["ogrenci"].numara,
                 f"{ctx['sinif']}{o['sube']}", o["yuzde"], o["dogru"], o["yanlis"], o["bos"], o["net"], o["toplam"]]
                for g in gruplar
                for o in g["ogrenciler"]
            ]
            return excel_yaniti(
                "kazanim-yuzde-analizi",
                [("Kazanım yüzde", ["Ders", "Konu / kazanım", "Öğrenci", "Numara", "Şube", "Doğru %", "Doğru", "Yanlış", "Boş", "Net", "Toplam"], veri)],
            )
    return render(request, "okuma/rapor_kazanim.html", ctx)


@erisim_gerekli
def rapor_sinif_konu(request):
    ctx = _secim(request)
    ctx["rapor"] = "rapor_sinif_konu"
    if ctx["denemeler"]:
        subeler, satirlar = r.sinif_konu_analizi(ctx["denemeler"], ctx["sube"] or None)
        ctx.update(konu_subeleri=subeler, satirlar=satirlar)
        if _excel_mi(request):
            basliklar = ["Ders", "Konu / kazanım", "Soru"] + [f"{ctx['sinif']}{s}" if s else "Şubesiz" for s in subeler] + ["Genel"]
            veri = [[s["kayit"].ders_adi, str(s["kayit"].kazanim), s["kayit"].soru_sayisi, *s["subeler"], s["genel"]] for s in satirlar]
            return excel_yaniti("sinif-konu-analizi", [("Sınıf konu analizi", basliklar, veri)])
    return render(request, "okuma/rapor_sinif_konu.html", ctx)


@erisim_gerekli
def rapor_gelisim(request):
    ctx = _secim(request)
    ctx["rapor"] = "rapor_gelisim"
    if ctx["denemeler"]:
        g = r.gelisim_raporu(ctx["denemeler"], ctx["sube"] or None)
        ctx["g"] = g
        if _excel_mi(request):
            basliklar = ["Genel sıra", "Ad soyad", "Numara", "Şube", "Ort. net", "Ort. puan", "Katılım %", "Eğilim", "Kategori", "Risk"]
            basliklar += [d.ad for d in ctx["denemeler"]]
            veri = [
                [s.sira or "", s.ogrenci.ad_soyad, s.ogrenci.numara, f"{ctx['sinif']}{s.sube}", s.ort_net, s.ort_puan or "",
                 100 * s.katilim, s.trend, s.kategori, ", ".join(s.riskler), *[v if v is not None else "" for v in s.netler]]
                for s in g["satirlar"]
            ]
            subeler = [[x["sube"], x["ogrenci"], x["ort_net"] or "", x["katilim"], x["degisim"]] for x in g["subeler"]]
            return excel_yaniti(
                "gelisim-raporu",
                [("Öğrenciler", basliklar, veri), ("Şubeler", ["Şube", "Öğrenci", "Ort. net", "Katılım %", "% değişim"], subeler)],
            )
    return render(request, "okuma/rapor_gelisim.html", ctx)
