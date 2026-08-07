from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from django.http import HttpResponse
from django.utils.text import slugify
from django.template.loader import render_to_string
from datetime import date
from typing import Any
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, Max, Q
from django.forms import modelform_factory
from .forms import StyledModelForm
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import localdate

from config.branding import panel_branding_context
from .pdf_utils import (
    html_to_pdf,
    make_pdf_response,
    pdf_engine_status,
    pdf_error_response,
)

from .models import (
    EtutHocasi,
    ImamMuezzinListesi,
    Kitap,
    OkumaKaydi,
    ProgramPlan,
    Sinav,
    SinavSonucu,
    SinifSube,
    Talebe,
    TalebeDosyasi,
    TalebeGenelDurum,
    TalebePersonelNotu,
    KttSonucu,
    GunlukSoruKaydi,
    AkademikMudahale,
    DenemeSonucu,
    TemizlikListesi,
    VeliKisi,
    YemekciListesi,
    Zimmet,
)
from .forms import (
    TalebeDosyasiForm,
    TalebeGenelDurumForm,
    TalebePersonelNotuForm,
)
from .gelisim_service import talebe_gelisim_dosyasi, talebe_timeline
from .akademik_mudahale_service import talebe_akademik_ozet
from .dini_ders_takip_service import talebe_ilerleme_ozeti
from .veli_service import kullanici_veli_mi
from .talebe_panel_service import kullanici_talebe_mi
from .ogretmen_service import ogretmen_paneli_kullanicisi_mi
from .deneme_service import BRANS_ETIKETLERI, talebe_deneme_sonuclari
from .permissions.service import can
from .duyuru_service import kullaniciya_gorunur_duyurular
from .dashboard_service import (
    bugunku_sinav_sayisi,
    dashboard_etut_plani_onizleme,
    dashboard_gunluk_gorevler,
    dashboard_kisayollari,
    dashboard_son_aktiviteler,
    dashboard_son_gorusmeler,
    dashboard_son_iletisim,
    dashboard_yaklasan_etkinlikler,
)
from .imam_muezzin_service import bugunun_atamasi, bugunun_listesi
from .program_service import bugunun_programi, program_arsivi, tarihe_uygun_programlar
from .temizlik_service import (
    bugunun_atamalari,
    bugunun_atamalari_kullanici,
    bugunun_listesi as bugunun_temizlik_listesi,
    kullanici_kat_sorumluluklari,
)
from .yemekci_service import bugunun_atamalari as bugunun_yemek_atamalari
from .yemekci_service import bugunun_listesi as bugunun_yemekci_listesi
from .panel_permissions import (
    egitim_modulu_erisimi_var,
    gelisim_dosyasi_erisimi_var,
    imam_muezzin_modulu_erisimi_var,
    program_modulu_erisimi_var,
    rol_etiketi,
    temizlik_modulu_erisimi_var,
    temizlik_paneli_gorebilir,
    tum_talebe_erisimi_var,
    yemekcilik_modulu_erisimi_var,
    yonetim_erisimi_var,
)


# =========================================================
# YARDIMCI FONKSİYONLAR
# =========================================================


def _model_alanlari(model) -> set[str]:
    """Modelde bulunan gerçek alan isimlerini döndürür."""
    return {
        field.name
        for field in model._meta.get_fields()
    }


def _alan_var_mi(model, alan_adi: str) -> bool:
    return alan_adi in _model_alanlari(model)


def _etut_hocasi(user):
    """Giriş yapan kullanıcıya bağlı etüt hocasını bulur."""

    if not user.is_authenticated:
        return None

    if _alan_var_mi(EtutHocasi, "user"):
        hoca = EtutHocasi.objects.filter(
            user=user
        ).first()

        if hoca:
            return hoca

    if _alan_var_mi(EtutHocasi, "kullanici"):
        hoca = EtutHocasi.objects.filter(
            kullanici=user
        ).first()

        if hoca:
            return hoca

    return None


def _yetkili_talebeler(user):
    from takip.permissions.scope import yetkili_talebeler as scope_yetkili_talebeler

    return scope_yetkili_talebeler(user, aktif_only=True)


def _yetkili_zimmetler(user):
    zimmetler = Zimmet.objects.all()

    if tum_talebe_erisimi_var(user):
        return zimmetler

    hoca = _etut_hocasi(user)

    if not hoca:
        return Zimmet.objects.none()

    if _alan_var_mi(Zimmet, "etut_hocasi"):
        return zimmetler.filter(
            Q(etut_hocasi=hoca)
            | Q(talebe__dini_ders_hocasi=hoca)
        )

    if _alan_var_mi(Zimmet, "talebe"):
        return zimmetler.filter(
            talebe__in=_yetkili_talebeler(user)
        )

    return Zimmet.objects.none()


def _aktif_zimmetler(user):
    zimmetler = _yetkili_zimmetler(user)

    if _alan_var_mi(Zimmet, "durum"):
        zimmetler = zimmetler.filter(
            durum="okunuyor"
        )

    return zimmetler


def _yetkili_sinavlar(user):
    sinavlar = Sinav.objects.all()

    if tum_talebe_erisimi_var(user):
        return sinavlar

    hoca = _etut_hocasi(user)

    if not hoca:
        return Sinav.objects.none()

    if _alan_var_mi(Sinav, "etut_hocasi"):
        return sinavlar.filter(
            etut_hocasi=hoca
        )

    return Sinav.objects.none()


def _zimmet_ilerleme_yuzdesi(zimmet) -> float:
    son_sayfa = (
        getattr(zimmet, "son_sayfa", 0)
        or 0
    )

    toplam_sayfa = (
        getattr(zimmet.kitap, "toplam_sayfa", 0)
        or 0
    )

    if toplam_sayfa <= 0:
        return 0

    return min(
        round(
            son_sayfa / toplam_sayfa * 100,
            1,
        ),
        100,
    )


def _okunan_sayfa_hesapla(kayit: OkumaKaydi) -> int:
    """
    OkumaKaydi modelinde okunan_sayfa alanı yoktur.

    Okunan miktar:
    mevcut son sayfa - önceki kaydın son sayfası
    şeklinde hesaplanır.
    """

    onceki_kayit = (
        OkumaKaydi.objects
        .filter(
            zimmet=kayit.zimmet,
        )
        .filter(
            Q(tarih__lt=kayit.tarih)
            |
            Q(
                tarih=kayit.tarih,
                id__lt=kayit.id,
            )
        )
        .order_by(
            "-tarih",
            "-id",
        )
        .first()
    )

    if onceki_kayit:
        onceki_sayfa = (
            onceki_kayit.son_sayfa
            or 0
        )
    else:
        onceki_sayfa = (
            getattr(
                kayit.zimmet,
                "baslangic_sayfasi",
                0,
            )
            or 0
        )

    return max(
        (kayit.son_sayfa or 0)
        - onceki_sayfa,
        0,
    )


def _zimmet_okuma_toplami(zimmet) -> int:
    kayitlar = (
        OkumaKaydi.objects
        .filter(zimmet=zimmet)
        .select_related("zimmet")
        .order_by("tarih", "id")
    )

    return sum(
        _okunan_sayfa_hesapla(kayit)
        for kayit in kayitlar
    )


# =========================================================
# ANA SAYFA
# =========================================================


def home(request):
    if request.user.is_authenticated:
        if kullanici_veli_mi(request.user):
            return redirect("veli_dashboard")
        if kullanici_talebe_mi(request.user):
            return redirect("talebe_dashboard")
        if ogretmen_paneli_kullanicisi_mi(request.user):
            return redirect("ogretmen_dashboard")
        return redirect("dashboard")

    return redirect("login")


# =========================================================
# GENEL BAKIŞ
# =========================================================


