"""Yönetim — rol ve yetki ekranları."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from takip.models import Rol, RolIslemYetki, RolModulErisim, YetkiIslem, YetkiModul
from takip.permissions.service import can, clear_permission_cache

from .yonetim_views import yonetici_gerekli


@yonetici_gerekli
def rol_listesi(request):
    if not can(request.user, "rbac", "view"):
        messages.error(request, "Rol yönetimi için yetkiniz yok.")
        return redirect("yonetim:dashboard")

    roller = Rol.objects.filter(aktif=True).order_by("sira", "ad")
    return render(
        request,
        "yonetim/rol_listesi.html",
        {"roller": roller},
    )


@yonetici_gerekli
def rol_duzenle(request, pk):
    if not can(request.user, "rbac", "edit"):
        messages.error(request, "Rol düzenleme yetkiniz yok.")
        return redirect("yonetim:rol_listesi")

    rol = get_object_or_404(Rol, pk=pk)
    moduller = (
        YetkiModul.objects.filter(aktif=True)
        .prefetch_related("islemler")
        .order_by("sira")
    )

    if request.method == "POST":
        for modul in moduller:
            erisim = request.POST.get(f"modul_{modul.kod}") == "on"
            RolModulErisim.objects.update_or_create(
                rol=rol,
                modul=modul,
                defaults={"erisim": erisim},
            )
            for islem in modul.islemler.all():
                izin = request.POST.get(f"islem_{modul.kod}_{islem.kod}") == "on"
                RolIslemYetki.objects.update_or_create(
                    rol=rol,
                    islem=islem,
                    defaults={"izin": izin},
                )

        clear_permission_cache()
        messages.success(request, f"{rol.ad} yetkileri güncellendi.")
        return redirect("yonetim:rol_listesi")

    modul_erisim = {
        e.modul_id: e.erisim
        for e in rol.modul_erisimleri.select_related("modul")
    }
    islem_yetki = {
        y.islem_id: y.izin
        for y in rol.islem_yetkileri.select_related("islem")
    }

    satirlar = []
    for modul in moduller:
        satirlar.append(
            {
                "modul": modul,
                "erisim": modul_erisim.get(modul.id, False),
                "islemler": [
                    {
                        "islem": islem,
                        "izin": islem_yetki.get(islem.id, False),
                    }
                    for islem in modul.islemler.all()
                ],
            }
        )

    return render(
        request,
        "yonetim/rol_duzenle.html",
        {
            "rol": rol,
            "satirlar": satirlar,
        },
    )
