"""Mezun takip merkezi görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate

from takip.mezun_forms import (
    MezunBasariForm,
    MezunEtkinlikForm,
    MezunGorevForm,
    MezunIletisimForm,
    MezunProfilGuncelleForm,
)
from takip.mezun_models import MezunBasari, MezunGuncellemeGorevKayit, MezunProfil
from takip.mezun_service import (
    ALAN_ETIKETLERI,
    akademik_arsiv_ozeti,
    basari_ekle,
    dashboard_ozet,
    gorev_olustur,
    iletisim_kaydi_ekle,
    istatistik_merkezi,
    kullanici_gorevleri,
    mezun_duzenleyebilir,
    mezun_yonetebilir,
    mezun_yolculuk_olustur,
    mezuniyet_yillari,
    mezunlari_filtrele,
    mezun_yil_ozetleri,
    sag_panel_verisi,
    yetkili_mezun_profilleri,
)
from takip.permissions.decorators import require_permission


@login_required
@require_permission("mezun", "view")
def mezun_listesi(request):
    qs = yetkili_mezun_profilleri(request.user).order_by("-mezuniyet_tarihi", "talebe__ad_soyad")
    q = request.GET.get("q", "").strip()
    yil = request.GET.get("yil", "").strip()
    lise = request.GET.get("lise", "").strip()
    universite = request.GET.get("universite", "").strip()
    bolum = request.GET.get("bolum", "").strip()
    iletisim = request.GET.get("iletisim", "").strip()
    qs = mezunlari_filtrele(
        qs,
        q=q or None,
        mezuniyet_yili=yil or None,
        lise=lise or None,
        universite=universite or None,
        bolum=bolum or None,
        iletisim=iletisim or None,
    )

    ozet = dashboard_ozet(yetkili_mezun_profilleri(request.user))
    sag = sag_panel_verisi(request.user, yetkili_mezun_profilleri(request.user))
    yil_ozet = mezun_yil_ozetleri(yetkili_mezun_profilleri(request.user))

    return render(
        request,
        "mezun/panel.html",
        {
            "mezunlar": qs[:150],
            "ozet": ozet,
            "sag": sag,
            "yil_ozet": yil_ozet,
            "filtre_q": q,
            "filtre_yil": yil,
            "filtre_lise": lise,
            "filtre_universite": universite,
            "filtre_bolum": bolum,
            "filtre_iletisim": iletisim,
            "yillar": mezuniyet_yillari(yetkili_mezun_profilleri(request.user)),
            "iletisim_secenekleri": MezunProfil.IletisimDurumu.choices,
            "duzenleyebilir": mezun_duzenleyebilir(request.user),
            "yonetebilir": mezun_yonetebilir(request.user),
        },
    )


@login_required
@require_permission("mezun", "view")
def mezun_detay(request, pk):
    profil = get_object_or_404(
        yetkili_mezun_profilleri(request.user).prefetch_related(
            "yolculuk_olaylari",
            "iletisim_kayitlari__kaydeden",
            "basarilar",
            "etkinlik_katilimlari__etkinlik",
        ),
        pk=pk,
    )
    talebe = profil.talebe
    yonetebilir = mezun_yonetebilir(request.user)
    duzenleyebilir = mezun_duzenleyebilir(request.user)

    profil_form = None
    iletisim_form = None
    basari_form = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "profil_guncelle" and duzenleyebilir:
            profil_form = MezunProfilGuncelleForm(request.POST, instance=profil)
            if profil_form.is_valid():
                profil_form.save()
                mezun_yolculuk_olustur(profil)
                messages.success(request, "Profil güncellendi.")
                return redirect("mezun_detay", pk=profil.pk)
        elif action == "iletisim" and duzenleyebilir:
            iletisim_form = MezunIletisimForm(request.POST)
            if iletisim_form.is_valid():
                iletisim_kaydi_ekle(
                    profil,
                    tur=iletisim_form.cleaned_data["tur"],
                    tarih=iletisim_form.cleaned_data["tarih"],
                    aciklama=iletisim_form.cleaned_data["aciklama"],
                    user=request.user,
                )
                messages.success(request, "İletişim kaydı eklendi.")
                return redirect("mezun_detay", pk=profil.pk)
        elif action == "basari" and duzenleyebilir:
            basari_form = MezunBasariForm(request.POST)
            if basari_form.is_valid():
                basari_ekle(
                    profil,
                    baslik=basari_form.cleaned_data["baslik"],
                    kategori=basari_form.cleaned_data["kategori"],
                    tarih=basari_form.cleaned_data["tarih"],
                    aciklama=basari_form.cleaned_data.get("aciklama") or "",
                    kurum_yarisma=basari_form.cleaned_data.get("kurum_yarisma") or "",
                    arsivde_goster=basari_form.cleaned_data.get("arsivde_goster") or False,
                    user=request.user,
                )
                messages.success(request, "Başarı kaydı eklendi.")
                return redirect("mezun_detay", pk=profil.pk)

    if profil_form is None and duzenleyebilir:
        profil_form = MezunProfilGuncelleForm(instance=profil)
    if iletisim_form is None and duzenleyebilir:
        iletisim_form = MezunIletisimForm(initial={"tarih": localdate()})
    if basari_form is None and duzenleyebilir:
        basari_form = MezunBasariForm(initial={"tarih": localdate()})

    arsiv = akademik_arsiv_ozeti(talebe)
    arsiv_basarilar = MezunBasari.objects.filter(arsivde_goster=True).select_related("profil__talebe")[:6]

    return render(
        request,
        "mezun/profil.html",
        {
            "profil": profil,
            "talebe": talebe,
            "yolculuk": profil.yolculuk_olaylari.all(),
            "iletisimler": profil.iletisim_kayitlari.all(),
            "basarilar": profil.basarilar.all(),
            "profil_form": profil_form,
            "iletisim_form": iletisim_form,
            "basari_form": basari_form,
            "arsiv": arsiv,
            "arsiv_basarilar": arsiv_basarilar,
            "duzenleyebilir": duzenleyebilir,
            "yonetebilir": yonetebilir,
        },
    )


@login_required
@require_permission("mezun", "view")
def mezun_etkinlikler(request):
    from takip.mezun_models import MezunEtkinlik

    etkinlikler = MezunEtkinlik.objects.all().order_by("-tarih")[:40]
    form = None
    if mezun_yonetebilir(request.user) and request.method == "POST":
        form = MezunEtkinlikForm(request.POST)
        if form.is_valid():
            etkinlik = form.save(commit=False)
            etkinlik.olusturan = request.user
            etkinlik.save()
            messages.success(request, "Etkinlik oluşturuldu.")
            return redirect("mezun_etkinlikler")
    elif mezun_yonetebilir(request.user):
        form = MezunEtkinlikForm(initial={"tarih": localdate()})

    return render(
        request,
        "mezun/etkinlikler.html",
        {
            "etkinlikler": etkinlikler,
            "form": form,
            "yonetebilir": mezun_yonetebilir(request.user),
        },
    )


@login_required
@require_permission("mezun", "view")
def mezun_gorevler(request):
    gorevler = kullanici_gorevleri(request.user).select_related("sorumlu", "olusturan")
    form = None
    if mezun_yonetebilir(request.user) and request.method == "POST":
        form = MezunGorevForm(request.POST)
        if form.is_valid():
            gorev_olustur(
                baslik=form.cleaned_data["baslik"],
                aciklama=form.cleaned_data.get("aciklama") or "",
                sorumlu=form.cleaned_data["sorumlu"],
                son_tarih=form.cleaned_data["son_tarih"],
                talep_edilen_alanlar=form.cleaned_data.get("talep_edilen_alanlar") or [],
                mezuniyet_yili=form.cleaned_data.get("mezuniyet_yili"),
                olusturan=request.user,
                qs=yetkili_mezun_profilleri(request.user),
            )
            messages.success(request, "Güncelleme görevi oluşturuldu.")
            return redirect("mezun_gorevler")
    elif mezun_yonetebilir(request.user):
        form = MezunGorevForm(initial={"son_tarih": localdate()})

    return render(
        request,
        "mezun/gorevler.html",
        {
            "gorevler": gorevler[:30],
            "form": form,
            "alan_etiketleri": ALAN_ETIKETLERI,
            "yonetebilir": mezun_yonetebilir(request.user),
        },
    )


@login_required
@require_permission("mezun", "view")
def mezun_gorev_detay(request, pk):
    gorev = get_object_or_404(kullanici_gorevleri(request.user), pk=pk)
    kayitlar = gorev.kayitlar.select_related("profil__talebe").order_by("profil__talebe__ad_soyad")

    if request.method == "POST" and request.POST.get("action") == "tamamla":
        kayit_id = request.POST.get("kayit_id")
        kayit = get_object_or_404(MezunGuncellemeGorevKayit, pk=kayit_id, gorev=gorev)
        kayit.tamamlandi = True
        kayit.save(update_fields=["tamamlandi", "guncellenme"])
        if not gorev.kayitlar.filter(tamamlandi=False).exists():
            gorev.tamamlandi = True
            gorev.save(update_fields=["tamamlandi"])
        messages.success(request, "Kayıt tamamlandı.")
        return redirect("mezun_gorev_detay", pk=gorev.pk)

    talep_etiketleri = [ALAN_ETIKETLERI.get(a, a) for a in gorev.talep_edilen_alanlar]

    return render(
        request,
        "mezun/gorev_detay.html",
        {
            "gorev": gorev,
            "kayitlar": kayitlar,
            "alan_etiketleri": ALAN_ETIKETLERI,
            "talep_etiketleri": talep_etiketleri,
        },
    )


@login_required
@require_permission("mezun", "view")
def mezun_istatistik(request):
    qs = yetkili_mezun_profilleri(request.user)
    stats = istatistik_merkezi(qs)
    return render(request, "mezun/istatistik.html", {"stats": stats})


@login_required
@require_permission("mezun", "view")
def mezun_raporlar(request):
    qs = yetkili_mezun_profilleri(request.user)
    return render(
        request,
        "mezun/raporlar.html",
        {
            "ozet": dashboard_ozet(qs),
            "yillar": mezuniyet_yillari(qs),
            "iletisim_secenekleri": MezunProfil.IletisimDurumu.choices,
            "basari_secenekleri": MezunBasari.Kategori.choices,
        },
    )


@login_required
@require_permission("mezun", "create")
def mezun_ekle(request):
    if not mezun_yonetebilir(request.user):
        return HttpResponseForbidden("Mezun ekleme yetkiniz yok.")
    return redirect("yonetim:mezuniyet_islemi")