@login_required
def dashboard(request):
    if kullanici_veli_mi(request.user):
        return redirect("veli_dashboard")
    if kullanici_talebe_mi(request.user):
        return redirect("talebe_dashboard")
    if ogretmen_paneli_kullanicisi_mi(request.user):
        return redirect("ogretmen_dashboard")

    bugun = localdate()

    talebeler = _yetkili_talebeler(
        request.user
    )

    zimmetler = list(
        _yetkili_zimmetler(
            request.user
        )
        .select_related(
            "talebe",
            "kitap",
        )
        .order_by(
            "talebe__ad_soyad"
        )
    )

    zimmet_idleri = [
        zimmet.id
        for zimmet in zimmetler
    ]

    bugunku_kayitlar = list(
        OkumaKaydi.objects
        .filter(
            zimmet_id__in=zimmet_idleri,
            tarih=bugun,
        )
        .select_related(
            "zimmet",
            "zimmet__talebe",
            "zimmet__kitap",
        )
    )

    bugun_toplam = sum(
        _okunan_sayfa_hesapla(kayit)
        for kayit in bugunku_kayitlar
    )

    for zimmet in zimmetler:
        pass

    aktif_zimmetler = [
        zimmet
        for zimmet in zimmetler
        if getattr(
            zimmet,
            "durum",
            "okunuyor",
        ) == "okunuyor"
    ]

    tamamlanan = sum(
        1
        for zimmet in zimmetler
        if getattr(zimmet, "durum", "")
        in {
            "sinav_bekliyor",
            "sinav_yapildi",
            "tamamlandi",
        }
    )

    sinav_bekleyen = sum(
        1
        for zimmet in zimmetler
        if getattr(zimmet, "durum", "")
        == "sinav_bekliyor"
    )

    bugunku_kayit_sayisi = len(
        {
            kayit.zimmet_id
            for kayit in bugunku_kayitlar
        }
    )

    bekleyen = max(
        len(aktif_zimmetler)
        - bugunku_kayit_sayisi,
        0,
    )

    siniflar = (
        SinifSube.objects
        .filter(talebeler__in=talebeler, aktif=True)
        .annotate(talebe_sayisi=Count("talebeler", distinct=True))
        .distinct()
        .order_by("sinif", "sube")
    )

    son_kayitlar = (
        OkumaKaydi.objects
        .filter(
            zimmet_id__in=zimmet_idleri
        )
        .select_related(
            "zimmet",
            "zimmet__talebe",
            "zimmet__kitap",
        )
        .order_by(
            "-tarih",
            "-id",
        )[:8]
    )

    bugun_program = (
        bugunun_programi()
        if program_modulu_erisimi_var(request.user)
        else None
    )
    bugun_imam_atama = (
        bugunun_atamasi()
        if imam_muezzin_modulu_erisimi_var(request.user)
        else None
    )
    bugun_temizlik_atamalari = (
        bugunun_atamalari_kullanici(request.user)
        if temizlik_paneli_gorebilir(request.user)
        else []
    )
    bugun_yemek_atamalari = (
        bugunun_yemek_atamalari()
        if yemekcilik_modulu_erisimi_var(request.user)
        else []
    )

    bugunku_sinav = bugunku_sinav_sayisi(request.user, bugun)
    dashboard_widgets = {
        "kisayollar": dashboard_kisayollari(request.user, bugun=bugun),
        "son_aktiviteler": dashboard_son_aktiviteler(request.user),
        "son_gorusmeler": dashboard_son_gorusmeler(request.user),
        "son_iletisim": dashboard_son_iletisim(request.user),
        "yaklasan_etkinlikler": dashboard_yaklasan_etkinlikler(
            request.user,
            bugun=bugun,
        ),
        "etut_plani_onizleme": dashboard_etut_plani_onizleme(request.user),
        "gunluk_gorevler": dashboard_gunluk_gorevler(request.user, bugun=bugun),
    }

    return render(
        request,
        "dashboard.html",
        {
            "talebeler": talebeler,
            "talebe_sayisi": talebeler.count(),
            "zimmetler": zimmetler,
            "devam_eden": len(aktif_zimmetler),
            "tamamlanan": tamamlanan,
            "sinav_bekleyen": sinav_bekleyen,
            "sinav_sayisi": _yetkili_sinavlar(
                request.user
            ).count(),
            "bugunku_sinav": bugunku_sinav,
            "bugunku_kayit": bugunku_kayit_sayisi,
            "bekleyen": bekleyen,
            "bugun_toplam": bugun_toplam,
            "toplam_okunan": bugun_toplam,
            "son_kayitlar": son_kayitlar,
            "siniflar": siniflar,
            "panel_rol": rol_etiketi(request.user),
            "egitim_modulu": egitim_modulu_erisimi_var(request.user),
            "yonetim_modulu": yonetim_erisimi_var(request.user),
            "duyurular": kullaniciya_gorunur_duyurular(request.user),
            "bugun_program": bugun_program,
            "bugun_program_satir_sayisi": (
                bugun_program.satirlar.count() if bugun_program else 0
            ),
            "program_modulu": program_modulu_erisimi_var(request.user),
            "bugun_imam_atama": bugun_imam_atama,
            "imam_muezzin_modulu": imam_muezzin_modulu_erisimi_var(request.user),
            "bugun_temizlik_atamalari": bugun_temizlik_atamalari,
            "temizlik_modulu": temizlik_modulu_erisimi_var(request.user),
            "bugun_yemek_atamalari": bugun_yemek_atamalari,
            "yemekcilik_modulu": yemekcilik_modulu_erisimi_var(request.user),
            **dashboard_widgets,
        },
    )


# =========================================================
# TALEBELER
# =========================================================


@login_required
def talebe_listesi(request):
    talebe_qs = _yetkili_talebeler(request.user)
    sinif_id = request.GET.get("sinif", "").strip()
    if sinif_id.isdigit():
        talebe_qs = talebe_qs.filter(sinif_sube_id=int(sinif_id))
    talebeler = list(talebe_qs.order_by("ad_soyad"))

    zimmetler = list(
        _yetkili_zimmetler(
            request.user
        )
        .select_related(
            "talebe",
            "kitap",
        )
        .order_by("-id")
    )

    aktif_zimmetler = {}

    for zimmet in zimmetler:
        if zimmet.talebe_id in aktif_zimmetler:
            continue

        if getattr(
                zimmet,
                "durum",
                "okunuyor",
        ) == "okunuyor":
            aktif_zimmetler[
                zimmet.talebe_id
            ] = zimmet

    for talebe in talebeler:
        talebe.aktif_zimmet = (
            aktif_zimmetler.get(
                talebe.id
            )
        )

    from takip.panel_permissions import tum_talebe_erisimi_var
    from takip.talebe_liste_raporu_service import erisilebilir_siniflar

    talebe_qs = _yetkili_talebeler(request.user)
    return render(
        request,
        "talebe_listesi.html",
        {
            "talebeler": talebeler,
            "talebe_sayisi": len(talebeler),
            "sinif_id": sinif_id,
            "rapor_siniflar": erisilebilir_siniflar(talebe_qs),
            "rapor_pdf_url": reverse("talebe_liste_raporu_pdf"),
            "kurum_raporu_goster": (
                request.user.is_superuser or tum_talebe_erisimi_var(request.user)
            ),
        },
    )


@login_required
def talebe_liste_raporu_pdf(request):
    from takip.filter_utils import get_int_list
    from takip.talebe_liste_raporu_service import talebe_liste_raporu_pdf_yanit

    rapor_turu = request.GET.get("tur", "").strip()
    sinif_sube_ids = get_int_list(request.GET, "sinif_sube")

    return talebe_liste_raporu_pdf_yanit(
        request,
        rapor_turu=rapor_turu,
        sinif_sube_id=sinif_sube_ids[0] if len(sinif_sube_ids) == 1 else None,
        sinif_sube_ids=sinif_sube_ids,
        talebe_qs=_yetkili_talebeler(request.user),
    )


