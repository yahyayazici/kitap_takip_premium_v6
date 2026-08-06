from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from django.http import HttpResponse
from django.utils.text import slugify
from django.template.loader import render_to_string
try:
    from weasyprint import HTML
except (ImportError, OSError):
    HTML = None
from datetime import date
from typing import Any
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, Max, Q
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate

from .models import (
    EtutHocasi,
    Kitap,
    OkumaKaydi,
    Sinav,
    SinavSonucu,
    SinifSube,
    Talebe,
    Zimmet,
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
    talebeler = Talebe.objects.all()

    if _alan_var_mi(Talebe, "aktif"):
        talebeler = talebeler.filter(
            aktif=True
        )

    if user.is_superuser:
        return talebeler

    hoca = _etut_hocasi(user)

    if not hoca:
        return Talebe.objects.none()

    if _alan_var_mi(Talebe, "etut_hocasi"):
        return talebeler.filter(
            etut_hocasi=hoca
        )

    return Talebe.objects.none()


def _yetkili_zimmetler(user):
    zimmetler = Zimmet.objects.all()

    if user.is_superuser:
        return zimmetler

    hoca = _etut_hocasi(user)

    if not hoca:
        return Zimmet.objects.none()

    if _alan_var_mi(Zimmet, "etut_hocasi"):
        return zimmetler.filter(
            etut_hocasi=hoca
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

    if user.is_superuser:
        return sinavlar

    hoca = _etut_hocasi(user)

    if not hoca:
        return Sinav.objects.none()

    if _alan_var_mi(Sinav, "etut_hocasi"):
        return sinavlar.filter(
            etut_hocasi=hoca
        )

    return sinavlar


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
        return redirect("dashboard")

    return redirect("login")


# =========================================================
# GENEL BAKIŞ
# =========================================================


@login_required
def dashboard(request):
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
            "bugunku_kayit": bugunku_kayit_sayisi,
            "bekleyen": bekleyen,
            "bugun_toplam": bugun_toplam,
            "toplam_okunan": bugun_toplam,
            "son_kayitlar": son_kayitlar,
            "siniflar": siniflar,
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

    return render(
        request,
        "talebe_listesi.html",
        {
            "talebeler": talebeler,
            "talebe_sayisi": len(talebeler),
            "sinif_id": sinif_id,
        },
    )


@login_required
def talebe_detay(
    request,
    talebe_id: int,
):
    talebe = get_object_or_404(
        _yetkili_talebeler(
            request.user
        ),
        id=talebe_id,
    )

    zimmetler = list(
        _yetkili_zimmetler(
            request.user
        )
        .filter(talebe=talebe)
        .select_related("kitap")
        .order_by("-id")
    )

    for zimmet in zimmetler:
        zimmet.okunan_toplam = (
            _zimmet_okuma_toplami(
                zimmet
            )
        )

    kayitlar = list(
        OkumaKaydi.objects
        .filter(
            zimmet__in=zimmetler
        )
        .select_related(
            "zimmet",
            "zimmet__kitap",
        )
        .order_by(
            "-tarih",
            "-id",
        )
    )

    for kayit in kayitlar:
        kayit.okunan_miktar = (
            _okunan_sayfa_hesapla(
                kayit
            )
        )

    sinav_sonuclari = (
        SinavSonucu.objects
        .filter(talebe=talebe)
        .select_related("sinav")
        .order_by("-id")
    )

    toplam_okunan = sum(
        kayit.okunan_miktar
        for kayit in kayitlar
    )

    return render(
        request,
        "talebe_detay.html",
        {
            "talebe": talebe,
            "zimmetler": zimmetler,
            "kayitlar": kayitlar,
            "sinav_sonuclari": sinav_sonuclari,
            "toplam_okunan": toplam_okunan,
        },
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

    for kitap in kitaplar:
        kitap.zimmet_sayisi = (
            Zimmet.objects
            .filter(kitap=kitap)
            .count()
        )

    return render(
        request,
        "kitap_listesi.html",
        {
            "kitaplar": kitaplar,
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
            "aciklama": (
                "Kitabın temel bilgilerini girin."
            ),
            "buton_metni": "Kitabı Kaydet",
        },
    )


# =========================================================
# TOPLU KİTAP ZİMMETLEME
# =========================================================


@login_required
def toplu_zimmet(request):
    talebeler = list(
        _yetkili_talebeler(request.user)
        .select_related("sinif_sube", "etut_hocasi")
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
    zimmet_qs = _yetkili_zimmetler(request.user).select_related(
        "talebe", "talebe__sinif_sube", "kitap", "etut_hocasi"
    )
    baslangic = request.GET.get("baslangic", "").strip()
    bitis = request.GET.get("bitis", "").strip()
    sinif_id = request.GET.get("sinif", "").strip()
    durum = request.GET.get("durum", "tum").strip()

    if sinif_id.isdigit():
        zimmet_qs = zimmet_qs.filter(talebe__sinif_sube_id=int(sinif_id))
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
        "filtre": {"baslangic": baslangic, "bitis": bitis, "sinif": sinif_id, "durum": durum},
    })


@login_required
def okuma_raporu_pdf(request):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    zimmet_qs = _yetkili_zimmetler(request.user).select_related(
        "talebe", "talebe__sinif_sube", "kitap", "etut_hocasi"
    )
    baslangic = request.GET.get("baslangic", "").strip()
    bitis = request.GET.get("bitis", "").strip()
    sinif_id = request.GET.get("sinif", "").strip()
    durum = request.GET.get("durum", "tum").strip()
    if sinif_id.isdigit():
        zimmet_qs = zimmet_qs.filter(talebe__sinif_sube_id=int(sinif_id))
    if durum == "aktif": zimmet_qs = zimmet_qs.filter(durum="okunuyor")
    elif durum == "gecmis": zimmet_qs = zimmet_qs.exclude(durum="okunuyor")
    zimmetler = list(zimmet_qs.order_by("talebe__ad_soyad", "-zimmet_tarihi"))

    kayit_qs = OkumaKaydi.objects.filter(zimmet__in=zimmetler)
    if baslangic: kayit_qs = kayit_qs.filter(tarih__gte=baslangic)
    if bitis: kayit_qs = kayit_qs.filter(tarih__lte=bitis)
    totals = {}
    for k in kayit_qs:
        totals[k.zimmet_id] = totals.get(k.zimmet_id, 0) + _okunan_sayfa_hesapla(k)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=24, leftMargin=24, topMargin=22, bottomMargin=22)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleX", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=19, textColor=colors.HexColor("#0b2a57"), alignment=TA_LEFT, spaceAfter=4)
    small = ParagraphStyle("SmallX", parent=styles["BodyText"], fontSize=8.5, textColor=colors.HexColor("#5f6f85"))
    story = [Paragraph("ÇİNİLİ SARAY PROJE — KİTAP OKUMA RAPORU", title)]
    kapsam = "Kurum Geneli" if request.user.is_superuser else "Etüt Grubu"
    tarih = f"{baslangic or 'Tüm tarihler'} — {bitis or 'Bugün'}"
    story += [Paragraph(f"Kapsam: {kapsam} &nbsp;&nbsp; | &nbsp;&nbsp; Tarih: {tarih} &nbsp;&nbsp; | &nbsp;&nbsp; Kayıt: {len(zimmetler)}", small), Spacer(1, 12)]
    data = [["Talebe", "No", "Sınıf", "Kitap", "Etüt Hocası", "Durum", "Okunan", "Toplam"]]
    for z in zimmetler[:22]:
        data.append([z.talebe.ad_soyad, z.talebe.talebe_no or "—", str(z.talebe.sinif_sube or "—"), z.kitap.ad, z.etut_hocasi.ad_soyad, z.get_durum_display(), str(totals.get(z.id,0)), str(z.kitap.toplam_sayfa)])
    table=Table(data, colWidths=[115,52,50,150,105,75,55,55], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0b2a57")), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTNAME",(0,1),(-1,-1),"Helvetica"),
        ("FONTSIZE",(0,0),(-1,-1),8), ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#dce5f0")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f5f8fc")]),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"), ("TOPPADDING",(0,0),(-1,-1),6), ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    story.append(table)
    if len(zimmetler)>22:
        story += [Spacer(1,7), Paragraph(f"Not: Tek sayfa düzeni için ilk 22 kayıt gösterilmiştir. Toplam kayıt: {len(zimmetler)}", small)]
    doc.build(story)
    response=HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"]='attachment; filename="kitap-okuma-raporu.pdf"'
    return response


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
    if HTML is None:
        messages.error(request, "PDF bileşeni bu bilgisayarda hazır değil. Siteyi kullanmaya devam edebilirsiniz.")
        return redirect("raporlar")
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

    try:
        pdf_verisi = HTML(
            string=html_metni,
            base_url=request.build_absolute_uri("/"),
        ).write_pdf()
    except Exception as hata:
        return HttpResponse(
            f"PDF oluşturulamadı: {hata}",
            status=500,
            content_type="text/plain; charset=utf-8",
        )

    talebe_adi = slugify(talebe.ad_soyad) or f"talebe-{talebe.id}"
    sinav_adi = slugify(sinav.ad) or f"sinav-{sinav.id}"

    response = HttpResponse(
        pdf_verisi,
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{talebe_adi}-{sinav_adi}-karne.pdf"'
    )

    return response


@login_required
def sinav_sirali_sonuc_pdf(request, sinav_id):
    if HTML is None:
        messages.error(request, "PDF bileşeni bu bilgisayarda hazır değil. Siteyi kullanmaya devam edebilirsiniz.")
        return redirect("raporlar")
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

    try:
        pdf_verisi = HTML(
            string=html_metni,
            base_url=request.build_absolute_uri("/"),
        ).write_pdf()
    except Exception as hata:
        return HttpResponse(
            f"Sıralı sonuç PDF'i oluşturulamadı: {hata}",
            status=500,
            content_type="text/plain; charset=utf-8",
        )

    sinav_adi = slugify(sinav.ad) or f"sinav-{sinav.id}"
    grup_dosya_adi = slugify(grup_adi) or "grup"

    response = HttpResponse(
        pdf_verisi,
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="'
        f'{grup_dosya_adi}-{sinav_adi}-sirali-sonuclar.pdf"'
    )

    return response