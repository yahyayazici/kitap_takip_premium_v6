"""Etüt Kontrol paneli + kazanım Excel indirme."""

from __future__ import annotations

import json
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl import Workbook

from takip.deneme_models import DenemeSinavi
from takip.etut_kontrol_service import (
    etut_deneme_kutulari,
    etut_deneme_siralamasi,
    etut_dikkat,
    etut_gorunum_serisi,
    etut_konu_ozeti,
    etut_talebe_kutulari,
    hoca_baskin_sinif_etiket,
    hoca_seviye_kirilimi,
    hoca_talebe_ids,
    kullanici_etut_hocalari,
    deneme_ortalama,
    talebe_deneme_kutulari,
    talebe_gelisim_serisi,
)
from takip.models import EtutHocasi, Talebe
from takip.panel_permissions import deneme_modulu_erisimi_var


def _hoca_erisim(request, hoca_id: int) -> EtutHocasi | None:
    allowed = {h.id: h for h in kullanici_etut_hocalari(request.user)}
    return allowed.get(hoca_id)


@login_required
def etut_kontrol_panel(request):
    if not deneme_modulu_erisimi_var(request.user) and not request.user.is_staff:
        messages.error(request, "Etüt Kontrol için yetkiniz yok.")
        return redirect("dashboard")

    hocalar = kullanici_etut_hocalari(request.user)
    if not hocalar:
        return render(
            request,
            "etut_kontrol/bos.html",
            {"mesaj": "Henüz etüt / sınıf mesulü atanmamış."},
        )
    hoca_id = request.GET.get("hoca")
    if hoca_id:
        return redirect("etut_kontrol", hoca_id=hoca_id)
    return redirect("etut_kontrol", hoca_id=hocalar[0].id)


@login_required
def etut_kontrol(request, hoca_id):
    if not deneme_modulu_erisimi_var(request.user) and not request.user.is_staff:
        messages.error(request, "Etüt Kontrol için yetkiniz yok.")
        return redirect("dashboard")

    hoca = _hoca_erisim(request, hoca_id)
    if hoca is None:
        messages.error(request, "Bu etüde erişiminiz yok.")
        return redirect("dashboard")

    hocalar = kullanici_etut_hocalari(request.user)
    kirilim = hoca_seviye_kirilimi(hoca)
    gorunum = request.GET.get("gorunum")
    if gorunum not in {"genel", "ayrim"} or len(kirilim["subeler"]) < 2:
        gorunum = "genel"
    ayrim = gorunum == "ayrim"
    seri = etut_gorunum_serisi(hoca, kirilim, ayrim)
    dikkat = etut_dikkat(
        hoca,
        talebe_ids=kirilim["genel_ids"] or None,
        subeler=kirilim["subeler"] if ayrim else None,
    )
    kutular = etut_deneme_kutulari(hoca)
    for kutu in kutular:
        kutu["seviye_ortalama"] = deneme_ortalama(kutu["deneme"], kirilim["genel_ids"])
    cizgi = seri["seriler"][0]["degerler"] if seri["seriler"] else []
    return render(
        request,
        "etut_kontrol/kontrol.html",
        {
            "hoca": hoca,
            "hocalar": hocalar,
            "kirilim": kirilim,
            "gorunum": gorunum,
            "seri": seri,
            "dikkat": dikkat,
            "kutular": kutular,
            "talebe_sayisi": len(kirilim["genel_ids"] or hoca_talebe_ids(hoca)),
            "gelisim_json": json.dumps(
                {
                    "labels": seri["labels"],
                    "sinif": cizgi,
                    "sinif_ad": kirilim["etiket"],
                    "tarihler": seri["tarihler"],
                    "seriler": seri["seriler"],
                    "ayrim": ayrim,
                },
                ensure_ascii=False,
            ),
        },
    )


@login_required
def etut_kontrol_deneme(request, hoca_id, deneme_id):
    hoca = _hoca_erisim(request, hoca_id)
    if hoca is None:
        messages.error(request, "Bu etüde erişiminiz yok.")
        return redirect("dashboard")
    deneme = get_object_or_404(DenemeSinavi, pk=deneme_id)
    sekme = request.GET.get("sekme", "siralama")
    if sekme not in {"siralama", "kazanim"}:
        sekme = "siralama"

    kirilim = hoca_seviye_kirilimi(hoca)
    gorunum = request.GET.get("gorunum")
    if gorunum not in {"genel", "ayrim"} or len(kirilim["subeler"]) < 2:
        gorunum = "genel"
    ayrim = gorunum == "ayrim"
    ids = kirilim["genel_ids"] or hoca_talebe_ids(hoca)
    izinli = set(ids)
    siralama = [
        row for row in etut_deneme_siralamasi(hoca, deneme) if row["talebe_id"] in izinli
    ]
    kazanimlar = etut_konu_ozeti(
        hoca,
        deneme,
        talebe_ids=ids,
        subeler=kirilim["subeler"] if ayrim else None,
    )
    sinif_ad = kirilim["etiket"] or hoca_baskin_sinif_etiket(hoca)

    indir = request.GET.get("indir")
    if indir == "excel":
        return _excel_deneme(hoca, deneme, sekme, siralama, kazanimlar)
    if indir == "pdf":
        return _pdf_deneme(request, hoca, deneme, sekme, siralama, kazanimlar)

    return render(
        request,
        "etut_kontrol/deneme.html",
        {
            "hoca": hoca,
            "deneme": deneme,
            "sekme": sekme,
            "siralama": siralama,
            "kazanimlar": kazanimlar,
            "sinif_ad": sinif_ad,
            "kirilim": kirilim,
            "gorunum": gorunum,
            "etut_ortalama": deneme_ortalama(deneme, ids),
            "sinif_ortalama": deneme_ortalama(deneme, ids),
        },
    )


