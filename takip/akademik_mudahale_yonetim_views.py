"""Akademik müdahale — yönetim (müdahale türleri)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from takip.forms import MudahaleTuruForm
from takip.models import MudahaleTuru
from takip.permissions.service import can

from .yonetim_views import yonetici_gerekli


@yonetici_gerekli
def mudahale_turu_listesi(request):
    if not can(request.user, "akademik_mudahale", "view"):
        messages.error(request, "Akademik müdahale modülüne erişim yok.")
        return redirect("yonetim:dashboard")

    turler = MudahaleTuru.objects.order_by("sira", "ad")
    return render(
        request,
        "yonetim/mudahale_turu_listesi.html",
        {
            "turler": turler,
            "duzenleyebilir": can(request.user, "akademik_mudahale", "edit"),
        },
    )


@yonetici_gerekli
def mudahale_turu_ekle(request):
    if not can(request.user, "akademik_mudahale", "edit"):
        messages.error(request, "Müdahale türü ekleme yetkiniz yok.")
        return redirect("yonetim:mudahale_turu_listesi")

    form = MudahaleTuruForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Müdahale türü eklendi.")
        return redirect("yonetim:mudahale_turu_listesi")

    return render(
        request,
        "yonetim/mudahale_turu_form.html",
        {"form": form, "baslik": "Yeni Müdahale Türü"},
    )


@yonetici_gerekli
def mudahale_turu_duzenle(request, pk):
    if not can(request.user, "akademik_mudahale", "edit"):
        messages.error(request, "Düzenleme yetkiniz yok.")
        return redirect("yonetim:mudahale_turu_listesi")

    tur = get_object_or_404(MudahaleTuru, pk=pk)
    form = MudahaleTuruForm(request.POST or None, instance=tur)
    if form.is_valid():
        form.save()
        messages.success(request, "Müdahale türü güncellendi.")
        return redirect("yonetim:mudahale_turu_listesi")

    return render(
        request,
        "yonetim/mudahale_turu_form.html",
        {"form": form, "baslik": f"Düzenle — {tur.ad}"},
    )


@yonetici_gerekli
def mudahale_turu_sil(request, pk):
    if not can(request.user, "akademik_mudahale", "delete"):
        messages.error(request, "Silme yetkiniz yok.")
        return redirect("yonetim:mudahale_turu_listesi")

    tur = get_object_or_404(MudahaleTuru, pk=pk)
    if tur.kayitlar.exists():
        messages.error(
            request,
            "Bu türde kayıt var; silinemez. Pasif yapabilirsiniz.",
        )
        return redirect("yonetim:mudahale_turu_listesi")

    ad = tur.ad
    tur.delete()
    messages.success(request, f"{ad} silindi.")
    return redirect("yonetim:mudahale_turu_listesi")
