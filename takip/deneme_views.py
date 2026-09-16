"""Deneme — personel görüntüleme."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.utils.timezone import localdate, now
from django.views.decorators.http import require_POST

from takip.deneme_service import (
    BRANS_ETIKETLERI,
    DENEME_DETAY_BRANSLAR,
    deneme_detay_satirlari,
    deneme_silebilir,
    deneme_sinavini_sil,
    deneme_sonuc_ozeti,
    deneme_sonuclari,
    yetkili_denemeler,
)
from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.pdf_utils import (
    coz_pdf_sayfa,
    html_to_pdf,
    make_pdf_response,
    pdf_engine_status,
    pdf_error_response,
)


def _deneme_detay_verisi(request, deneme):
    sonuclar = deneme_sonuclari(request.user, deneme)
    detay_satirlari = deneme_detay_satirlari(sonuclar)
    return {
        "deneme": deneme,
        "sonuclar": sonuclar,
        "detay_satirlari": detay_satirlari,
        "brans_etiketleri": BRANS_ETIKETLERI,
        "detay_branslar": DENEME_DETAY_BRANSLAR,
        "detay_brans_basliklari": [BRANS_ETIKETLERI[k] for k in DENEME_DETAY_BRANSLAR],
        "ozet": deneme_sonuc_ozeti(sonuclar),
        "sil_yetkisi": deneme_silebilir(request.user),
    }


@login_required
@require_permission("deneme", "view")
def deneme_listesi(request):
    denemeler = yetkili_denemeler(request.user).filter(
        durum="aktif",
    )
    context = {
        "denemeler": denemeler,
        "sil_yetkisi": deneme_silebilir(request.user),
    }
    template_name = (
        "partials/deneme_listesi_content.html"
        if getattr(request, "htmx", False)
        else "deneme_listesi.html"
    )
    return render(request, template_name, context)


@login_required
@require_permission("deneme", "view")
def deneme_detay(request, pk):
    deneme = get_object_or_404(yetkili_denemeler(request.user), pk=pk)
    ctx = _deneme_detay_verisi(request, deneme)
    ctx.update(
        {
            "pdf_yetkisi": can(request.user, "deneme", "export_pdf"),
            "excel_yetkisi": can(request.user, "deneme", "export_excel"),
            "pdf_sayfa": coz_pdf_sayfa(request),
        }
    )
    return render(request, "deneme_detay.html", ctx)


@login_required
@require_permission("deneme", "export_excel")
def deneme_excel_indir(request, pk):
    from takip.excel_rapor import (
        ExcelKolon,
        ExcelSayfa,
        basit_rapor_xlsx,
        coklu_rapor_xlsx,
        excel_http_yanit,
    )

    deneme = get_object_or_404(yetkili_denemeler(request.user), pk=pk)
    veri = _deneme_detay_verisi(request, deneme)
    sonuclar = veri["sonuclar"]
    detay_satirlari = veri["detay_satirlari"]
    alt = deneme.sinav_tarihi.strftime("%d.%m.%Y") if deneme.sinav_tarihi else ""

    genel_satirlar = [
        [
            sira,
            (sonuc.talebe.ad_soyad or "").upper(),
            str(sonuc.talebe.sinif_sube or ""),
            sonuc.toplam_dogru,
            sonuc.toplam_yanlis,
            sonuc.toplam_bos,
            str(sonuc.toplam_net).replace(".", ","),
            str(sonuc.puan).replace(".", ","),
        ]
        for sira, sonuc in enumerate(sonuclar, start=1)
    ]

    if not detay_satirlari:
        icerik = basit_rapor_xlsx(
            baslik=f"Deneme Sonuçları — {deneme.ad}",
            alt_baslik=alt,
            kolon_basliklari=[
                "Sıra", "Ad-Soyad", "Sınıf", "Doğru", "Yanlış", "Boş", "Net", "Puan",
            ],
            satirlar=genel_satirlar,
            sayfa_adi="Genel Sıralama",
            vurgu_kolonlari=[7],
            ortala_kolonlari=[0, 2, 3, 4, 5, 6],
            buyuk_harf_kolonlari=[1],
            genislikler=[8, 28, 12, 9, 9, 9, 10, 12],
        )
    else:
        brans_kolonlar = ["Sıra", "Ad-Soyad", "Sınıf"]
        for baslik in veri["detay_brans_basliklari"]:
            brans_kolonlar.extend([f"{baslik} D", f"{baslik} Y", f"{baslik} B"])
        brans_kolonlar.extend(["Toplam Net", "Puan"])

        brans_satirlar = []
        for satir in detay_satirlari:
            satir_veri = [
                satir["sira"],
                (satir["sonuc"].talebe.ad_soyad or "").upper(),
                str(satir["sonuc"].talebe.sinif_sube or ""),
            ]
            for brans in satir["branslar"]:
                satir_veri.extend([brans["dogru"], brans["yanlis"], brans["bos"]])
            satir_veri.extend(
                [
                    str(satir["sonuc"].toplam_net).replace(".", ","),
                    str(satir["sonuc"].puan).replace(".", ","),
                ]
            )
            brans_satirlar.append(satir_veri)

        def _kolonlar(basliklar: list[str]) -> list[ExcelKolon]:
            return [
                ExcelKolon(
                    baslik=ad,
                    genislik=28 if i == 1 else (12 if i == 2 else 10),
                    tip="vurgu" if ad == "Puan" else ("ortala" if i != 1 else "metin"),
                    buyuk_harf=i == 1,
                )
                for i, ad in enumerate(basliklar)
            ]

        icerik = coklu_rapor_xlsx(
            [
                ExcelSayfa(
                    adi="Genel Sıralama",
                    baslik=f"Deneme Sonuçları — {deneme.ad}",
                    alt_baslik=alt,
                    kolonlar=_kolonlar(
                        ["Sıra", "Ad-Soyad", "Sınıf", "Doğru", "Yanlış", "Boş", "Net", "Puan"]
                    ),
                    satirlar=genel_satirlar,
                ),
                ExcelSayfa(
                    adi="Branş Detay",
                    baslik=f"Branş Detay — {deneme.ad}",
                    alt_baslik=alt,
                    kolonlar=_kolonlar(brans_kolonlar),
                    satirlar=brans_satirlar,
                    satir_yukseklik=24,
                    metin_kaydir=True,
                ),
            ]
        )

    dosya = slugify(deneme.ad) or f"deneme_{deneme.pk}"
    return excel_http_yanit(icerik, f"deneme_{dosya}_{localdate():%Y%m%d}.xlsx")


class _BransSatir:
    __slots__ = (
        "talebe",
        "toplam_dogru",
        "toplam_yanlis",
        "toplam_bos",
        "toplam_net",
        "puan",
    )

    def __init__(self, talebe, dogru, yanlis, bos, net, puan):
        self.talebe = talebe
        self.toplam_dogru = dogru
        self.toplam_yanlis = yanlis
        self.toplam_bos = bos
        self.toplam_net = net
        self.puan = puan


def _deneme_liste_ctx(sonuclar, *, kicker, baslik):
    adet = len(sonuclar)
    split_at = (adet + 1) // 2
    return {
        "sonuclar": sonuclar,
        "sonuclar_sol": sonuclar[:split_at],
        "sonuclar_sag": sonuclar[split_at:],
        "sonuc_split": adet > 24,
        "split_at": split_at,
        "ozet": deneme_sonuc_ozeti(sonuclar),
        "liste_kicker": kicker,
        "liste_baslik": baslik,
    }


def _brans_pdf_satirlari(sonuclar, kod):
    satirlar = []
    for sonuc in sonuclar:
        brans = next((b for b in sonuc.brans_satirlari.all() if b.brans == kod), None)
        if brans is None:
            continue
        satirlar.append(
            _BransSatir(
                sonuc.talebe,
                int(brans.dogru or 0),
                int(brans.yanlis or 0),
                int(brans.bos or 0),
                brans.net,
                sonuc.puan,
            )
        )
    satirlar.sort(
        key=lambda s: (-float(s.toplam_net or 0), (s.talebe.ad_soyad or "").upper())
    )
    return satirlar


@login_required
@require_permission("deneme", "export_pdf")
def deneme_detay_pdf(request, pk):
    deneme = get_object_or_404(yetkili_denemeler(request.user), pk=pk)
    veri = _deneme_detay_verisi(request, deneme)
    sonuclar = veri["sonuclar"]
    pdf_sayfa = coz_pdf_sayfa(request)
    listeler = [
        _deneme_liste_ctx(
            sonuclar,
            kicker="Genel Sıralama",
            baslik="Doğru / Yanlış / Boş / Net / Puan",
        )
    ]
    for kod, etiket in BRANS_ETIKETLERI.items():
        brans_satir = _brans_pdf_satirlari(sonuclar, kod)
        if not brans_satir:
            continue
        listeler.append(
            _deneme_liste_ctx(
                brans_satir,
                kicker=etiket,
                baslik=f"{etiket} — D / Y / B / Net",
            )
        )

    html = render(
        request,
        "deneme_detay_pdf.html",
        {
            **veri,
            "listeler": listeler,
            "olusturma_tarihi": now(),
            "pdf_sayfa": pdf_sayfa,
        },
    ).content.decode("utf-8")
    pdf_verisi = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )
    ad = slugify(deneme.ad) or f"deneme_{deneme.pk}"
    return make_pdf_response(
        pdf_verisi,
        f"deneme_{ad}_{pdf_sayfa['kod']}_{localdate():%Y%m%d}.pdf",
    )


@login_required
@require_permission("deneme", "delete")
@require_POST
def deneme_sil(request, pk):
    deneme = get_object_or_404(yetkili_denemeler(request.user), pk=pk)
    if not deneme_silebilir(request.user):
        messages.error(request, "Bu denemeyi silemezsiniz.")
        return redirect("deneme_listesi")
    ad = deneme.ad
    deneme_sinavini_sil(request.user, deneme)
    messages.success(request, f"«{ad}» silindi.")
    return redirect("deneme_listesi")