@login_required
def etut_kontrol_talebeler(request, hoca_id):
    hoca = _hoca_erisim(request, hoca_id)
    if hoca is None:
        messages.error(request, "Bu etüde erişiminiz yok.")
        return redirect("dashboard")
    return render(
        request,
        "etut_kontrol/talebeler.html",
        {"hoca": hoca, "kutular": etut_talebe_kutulari(hoca)},
    )


@login_required
def etut_kontrol_talebe(request, hoca_id, talebe_id):
    hoca = _hoca_erisim(request, hoca_id)
    if hoca is None:
        messages.error(request, "Bu etüde erişiminiz yok.")
        return redirect("dashboard")
    talebe = get_object_or_404(
        Talebe.objects.select_related("sinif_sube"), pk=talebe_id
    )
    if talebe.id not in hoca_talebe_ids(hoca):
        messages.error(request, "Bu talebe seçili etütte değil.")
        return redirect("etut_kontrol_talebeler", hoca_id=hoca.id)

    gelisim = talebe_gelisim_serisi(talebe)
    kutular = talebe_deneme_kutulari(talebe)
    indir = request.GET.get("indir")
    if indir == "excel":
        return _excel_talebe(talebe, kutular)
    if indir == "pdf":
        return _pdf_talebe(request, hoca, talebe, gelisim, kutular)

    return render(
        request,
        "etut_kontrol/talebe.html",
        {
            "hoca": hoca,
            "talebe": talebe,
            "gelisim": gelisim,
            "kutular": kutular,
            "gelisim_json": json.dumps(
                {"labels": gelisim["labels"], "puanlar": gelisim["puanlar"], "tarihler": gelisim["tarihler"]},
                ensure_ascii=False,
            ),
        },
    )


def _excel_deneme(hoca, deneme, sekme, siralama, kazanimlar):
    wb = Workbook()
    ws = wb.active
    if sekme == "kazanim":
        ws.title = "Kazanımlar"
        ws.append(["Ders", "Kazanım", "Etüt ort. %", "Katılan"])
        for r in kazanimlar:
            ws.append([r["ders"], r["konu"], float(r["ortalama"] or 0), r["talebe_sayisi"]])
    else:
        ws.title = "Sıralama"
        ws.append(["#", "Talebe", "Sınıf", "Ortalama %", "Konu"])
        for r in siralama:
            ws.append(
                [
                    r["sira"],
                    r["ad_soyad"],
                    r["sinif"],
                    float(r["ortalama"] or 0),
                    r["konu_sayisi"],
                ]
            )
    buf = BytesIO()
    wb.save(buf)
    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="etut-{deneme.id}-{sekme}.xlsx"'
    return resp


def _excel_talebe(talebe, kutular):
    wb = Workbook()
    ws = wb.active
    ws.title = "Kazanımlar"
    ws.append(["Deneme", "Ders", "Kazanım", "Yüzde", "Net"])
    for k in kutular:
        for row in k["kazanimlar"]:
            net = ""
            if row["net_dogru"] is not None and row["net_toplam"] is not None:
                net = f"{row['net_dogru']}/{row['net_toplam']}"
            ws.append(
                [
                    k["deneme"].ad,
                    row["ders"],
                    row["konu"],
                    float(row["yuzde"]) if row["yuzde"] is not None else "",
                    net,
                ]
            )
    buf = BytesIO()
    wb.save(buf)
    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="talebe-{talebe.id}-kazanim.xlsx"'
    return resp


def _pdf_deneme(request, hoca, deneme, sekme, siralama, kazanimlar):
    from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_error_response

    html = render(
        request,
        "etut_kontrol/pdf_deneme.html",
        {
            "hoca": hoca,
            "deneme": deneme,
            "sekme": sekme,
            "siralama": siralama,
            "kazanimlar": kazanimlar,
        },
    ).content.decode("utf-8")
    pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf:
        return pdf_error_response("PDF üretilemedi.")
    return make_pdf_response(pdf, f"etut-{deneme.id}-{sekme}.pdf")


def _pdf_talebe(request, hoca, talebe, gelisim, kutular):
    from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_error_response

    html = render(
        request,
        "etut_kontrol/pdf_talebe.html",
        {
            "hoca": hoca,
            "talebe": talebe,
            "gelisim": gelisim,
            "kutular": kutular,
        },
    ).content.decode("utf-8")
    pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf:
        return pdf_error_response("PDF üretilemedi.")
    return make_pdf_response(pdf, f"talebe-{talebe.id}-kazanim.pdf")
