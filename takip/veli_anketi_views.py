"""Public veli değerlendirme anketi — giriş gerektirmez."""

from __future__ import annotations

from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from takip.forms import VeliAnketForm

ANKET_BASLIK = "Veli Değerlendirme Anketi"


@require_http_methods(["GET", "POST"])
def veli_anketi_form(request):
    form = VeliAnketForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(reverse("veli_anketi_tesekkur"))

    return render(
        request,
        "veli_anketi/form.html",
        {
            "form": form,
            "anket_baslik": ANKET_BASLIK,
        },
    )


@require_http_methods(["GET"])
def veli_anketi_tesekkur(request):
    return render(
        request,
        "veli_anketi/tesekkur.html",
        {"anket_baslik": ANKET_BASLIK},
    )