@login_required
def talebe_detay(
    request,
    talebe_id: int,
):
    talebe = get_object_or_404(
        _yetkili_talebeler(
            request.user
        ).select_related(
            "sinif_sube",
            "etut_hocasi",
            "dini_ders_hocasi",
            "dini_ders_seviyesi",
        ),
        id=talebe_id,
    )

    gelisim_erisim = gelisim_dosyasi_erisimi_var(request.user)

    sekme = request.GET.get("sekme")
    if sekme not in {"egitim", "gelisim", "kimlik"}:
        sekme = "gelisim" if gelisim_erisim else "egitim"

    if request.method == "POST" and gelisim_erisim:
        aksiyon = request.POST.get("aksiyon")

        if aksiyon == "genel_durum" and can(request.user, "gelisim_dosyasi", "edit"):
            form = TalebeGenelDurumForm(request.POST)
            if form.is_valid():
                kayit, _ = TalebeGenelDurum.objects.get_or_create(talebe=talebe)
                kayit.durum_kodu = form.cleaned_data["durum_kodu"]
                kayit.ozet = form.cleaned_data["ozet"]
                kayit.guncelleyen = request.user
                kayit.save()
                messages.success(request, "Genel durum güncellendi.")
                return redirect(f"{request.path}?sekme=gelisim")

        if aksiyon == "not_ekle" and can(request.user, "gelisim_dosyasi", "create"):
            not_form = TalebePersonelNotuForm(request.POST)
            if not_form.is_valid():
                not_kaydi = not_form.save(commit=False)
                not_kaydi.talebe = talebe
                not_kaydi.yazar = request.user
                not_kaydi.save()
                messages.success(request, "Personel notu eklendi.")
                return redirect(f"{request.path}?sekme=gelisim")

        if aksiyon == "dosya_yukle" and can(request.user, "gelisim_dosyasi", "create"):
            dosya_form = TalebeDosyasiForm(request.POST, request.FILES)
            if dosya_form.is_valid():
                dosya = dosya_form.save(commit=False)
                dosya.talebe = talebe
                dosya.yukleyen = request.user
                dosya.save()
                messages.success(request, "Dosya yüklendi.")
                return redirect(f"{request.path}?sekme=gelisim")

        if aksiyon == "dosya_sil" and can(request.user, "gelisim_dosyasi", "delete"):
            dosya_id = request.POST.get("dosya_id", "").strip()
            if dosya_id.isdigit():
                dosya = get_object_or_404(
                    TalebeDosyasi,
                    id=int(dosya_id),
                    talebe=talebe,
                )
                dosya.dosya.delete(save=False)
                dosya.delete()
                messages.success(request, "Dosya silindi.")
            return redirect(f"{request.path}?sekme=gelisim")

    context = _talebe_profil_verisi(
        request.user,
        talebe,
    )
    context["aktif_sekme"] = sekme
    context["gelisim_erisim"] = gelisim_erisim

    if gelisim_erisim:
        genel, _ = TalebeGenelDurum.objects.get_or_create(talebe=talebe)
        context["genel_durum"] = genel
        context["genel_durum_form"] = TalebeGenelDurumForm(
            initial={
                "ozet": genel.ozet,
                "durum_kodu": genel.durum_kodu,
            }
        )
        context["not_form"] = TalebePersonelNotuForm()
        context["dosya_form"] = TalebeDosyasiForm()
        context["personel_notlari"] = (
            TalebePersonelNotu.objects.filter(talebe=talebe)
            .select_related("yazar")
            .order_by("-olusturulma")[:20]
        )
        context["dosyalar"] = (
            TalebeDosyasi.objects.filter(talebe=talebe)
            .select_related("yukleyen")
            .order_by("-olusturulma")[:20]
        )
        context["timeline"] = talebe_timeline(talebe, request.user)
        context["gelisim"] = talebe_gelisim_dosyasi(
            request.user,
            talebe,
            sinif_goster=context["sinif_goster"],
            genel=genel,
        )

    context["veli_kisileri"] = VeliKisi.objects.filter(talebe=talebe)

    from takip.disiplin_kurul_service import kurul_gorebilir, talebe_kurul_gecmisi

    if kurul_gorebilir(request.user):
        context["disiplin_kurul_erisim"] = True
        context["kurul_gecmisi"] = talebe_kurul_gecmisi(talebe)

    from takip.models import MezunProfil

    context["mezun_profil"] = MezunProfil.objects.filter(talebe=talebe).first()
    context["mezun_etkin"] = can(request.user, "mezun", "create") and talebe.durum != Talebe.Durum.MEZUN

    return render(
        request,
        "talebe_detay.html",
        context,
    )


def _talebe_profil_verisi(user, talebe):
    zimmetler = list(
        _yetkili_zimmetler(user)
        .filter(talebe=talebe)
        .select_related("kitap")
        .order_by("-id")
    )

    for zimmet in zimmetler:
        zimmet.okunan_toplam = _zimmet_okuma_toplami(zimmet)

    kayitlar = list(
        OkumaKaydi.objects.filter(zimmet__in=zimmetler)
        .select_related("zimmet", "zimmet__kitap")
        .order_by("-tarih", "-id")
    )

    for kayit in kayitlar:
        kayit.okunan_miktar = _okunan_sayfa_hesapla(kayit)

    sinav_sonuclari = list(
        SinavSonucu.objects.filter(talebe=talebe)
        .select_related("sinav", "sinav__kitap")
        .order_by("-sinav__sinav_tarihi", "-id")
    )

    ktt_sonuclari = list(
        KttSonucu.objects.filter(talebe=talebe)
        .select_related("ktt", "ktt__ders")
        .order_by("-ktt__sinav_tarihi", "-id")
    )

    soru_kayitlari = list(
        GunlukSoruKaydi.objects.filter(talebe=talebe)
        .prefetch_related("ders_satirlari__ders")
        .order_by("-tarih", "-id")[:15]
    )

    akademik_mudahaleler = list(
        AkademikMudahale.objects.filter(talebe=talebe)
        .select_related("mudahale_turu", "ders", "olusturan")
        .order_by("-tarih", "-id")[:15]
    )
    akademik_ozet = talebe_akademik_ozet(talebe)

    deneme_sonuclari = list(talebe_deneme_sonuclari(talebe)[:15])
    dini_ders_ozet = talebe_ilerleme_ozeti(talebe)

    toplam_okunan = sum(kayit.okunan_miktar for kayit in kayitlar)
    aktif_zimmet = next(
        (z for z in zimmetler if z.durum == "okunuyor"),
        None,
    )
    aktif_yuzde = 0
    if aktif_zimmet and aktif_zimmet.kitap.toplam_sayfa:
        aktif_yuzde = round(
            100 * aktif_zimmet.okunan_toplam / aktif_zimmet.kitap.toplam_sayfa
        )

    if talebe.sinif_sube_id:
        sinif_goster = str(talebe.sinif_sube)
    else:
        sinif_goster = talebe.sinif
        if talebe.sube:
            sinif_goster = f"{sinif_goster} / {talebe.sube}"

    return {
        "talebe": talebe,
        "zimmetler": zimmetler,
        "kayitlar": kayitlar,
        "sinav_sonuclari": sinav_sonuclari,
        "ktt_sonuclari": ktt_sonuclari,
        "soru_kayitlari": soru_kayitlari,
        "akademik_mudahaleler": akademik_mudahaleler,
        "akademik_ozet": akademik_ozet,
        "deneme_sonuclari": deneme_sonuclari,
        "deneme_brans_etiketleri": BRANS_ETIKETLERI,
        "dini_ders_ozet": dini_ders_ozet,
        "toplam_okunan": toplam_okunan,
        "aktif_zimmet": aktif_zimmet,
        "aktif_yuzde": aktif_yuzde,
        "sinif_goster": sinif_goster,
    }


@login_required
def talebe_profil_karne_pdf(request, talebe_id):
    talebe = get_object_or_404(
        _yetkili_talebeler(request.user).select_related(
            "sinif_sube",
            "etut_hocasi",
            "dini_ders_hocasi",
        ),
        id=talebe_id,
    )

    html_metni = render_to_string(
        "talebe_profil_karne_pdf.html",
        _talebe_profil_verisi(request.user, talebe),
        request=request,
    )

    pdf_verisi = html_to_pdf(
        html_metni,
        base_url=request.build_absolute_uri("/"),
    )

    if not pdf_verisi:
        messages.error(
            request,
            "Profil karne PDF oluşturulamadı. "
            f"(Motor: {pdf_engine_status()})",
        )
        return redirect("talebe_detay", talebe_id=talebe.id)

    talebe_adi = slugify(talebe.ad_soyad) or f"talebe-{talebe.id}"

    return make_pdf_response(
        pdf_verisi,
        f"{talebe_adi}-kitap-karnesi.pdf",
    )


# =========================================================
# KİTAPLAR
# =========================================================


@login_required
def kitap_listesi(request):
    kitaplar = list(
        Kitap.objects
        .all()
        .order_by("ad")
    )

    toplam_zimmet = 0
    for kitap in kitaplar:
        kitap.zimmet_sayisi = (
            Zimmet.objects
            .filter(kitap=kitap)
            .count()
        )
        toplam_zimmet += kitap.zimmet_sayisi

    aktif_okuma = (
        Zimmet.objects
        .filter(durum="okunuyor")
        .count()
    )

    return render(
        request,
        "kitap_listesi.html",
        {
            "kitaplar": kitaplar,
            "toplam_zimmet": toplam_zimmet,
            "aktif_okuma": aktif_okuma,
        },
    )


