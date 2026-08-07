"""Deneme — personel görüntüleme."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from takip.deneme_service import BRANS_ETIKETLERI, deneme_sonuclari, yetkili_denemeler
from takip.permissions.decorators import require_permission


@login_required
@require_permission("deneme", "view")
def deneme_listesi(request):
    denemeler = yetkili_denemeler(request.user).filter(
        durum="aktif",
    )
    return render(
        request,
        "deneme_listesi.html",
        {"denemeler": denemeler},
    )


@login_required
@require_permission("deneme", "view")
def deneme_detay(request, pk):
    deneme = get_object_or_404(yetkili_denemeler(request.user), pk=pk)
    sonuclar = deneme_sonuclari(request.user, deneme)
    return render(
        request,
        "deneme_detay.html",
        {
            "deneme": deneme,
            "sonuclar": sonuclar,
            "brans_etiketleri": BRANS_ETIKETLERI,
        },
    )
