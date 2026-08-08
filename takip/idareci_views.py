"""İdareci paneli — özet, vazife, YÇT (kayıt girişi yok; vazife/YÇT yönetir)."""

from __future__ import annotations

from calendar import month_name
from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate, now

from takip.forms import PersonelVazifeForm, YctOlayForm
from takip.idareci_service import idareci_ozet, yct_ay_takvimi
from takip.models import PersonelProfili
from takip.permissions.service import can, kullanici_birincil_rol_slug
from takip.vazife_models import PersonelVazife
from takip.yct_models import YctOlay
from takip.yonetim_views import yonetici_gerekli


def _idareci_erisim(user) -> bool:
    if user.is_superuser:
        return True
    slug = kullanici_birincil_rol_slug(user)
    if slug in {"idareci", "ic_mesul"}:
        return True
    return can(user, "yonetim", "view")


@yonetici_gerekli
def idareci_panel(request):
    if not _idareci_erisim(request.user):
        messages.error(request, "İdareci paneline erişim yok.")
        return redirect("yonetim:dashboard")

    ctx = idareci_ozet()
    ctx["baslik"] = "İdareci özeti"
    return render(request, "yonetim/idareci_panel.html", ctx)


# —— Vazife ——

@yonetici_gerekli
def vazife_listesi(request):
    if not _idareci_erisim(request.user):
        messages.error(request, "Vazife modülüne erişim yok.")
        return redirect("yonetim:dashboard")

    durum = request.GET.get("durum", "")
    qs = PersonelVazife.objects.select_related(
        "atanan", "atayan", "sinif_sube"
    ).order_by("-olusturulma")
    if durum:
        qs = qs.filter(durum=durum)

    return render(
        request,
        "yonetim/vazife_listesi.html",
        {
            "vazifeler": qs[:200],
            "durum": durum,
            "durumlar": PersonelVazife.Durum.choices,
            "olusturabilir": True,
        },
    )


@yonetici_gerekli
def vazife_ekle(request):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    form = PersonelVazifeForm(request.POST or None)
    if form.is_valid():
        vazife = form.save(commit=False)
        vazife.atayan = request.user
        vazife.save()
        from takip.bildirim_service import vazife_bildirimi_gonder

        vazife_bildirimi_gonder(vazife, olusturan=request.user)
        bitis_txt = vazife.bitis.strftime("%d.%m.%Y") if vazife.bitis else "—"
        messages.success(
            request,
            f"Vazife atandı. {vazife.atanan.ad_soyad} için {bitis_txt} tarihine kadar bildirim gidecek.",
        )
        return redirect("yonetim:vazife_listesi")

    return render(
        request,
        "yonetim/vazife_form.html",
        {"form": form, "baslik": "Yeni vazife ata"},
    )


@yonetici_gerekli
def vazife_duzenle(request, pk):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    vazife = get_object_or_404(PersonelVazife, pk=pk)
    form = PersonelVazifeForm(request.POST or None, instance=vazife)
    if form.is_valid():
        vazife = form.save()
        from takip.bildirim_service import vazife_bildirimi_gonder

        vazife_bildirimi_gonder(vazife, olusturan=request.user)
        messages.success(request, "Vazife güncellendi; bildirim yenilendi.")
        return redirect("yonetim:vazife_listesi")

    return render(
        request,
        "yonetim/vazife_form.html",
        {"form": form, "baslik": f"Düzenle — {vazife.baslik}", "vazife": vazife},
    )


@yonetici_gerekli
def vazife_durum(request, pk):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    vazife = get_object_or_404(PersonelVazife, pk=pk)
    yeni = request.POST.get("durum")
    if yeni in dict(PersonelVazife.Durum.choices):
        vazife.durum = yeni
        if yeni == PersonelVazife.Durum.ONAYLANDI and not vazife.onay_tarihi:
            vazife.onay_tarihi = now()
        if yeni == PersonelVazife.Durum.TAMAMLANDI:
            vazife.tamamlanma_tarihi = now()
        vazife.save(update_fields=["durum", "onay_tarihi", "tamamlanma_tarihi", "guncellenme"])
        messages.success(request, "Durum güncellendi.")
    return redirect("yonetim:vazife_listesi")


# —— YÇT ——

@yonetici_gerekli
def yct_takvim(request):
    if not _idareci_erisim(request.user):
        messages.error(request, "YÇT erişimi yok.")
        return redirect("yonetim:dashboard")

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

    return render(
        request,
        "yonetim/yct_takvim.html",
        {
            **takvim,
            "ay_adi_tr": _ay_tr(ay),
            "onceki": {"yil": onceki_yil, "ay": onceki_ay},
            "sonraki": {"yil": sonraki_yil, "ay": sonraki_ay},
            "form": YctOlayForm(initial={"baslangic": date(yil, ay, min(bugun.day, 28))}),
        },
    )


@yonetici_gerekli
def yct_ekle(request):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")

    form = YctOlayForm(request.POST or None)
    if form.is_valid():
        olay = form.save(commit=False)
        olay.olusturan = request.user
        olay.save()
        messages.success(request, "YÇT kaydı eklendi.")
        return redirect(
            f"/yonetim/yct/?yil={olay.baslangic.year}&ay={olay.baslangic.month}"
        )

    messages.error(request, "YÇT kaydı eklenemedi — formu kontrol edin.")
    return redirect("yonetim:yct_takvim")


@yonetici_gerekli
def yct_sil(request, pk):
    if not _idareci_erisim(request.user):
        return redirect("yonetim:dashboard")
    if request.method != "POST":
        return redirect("yonetim:yct_takvim")
    olay = get_object_or_404(YctOlay, pk=pk)
    yil, ay = olay.baslangic.year, olay.baslangic.month
    olay.delete()
    messages.success(request, "YÇT kaydı silindi.")
    return redirect(f"/yonetim/yct/?yil={yil}&ay={ay}")


def _ay_tr(ay: int) -> str:
    isimler = [
        "",
        "Ocak",
        "Şubat",
        "Mart",
        "Nisan",
        "Mayıs",
        "Haziran",
        "Temmuz",
        "Ağustos",
        "Eylül",
        "Ekim",
        "Kasım",
        "Aralık",
    ]
    return isimler[ay] if 1 <= ay <= 12 else month_name[ay]