@login_required
def kitap_ekle(request):
    kullanilacak_alanlar = [
        alan
        for alan in [
            "ad",
            "yazar",
            "toplam_sayfa",
        ]
        if _alan_var_mi(
            Kitap,
            alan,
        )
    ]

    KitapForm = modelform_factory(
        Kitap,
        fields=kullanilacak_alanlar,
        form=StyledModelForm,
    )

    form = KitapForm(
        request.POST or None
    )

    if form.is_valid():
        form.save()

        messages.success(
            request,
            "Kitap başarıyla eklendi.",
        )

        return redirect(
            "kitap_listesi"
        )

    return render(
        request,
        "form_page.html",
        {
            "form": form,
            "baslik": "Yeni Kitap",
            "aciklama": "Kitabın temel bilgilerini girin.",
            "buton_metni": "Kitabı Kaydet",
            "kicker": "KÜTÜPHANE",
            "geri_url": reverse("kitap_listesi"),
            "geri_etiket": "Kitap Arşivi",
        },
    )


# =========================================================
# TOPLU KİTAP ZİMMETLEME
# =========================================================


@login_required
def toplu_zimmet(request):
    talebeler = list(
        _yetkili_talebeler(request.user)
        .select_related("sinif_sube", "etut_hocasi", "dini_ders_hocasi")
        .order_by("ad_soyad")
    )

    kitaplar = Kitap.objects.filter(aktif=True).order_by("ad")

    if request.method == "POST":
        kitap_id = (
            request.POST.get("kitap_id")
            or request.POST.get("kitap")
            or ""
        ).strip()

        secili_talebe_idleri = (
            request.POST.getlist("talebe_ids")
            or request.POST.getlist("talebeler")
            or request.POST.getlist("talebe")
        )

        zimmet_tarihi_raw = (
            request.POST.get("zimmet_tarihi")
            or str(localdate())
        ).strip()

        hedef_bitis_raw = (
            request.POST.get("hedef_bitis_tarihi")
            or ""
        ).strip()

        kitap_sayfa_sayisi_raw = (
            request.POST.get("kitap_sayfa_sayisi")
            or ""
        ).strip()

        aktif_kitabi_olanlari_atla = (
            request.POST.get("aktif_kitabi_olanlari_atla")
            in {"on", "1", "true", "True"}
        )

        hatalar = []

        if not kitap_id:
            hatalar.append("Lütfen bir kitap seçin.")

        if not secili_talebe_idleri:
            hatalar.append("En az bir talebe seçmelisiniz.")

        try:
            kitap_sayfa_sayisi = int(kitap_sayfa_sayisi_raw)
            if kitap_sayfa_sayisi < 1:
                raise ValueError
        except (TypeError, ValueError):
            kitap_sayfa_sayisi = None
            hatalar.append("Geçerli bir kitap sayfa sayısı girin.")

        try:
            zimmet_tarihi = date.fromisoformat(zimmet_tarihi_raw)
        except (TypeError, ValueError):
            zimmet_tarihi = localdate()
            hatalar.append("Geçerli bir zimmet tarihi seçin.")

        hedef_bitis_tarihi = None
        if hedef_bitis_raw:
            try:
                hedef_bitis_tarihi = date.fromisoformat(hedef_bitis_raw)
            except (TypeError, ValueError):
                hatalar.append("Geçerli bir hedef bitiş tarihi seçin.")

        if (
            hedef_bitis_tarihi
            and zimmet_tarihi
            and hedef_bitis_tarihi < zimmet_tarihi
        ):
            hatalar.append(
                "Hedef bitiş tarihi zimmet tarihinden önce olamaz."
            )

        if hatalar:
            for hata in hatalar:
                messages.error(request, hata)
        else:
            kitap = get_object_or_404(Kitap, id=kitap_id)

            if kitap.toplam_sayfa != kitap_sayfa_sayisi:
                kitap.toplam_sayfa = kitap_sayfa_sayisi
                if _alan_var_mi(Kitap, "son_duzenleyen"):
                    kitap.son_duzenleyen = request.user
                kitap.save()

            secili_talebeler = list(
                _yetkili_talebeler(request.user)
                .filter(id__in=secili_talebe_idleri)
                .select_related("etut_hocasi")
            )

            olusturulan = 0
            atlanan = 0

            with transaction.atomic():
                for talebe in secili_talebeler:
                    aktif_zimmet = (
                        Zimmet.objects
                        .filter(talebe=talebe, durum="okunuyor")
                        .select_related("kitap")
                        .first()
                    )

                    if aktif_kitabi_olanlari_atla and aktif_zimmet:
                        atlanan += 1
                        continue

                    zimmet = Zimmet(
                        talebe=talebe,
                        kitap=kitap,
                        etut_hocasi=talebe.etut_hocasi,
                        zimmet_tarihi=zimmet_tarihi,
                        hedef_bitis_tarihi=hedef_bitis_tarihi,
                        baslangic_sayfasi=0,
                        durum="okunuyor",
                    )

                    if _alan_var_mi(Zimmet, "olusturan"):
                        zimmet.olusturan = request.user

                    if _alan_var_mi(Zimmet, "son_duzenleyen"):
                        zimmet.son_duzenleyen = request.user

                    zimmet.save()
                    olusturulan += 1

            if olusturulan:
                mesaj = f"{olusturulan} talebeye kitap zimmetlendi."
                if atlanan:
                    mesaj += f" {atlanan} talebe aktif kitabı olduğu için atlandı."
                messages.success(request, mesaj)
                return redirect("toplu_zimmet")

            if atlanan:
                messages.warning(
                    request,
                    "Seçilen talebelerin tamamında aktif kitap bulunduğu için yeni zimmet oluşturulmadı.",
                )
            else:
                messages.error(request, "Zimmet oluşturulamadı.")

    return render(
        request,
        "toplu_zimmet.html",
        {
            "talebeler": talebeler,
            "kitaplar": kitaplar,
        },
    )


# =========================================================
# TOPLU GÜNLÜK OKUMA
# =========================================================


@login_required
def toplu_gunluk_okuma(request):
    bugun = localdate()

    zimmetler = list(
        _aktif_zimmetler(request.user)
        .select_related("talebe", "kitap")
        .order_by("talebe__ad_soyad")
    )

    zimmet_idleri = [zimmet.id for zimmet in zimmetler]

    if request.method == "POST":
        kaydedilen = 0
        hatalar = []

        with transaction.atomic():
            for zimmet in zimmetler:
                yeni_sayfa_raw = (
                    request.POST.get(f"son_sayfa_{zimmet.id}")
                    or request.POST.get(f"sayfa_{zimmet.id}")
                    or ""
                ).strip()

                if not yeni_sayfa_raw:
                    continue

                try:
                    yeni_sayfa = int(yeni_sayfa_raw)
                except (TypeError, ValueError):
                    hatalar.append(
                        f"{zimmet.talebe.ad_soyad}: Sayfa değeri sayı olmalıdır."
                    )
                    continue

                mevcut_sayfa = int(zimmet.son_sayfa or 0)
                toplam_sayfa = int(zimmet.kitap.toplam_sayfa or 0)

                if yeni_sayfa < mevcut_sayfa:
                    hatalar.append(
                        f"{zimmet.talebe.ad_soyad}: Yeni değer {mevcut_sayfa} sayfasından küçük olamaz."
                    )
                    continue

                if toplam_sayfa > 0 and yeni_sayfa > toplam_sayfa:
                    hatalar.append(
                        f"{zimmet.talebe.ad_soyad}: Kitap toplam {toplam_sayfa} sayfadır."
                    )
                    continue

                kayit_degerleri = {"son_sayfa": yeni_sayfa}

                if _alan_var_mi(OkumaKaydi, "son_duzenleyen"):
                    kayit_degerleri["son_duzenleyen"] = request.user

                mevcut_kayit = OkumaKaydi.objects.filter(
                    zimmet=zimmet,
                    tarih=bugun,
                ).first()

                if mevcut_kayit:
                    for alan, deger in kayit_degerleri.items():
                        setattr(mevcut_kayit, alan, deger)
                    mevcut_kayit.save()
                else:
                    if _alan_var_mi(OkumaKaydi, "olusturan"):
                        kayit_degerleri["olusturan"] = request.user
                    OkumaKaydi.objects.create(
                        zimmet=zimmet,
                        tarih=bugun,
                        **kayit_degerleri,
                    )

                if toplam_sayfa > 0 and yeni_sayfa >= toplam_sayfa:
                    zimmet.durum = "sinav_bekliyor"
                    if _alan_var_mi(Zimmet, "son_duzenleyen"):
                        zimmet.son_duzenleyen = request.user
                    zimmet.save()

                kaydedilen += 1

        if kaydedilen:
            messages.success(
                request,
                f"{kaydedilen} talebenin okuma kaydı kaydedildi.",
            )

        for hata in hatalar:
            messages.error(request, hata)

        if not hatalar:
            return redirect("toplu_gunluk_okuma")

    bugunku_kayitlar = {
        kayit.zimmet_id: kayit
        for kayit in OkumaKaydi.objects.filter(
            zimmet_id__in=zimmet_idleri,
            tarih=bugun,
        ).select_related("zimmet")
    }

    satirlar = []

    for zimmet in zimmetler:
        kayit = bugunku_kayitlar.get(zimmet.id)
        bugun_okunan = _okunan_sayfa_hesapla(kayit) if kayit else 0

        satirlar.append(
            {
                "zimmet": zimmet,
                "kayit": kayit,
                "onceki_sayfa": int(zimmet.son_sayfa or 0),
                "bugun_okunan": bugun_okunan,
            }
        )

    bugun_okunan_toplam = sum(
        _okunan_sayfa_hesapla(kayit)
        for kayit in bugunku_kayitlar.values()
    )

    return render(
        request,
        "toplu_gunluk_okuma.html",
        {
            "bugun": bugun,
            "satirlar": satirlar,
            "zimmetler": zimmetler,
            "aktif_kitap": len(zimmetler),
            "aktif_kitap_sayisi": len(zimmetler),
            "giris_yapilan": len(bugunku_kayitlar),
            "bugunku_kayit": len(bugunku_kayitlar),
            "bugun_okunan": bugun_okunan_toplam,
            "bugun_toplam": bugun_okunan_toplam,
        },
    )


