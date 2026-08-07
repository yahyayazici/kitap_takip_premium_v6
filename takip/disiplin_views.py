"""Disiplin panel görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate

from takip.disiplin_service import (
    aktif_disiplin_turleri,
    disiplin_duzenleyebilir,
    disiplin_kayitlari_filtrele,
    yetkili_disiplin_kayitlari,
)
from takip.forms import DisiplinKaydiForm
from takip.permissions.decorators import require_permission


@login_required
@require_permission("disiplin", "view")
def disiplin_listesi(request):
    qs = yetkili_disiplin_kayitlari(request.user).order_by("-tarih", "-id")
    q = request.GET.get("q", "").strip()
    tur_id = request.GET.get("tur", "").strip()
    qs = disiplin_kayitlari_filtrele(qs, q=q or None, tur_id=tur_id or None)

    form = None
    if disiplin_duzenleyebilir(request.user):
        if request.method == "POST":
            form = DisiplinKaydiForm(request.user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Disiplin kaydı eklendi.")
                return redirect("disiplin_listesi")
        else:
            form = DisiplinKaydiForm(
                request.user,
                initial={"tarih": localdate()},
            )

    return render(
        request,
        "disiplin_listesi.html",
        {
            "kayitlar": qs[:200],
            "form": form,
            "turler": aktif_disiplin_turleri(),
            "filtre_q": q,
            "filtre_tur": tur_id,
            "duzenleyebilir": disiplin_duzenleyebilir(request.user),
        },
    )


@login_required
@require_permission("disiplin", "view")
def disiplin_detay(request, pk):
    kayit = get_object_or_404(yetkili_disiplin_kayitlari(request.user), pk=pk)
    return render(
        request,
        "disiplin_detay.html",
        {
            "kayit": kayit,
            "duzenleyebilir": disiplin_duzenleyebilir(request.user),
        },
    )


@login_required
@require_permission("disiplin", "edit")
def disiplin_duzenle(request, pk):
    kayit = get_object_or_404(yetkili_disiplin_kayitlari(request.user), pk=pk)
    form = DisiplinKaydiForm(
        request.user,
        request.POST or None,
        instance=kayit,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Disiplin kaydı güncellendi.")
        return redirect("disiplin_detay", pk=kayit.pk)

    return render(
        request,
        "disiplin_form.html",
        {
            "form": form,
            "kayit": kayit,
            "baslik": "Disiplin Kaydı Düzenle",
        },
    )
