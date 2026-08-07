"""Dini ders takip — toplu çizelge ve rapor."""

from __future__ import annotations

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from takip.dini_ders_takip_service import (
    cizelge_sidebar_ozeti,
    duzenleyebilir,
    kayitlari_kaydet,
    konular_for,
    rapor_ozeti,
    son_islenen_konular,
    talebe_matris_satirlari,
    yetkili_dini_talebeler,
)
from takip.models import DiniDersSeviyesi, DiniDersTakipAlani
from takip.permissions.decorators import require_permission
from takip.permissions.service import can


@login_required
@require_permission("dini_ders_takip", "view")
def dini_ders_panel(request):
    seviyeler = DiniDersSeviyesi.objects.filter(aktif=True).order_by("sira", "ad")
    alanlar = DiniDersTakipAlani.objects.filter(aktif=True).order_by("sira", "ad")

    seviye_id = request.GET.get("seviye") or request.POST.get("seviye_id")
    alan_id = request.GET.get("alan") or request.POST.get("alan_id")

    seviye = None
    alan = None
    konular = []
    talebeler = yetkili_dini_talebeler(request.user).none()
    talebe_satirlari = []
    sidebar_ozet = None
    son_kayitlar = []

    if seviye_id and alan_id:
        seviye = seviyeler.filter(pk=seviye_id).first()
        alan = alanlar.filter(pk=alan_id).first()
        if seviye and alan:
            konular = list(konular_for(seviye, alan))
            talebeler = (
                yetkili_dini_talebeler(request.user)
                .filter(dini_ders_seviyesi=seviye)
                .order_by("ad_soyad")
            )

            if request.method == "POST" and duzenleyebilir(request.user):
                isaretli: set[tuple[int, int]] = set()
                for key in request.POST:
                    if key.startswith("k_"):
                        parts = key.split("_")
                        if len(parts) == 3:
                            isaretli.add((int(parts[1]), int(parts[2])))
                talebe_ids = list(talebeler.values_list("id", flat=True))
                konu_ids = [k.id for k in konular]
                guncellenen = kayitlari_kaydet(
                    request.user,
                    talebe_ids,
                    konu_ids,
                    isaretli,
                )
                messages.success(
                    request,
                    f"Çizelge kaydedildi ({guncellenen} değişiklik).",
                )
                return redirect(
                    f"{request.path}?seviye={seviye.pk}&alan={alan.pk}"
                )

            talebe_satirlari = talebe_matris_satirlari(talebeler, konular)
            sidebar_ozet = cizelge_sidebar_ozeti(talebeler, konular)
            son_kayitlar = son_islenen_konular(talebeler, konular)

    ornek_cizelge_link = None
    seviye_ornek = seviyeler.filter(ad="Seviye 1").first()
    alan_ornek = alanlar.filter(ad="Sure Ezberi").first()
    if seviye_ornek and alan_ornek:
        ornek_cizelge_link = (
            f"{request.path}?seviye={seviye_ornek.pk}&alan={alan_ornek.pk}"
        )

    return render(
        request,
        "dini_ders_panel.html",
        {
            "seviyeler": seviyeler,
            "alanlar": alanlar,
            "seviye": seviye,
            "alan": alan,
            "konular": konular,
            "talebeler": talebeler,
            "talebe_satirlari": talebe_satirlari,
            "sidebar_ozet": sidebar_ozet,
            "son_kayitlar": son_kayitlar,
            "duzenleyebilir": duzenleyebilir(request.user),
            "ornek_cizelge_link": ornek_cizelge_link,
        },
    )


@login_required
@require_permission("dini_ders_takip", "view")
def dini_ders_rapor(request):
    if request.GET.get("format") == "excel" and can(
        request.user, "dini_ders_takip", "export_excel"
    ):
        return dini_ders_excel(request)

    seviyeler = DiniDersSeviyesi.objects.filter(aktif=True).order_by("sira", "ad")
    alanlar = DiniDersTakipAlani.objects.filter(aktif=True).order_by("sira", "ad")

    seviye_id = request.GET.get("seviye")
    alan_id = request.GET.get("alan")
    seviye = seviyeler.filter(pk=seviye_id).first() if seviye_id else None
    alan = alanlar.filter(pk=alan_id).first() if alan_id else None

    talebeler = yetkili_dini_talebeler(request.user)
    ozet = rapor_ozeti(talebeler, seviye=seviye, alan=alan)

    satirlar = []
    for talebe in talebeler.order_by("ad_soyad")[:200]:
        if not talebe.dini_ders_seviyesi_id:
            continue
        konu_qs = konular_for(
            talebe.dini_ders_seviyesi,
            alan,
        ) if alan else talebe.dini_ders_seviyesi.dini_ders_konulari.filter(
            aktif=True
        )
        toplam = konu_qs.count()
        if not toplam:
            continue
        from takip.models import DiniDersKonuKaydi

        tamamlanan = DiniDersKonuKaydi.objects.filter(
            talebe=talebe,
            konu__in=konu_qs,
            tamamlandi=True,
        ).count()
        satirlar.append(
            {
                "talebe": talebe,
                "tamamlanan": tamamlanan,
                "toplam": toplam,
                "yuzde": round(100 * tamamlanan / toplam) if toplam else 0,
            }
        )

    return render(
        request,
        "dini_ders_rapor.html",
        {
            "seviyeler": seviyeler,
            "alanlar": alanlar,
            "seviye": seviye,
            "alan": alan,
            "ozet": ozet,
            "satirlar": satirlar,
        },
    )


@login_required
@require_permission("dini_ders_takip", "export_excel")
def dini_ders_excel(request):
    seviye_id = request.GET.get("seviye")
    alan_id = request.GET.get("alan")
    seviye = (
        DiniDersSeviyesi.objects.filter(pk=seviye_id).first()
        if seviye_id
        else None
    )
    alan = (
        DiniDersTakipAlani.objects.filter(pk=alan_id).first()
        if alan_id
        else None
    )

    talebeler = yetkili_dini_talebeler(request.user).order_by("ad_soyad")
    if seviye:
        talebeler = talebeler.filter(dini_ders_seviyesi=seviye)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="dini-ders-rapor.csv"'
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow(
        ["Talebe", "Seviye", "Alan", "Konu", "Durum", "Güncellenme"]
    )

    from takip.models import DiniDersKonu, DiniDersKonuKaydi

    konu_qs = DiniDersKonu.objects.filter(aktif=True).select_related(
        "alan", "seviye"
    )
    if seviye:
        konu_qs = konu_qs.filter(seviye=seviye)
    if alan:
        konu_qs = konu_qs.filter(alan=alan)

    kayit_map = {
        (k.talebe_id, k.konu_id): k
        for k in DiniDersKonuKaydi.objects.filter(
            talebe__in=talebeler,
            konu__in=konu_qs,
        ).select_related("talebe", "konu")
    }

    for talebe in talebeler:
        if not talebe.dini_ders_seviyesi_id:
            continue
        for konu in konu_qs.filter(seviye=talebe.dini_ders_seviyesi):
            kayit = kayit_map.get((talebe.id, konu.id))
            writer.writerow(
                [
                    talebe.ad_soyad,
                    talebe.dini_ders_seviyesi.ad,
                    konu.alan.ad,
                    konu.ad,
                    "Tamamlandı" if kayit and kayit.tamamlandi else "Bekliyor",
                    kayit.guncellenme.strftime("%d.%m.%Y %H:%M")
                    if kayit
                    else "",
                ]
            )

    return response
