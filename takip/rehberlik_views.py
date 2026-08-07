"""Rehberlik ve veli/talebe iletişim panel görünümleri."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import localdate

from takip.forms import OgrenciGorusmesiForm
from takip.models import GorusmeDosyasi, GorusmeTuru
from takip.permissions.decorators import require_permission
from takip.permissions.scope import yetkili_talebeler
from takip.rehberlik_service import (
    ILETISIM_ETIKET_ONERILERI,
    REHBERLIK_ETIKET_ONERILERI,
    aktif_gorusme_turleri,
    iletisim_duzenleyebilir,
    iletisim_gorebilir,
    kararlar_listesi,
    rehberlik_duzenleyebilir,
    rehberlik_gorebilir,
    seed_gorusme_turleri,
    talebe_gorusme_paneli,
    veli_gorusmeleri,
    yapilacaklar_listesi,
    yetkili_gorusmeler,
)

PANEL_KONFIG = {
    GorusmeTuru.Alan.REHBERLIK: {
        "modul": "rehberlik",
        "template": "gorusme_panel.html",
        "list_url": "rehberlik_listesi",
        "detay_url": "rehberlik_detay",
        "duzenle_url": "rehberlik_duzenle",
        "diger_list_url": "iletisim_listesi",
        "baslik": "Rehberlik",
        "eyebrow": "Rehberlik & Öğrenci Takip",
        "aciklama": "Rehber öğretmeni görüşmeleri, takip planları ve karar kayıtları.",
        "sorumlu_etiket": "Rehber Öğretmeni",
        "diger_modul_etiket": "Veli & Talebe İletişim",
        "yeni_kayit_baslik": "Yeni Rehberlik Görüşmesi",
        "gecmis_baslik": "Rehberlik Geçmişi",
        "etiket_onerileri": REHBERLIK_ETIKET_ONERILERI,
    },
    GorusmeTuru.Alan.ILETISIM: {
        "modul": "veli_iletisim",
        "template": "gorusme_panel.html",
        "list_url": "iletisim_listesi",
        "detay_url": "iletisim_detay",
        "duzenle_url": "iletisim_duzenle",
        "diger_list_url": "rehberlik_listesi",
        "baslik": "Veli & Talebe İletişim",
        "eyebrow": "Veli & Öğrenci İletişimi",
        "aciklama": "Etüt hocasının veli ve öğrenci görüşme kayıtları.",
        "sorumlu_etiket": "Hocamız",
        "diger_modul_etiket": "Rehberlik",
        "yeni_kayit_baslik": "Yeni İletişim Kaydı",
        "gecmis_baslik": "İletişim Geçmişi",
        "etiket_onerileri": ILETISIM_ETIKET_ONERILERI,
    },
}


def _duzenleyebilir(user, alan: str) -> bool:
    if alan == GorusmeTuru.Alan.ILETISIM:
        return iletisim_duzenleyebilir(user)
    return rehberlik_duzenleyebilir(user)


def _gorusme_paneli(request, alan: str):
    seed_gorusme_turleri()
    cfg = PANEL_KONFIG[alan]

    talebeler = yetkili_talebeler(request.user).select_related(
        "sinif_sube", "etut_hocasi", "dini_ders_seviyesi"
    ).order_by("ad_soyad")

    talebe_id = request.GET.get("talebe", "").strip()
    detay_id = request.GET.get("detay", "").strip()
    talebe = None
    panel = None
    secili = None
    form = None

    if talebe_id.isdigit():
        talebe = get_object_or_404(talebeler, pk=int(talebe_id))
        filtre = {
            "q": request.GET.get("q", "").strip() or None,
            "tur": request.GET.get("tur", "").strip() or None,
            "etiket": request.GET.get("etiket", "").strip() or None,
            "takip": request.GET.get("takip", "").strip() or None,
        }
        panel = talebe_gorusme_paneli(request.user, talebe, alan, filtre=filtre)

        if detay_id.isdigit():
            secili = get_object_or_404(
                yetkili_gorusmeler(request.user, alan=alan).filter(talebe=talebe),
                pk=int(detay_id),
            )
        elif panel["gorusmeler"]:
            secili = panel["gorusmeler"][0]

        if _duzenleyebilir(request.user, alan):
            if request.method == "POST":
                form = OgrenciGorusmesiForm(
                    request.user,
                    request.POST,
                    request.FILES,
                    alan=alan,
                )
                if form.is_valid():
                    gorusme = form.save()
                    dosya = request.FILES.get("ek_dosya")
                    if dosya:
                        GorusmeDosyasi.objects.create(
                            gorusme=gorusme,
                            dosya=dosya,
                            ad=dosya.name,
                            tur=request.POST.get("dosya_turu", "diger"),
                            yukleyen=request.user,
                        )
                    messages.success(request, "Kayıt eklendi.")
                    url = reverse(cfg["list_url"])
                    return redirect(f"{url}?talebe={talebe.pk}&detay={gorusme.pk}")
            else:
                form = OgrenciGorusmesiForm(
                    request.user,
                    initial={"talebe": talebe.pk, "tarih": localdate()},
                    alan=alan,
                )
                form.fields["talebe"].widget.attrs["readonly"] = True

    turler = aktif_gorusme_turleri(alan=alan)
    return render(
        request,
        cfg["template"],
        {
            "panel_cfg": cfg,
            "panel_alan": alan,
            "talebeler": talebeler,
            "talebe": talebe,
            "panel": panel,
            "secili": secili,
            "form": form,
            "turler": turler,
            "etiket_onerileri": cfg["etiket_onerileri"],
            "duzenleyebilir": _duzenleyebilir(request.user, alan),
            "filtre_q": request.GET.get("q", ""),
            "filtre_tur": request.GET.get("tur", ""),
            "filtre_etiket": request.GET.get("etiket", ""),
            "filtre_takip": request.GET.get("takip", ""),
            "kararlar_listesi": kararlar_listesi(secili) if secili else [],
            "yapilacaklar_listesi": yapilacaklar_listesi(secili) if secili else [],
            "veli_gorusmeleri": veli_gorusmeleri(talebe)[:5] if talebe else [],
            "turler_json": json.dumps(
                [
                    {
                        "id": t.pk,
                        "ad": t.ad,
                        "grup": t.grup,
                        "ikon": t.ikon,
                        "renk": t.renk,
                    }
                    for t in turler
                ],
                ensure_ascii=False,
            ),
        },
    )


@login_required
@require_permission("rehberlik", "view")
def rehberlik_listesi(request):
    return _gorusme_paneli(request, GorusmeTuru.Alan.REHBERLIK)


@login_required
@require_permission("rehberlik", "view")
def rehberlik_detay(request, pk):
    gorusme = get_object_or_404(
        yetkili_gorusmeler(request.user, alan=GorusmeTuru.Alan.REHBERLIK),
        pk=pk,
    )
    return redirect(
        f"{reverse('rehberlik_listesi')}?talebe={gorusme.talebe_id}&detay={gorusme.pk}"
    )


@login_required
@require_permission("rehberlik", "edit")
def rehberlik_duzenle(request, pk):
    gorusme = get_object_or_404(
        yetkili_gorusmeler(request.user, alan=GorusmeTuru.Alan.REHBERLIK),
        pk=pk,
    )
    form = OgrenciGorusmesiForm(
        request.user,
        request.POST or None,
        instance=gorusme,
        alan=GorusmeTuru.Alan.REHBERLIK,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Rehberlik kaydı güncellendi.")
        return redirect(
            f"{reverse('rehberlik_listesi')}?talebe={gorusme.talebe_id}&detay={gorusme.pk}"
        )

    return render(
        request,
        "rehberlik_form.html",
        {
            "form": form,
            "gorusme": gorusme,
            "baslik": "Rehberlik Görüşmesi Düzenle",
        },
    )


@login_required
@require_permission("veli_iletisim", "view")
def iletisim_listesi(request):
    return _gorusme_paneli(request, GorusmeTuru.Alan.ILETISIM)


@login_required
@require_permission("veli_iletisim", "view")
def iletisim_detay(request, pk):
    gorusme = get_object_or_404(
        yetkili_gorusmeler(request.user, alan=GorusmeTuru.Alan.ILETISIM),
        pk=pk,
    )
    return redirect(
        f"{reverse('iletisim_listesi')}?talebe={gorusme.talebe_id}&detay={gorusme.pk}"
    )


@login_required
@require_permission("veli_iletisim", "edit")
def iletisim_duzenle(request, pk):
    gorusme = get_object_or_404(
        yetkili_gorusmeler(request.user, alan=GorusmeTuru.Alan.ILETISIM),
        pk=pk,
    )
    form = OgrenciGorusmesiForm(
        request.user,
        request.POST or None,
        instance=gorusme,
        alan=GorusmeTuru.Alan.ILETISIM,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "İletişim kaydı güncellendi.")
        return redirect(
            f"{reverse('iletisim_listesi')}?talebe={gorusme.talebe_id}&detay={gorusme.pk}"
        )

    return render(
        request,
        "rehberlik_form.html",
        {
            "form": form,
            "gorusme": gorusme,
            "baslik": "İletişim Kaydı Düzenle",
        },
    )
