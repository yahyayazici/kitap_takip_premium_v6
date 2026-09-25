from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from takip.karsilama_models import KarsilamaSozu
from takip.panel_permissions import yonetim_erisimi_var


def karsilama_sozu():
    soz = KarsilamaSozu.objects.filter(pk=1).first()
    if soz and (soz.metin or "").strip():
        return soz
    return None


@login_required
def karsilama_sozu_duzenle(request):
    if not yonetim_erisimi_var(request.user):
        messages.error(request, "Karşılama sözünü düzenleme yetkiniz yok.")
        return redirect("dashboard")
    soz, _ = KarsilamaSozu.objects.get_or_create(pk=1)
    if request.method == "POST":
        soz.metin = (request.POST.get("metin") or "").strip()
        soz.kaynak = (request.POST.get("kaynak") or "").strip()[:160]
        soz.save()
        if soz.metin:
            messages.success(request, "Karşılama sözü kaydedildi.")
        else:
            messages.success(request, "Söz kaldırıldı. Bantta görünmez.")
        return redirect("dashboard")
    return render(request, "yonetim/karsilama_sozu.html", {"soz": soz})
