"""Veli randevu — personel paneli ve raporlar."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate

from takip.models import PersonelProfili
from takip.permissions.decorators import require_permission
from takip.permissions.scope import tum_talebe_kapsami_var
from takip.veli_randevu_forms import RandevuGorusmeNotForm
from takip.veli_randevu_models import VeliRandevu
from takip.veli_randevu_service import (
    personel_randevulari,
    randevu_gorusme_kaydet,
    randevu_ozet,
    randevu_raporla,
)


def _personel_mi(user):
    try:
        return user.personel_profili
    except PersonelProfili.DoesNotExist:
        return None


@login_required
@require_permission("veli_randevu", "view")
def randevu_panel(request):
    personel = _personel_mi(request.user)
    if not personel and not (request.user.is_superuser or tum_talebe_kapsami_var(request.user)):
        messages.error(request, "Personel profiliniz bulunamadı.")
        return redirect("dashboard")

    if personel:
        qs = personel_randevulari(request.user).filter(
            durum__in=(VeliRandevu.Durum.PLANLANDI, VeliRandevu.Durum.TAMAMLANDI)
        )
    else:
        qs = VeliRandevu.objects.all().select_related("personel", "talebe", "veli")

    bugun = localdate()
    yaklasan = qs.filter(tarih__gte=bugun).order_by("tarih", "baslangic")[:30]
    gecmis = qs.filter(tarih__lt=bugun).order_by("-tarih", "-baslangic")[:20]

    return render(
        request,
        "randevu/panel.html",
        {
            "yaklasan": yaklasan,
            "gecmis": gecmis,
            "personel": personel,
            "admin_gorunum": not personel,
        },
    )


@login_required
@require_permission("veli_randevu", "edit")
def randevu_detay(request, pk):
    personel = _personel_mi(request.user)
    randevu = get_object_or_404(
        VeliRandevu.objects.select_related("talebe", "veli", "personel", "gorusme"),
        pk=pk,
    )
    if personel and randevu.personel_id != personel.pk:
        messages.error(request, "Bu randevuya erişiminiz yok.")
        return redirect("randevu_panel")

    not_form = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "not" and not randevu.gorusme:
            not_form = RandevuGorusmeNotForm(request.POST)
            if not_form.is_valid():
                randevu_gorusme_kaydet(
                    randevu,
                    ozet=not_form.cleaned_data["ozet"],
                    detay=not_form.cleaned_data["detay"],
                    kararlar=not_form.cleaned_data.get("kararlar") or "",
                    user=request.user,
                )
                messages.success(request, "Görüşme notu öğrenci dosyasına kaydedildi.")
                return redirect("randevu_detay", pk=randevu.pk)
        elif action == "iptal" and randevu.durum == VeliRandevu.Durum.PLANLANDI:
            randevu.durum = VeliRandevu.Durum.IPTAL_PERSONEL
            randevu.save(update_fields=["durum", "guncellenme"])
            messages.success(request, "Randevu iptal edildi.")
            return redirect("randevu_panel")

    if not_form is None and randevu.durum == VeliRandevu.Durum.PLANLANDI:
        not_form = RandevuGorusmeNotForm(
            initial={"ozet": randevu.konu or f"Veli görüşmesi — {randevu.talebe.ad_soyad}"}
        )

    return render(
        request,
        "randevu/detay.html",
        {
            "randevu": randevu,
            "not_form": not_form,
        },
    )


@login_required
@require_permission("veli_randevu", "view")
def randevu_raporlar(request):
    if not (request.user.is_superuser or tum_talebe_kapsami_var(request.user)):
        messages.error(request, "Rapor yetkiniz yok.")
        return redirect("randevu_panel")

    periyot = request.GET.get("periyot", "hafta")
    personel_id = request.GET.get("personel", "").strip()
    talebe_id = request.GET.get("talebe", "").strip()
    bugun = localdate()

    if periyot == "gun":
        baslangic = bitis = bugun
    elif periyot == "ay":
        baslangic = bugun.replace(day=1)
        bitis = bugun
    elif periyot == "ozel":
        baslangic_str = request.GET.get("baslangic", "")
        bitis_str = request.GET.get("bitis", "")
        baslangic = date.fromisoformat(baslangic_str) if baslangic_str else bugun - timedelta(days=7)
        bitis = date.fromisoformat(bitis_str) if bitis_str else bugun
    else:
        baslangic = bugun - timedelta(days=bugun.weekday())
        bitis = baslangic + timedelta(days=6)

    qs = randevu_raporla(
        baslangic=baslangic,
        bitis=bitis,
        personel_id=int(personel_id) if personel_id.isdigit() else None,
        talebe_id=int(talebe_id) if talebe_id.isdigit() else None,
    )
    ozet = randevu_ozet(qs)
    personel_dagilim = list(
        qs.values("personel__ad_soyad")
        .annotate(adet=Count("id"))
        .order_by("-adet")[:10]
    )

    return render(
        request,
        "randevu/raporlar.html",
        {
            "kayitlar": qs[:200],
            "ozet": ozet,
            "personel_dagilim": personel_dagilim,
            "baslangic": baslangic,
            "bitis": bitis,
            "periyot": periyot,
            "personeller": PersonelProfili.objects.filter(aktif=True).order_by("ad_soyad"),
        },
    )