# =========================================================
# ESKİ SINAV BAĞLANTISI
# =========================================================


@login_required
def toplu_kitap_sinavi(request):
    return redirect(
        "sinav_ekle_panel"
    )


# =========================================================
# RAPORLAR
# =========================================================


@login_required
def raporlar(request):
    from takip.filter_utils import get_int_list

    zimmet_qs = _yetkili_zimmetler(request.user).select_related(
        "talebe", "talebe__sinif_sube", "kitap", "etut_hocasi"
    )
    baslangic = request.GET.get("baslangic", "").strip()
    bitis = request.GET.get("bitis", "").strip()
    sinif_ids = get_int_list(request.GET, "sinif")
    durum = request.GET.get("durum", "tum").strip()

    if sinif_ids:
        zimmet_qs = zimmet_qs.filter(talebe__sinif_sube_id__in=sinif_ids)
    if durum == "aktif":
        zimmet_qs = zimmet_qs.filter(durum="okunuyor")
    elif durum == "gecmis":
        zimmet_qs = zimmet_qs.exclude(durum="okunuyor")

    zimmetler = list(zimmet_qs.order_by("talebe__ad_soyad", "-zimmet_tarihi"))
    kayit_qs = OkumaKaydi.objects.filter(zimmet__in=zimmetler).select_related(
        "zimmet", "zimmet__talebe", "zimmet__kitap"
    )
    if baslangic:
        kayit_qs = kayit_qs.filter(tarih__gte=baslangic)
    if bitis:
        kayit_qs = kayit_qs.filter(tarih__lte=bitis)
    kayitlar = list(kayit_qs.order_by("tarih", "id"))

    toplamlar = {}
    for kayit in kayitlar:
        toplamlar[kayit.zimmet_id] = toplamlar.get(kayit.zimmet_id, 0) + _okunan_sayfa_hesapla(kayit)
    for zimmet in zimmetler:
        zimmet.okunan_toplam = toplamlar.get(zimmet.id, 0)

    siniflar = SinifSube.objects.filter(aktif=True)
    if not request.user.is_superuser:
        hoca = _etut_hocasi(request.user)
        if hoca:
            siniflar = hoca.sorumlu_sinif_subeler.filter(aktif=True)
        else:
            siniflar = SinifSube.objects.none()

    return render(request, "raporlar.html", {
        "toplam_okunan": sum(toplamlar.values()),
        "devam_eden": sum(1 for z in zimmetler if z.durum == "okunuyor"),
        "tamamlanan": sum(1 for z in zimmetler if z.durum != "okunuyor"),
        "sinav_sayisi": _yetkili_sinavlar(request.user).count(),
        "zimmetler": zimmetler,
        "siniflar": siniflar,
        "filtre": {"baslangic": baslangic, "bitis": bitis, "sinif": sinif_ids, "durum": durum},
    })


@login_required
def okuma_raporu_pdf(request):
    from takip.filter_utils import get_int_list

    zimmet_qs = _yetkili_zimmetler(request.user).select_related(
        "talebe", "talebe__sinif_sube", "kitap", "etut_hocasi"
    )
    baslangic = request.GET.get("baslangic", "").strip()
    bitis = request.GET.get("bitis", "").strip()
    sinif_ids = get_int_list(request.GET, "sinif")
    durum = request.GET.get("durum", "tum").strip()

    if sinif_ids:
        zimmet_qs = zimmet_qs.filter(talebe__sinif_sube_id__in=sinif_ids)
    if durum == "aktif":
        zimmet_qs = zimmet_qs.filter(durum="okunuyor")
    elif durum == "gecmis":
        zimmet_qs = zimmet_qs.exclude(durum="okunuyor")

    zimmetler = list(zimmet_qs.order_by("talebe__ad_soyad", "-zimmet_tarihi"))
    kayit_qs = OkumaKaydi.objects.filter(zimmet__in=zimmetler)
    if baslangic:
        kayit_qs = kayit_qs.filter(tarih__gte=baslangic)
    if bitis:
        kayit_qs = kayit_qs.filter(tarih__lte=bitis)

    totals = {}
    for kayit in kayit_qs:
        totals[kayit.zimmet_id] = (
            totals.get(kayit.zimmet_id, 0) + _okunan_sayfa_hesapla(kayit)
        )
    for zimmet in zimmetler:
        zimmet.okunan_toplam = totals.get(zimmet.id, 0)

    sinif_adi = "Tümü"
    if sinif_id.isdigit():
        sinif = SinifSube.objects.filter(id=int(sinif_id)).first()
        if sinif:
            sinif_adi = str(sinif)

    durum_etiketleri = {
        "tum": "Aktif ve geçmiş",
        "aktif": "Aktif okunanlar",
        "gecmis": "Geçmiş kitaplar",
    }

    html_metni = render_to_string(
        "okuma_raporu_pdf.html",
        {
            "zimmetler": zimmetler,
            "toplam_okunan": sum(totals.values()),
            "devam_eden": sum(1 for z in zimmetler if z.durum == "okunuyor"),
            "tamamlanan": sum(1 for z in zimmetler if z.durum != "okunuyor"),
            "sinav_sayisi": _yetkili_sinavlar(request.user).count(),
            "kapsam": "Kurum Geneli" if request.user.is_superuser else "Etüt Grubu",
            "kayit_sayisi": len(zimmetler),
            "filtre": {
                "baslangic": baslangic or "Tüm tarihler",
                "bitis": bitis or "Bugün",
                "sinif": sinif_adi,
                "durum": durum_etiketleri.get(durum, durum),
            },
        },
        request=request,
    )

    pdf_verisi = html_to_pdf(
        html_metni,
        base_url=request.build_absolute_uri("/"),
    )
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    return make_pdf_response(
        pdf_verisi,
        "kitap-okuma-raporu.pdf",
    )


# =========================================================
# SINAV OLUŞTURMA
# =========================================================


