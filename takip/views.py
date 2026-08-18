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
from django.db.models.deletion import ProtectedError
from django.db.models import Avg, Count, Max, Q
from django.forms import modelform_factory
from .forms import StyledModelForm
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import localdate

from config.branding import panel_branding_context
from .pdf_utils import (
    coz_pdf_sayfa,
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
from .deneme_service import BRANS_ETIKETLERI, talebe_deneme_performans_ozeti, talebe_deneme_sonuclari
from .permissions.service import can
from .permissions.decorators import require_permission
from .duyuru_service import kullaniciya_gorunur_duyurular
from .dashboard_service import (
    bugunku_sinav_sayisi,
    dashboard_dershane_onizleme,
    dashboard_etut_plani_onizleme,
    dashboard_gunluk_gorevler,
    dashboard_kisayollari,
    dashboard_metrikleri,
    dashboard_namaz_gelmedi,
    dashboard_son_aktiviteler,
    dashboard_son_gorusmeler,
    dashboard_son_iletisim,
    dashboard_yaklasan_etkinlikler,
)
from .imam_muezzin_service import bugunun_atamasi, bugunun_listesi
from .program_service import bugunun_programi, program_arsivi, tarihe_uygun_programlar
from .temizlik_service import (
    kullanici_kat_sorumluluklari,
    sabit_temizlik_katlari,
    sabit_temizlik_satirlari,
)
from .yemekci_service import bugunun_atamalari as bugunun_yemek_atamalari
from .yemekci_service import bugunun_listesi as bugunun_yemekci_listesi
from . import yemekci_views  # noqa: F401 — panel URL'leri yemekci_views'ta
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
            from takip.ogretmen_service import ogretmen_giris_url_adi

            return redirect(ogretmen_giris_url_adi(request.user))
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
        from takip.ogretmen_service import ogretmen_giris_url_adi

        return redirect(ogretmen_giris_url_adi(request.user))

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
        sabit_temizlik_satirlari(request.user)
        if temizlik_paneli_gorebilir(request.user)
        else []
    )
    bugun_yemek_atamalari = (
        bugunun_yemek_atamalari()
        if yemekcilik_modulu_erisimi_var(request.user)
        else []
    )

    bugunku_sinav = bugunku_sinav_sayisi(request.user, bugun)
    from takip.idareci_service import yct_ay_takvimi

    yct = yct_ay_takvimi(bugun.year, bugun.month)
    ay_tr = [
        "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
    ][bugun.month]
    yct["ay_adi_tr"] = ay_tr

    dashboard_widgets = {
        "kisayollar": dashboard_kisayollari(request.user, bugun=bugun),
        "metrikler": dashboard_metrikleri(
            request.user,
            hedef="personel",
            baglam={
                "talebe_sayisi": talebeler.count(),
                "toplam_okunan": bugun_toplam,
                "bugunku_kayit": bugunku_kayit_sayisi,
                "bekleyen": bekleyen,
                "bugunku_sinav": bugunku_sinav,
                "sinav_bekleyen": sinav_bekleyen,
            },
        ),
        "son_aktiviteler": dashboard_son_aktiviteler(request.user),
        "son_gorusmeler": dashboard_son_gorusmeler(request.user),
        "son_iletisim": dashboard_son_iletisim(request.user),
        "yaklasan_etkinlikler": dashboard_yaklasan_etkinlikler(
            request.user,
            bugun=bugun,
        ),
        "etut_plani_onizleme": dashboard_etut_plani_onizleme(request.user),
        "dershane_onizleme": dashboard_dershane_onizleme(request.user),
        "gunluk_gorevler": dashboard_gunluk_gorevler(request.user, bugun=bugun),
        "namaz_gelmedi": dashboard_namaz_gelmedi(request.user, bugun=bugun),
        "sinif_sayisi": siniflar.count(),
        "yct": yct,
    }

    from takip.vazife_service import vazife_bildirim_kartlari

    vazife_bildirimleri = vazife_bildirim_kartlari(request.user, bugun=bugun)

    from takip.hatim_service import personel_aktif_gorevleri

    hatim_gorevleri = personel_aktif_gorevleri(request.user, bugun=bugun)

    from takip.user_helpers import etut_hocasi_for_user

    etut_hocasi = etut_hocasi_for_user(request.user)

    mudahale_adaylari = []
    from takip.ai_permissions import kurum_ai_erisebilir

    if kurum_ai_erisebilir(request.user):
        from takip.ai_service import mudahale_oneri_listesi

        mudahale_adaylari = mudahale_oneri_listesi(request.user)[:6]

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
            "vazife_bildirimleri": vazife_bildirimleri,
            "hatim_gorevleri": hatim_gorevleri,
            "etut_hocasi": etut_hocasi,
            "mudahale_adaylari": mudahale_adaylari,
            **dashboard_widgets,
        },
    )


