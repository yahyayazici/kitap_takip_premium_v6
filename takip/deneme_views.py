"""Deneme — personel görüntüleme."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from takip.deneme_service import (
    BRANS_ETIKETLERI,
    DENEME_DETAY_BRANSLAR,
    deneme_detay_satirlari,
    deneme_sonuclari,
    yetkili_denemeler,
)
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
    sonuclar = list(deneme_sonuclari(request.user, deneme))
    return render(
        request,
        "deneme_detay.html",
        {
            "deneme": deneme,
            "sonuclar": sonuclar,
            "detay_satirlari": deneme_detay_satirlari(sonuclar),
            "brans_etiketleri": BRANS_ETIKETLERI,
            "detay_branslar": DENEME_DETAY_BRANSLAR,
            "detay_brans_basliklari": [BRANS_ETIKETLERI[k] for k in DENEME_DETAY_BRANSLAR],
        },
    )