@login_required
def sinav_ekle_panel(request):
    sinav_alanlari = [
        alan
        for alan in [
            "kitap",
            "ad",
            "soru_sayisi",
            "sinav_tarihi",
        ]
        if _alan_var_mi(
            Sinav,
            alan,
        )
    ]

    SinavForm = modelform_factory(
        Sinav,
        fields=sinav_alanlari,
    )

    form = SinavForm(
        request.POST or None
    )

    for alan_adi, alan in form.fields.items():
        alan.widget.attrs.update(
            {
                "class": "input",
            }
        )

        if alan_adi == "kitap":
            alan.label = "Kitap"
            alan.empty_label = "Kitap seçiniz"

        elif alan_adi == "ad":
            alan.label = "Sınav Adı"
            alan.widget.attrs["placeholder"] = (
                "Örnek: Gizli Çekmece Kitap Sınavı"
            )

        elif alan_adi == "soru_sayisi":
            alan.label = "Soru Sayısı"
            alan.widget.attrs["placeholder"] = "Örnek: 30"

        elif alan_adi == "sinav_tarihi":
            alan.label = "Sınav Tarihi"
            alan.widget.input_type = "date"

    if form.is_valid():
        sinav = form.save(
            commit=False
        )

        hoca = _etut_hocasi(
            request.user
        )

        if _alan_var_mi(
            Sinav,
            "etut_hocasi",
        ):
            sinav.etut_hocasi = hoca

        if _alan_var_mi(
            Sinav,
            "olusturan",
        ):
            sinav.olusturan = request.user

        sinav.save()

        messages.success(
            request,
            "Sınav başarıyla oluşturuldu.",
        )

        return redirect(
            "sinav_sonuc_paneli"
        )

    return render(
        request,
        "sinav_ekle_panel.html",
        {
            "form": form,
        },
    )


# =========================================================
# SINAV SONUÇLARI
# =========================================================


@login_required
def sinav_sonuc_paneli(request):
    sinavlar = (
        _yetkili_sinavlar(
            request.user
        )
        .order_by("-id")
    )

    for sinav in sinavlar:
        sinav.girilen_sonuc = (
            SinavSonucu.objects
            .filter(sinav=sinav)
            .count()
        )

    return render(
        request,
        "sinav_sonuc_paneli.html",
        {
            "sinavlar": sinavlar,
        },
    )


@login_required
def sinav_sonuclari_gir(request, sinav_id):
    sinav = get_object_or_404(
        _yetkili_sinavlar(request.user),
        id=sinav_id,
    )

    talebeler = (
        _yetkili_talebeler(request.user)
        .order_by("ad_soyad")
    )

    toplam_soru = int(sinav.soru_sayisi or 0)

    if toplam_soru <= 0:
        messages.error(
            request,
            "Sınavın soru sayısı geçerli değildir.",
        )
        return redirect("sinav_sonuc_paneli")

    if request.method == "POST":
        kaydedilen = 0
        hatalar = []

        with transaction.atomic():
            for talebe in talebeler:
                try:
                    dogru = int(
                        request.POST.get(
                            f"dogru_{talebe.id}",
                            0,
                        ) or 0
                    )

                    yanlis = int(
                        request.POST.get(
                            f"yanlis_{talebe.id}",
                            0,
                        ) or 0
                    )

                    bos = int(
                        request.POST.get(
                            f"bos_{talebe.id}",
                            0,
                        ) or 0
                    )

                except (TypeError, ValueError):
                    hatalar.append(
                        f"{talebe.ad_soyad}: "
                        "Geçerli sayılar girilmelidir."
                    )
                    continue

                if dogru < 0 or yanlis < 0 or bos < 0:
                    hatalar.append(
                        f"{talebe.ad_soyad}: "
                        "Sonuç değerleri negatif olamaz."
                    )
                    continue

                if dogru + yanlis + bos != toplam_soru:
                    hatalar.append(
                        f"{talebe.ad_soyad}: "
                        f"Doğru, yanlış ve boş toplamı "
                        f"{toplam_soru} olmalıdır."
                    )
                    continue

                sonuc_degerleri = {
                    "dogru": dogru,
                    "yanlis": yanlis,
                    "bos": bos,
                }

                if _alan_var_mi(
                    SinavSonucu,
                    "kaydeden",
                ):
                    sonuc_degerleri["kaydeden"] = request.user

                SinavSonucu.objects.update_or_create(
                    sinav=sinav,
                    talebe=talebe,
                    defaults=sonuc_degerleri,
                )

                kaydedilen += 1

            if hatalar:
                transaction.set_rollback(True)

        if hatalar:
            for hata in hatalar:
                messages.error(request, hata)

        else:
            messages.success(
                request,
                f"{kaydedilen} talebenin sonucu başarıyla kaydedildi.",
            )

            return redirect(
                "sinav_sonuclari_gir",
                sinav_id=sinav.id,
            )

    mevcut_sonuclar = {
        sonuc.talebe_id: sonuc
        for sonuc in SinavSonucu.objects.filter(
            sinav=sinav,
            talebe__in=talebeler,
        ).select_related("talebe")
    }

    satirlar = []

    for talebe in talebeler:
        sonuc = mevcut_sonuclar.get(talebe.id)

        satirlar.append(
            {
                "talebe": talebe,
                "sonuc": sonuc,
                "dogru": sonuc.dogru if sonuc else 0,
                "yanlis": sonuc.yanlis if sonuc else 0,
                "bos": sonuc.bos if sonuc else toplam_soru,
                "puan": sonuc.puan if sonuc else 0,
            }
        )

    siralama = list(
        SinavSonucu.objects.filter(
            sinav=sinav,
            talebe__in=talebeler,
        )
        .select_related("talebe")
        .order_by(
            "-puan",
            "-dogru",
            "yanlis",
            "talebe__ad_soyad",
        )
    )

    onceki_puan = None
    derece = 0

    for sira, sonuc in enumerate(siralama, start=1):
        if sonuc.puan != onceki_puan:
            derece = sira

        sonuc.derece = derece
        onceki_puan = sonuc.puan

    return render(
        request,
        "sinav_sonuclari_gir.html",
        {
            "sinav": sinav,
            "satirlar": satirlar,
            "siralama": siralama,
            "toplam_soru": toplam_soru,
        },
    )



# =========================================================
# SINAV PDF RAPORLARI
# =========================================================


def _sinav_siralamasi(sinav, talebeler):
    """
    Sınav sonuçlarını puana göre sıralar ve eşit puanlara
    aynı dereceyi verir.
    """
    sonuclar = list(
        SinavSonucu.objects.filter(
            sinav=sinav,
            talebe__in=talebeler,
        )
        .select_related("talebe", "sinav")
        .order_by(
            "-puan",
            "-dogru",
            "yanlis",
            "talebe__ad_soyad",
        )
    )

    onceki_puan = None
    derece = 0

    for sira, sonuc in enumerate(sonuclar, start=1):
        if sonuc.puan != onceki_puan:
            derece = sira

        sonuc.derece = derece
        onceki_puan = sonuc.puan

    return sonuclar


def _grup_adi_bul(sonuclar):
    """
    Sonuç listesindeki ilk talebeden grup adını üretir.
    Örnek: 7/A
    """
    if not sonuclar:
        return "Grup"

    talebe = sonuclar[0].talebe
    sinif = str(getattr(talebe, "sinif", "") or "").strip()
    sube = str(getattr(talebe, "sube", "") or "").strip()

    if sinif and sube:
        return f"{sinif}/{sube}"

    return sinif or sube or "Grup"


@login_required
def sinav_karne_pdf(request, sinav_id, talebe_id):
    """
    Tek bir talebenin sınav sonuç karnesini PDF olarak üretir.
    """
    sinav = get_object_or_404(
        _yetkili_sinavlar(request.user),
        id=sinav_id,
    )

    talebe = get_object_or_404(
        _yetkili_talebeler(request.user),
        id=talebe_id,
    )

    sonuc = get_object_or_404(
        SinavSonucu.objects.select_related(
            "sinav",
            "talebe",
        ),
        sinav=sinav,
        talebe=talebe,
    )

    talebeler = _yetkili_talebeler(request.user)
    siralama = _sinav_siralamasi(sinav, talebeler)

    derece = None

    for sirali_sonuc in siralama:
        if sirali_sonuc.talebe_id == talebe.id:
            derece = sirali_sonuc.derece
            break

    puan = Decimal(str(sonuc.puan or 0))

    if puan >= Decimal("90"):
        degerlendirme = (
            "Talebemiz kitabın olay örgüsünü, ana düşüncesini ve "
            "ayrıntılarını güçlü bir şekilde kavramıştır."
        )
    elif puan >= Decimal("75"):
        degerlendirme = (
            "Talebemiz kitabın temel olaylarını ve ana düşüncesini "
            "başarıyla kavramıştır."
        )
    elif puan >= Decimal("60"):
        degerlendirme = (
            "Talebemiz kitabın genel yapısını kavramış, bazı "
            "ayrıntılarda desteğe ihtiyaç duymuştur."
        )
    else:
        degerlendirme = (
            "Talebemizin kitabın temel bölümlerini yeniden gözden "
            "geçirmesi tavsiye edilmektedir."
        )

    html_metni = render_to_string(
        "sinav_karne_pdf.html",
        {
            "sinav": sinav,
            "talebe": talebe,
            "sonuc": sonuc,
            "derece": derece,
            "toplam_talebe": len(siralama),
            "degerlendirme": degerlendirme,
        },
        request=request,
    )

    pdf_verisi = html_to_pdf(
        html_metni,
        base_url=request.build_absolute_uri("/"),
    )

    if not pdf_verisi:
        messages.error(
            request,
            "Karne PDF oluşturulamadı. "
            f"(Motor: {pdf_engine_status()})",
        )
        return redirect(
            "sinav_sonuclari_gir",
            sinav_id=sinav.id,
        )

    talebe_adi = slugify(talebe.ad_soyad) or f"talebe-{talebe.id}"
    sinav_adi = slugify(sinav.ad) or f"sinav-{sinav.id}"

    return make_pdf_response(
        pdf_verisi,
        f"{talebe_adi}-{sinav_adi}-karne.pdf",
    )


