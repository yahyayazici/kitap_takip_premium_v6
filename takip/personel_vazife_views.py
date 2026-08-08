"""Personel paneli — kendi vazife ve YÇT görünümü."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate, now

from takip.idareci_service import yct_ay_takvimi
from takip.models import PersonelProfili
from takip.vazife_models import PersonelVazife
from takip.vazife_service import (
    acik_vazifeler_qs,
    bildirim_aktif_qs,
    ornek_vazifeler_olustur,
    vazife_bildirim_kartlari,
)


def _profil(user):
    return PersonelProfili.objects.filter(user=user, aktif=True).first()


@login_required
def yct_personel(request):
    bugun = localdate()
    try:
        yil = int(request.GET.get("yil", bugun.year))
        ay = int(request.GET.get("ay", bugun.month))
    except (TypeError, ValueError):
        yil, ay = bugun.year, bugun.month
    ay = max(1, min(12, ay))
    takvim = yct_ay_takvimi(yil, ay)
    onceki_ay = ay - 1 or 12
    onceki_yil = yil if ay > 1 else yil - 1
    sonraki_ay = ay + 1 if ay < 12 else 1
    sonraki_yil = yil if ay < 12 else yil + 1
    ay_tr = [
        "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
    ][ay]
    return render(
        request,
        "yct_personel.html",
        {
            **takvim,
            "ay_adi_tr": ay_tr,
            "onceki": {"yil": onceki_yil, "ay": onceki_ay},
            "sonraki": {"yil": sonraki_yil, "ay": sonraki_ay},
            "salt_okunur": True,
        },
    )


@login_required
def vazife_personel(request):
    profil = _profil(request.user)
    if not profil:
        messages.info(request, "Personel profiliniz bulunamadı.")
        return redirect("dashboard")

    # Görünüm için: ?ornek=1 ile örnek vazife üret
    if request.GET.get("ornek") == "1":
        olusan = ornek_vazifeler_olustur(profil, atayan=request.user)
        if olusan:
            messages.info(request, f"{len(olusan)} örnek vazife eklendi.")
        else:
            messages.info(request, "Zaten vazife kaydı var; örnek eklenmedi.")

    bugun = localdate()
    vazifeler = list(
        PersonelVazife.objects.filter(atanan=profil)
        .select_related("sinif_sube", "atayan")
        .order_by("-olusturulma")
    )
    for v in vazifeler:
        if v.bitis:
            v.kalan_gun = (v.bitis - bugun).days
            v.gecikti = (
                v.kalan_gun < 0
                and v.durum
                not in {
                    PersonelVazife.Durum.TAMAMLANDI,
                    PersonelVazife.Durum.IPTAL,
                }
            )
        else:
            v.kalan_gun = None
            v.gecikti = False

    bildirimler = vazife_bildirim_kartlari(request.user, bugun=bugun)
    acik = acik_vazifeler_qs(profil).count()
    bildirim_n = bildirim_aktif_qs(profil, bugun=bugun).count()
    geciken = sum(1 for v in vazifeler if getattr(v, "gecikti", False))

    return render(
        request,
        "vazife_personel.html",
        {
            "vazifeler": vazifeler,
            "durumlar": PersonelVazife.Durum.choices,
            "profil": profil,
            "bildirimler": bildirimler,
            "ozet": {
                "toplam": len(vazifeler),
                "acik": acik,
                "bildirim": bildirim_n,
                "geciken": geciken,
            },
        },
    )


@login_required
def vazife_personel_durum(request, pk):
    profil = _profil(request.user)
    if not profil:
        return redirect("dashboard")

    vazife = get_object_or_404(PersonelVazife, pk=pk, atanan=profil)
    yeni = request.POST.get("durum")
    izinli = {
        PersonelVazife.Durum.ONAYLANDI,
        PersonelVazife.Durum.DEVAM,
        PersonelVazife.Durum.TAMAMLANDI,
    }
    if yeni in izinli:
        vazife.durum = yeni
        if yeni == PersonelVazife.Durum.ONAYLANDI and not vazife.onay_tarihi:
            vazife.onay_tarihi = now()
        if yeni == PersonelVazife.Durum.TAMAMLANDI:
            vazife.tamamlanma_tarihi = now()
        notu = (request.POST.get("personel_notu") or "").strip()
        if notu:
            vazife.personel_notu = notu
        vazife.save()
        messages.success(request, "Vazife durumu güncellendi.")
    return redirect("vazife_personel")
