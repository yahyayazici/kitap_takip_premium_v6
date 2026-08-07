"""KTT yönetim görünümleri."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from takip.ktt_service import ktt_tam_yetki, yetkili_ktt_sinavlari
from takip.models import KttSinav
from takip.permissions.service import can

from .yonetim_views import yonetici_gerekli


@yonetici_gerekli
def ktt_listesi(request):
    if not can(request.user, "ktt", "view"):
        messages.error(request, "KTT modülüne erişim yok.")
        return redirect("yonetim:dashboard")

    sinavlar = (
        KttSinav.objects.filter(aktif=True)
        .select_related("ders", "etut_hocasi", "olusturan")
        .order_by("-sinav_tarihi", "-id")
    )

    ders = request.GET.get("ders")
    sinif = request.GET.get("sinif")
    if ders:
        sinavlar = sinavlar.filter(ders_id=ders)
    if sinif:
        sinavlar = sinavlar.filter(sinif_seviyesi=sinif)

    return render(
        request,
        "yonetim/ktt_listesi.html",
        {
            "sinavlar": sinavlar,
            "silme_yetkisi": ktt_tam_yetki(request.user),
        },
    )


@yonetici_gerekli
def ktt_sil(request, pk):
    if not can(request.user, "ktt", "delete"):
        messages.error(request, "KTT silme yetkiniz yok.")
        return redirect("yonetim:ktt_listesi")

    ktt = get_object_or_404(KttSinav, pk=pk)
    ad = ktt.ad
    ktt.delete()
    messages.success(request, f"{ad} silindi.")
    return redirect("yonetim:ktt_listesi")


@yonetici_gerekli
def ktt_veli_toggle(request, pk):
    if not can(request.user, "ktt", "edit"):
        return redirect("yonetim:ktt_listesi")

    ktt = get_object_or_404(KttSinav, pk=pk)
    ktt.veliye_goster = not ktt.veliye_goster
    ktt.save(update_fields=["veliye_goster", "guncellenme"])
    messages.success(
        request,
        f"Veli görünürlüğü: {'Açık' if ktt.veliye_goster else 'Kapalı'}",
    )
    return redirect("yonetim:ktt_listesi")