@login_required
def sinav_sirali_sonuc_pdf(request, sinav_id):
    """
    Bir kitap sınavındaki bütün talebelerin neticelerini,
    deneme sıralaması biçiminde tek PDF olarak üretir.
    """
    sinav = get_object_or_404(
        _yetkili_sinavlar(request.user),
        id=sinav_id,
    )

    talebeler = _yetkili_talebeler(request.user)
    sonuclar = _sinav_siralamasi(sinav, talebeler)

    if not sonuclar:
        messages.error(
            request,
            "Bu sınava ait kaydedilmiş sonuç bulunamadı.",
        )
        return redirect(
            "sinav_sonuclari_gir",
            sinav_id=sinav.id,
        )

    istatistik = SinavSonucu.objects.filter(
        sinav=sinav,
        talebe__in=talebeler,
    ).aggregate(
        ortalama=Avg("puan"),
        en_yuksek=Max("puan"),
    )

    grup_adi = _grup_adi_bul(sonuclar)

    html_metni = render_to_string(
        "sinav_sirali_sonuc_pdf.html",
        {
            "sinav": sinav,
            "sonuclar": sonuclar,
            "grup_adi": grup_adi,
            "toplam_talebe": len(sonuclar),
            "sinif_ortalamasi": istatistik["ortalama"] or Decimal("0.00"),
            "en_yuksek_puan": istatistik["en_yuksek"] or Decimal("0.00"),
        },
        request=request,
    )

    pdf_verisi = html_to_pdf(
        html_metni,
        base_url=request.build_absolute_uri("/"),
    )

    if not pdf_verisi:
        messages.error(
            request,
            "Sıralı sonuç PDF oluşturulamadı. "
            f"(Motor: {pdf_engine_status()})",
        )
        return redirect(
            "sinav_sonuclari_gir",
            sinav_id=sinav.id,
        )

    sinav_adi = slugify(sinav.ad) or f"sinav-{sinav.id}"
    grup_dosya_adi = slugify(grup_adi) or "grup"

    return make_pdf_response(
        pdf_verisi,
        f"{grup_dosya_adi}-{sinav_adi}-sirali-sonuclar.pdf",
    )


# =========================================================
# PROGRAMLAR
# =========================================================


def _program_erisim_kontrol(request):
    if not program_modulu_erisimi_var(request.user):
        messages.error(request, "Program modülüne erişim yetkiniz yok.")
        return False

    return True


def program_plan_pdf_yanit(request, program):
    satirlar = list(program.satirlar.all())
    toplam_dakika = sum(satir.sure_dakika for satir in satirlar)

    html_metni = render_to_string(
        "program_plan_pdf.html",
        {
            "program": program,
            "satirlar": satirlar,
            "toplam_dakika": toplam_dakika,
            **panel_branding_context(),
        },
        request=request,
    )

    pdf_verisi = html_to_pdf(
        html_metni,
        base_url=request.build_absolute_uri("/"),
    )

    if not pdf_verisi:
        messages.error(
            request,
            "Program PDF oluşturulamadı. "
            f"(Motor: {pdf_engine_status()})",
        )
        return redirect("program_detay", pk=program.pk)

    dosya_adi = slugify(program.ad) or f"program-{program.pk}"
    return make_pdf_response(pdf_verisi, f"{dosya_adi}-program.pdf")


@login_required
def program_panel(request):
    if not _program_erisim_kontrol(request):
        return redirect("dashboard")

    secili_id = request.GET.get("program", "").strip()
    bugun = localdate()
    bugun_program = bugunun_programi()
    aktif_programlar = tarihe_uygun_programlar(bugun)

    secili_program = bugun_program

    if secili_id.isdigit():
        secili_program = (
            ProgramPlan.objects.filter(pk=int(secili_id))
            .prefetch_related("satirlar")
            .first()
            or secili_program
        )

    secilebilir_programlar = list(program_arsivi())

    return render(
        request,
        "program_panel.html",
        {
            "bugun": bugun,
            "bugun_program": bugun_program,
            "aktif_programlar": aktif_programlar,
            "secilebilir_programlar": secilebilir_programlar,
            "secili_program": secili_program,
            "satirlar": (
                list(secili_program.satirlar.all())
                if secili_program
                else []
            ),
            "yonetim_modulu": yonetim_erisimi_var(request.user),
        },
    )


@login_required
def program_detay(request, pk):
    if not _program_erisim_kontrol(request):
        return redirect("dashboard")

    program = get_object_or_404(
        ProgramPlan.objects.prefetch_related("satirlar"),
        pk=pk,
    )

    return render(
        request,
        "program_detay.html",
        {
            "program": program,
            "satirlar": list(program.satirlar.all()),
        },
    )


@login_required
def program_pdf(request, pk):
    if not _program_erisim_kontrol(request):
        return redirect("dashboard")

    program = get_object_or_404(
        ProgramPlan.objects.prefetch_related("satirlar"),
        pk=pk,
    )
    return program_plan_pdf_yanit(request, program)


# =========================================================
# İMAM / MÜEZZİN
# =========================================================


def _imam_erisim_kontrol(request):
    if not imam_muezzin_modulu_erisimi_var(request.user):
        messages.error(request, "İmam / müezzin modülüne erişim yetkiniz yok.")
        return False

    return True


def imam_muezzin_pdf_yanit(request, liste):
    from takip.imam_muezzin_yonetim_service import pdf_baglami

    ctx = pdf_baglami(liste)
    html_metni = render_to_string(
        "imam_muezzin_pdf.html",
        ctx,
        request=request,
    )

    pdf_verisi = html_to_pdf(
        html_metni,
        base_url=request.build_absolute_uri("/"),
    )

    if not pdf_verisi:
        messages.error(
            request,
            "Liste PDF oluşturulamadı. "
            f"(Motor: {pdf_engine_status()})",
        )
        return redirect("imam_muezzin_panel")

    dosya_adi = slugify(liste.ad) or f"imam-liste-{liste.pk}"
    return make_pdf_response(pdf_verisi, f"{dosya_adi}-imam-muezzin.pdf")


@login_required
def imam_muezzin_panel(request):
    if not _imam_erisim_kontrol(request):
        return redirect("dashboard")

    secili_id = request.GET.get("liste", "").strip()
    bugun = localdate()
    bugun_liste = bugunun_listesi()
    bugun_gorev = bugunun_atamasi()
    listeler = list(
        ImamMuezzinListesi.objects.filter(aktif=True)
        .prefetch_related("atamalar__imam", "atamalar__muezzin")
        .order_by("-baslangic_tarihi", "ad")
    )

    secili_liste = bugun_liste or (listeler[0] if listeler else None)

    if secili_id.isdigit():
        secili_liste = (
            ImamMuezzinListesi.objects.filter(pk=int(secili_id))
            .prefetch_related("atamalar__imam", "atamalar__muezzin")
            .first()
            or secili_liste
        )

    atamalar = (
        list(
            secili_liste.atamalar.select_related("imam", "muezzin").order_by(
                "tarih"
            )
        )
        if secili_liste
        else []
    )

    return render(
        request,
        "imam_muezzin_panel.html",
        {
            "bugun": bugun,
            "bugun_gorev": bugun_gorev,
            "listeler": listeler,
            "secili_liste": secili_liste,
            "atamalar": atamalar,
            "yonetim_modulu": yonetim_erisimi_var(request.user),
        },
    )