# =========================================================
# TALEBELER
# =========================================================


@login_required
def talebe_listesi(request):
    from takip.etut_zimmet_service import (
        etut_mesul_mu,
        etut_mesul_sinif_zimmet_senkronize,
    )

    hoca = _etut_hocasi(request.user)
    if hoca and etut_mesul_mu(hoca):
        etut_mesul_sinif_zimmet_senkronize(hoca)

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

    from takip.talebe_profil_service import profil_eksik_mi

    for talebe in talebeler:
        talebe.aktif_zimmet = (
            aktif_zimmetler.get(
                talebe.id
            )
        )
        talebe.profil_eksik = profil_eksik_mi(talebe)

    from takip.panel_permissions import tum_talebe_erisimi_var, yonetim_erisimi_var
    from takip.talebe_liste_raporu_service import erisilebilir_siniflar

    talebe_qs = _yetkili_talebeler(request.user)
    context = {
        "talebeler": talebeler,
        "talebe_sayisi": len(talebeler),
        "sinif_id": sinif_id,
        "rapor_siniflar": erisilebilir_siniflar(talebe_qs),
        "rapor_pdf_url": reverse("talebe_liste_raporu_pdf"),
        "rapor_excel_url": reverse("talebe_liste_excel"),
        "kurum_raporu_goster": (
            request.user.is_superuser or tum_talebe_erisimi_var(request.user)
        ),
        "yonetim_erisim": yonetim_erisimi_var(request.user),
    }
    template_name = (
        "partials/talebe_listesi_content.html"
        if getattr(request, "htmx", False)
        else "talebe_listesi.html"
    )
    return render(request, template_name, context)


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
def talebe_liste_excel(request):
    from takip.panel_permissions import tum_talebe_erisimi_var
    from takip.talebe_liste_raporu_service import talebe_liste_excel_yanit

    qs = _yetkili_talebeler(request.user)
    sinif_id = request.GET.get("sinif", "").strip()
    if sinif_id.isdigit():
        qs = qs.filter(sinif_sube_id=int(sinif_id))

    if request.user.is_superuser or tum_talebe_erisimi_var(request.user):
        baslik = "Talebe Listesi — Kurum"
        dosya = "talebe-listesi-kurum.xlsx"
    else:
        baslik = "Talebe Listesi — Etüt"
        dosya = "talebe-listesi-etut.xlsx"

    return talebe_liste_excel_yanit(
        talebe_qs=qs,
        baslik=baslik,
        dosya_adi=dosya,
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

    from takip.talebe_profil_service import (
        etut_profil_duzenleyebilir,
        profil_eksik_alanlar,
        profil_eksik_mi,
    )
    from takip.turkiye_il_ilce import il_ilce_haritasi
    from takip.yonetim_forms import TalebeProfilTamamlaForm

    gelisim_erisim = gelisim_dosyasi_erisimi_var(request.user)
    profil_duzenle = etut_profil_duzenleyebilir(request.user, talebe)
    kimlik_erisim = gelisim_erisim or profil_duzenle

    sekme = request.GET.get("sekme")
    if sekme not in {"egitim", "gelisim", "kimlik"}:
        sekme = "gelisim" if gelisim_erisim else "egitim"

    profil_form = None
    if request.method == "POST":
        aksiyon = request.POST.get("aksiyon")

        if aksiyon == "profil_tamamla" and profil_duzenle:
            profil_form = TalebeProfilTamamlaForm(
                request.POST,
                request.FILES,
                instance=talebe,
            )
            if profil_form.is_valid():
                profil_form.save()
                messages.success(request, "Talebe profili güncellendi.")
                return redirect(f"{request.path}?sekme=kimlik")
            sekme = "kimlik"
            messages.error(request, "Profil kaydedilemedi — eksik veya hatalı alanları kontrol edin.")

        if gelisim_erisim:
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
    context["kimlik_erisim"] = kimlik_erisim
    context["profil_duzenle"] = profil_duzenle
    context["profil_eksik"] = profil_eksik_mi(talebe)
    context["profil_eksik_alanlar"] = profil_eksik_alanlar(talebe)
    context["il_ilce_json"] = il_ilce_haritasi()
    if profil_duzenle:
        pf = profil_form or TalebeProfilTamamlaForm(instance=talebe)
        context["profil_form"] = pf
        context["profil_form_bolumleri"] = [
            (
                "Fotoğraf ve ad",
                [pf[n] for n in ("biyometrik_foto", "ad_soyad", "kimlik_adi", "kimlik_soyadi")],
            ),
            (
                "Kimlik bilgileri",
                [
                    pf[n]
                    for n in (
                        "tc_kimlik",
                        "cinsiyet",
                        "dogum_tarihi",
                        "sinif_sube",
                        "dini_ders_seviyesi",
                    )
                ],
            ),
            (
                "Diğer bilgiler",
                [
                    pf[n]
                    for n in (
                        "baba_adi",
                        "anne_adi",
                        "dogum_yeri",
                        "memleket",
                        "memleket_ilce",
                        "telefon",
                        "eposta",
                    )
                ],
            ),
            (
                "Aile ve veli",
                [
                    pf[n]
                    for n in (
                        "aile_durumu",
                        "anne_ad_soyad",
                        "anne_telefon",
                        "baba_ad_soyad",
                        "baba_telefon",
                        "ev_adresi",
                    )
                ],
            ),
        ]

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
    from takip.panel_permissions import yonetim_erisimi_var

    context["yonetim_erisim"] = yonetim_erisimi_var(request.user)

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

    deneme_erisim = can(user, "deneme", "view")
    deneme_sonuclari = (
        list(talebe_deneme_sonuclari(talebe)[:15]) if deneme_erisim else []
    )
    deneme_performans = (
        talebe_deneme_performans_ozeti(talebe) if deneme_erisim else None
    )
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
        "deneme_performans": deneme_performans,
        "deneme_erisim": deneme_erisim,
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


def _kitap_silebilir(user, kitap) -> bool:
    if not (
        user.is_superuser
        or can(user, "egitim_kitap", "create")
        or can(user, "egitim_kitap", "delete")
    ):
        return False
    if user.is_superuser or can(user, "egitim_kitap", "delete"):
        return True
    return kitap.olusturan_id in {None, user.id}


@login_required
def kitap_listesi(request):
    kitaplar = list(
        Kitap.objects.annotate(zimmet_sayisi=Count("zimmetler")).order_by("ad")
    )

    toplam_zimmet = 0
    for kitap in kitaplar:
        toplam_zimmet += kitap.zimmet_sayisi
        kitap.silebilir = _kitap_silebilir(request.user, kitap)

    aktif_okuma = (
        Zimmet.objects
        .filter(durum="okunuyor")
        .count()
    )

    context = {
        "kitaplar": kitaplar,
        "toplam_zimmet": toplam_zimmet,
        "aktif_okuma": aktif_okuma,
    }
    template_name = (
        "partials/kitap_listesi_content.html"
        if getattr(request, "htmx", False)
        else "kitap_listesi.html"
    )
    return render(request, template_name, context)


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
        kitap = form.save(commit=False)
        if _alan_var_mi(Kitap, "olusturan"):
            kitap.olusturan = request.user
        kitap.save()

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


@login_required
@require_permission("egitim_kitap", "view")
def kitap_sil(request, pk):
    kitap = get_object_or_404(Kitap, pk=pk)
    kitap.zimmet_sayisi = kitap.zimmetler.count()
    if not _kitap_silebilir(request.user, kitap):
        messages.error(request, "Bu kitabı silme yetkiniz yok veya kitap kullanımda.")
        return redirect("kitap_listesi")

    if request.method != "POST":
        return redirect("kitap_listesi")

    ad = kitap.ad
    try:
        with transaction.atomic():
            Sinav.objects.filter(kitap=kitap).delete()
            kitap.zimmetler.all().delete()
            kitap.delete()
    except ProtectedError:
        messages.error(
            request,
            f"{ad} silinemedi: bağlı kayıtlar korumalı.",
        )
        return redirect("kitap_listesi")

    messages.success(request, f"{ad} arşivden silindi.")
    return redirect("kitap_listesi")


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

        kitap = None
        if kitap_id and not hatalar:
            kitap = Kitap.objects.filter(id=kitap_id, aktif=True).first()
            if not kitap:
                hatalar.append("Seçilen kitap bulunamadı.")

        kitap_sayfa_sayisi = None
        if kitap_sayfa_sayisi_raw:
            try:
                kitap_sayfa_sayisi = int(kitap_sayfa_sayisi_raw)
                if kitap_sayfa_sayisi < 1:
                    raise ValueError
            except (TypeError, ValueError):
                hatalar.append("Geçerli bir kitap sayfa sayısı girin.")
        elif kitap:
            kitap_sayfa_sayisi = kitap.toplam_sayfa
            if kitap_sayfa_sayisi < 1:
                hatalar.append(
                    "Seçilen kitabın sayfa sayısı tanımlı değil. "
                    "Kitap arşivinden düzenleyin."
                )

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
            from takip.messages_util import hatalari_ozetle

            hatalari_ozetle(request, hatalar)
        else:
            if kitap is None or kitap_sayfa_sayisi is None:
                messages.error(request, "Zimmet oluşturulamadı.")
                return render(
                    request,
                    "toplu_zimmet.html",
                    {"talebeler": talebeler, "kitaplar": kitaplar},
                )

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

        if hatalar:
            from takip.messages_util import hatalari_ozetle

            hatalari_ozetle(request, hatalar, tek_baslik="Okuma kaydı hatalı")
        else:
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
    if sinif_ids:
        siniflar = list(SinifSube.objects.filter(id__in=sinif_ids).order_by("sinif", "sube"))
        if siniflar:
            sinif_adi = ", ".join(str(s) for s in siniflar)

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
            from takip.messages_util import hatalari_ozetle

            hatalari_ozetle(
                request,
                hatalar,
                tek_baslik=f"Doğru+yanlış+boş toplamı {toplam_soru} olmalı",
            )

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
    from takip.program_service import program_sure_ozeti

    satirlar = list(program.satirlar.all())
    toplam_dakika = sum(satir.sure_dakika for satir in satirlar)
    sure_ozet = program_sure_ozeti(program, donem="gun")
    pdf_sayfa = coz_pdf_sayfa(request)

    html_metni = render_to_string(
        "program_plan_pdf.html",
        {
            "program": program,
            "satirlar": satirlar,
            "toplam_dakika": toplam_dakika,
            "sure_ozet": sure_ozet,
            "pdf_sayfa": pdf_sayfa,
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
    return make_pdf_response(
        pdf_verisi,
        f"{dosya_adi}-program-{pdf_sayfa['kod']}.pdf",
    )


@login_required
def program_panel(request):
    if not _program_erisim_kontrol(request):
        return redirect("dashboard")

    from takip.program_service import program_tum_donem_ozetleri

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
    sure_donemler = (
        program_tum_donem_ozetleri(secili_program, referans=bugun)
        if secili_program
        else None
    )

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
            "sure_donemler": sure_donemler,
            "pdf_sayfa": coz_pdf_sayfa(request) if secili_program else None,
            "yonetim_modulu": yonetim_erisimi_var(request.user),
        },
    )


@login_required
def program_detay(request, pk):
    if not _program_erisim_kontrol(request):
        return redirect("dashboard")

    from takip.program_service import program_tum_donem_ozetleri

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
            "sure_donemler": program_tum_donem_ozetleri(program),
            "pdf_sayfa": coz_pdf_sayfa(request),
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


@login_required
def program_excel(request, pk):
    if not _program_erisim_kontrol(request):
        return redirect("dashboard")

    from takip.excel_rapor import excel_http_yanit
    from takip.program_service import program_excel_icerik

    program = get_object_or_404(
        ProgramPlan.objects.prefetch_related("satirlar"),
        pk=pk,
    )
    dosya, icerik = program_excel_icerik(program)
    return excel_http_yanit(icerik, dosya)


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
    kat_kartlari = list(merkez["kat_kartlari"])
    yonetim_modu = yonetim_erisimi_var(request.user) or request.user.is_superuser
    if not yonetim_modu:
        kat_ids = {s.kat_id for s in kullanici_kat_sorumluluklari(request.user)}
        if kat_ids:
            kat_kartlari = [k for k in kat_kartlari if k["kat"].pk in kat_ids]
    fmt = (request.GET.get("format") or "a4").lower()
    yon = (request.GET.get("orientation") or "portrait").lower()
    if fmt not in ("a4", "a3"):
        fmt = "a4"
    if yon not in ("portrait", "landscape"):
        yon = "portrait"

    # Ortak sayfa tercihi (sayfa=a4_portrait …) varsa onu kullan
    from .pdf_utils import coz_pdf_sayfa

    pdf_sayfa = coz_pdf_sayfa(request)
    if request.GET.get("sayfa") or request.GET.get("pdf_sayfa"):
        kod = pdf_sayfa["kod"]
        fmt, yon = kod.split("_", 1)

    html_metni = render_to_string(
        "temizlik_pdf.html",
        {
            "liste": liste,
            "kat_kartlari": kat_kartlari,
            "stats": merkez["stats"],
            **panel_branding_context(),
            "pdf_format": fmt,
            "pdf_orientation": yon,
            "yazdirma_tarihi": localdate(),
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

    from .temizlik_service import aktif_temizlik_listesi

    kat_sorumluluklari = kullanici_kat_sorumluluklari(request.user)
    yonetim_modu = yonetim_erisimi_var(request.user) or request.user.is_superuser
    kat_ids = {s.kat_id for s in kat_sorumluluklari}

    secili_liste = aktif_temizlik_listesi()
    if yonetim_modu:
        secili_id = request.GET.get("liste", "").strip()
        if secili_id.isdigit():
            secili_liste = (
                TemizlikListesi.objects.filter(pk=int(secili_id), aktif=True).first()
                or secili_liste
            )

    kat_kartlari = sabit_temizlik_katlari(request.user, secili_liste) if secili_liste else []
    mahal_sayisi = sum(len(k["mahaller"]) for k in kat_kartlari)

    return render(
        request,
        "temizlik_panel.html",
        {
            "kat_sorumluluklari": kat_sorumluluklari,
            "kat_kartlari": kat_kartlari,
            "mahal_sayisi": mahal_sayisi,
            "secili_liste": secili_liste,
            "yonetim_modulu": yonetim_modu,
            "sadece_kat_gorunumu": (not yonetim_modu) and bool(kat_ids),
            "kat_zimmeti_yok": (not yonetim_modu) and not kat_ids and not kat_kartlari,
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
# YEMEKÇİLİK — sınıf döngüsü (yemekci_views)
# =========================================================

yemekcilik_panel = yemekci_views.yemekcilik_panel
yemekcilik_pdf = yemekci_views.yemekcilik_pdf


def yemekcilik_pdf_yanit(request, liste):
    return redirect("yemekcilik_panel")


def _yemekcilik_erisim_kontrol(request):
    return yemekci_views._erisim(request)