@login_required
def imam_muezzin_pdf(request, pk):
    if not _imam_erisim_kontrol(request):
        return redirect("dashboard")

    liste = get_object_or_404(
        ImamMuezzinListesi.objects.prefetch_related(
            "atamalar__imam",
            "atamalar__muezzin",
        ),
        pk=pk,
    )
    return imam_muezzin_pdf_yanit(request, liste)


# =========================================================
# TEMİZLİK
# =========================================================


def _temizlik_erisim_kontrol(request):
    if not temizlik_paneli_gorebilir(request.user):
        messages.error(
            request,
            "Temizlik modülüne erişim yetkiniz yok veya size atanmış bir kat bulunmuyor.",
        )
        return False

    return True


def temizlik_pdf_yanit(request, liste):
    from .temizlik_yonetim_service import yonetim_merkezi

    merkez = yonetim_merkezi(liste)
    fmt = (request.GET.get("format") or "a4").lower()
    yon = (request.GET.get("orientation") or "landscape").lower()
    if fmt not in ("a4", "a3"):
        fmt = "a4"
    if yon not in ("portrait", "landscape"):
        yon = "landscape"

    html_metni = render_to_string(
        "temizlik_pdf.html",
        {
            "liste": liste,
            "kat_kartlari": merkez["kat_kartlari"],
            "stats": merkez["stats"],
            **panel_branding_context(),
            "pdf_format": fmt,
            "pdf_orientation": yon,
            "bugun": merkez["bugun"],
        },
        request=request,
    )

    pdf_verisi = html_to_pdf(
        html_metni,
        base_url=request.build_absolute_uri("/"),
    )

    if not pdf_verisi:
        messages.error(
            request,
            "Liste PDF oluşturulamadı. "
            f"(Motor: {pdf_engine_status()})",
        )
        return redirect("temizlik_panel")

    dosya_adi = slugify(liste.ad) or f"temizlik-liste-{liste.pk}"
    suffix = f"-{fmt}-{yon}" if request.GET else ""
    return make_pdf_response(pdf_verisi, f"{dosya_adi}-temizlik{suffix}.pdf")


@login_required
def temizlik_panel(request):
    if not _temizlik_erisim_kontrol(request):
        return redirect("dashboard")

    secili_id = request.GET.get("liste", "").strip()
    tarih_metni = request.GET.get("tarih", "").strip()
    bugun = localdate()
    bugun_liste = bugunun_temizlik_listesi()
    bugun_gorevler = bugunun_atamalari_kullanici(request.user)
    kat_sorumluluklari = kullanici_kat_sorumluluklari(request.user)
    listeler = list(
        TemizlikListesi.objects.filter(aktif=True)
        .prefetch_related("atamalar__alan", "atamalar__talebe")
        .order_by("-baslangic_tarihi", "ad")
    )

    secili_liste = bugun_liste or (listeler[0] if listeler else None)

    if secili_id.isdigit():
        secili_liste = (
            TemizlikListesi.objects.filter(pk=int(secili_id))
            .prefetch_related("atamalar__alan", "atamalar__talebe")
            .first()
            or secili_liste
        )

    secili_tarih = bugun
    if tarih_metni:
        try:
            yil, ay, gun = tarih_metni.split("-")
            secili_tarih = date(int(yil), int(ay), int(gun))
        except ValueError:
            secili_tarih = bugun
    elif secili_liste:
        if not (
            secili_liste.baslangic_tarihi
            <= bugun
            <= secili_liste.bitis_tarihi
        ):
            secili_tarih = secili_liste.baslangic_tarihi

    atamalar = (
        list(
            secili_liste.atamalar.select_related("alan", "alan__kat", "talebe")
            .filter(tarih=secili_tarih)
            .order_by("alan__kat__sira", "alan__sira", "alan__ad")
        )
        if secili_liste
        else []
    )

    kat_ids = {s.kat_id for s in kat_sorumluluklari}
    if kat_ids and not request.user.is_superuser and not yonetim_erisimi_var(request.user):
        atamalar = [a for a in atamalar if a.alan.kat_id in kat_ids]

    return render(
        request,
        "temizlik_panel.html",
        {
            "bugun": bugun,
            "bugun_gorevler": bugun_gorevler,
            "kat_sorumluluklari": kat_sorumluluklari,
            "listeler": listeler,
            "secili_liste": secili_liste,
            "secili_tarih": secili_tarih,
            "atamalar": atamalar,
            "yonetim_modulu": yonetim_erisimi_var(request.user),
            "sadece_kat_gorunumu": bool(kat_ids),
        },
    )


@login_required
def temizlik_pdf(request, pk):
    if not _temizlik_erisim_kontrol(request):
        return redirect("dashboard")

    liste = get_object_or_404(
        TemizlikListesi.objects.prefetch_related(
            "atamalar__alan",
            "atamalar__talebe",
        ),
        pk=pk,
    )
    return temizlik_pdf_yanit(request, liste)


# =========================================================
# YEMEKÇİLİK
# =========================================================


def _yemekcilik_erisim_kontrol(request):
    if not yemekcilik_modulu_erisimi_var(request.user):
        messages.error(request, "Yemekçilik modülüne erişim yetkiniz yok.")
        return False

    return True


def yemekcilik_pdf_yanit(request, liste):
    atamalar = list(
        liste.atamalar.select_related("ogun", "talebe", "yardimci").order_by(
            "tarih",
            "ogun__sira",
            "ogun__ad",
        )
    )

    html_metni = render_to_string(
        "yemekcilik_pdf.html",
        {
            "liste": liste,
            "atamalar": atamalar,
            **panel_branding_context(),
        },
        request=request,
    )

    pdf_verisi = html_to_pdf(
        html_metni,
        base_url=request.build_absolute_uri("/"),
    )

    if not pdf_verisi:
        messages.error(
            request,
            "Liste PDF oluşturulamadı. "
            f"(Motor: {pdf_engine_status()})",
        )
        return redirect("yemekcilik_panel")

    dosya_adi = slugify(liste.ad) or f"yemekci-liste-{liste.pk}"
    return make_pdf_response(pdf_verisi, f"{dosya_adi}-yemekcilik.pdf")


@login_required
def yemekcilik_panel(request):
    if not _yemekcilik_erisim_kontrol(request):
        return redirect("dashboard")

    secili_id = request.GET.get("liste", "").strip()
    tarih_metni = request.GET.get("tarih", "").strip()
    bugun = localdate()
    bugun_liste = bugunun_yemekci_listesi()
    bugun_gorevler = bugunun_yemek_atamalari()
    listeler = list(
        YemekciListesi.objects.filter(aktif=True)
        .prefetch_related(
            "atamalar__ogun",
            "atamalar__talebe",
            "atamalar__yardimci",
        )
        .order_by("-baslangic_tarihi", "ad")
    )

    secili_liste = bugun_liste or (listeler[0] if listeler else None)

    if secili_id.isdigit():
        secili_liste = (
            YemekciListesi.objects.filter(pk=int(secili_id))
            .prefetch_related(
                "atamalar__ogun",
                "atamalar__talebe",
                "atamalar__yardimci",
            )
            .first()
            or secili_liste
        )

    secili_tarih = bugun
    if tarih_metni:
        try:
            yil, ay, gun = tarih_metni.split("-")
            secili_tarih = date(int(yil), int(ay), int(gun))
        except ValueError:
            secili_tarih = bugun
    elif secili_liste:
        if not (
            secili_liste.baslangic_tarihi
            <= bugun
            <= secili_liste.bitis_tarihi
        ):
            secili_tarih = secili_liste.baslangic_tarihi

    atamalar = (
        list(
            secili_liste.atamalar.select_related("ogun", "talebe", "yardimci")
            .filter(tarih=secili_tarih)
            .order_by("ogun__sira", "ogun__ad")
        )
        if secili_liste
        else []
    )

    return render(
        request,
        "yemekcilik_panel.html",
        {
            "bugun": bugun,
            "bugun_gorevler": bugun_gorevler,
            "listeler": listeler,
            "secili_liste": secili_liste,
            "secili_tarih": secili_tarih,
            "atamalar": atamalar,
            "yonetim_modulu": yonetim_erisimi_var(request.user),
        },
    )


@login_required
def yemekcilik_pdf(request, pk):
    if not _yemekcilik_erisim_kontrol(request):
        return redirect("dashboard")

    liste = get_object_or_404(
        YemekciListesi.objects.prefetch_related(
            "atamalar__ogun",
            "atamalar__talebe",
            "atamalar__yardimci",
        ),
        pk=pk,
    )
    return yemekcilik_pdf_yanit(request, liste)