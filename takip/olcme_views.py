"""Ölçme ve Değerlendirme Merkezi — panel görünümleri (Aşama 1)."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from django.template.loader import render_to_string

from takip.excel_rapor import excel_http_yanit
from takip.olcme_excel import sinav_analiz_xlsx, sinav_sonuc_csv
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_error_response
from takip.konu_destek_models import KonuKatalogu
from takip.konu_destek_service import ders_adindan_brans, konu_getir_veya_olustur
from takip.ktt_konu_normalize_service import ktt_konu_eslestir
from takip.ktt_service import (
    hedef_siniflar_kaydet,
    ktt_duzenleyebilir,
    ktt_olusturabilir,
    ktt_sinif_secenekleri,
    ktt_sinif_secimlerini_dogrula,
    ktt_sonuc_talebeleri,
    ktt_tam_yetki,
)
from takip.forms import KttSinavForm
from takip.models import Ders, KttSinav, KttSonucu
from takip.olcme_models import OlcumKazanim, OlcumSinavSablon, OlcumSoru, OlcumUnite
from takip.olcme_service import (
    anahtar_satir_isle,
    ders_bloklari_kaydet,
    kazanim_ara,
    konu_ara,
    konu_havuzu_listesi,
    mevcut_ktt_backfill,
    optik_satirlar_parcala,
    sablondan_sinav_kopyala,
    sablondan_sinav_olustur,
    satir_cevap_parcala,
    sinav_dogrulama,
    sinav_durum_guncelle,
    sinav_kazanim_analizi,
    sinav_konu_analizi,
    sinav_sablon_kaydet,
    sinav_sonuc_ozet,
    soru_zimmet_guncelle,
    sorulari_ders_bloklarina_dagit,
    sorulari_olustur,
    talebe_cevaplari_kaydet,
    toplu_optik_kaydet,
    toplu_zimmet_guncelle,
    yetkili_olcme_sinavlari,
    zimmet_ozet,
    yayinlanabilir_mi,
    zayif_konulari_etut_planina_aktar,
    olcme_silebilir,
)
from takip.olcme_qr import optik_form_satirlari, optik_karekod_parse, varsayilan_kitapcik
from takip.permissions.decorators import require_permission
from takip.permissions.service import can as perm_can
from takip.user_helpers import etut_hocasi_for_user


def _optik_foto_base_url(request, sinav_pk: int) -> str:
    return request.build_absolute_uri(reverse("olcme_optik_foto", kwargs={"pk": sinav_pk}))


OLCME_BOLUMLER = (
    {"key": "genel", "label": "Genel Bakış", "url": "olcme_hub", "ready": True},
    {"key": "sinavlar", "label": "Sınavlar", "url": "olcme_sinav_listesi", "ready": True},
    {"key": "yeni", "label": "Yeni Sınav Oluştur", "url": "olcme_sinav_wizard_yeni", "ready": True},
    {"key": "sonuc", "label": "Sonuç Girişi", "url": "olcme_sinav_listesi", "ready": True},
    {"key": "zimmet", "label": "Soru Zimmetleme", "url": "olcme_sinav_listesi", "ready": True},
    {"key": "konu_analiz", "label": "Konu ve Kazanım Analizi", "url": "olcme_konu_analiz_sec", "ready": True},
    {"key": "talebe_analiz", "label": "Talebe Analizleri", "url": "ktt_akilli_ozet", "ready": True},
    {"key": "sinif_analiz", "label": "Sınıf ve Grup Analizleri", "url": "ktt_rapor", "ready": True},
    {"key": "sablon", "label": "Sınav Şablonları", "url": "olcme_sablon_listesi", "ready": True},
    {"key": "konu_havuzu", "label": "Konu Havuzu", "url": "olcme_konu_havuzu", "ready": True},
    {"key": "raporlar", "label": "Raporlar", "url": "olcme_rapor_sec", "ready": True},
)


def _sinav_or_404(request, pk: int) -> KttSinav:
    return get_object_or_404(yetkili_olcme_sinavlari(request.user), pk=pk)


def _wizard_form(user, data=None, instance=None):
    admin_modu = ktt_tam_yetki(user)
    form = KttSinavForm(data, instance=instance, admin_modu=admin_modu)
    form.fields["ders"].queryset = Ders.objects.filter(aktif=True).order_by("sira", "ad")
    if not admin_modu:
        form.fields.pop("veliye_goster", None)
    if admin_modu and "etut_hocasi" in form.fields:
        from takip.models import EtutHocasi

        form.fields["etut_hocasi"].queryset = EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad")
    return form


def _hedef_sinif_etiketleri(sinav: KttSinav | None) -> list[str]:
    if not sinav or not sinav.hedef_siniflar:
        return []
    return [s.strip() for s in sinav.hedef_siniflar.split(",") if s.strip()]


def _wizard_context_extras(sinav: KttSinav | None, request) -> dict:
    return {
        "secili_sinif_etiketleri": _hedef_sinif_etiketleri(sinav),
        "secili_sablon_id": request.GET.get("sablon", ""),
    }


@login_required
@require_permission("olcme", "view")
def olcme_hub(request):
    sinavlar_qs = yetkili_olcme_sinavlari(request.user)
    sinavlar = sinavlar_qs.order_by("-sinav_tarihi")[:8]
    return render(
        request,
        "olcme/hub.html",
        {
            "bolumler": OLCME_BOLUMLER,
            "son_sinavlar": sinavlar,
            "taslak_sayisi": sinavlar_qs.filter(
                durum__in=[KttSinav.SinavDurum.TASLAK, KttSinav.SinavDurum.ZIMMETLEME]
            ).count(),
            "hazir_sayisi": sinavlar_qs.filter(durum=KttSinav.SinavDurum.HAZIR).count(),
            "sonuclandi_sayisi": sinavlar_qs.filter(
                durum__in=[KttSinav.SinavDurum.SONUCLANDI, KttSinav.SinavDurum.YAYINLANDI]
            ).count(),
            "toplam_sayisi": sinavlar_qs.count(),
        },
    )


@login_required
@require_permission("olcme", "view")
def olcme_sinav_listesi(request):
    tur = request.GET.get("tur", "")
    qs = yetkili_olcme_sinavlari(request.user).order_by("-sinav_tarihi", "-id")
    if tur:
        qs = qs.filter(sinav_turu=tur)
    sinavlar = list(qs[:100])
    return render(
        request,
        "olcme/sinav_listesi.html",
        {
            "sinavlar": sinavlar,
            "tur": tur,
            "tur_secenekleri": KttSinav.SinavTuru.choices,
            "silinebilir_ids": {s.pk for s in sinavlar if olcme_silebilir(request.user, s)},
        },
    )


@login_required
@require_permission("olcme", "create")
def olcme_sinav_wizard_yeni(request):
    return _olcme_sinav_wizard_core(request, pk=None)


@login_required
@require_permission("olcme", "create")
def olcme_sinav_wizard(request, pk):
    return _olcme_sinav_wizard_core(request, pk=pk)


def _olcme_sinav_wizard_core(request, pk: int | None):
    sinav = _sinav_or_404(request, pk) if pk else None
    step = int(request.GET.get("step") or request.POST.get("step") or 1)
    step = max(1, min(step, 6))

    if request.method == "POST" and step == 1 and not sinav:
        sablon_id = request.POST.get("sablon_id")
        if sablon_id:
            sablon = get_object_or_404(OlcumSinavSablon, pk=int(sablon_id))
            form = _wizard_form(request.user, request.POST)
            sinif_etiketleri, sinif_hata = ktt_sinif_secimlerini_dogrula(
                request.user,
                request.POST.getlist("sinif_subeler"),
            )
            if sinif_hata:
                messages.error(request, sinif_hata)
            elif not form.is_valid():
                pass
            elif form.is_valid():
                hoca = etut_hocasi_for_user(request.user)
                sinav = sablondan_sinav_olustur(
                    sablon,
                    ad=form.cleaned_data["ad"],
                    sinav_tarihi=form.cleaned_data["sinav_tarihi"],
                    ders=form.cleaned_data["ders"],
                    sinif_etiketleri=sinif_etiketleri,
                    kullanici=request.user,
                    etut_hocasi=hoca,
                )
                ktt_konu_eslestir(sinav, kullanici=request.user)
                messages.success(request, f"Şablondan sınav oluşturuldu: {sinav.ad}")
                return redirect(f"{reverse('olcme_sinav_wizard', kwargs={'pk': sinav.pk})}?step=5")
            if sinif_hata or not form.is_valid():
                return render(
                    request,
                    "olcme/sinav_wizard.html",
                    {
                        "step": 1,
                        "form": form,
                        "sinav": None,
                        "sinif_secenekleri": ktt_sinif_secenekleri(request.user),
                        "tur_secenekleri": KttSinav.SinavTuru.choices,
                        "sablonlar": OlcumSinavSablon.objects.order_by("-olusturulma")[:30],
                        "secili_sablon_id": sablon_id,
                        **_wizard_context_extras(None, request),
                    },
                )

        form = _wizard_form(request.user, request.POST)
        sinif_etiketleri, sinif_hata = ktt_sinif_secimlerini_dogrula(
            request.user,
            request.POST.getlist("sinif_subeler"),
        )
        if sinif_hata:
            messages.error(request, sinif_hata)
        elif form.is_valid():
            hoca = etut_hocasi_for_user(request.user)
            sinav = form.save(commit=False)
            sinav.sinav_turu = request.POST.get("sinav_turu") or KttSinav.SinavTuru.KTT
            sinav.durum = KttSinav.SinavDurum.TASLAK
            if hoca:
                sinav.etut_hocasi = hoca
            sinav.olusturan = request.user
            if sinif_etiketleri:
                hedef_siniflar_kaydet(sinav, sinif_etiketleri)
            sinav.save()
            ktt_konu_eslestir(sinav, kullanici=request.user)
            sorulari_olustur(sinav, varsayilan_ders=sinav.ders)
            sinav_durum_guncelle(sinav, KttSinav.SinavDurum.ZIMMETLEME, request.user)
            return redirect(f"{reverse('olcme_sinav_wizard', kwargs={'pk': sinav.pk})}?step=2")
        else:
            return render(
                request,
                "olcme/sinav_wizard.html",
                {
                    "step": 1,
                    "form": form,
                    "sinav": None,
                    "sinif_secenekleri": ktt_sinif_secenekleri(request.user),
                    "tur_secenekleri": KttSinav.SinavTuru.choices,
                    "sablonlar": OlcumSinavSablon.objects.order_by("-olusturulma")[:30],
                    **_wizard_context_extras(None, request),
                },
            )

    if not sinav:
        return render(
            request,
            "olcme/sinav_wizard.html",
            {
                "step": 1,
                "form": _wizard_form(request.user),
                "sinav": None,
                "sinif_secenekleri": ktt_sinif_secenekleri(request.user),
                "tur_secenekleri": KttSinav.SinavTuru.choices,
                "sablonlar": OlcumSinavSablon.objects.order_by("-olusturulma")[:30],
                **_wizard_context_extras(None, request),
            },
        )

    if request.method == "POST" and step == 1:
        form = _wizard_form(request.user, request.POST, instance=sinav)
        sinif_etiketleri, sinif_hata = ktt_sinif_secimlerini_dogrula(
            request.user,
            request.POST.getlist("sinif_subeler"),
        )
        if sinif_hata:
            messages.error(request, sinif_hata)
        elif form.is_valid():
            sinav = form.save(commit=False)
            sinav.sinav_turu = request.POST.get("sinav_turu") or sinav.sinav_turu
            if hoca := etut_hocasi_for_user(request.user):
                if not sinav.etut_hocasi_id:
                    sinav.etut_hocasi = hoca
            sinav.save()
            if sinif_etiketleri:
                hedef_siniflar_kaydet(sinav, sinif_etiketleri)
            messages.success(request, "Sınav bilgileri güncellendi.")
            return redirect(f"{reverse('olcme_sinav_wizard', kwargs={'pk': sinav.pk})}?step=2")
        elif not sinif_hata:
            return render(
                request,
                "olcme/sinav_wizard.html",
                {
                    "step": 1,
                    "form": form,
                    "sinav": sinav,
                    "sinif_secenekleri": ktt_sinif_secenekleri(request.user),
                    "tur_secenekleri": KttSinav.SinavTuru.choices,
                    "sablonlar": OlcumSinavSablon.objects.order_by("-olusturulma")[:30],
                    **_wizard_context_extras(sinav, request),
                },
            )

    if request.method == "POST":
        if step == 2:
            try:
                soru_sayisi = int(request.POST.get("soru_sayisi") or sinav.soru_sayisi)
                sinav.soru_sayisi = soru_sayisi
                sinav.secenek_sayisi = int(request.POST.get("secenek_sayisi") or 4)
                sinav.yanlis_goturme_orani = int(request.POST.get("yanlis_goturme_orani") or 4)
                sinav.kitapcik_turleri = request.POST.get("kitapcik_turleri") or "A"
                sinav.kazanim_zorunlu = request.POST.get("kazanim_zorunlu") == "on"
                sinav.save()
                sorulari_olustur(sinav, varsayilan_ders=sinav.ders)
                messages.success(request, f"{soru_sayisi} soru oluşturuldu.")
            except (TypeError, ValueError) as exc:
                messages.error(request, str(exc))
            return redirect(f"{reverse('olcme_sinav_wizard', kwargs={'pk': sinav.pk})}?step=3")

        if step == 3:
            bloklar = []
            ders_ids = request.POST.getlist("ders_id")
            for i, ders_id in enumerate(ders_ids):
                if not ders_id:
                    continue
                bloklar.append(
                    {
                        "ders_id": int(ders_id),
                        "bolum": request.POST.getlist("bolum")[i] if i < len(request.POST.getlist("bolum")) else "genel",
                        "soru_sayisi": request.POST.getlist("soru_sayisi_blok")[i],
                        "katsayi": request.POST.getlist("katsayi")[i] or 1,
                        "sira": i + 1,
                    }
                )
            try:
                if bloklar:
                    ders_bloklari_kaydet(sinav, bloklar)
                    sorulari_ders_bloklarina_dagit(sinav)
                messages.success(request, "Ders yapısı kaydedildi.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(f"{reverse('olcme_sinav_wizard', kwargs={'pk': sinav.pk})}?step=4")

        if step == 4:
            kitapcik = request.POST.get("kitapcik") or "A"
            satir = request.POST.get("anahtar_satir", "")
            adet = anahtar_satir_isle(sinav, kitapcik, satir)
            messages.success(request, f"{adet} sorunun cevap anahtarı güncellendi.")
            return redirect(f"{reverse('olcme_sinav_wizard', kwargs={'pk': sinav.pk})}?step=5")

        if step == 5:
            return redirect("olcme_sinav_zimmet", pk=sinav.pk)

        if step == 6:
            hatalar = sinav_dogrulama(sinav)
            if hatalar:
                for h in hatalar:
                    messages.warning(request, h["mesaj"])
                return redirect(f"{reverse('olcme_sinav_wizard', kwargs={'pk': sinav.pk})}?step=6")
            sinav_durum_guncelle(sinav, KttSinav.SinavDurum.HAZIR, request.user)
            messages.success(request, "Sınav hazır durumuna alındı.")
            return redirect("olcme_sinav_detay", pk=sinav.pk)

    context = {
        "step": step,
        "sinav": sinav,
        "ozet": zimmet_ozet(sinav) if sinav else None,
        "hatalar": sinav_dogrulama(sinav) if sinav and step == 6 else [],
        "dersler": Ders.objects.filter(aktif=True).order_by("sira", "ad"),
        "olcme_dersleri": sinav.olcme_dersleri.select_related("ders") if sinav else [],
        "sinif_secenekleri": ktt_sinif_secenekleri(request.user),
        "tur_secenekleri": KttSinav.SinavTuru.choices,
        "sablonlar": OlcumSinavSablon.objects.order_by("-olusturulma")[:30],
        **_wizard_context_extras(sinav, request),
    }
    if step == 1 and sinav:
        context["form"] = _wizard_form(request.user, instance=sinav)
    return render(request, "olcme/sinav_wizard.html", context)


@login_required
@require_permission("olcme", "view")
def olcme_sinav_detay(request, pk):
    sinav = _sinav_or_404(request, pk)
    mevcut_ktt_backfill(sinav)
    from takip.permissions.service import can as perm_can

    return render(
        request,
        "olcme/sinav_detay.html",
        {
            "sinav": sinav,
            "ozet": zimmet_ozet(sinav),
            "hatalar": sinav_dogrulama(sinav),
            "duzenleyebilir": ktt_duzenleyebilir(request.user, sinav),
            "sablon_kaydedebilir": perm_can(request.user, "olcme", "manage_sablon"),
            "sablonlar": OlcumSinavSablon.objects.order_by("-olusturulma")[:20],
            "sonuc_ozet": sinav_sonuc_ozet(sinav, ktt_sonuc_talebeleri(request.user, sinav)),
            "sonuc_tamam": KttSonucu.objects.filter(ktt=sinav).count(),
            "yayinlayabilir": perm_can(request.user, "olcme", "yayinla"),
            "veli_yonetebilir": perm_can(request.user, "olcme", "yayinla"),
            "silebilir": olcme_silebilir(request.user, sinav),
        },
    )


@login_required
@require_permission("olcme", "edit")
@require_POST
def olcme_sinav_sil(request, pk):
    sinav = _sinav_or_404(request, pk)
    if not olcme_silebilir(request.user, sinav):
        messages.error(request, "Bu sınavı silme yetkiniz yok.")
        return redirect("olcme_sinav_detay", pk=pk)

    ad = sinav.ad
    sinav.delete()
    messages.success(request, f"{ad} silindi.")
    return redirect("olcme_sinav_listesi")


@login_required
@require_permission("olcme", "yayinla")
@require_POST
def olcme_sinav_durum(request, pk):
    sinav = _sinav_or_404(request, pk)
    if not ktt_duzenleyebilir(request.user, sinav):
        messages.error(request, "Bu sınavın durumunu değiştiremezsiniz.")
        return redirect("olcme_sinav_detay", pk=pk)
    yeni = request.POST.get("durum")
    izinli = {
        KttSinav.SinavDurum.UYGULANDI,
        KttSinav.SinavDurum.SONUCLANDI,
        KttSinav.SinavDurum.YAYINLANDI,
    }
    if yeni not in izinli:
        messages.error(request, "Geçersiz durum.")
        return redirect("olcme_sinav_detay", pk=pk)
    if yeni == KttSinav.SinavDurum.YAYINLANDI:
        ok, mesajlar = yayinlanabilir_mi(sinav)
        if not ok:
            for mesaj in mesajlar:
                messages.error(request, mesaj)
            return redirect("olcme_sinav_detay", pk=pk)
        for mesaj in mesajlar:
            messages.warning(request, mesaj)
    sinav_durum_guncelle(sinav, yeni, request.user)
    if yeni == KttSinav.SinavDurum.YAYINLANDI:
        messages.success(request, "Sınav yayınlandı; veli panelinde görünür.")
    else:
        messages.success(request, f"Durum güncellendi: {sinav.get_durum_display()}")
    return redirect("olcme_sinav_detay", pk=pk)


@login_required
@require_permission("olcme", "yayinla")
@require_POST
def olcme_sinav_veli_toggle(request, pk):
    sinav = _sinav_or_404(request, pk)
    if not ktt_duzenleyebilir(request.user, sinav):
        messages.error(request, "Bu sınavın veli görünürlüğünü değiştiremezsiniz.")
        return redirect("olcme_sinav_detay", pk=pk)
    sinav.veliye_goster = not sinav.veliye_goster
    sinav.save(update_fields=["veliye_goster", "guncellenme"])
    messages.success(
        request,
        f"Veli görünürlüğü: {'Açık' if sinav.veliye_goster else 'Kapalı'}",
    )
    return redirect("olcme_sinav_detay", pk=pk)


@login_required
@require_permission("olcme", "zimmetle")
def olcme_sinav_zimmet(request, pk):
    sinav = _sinav_or_404(request, pk)
    if not ktt_duzenleyebilir(request.user, sinav):
        messages.error(request, "Bu sınavın zimmetini düzenleyemezsiniz.")
        return redirect("olcme_sinav_detay", pk=pk)

    filtre = request.GET.get("f", "tumu")
    qs = sinav.olcme_sorulari.select_related(
        "sinav_ders__ders", "unite", "konu", "kazanim"
    ).order_by("soru_no")
    if filtre == "tamam":
        qs = qs.filter(zimmet_tamam=True)
    elif filtre == "eksik":
        qs = qs.filter(zimmet_tamam=False)
    elif filtre == "ders_eksik":
        qs = qs.filter(sinav_ders__isnull=True)
    elif filtre == "konu_eksik":
        qs = qs.filter(konu__isnull=True)
    elif filtre == "kazanim_eksik":
        qs = qs.filter(kazanim__isnull=True)

    if request.method == "POST":
        action = request.POST.get("action")
        soru_id = request.POST.get("soru_id")
        if action == "tek" and soru_id:
            soru = get_object_or_404(OlcumSoru, pk=soru_id, sinav=sinav)
            konu_id = request.POST.get("konu_id")
            if not konu_id and request.POST.get("konu_q"):
                brans = ders_adindan_brans(sinav.ders.ad) or "turkce"
                konu = konu_getir_veya_olustur(sinav.sinif_seviyesi, brans, request.POST["konu_q"])
                konu_id = konu.id
            soru_zimmet_guncelle(
                soru,
                kullanici=request.user,
                sinav_ders_id=int(request.POST["sinav_ders_id"]) if request.POST.get("sinav_ders_id") else None,
                konu_id=int(konu_id) if konu_id else None,
                kazanim_id=int(request.POST["kazanim_id"]) if request.POST.get("kazanim_id") else None,
                beceri_turu=request.POST.get("beceri_turu", ""),
                zorluk=request.POST.get("zorluk", ""),
                ogretmen_notu=request.POST.get("ogretmen_notu", ""),
            )
            messages.success(request, f"Soru {soru.soru_no} zimmeti güncellendi.")
        elif action == "toplu":
            ids = [int(x) for x in request.POST.getlist("secili") if x.isdigit()]
            alanlar = {}
            if request.POST.get("toplu_konu_id"):
                alanlar["konu_id"] = int(request.POST["toplu_konu_id"])
            elif request.POST.get("toplu_konu_q"):
                brans = ders_adindan_brans(sinav.ders.ad) or "turkce"
                konu = konu_getir_veya_olustur(
                    sinav.sinif_seviyesi, brans, request.POST["toplu_konu_q"]
                )
                alanlar["konu_id"] = konu.id
            if request.POST.get("toplu_kazanim_id"):
                alanlar["kazanim_id"] = int(request.POST["toplu_kazanim_id"])
            if request.POST.get("toplu_sinav_ders_id"):
                alanlar["sinav_ders_id"] = int(request.POST["toplu_sinav_ders_id"])
            adet = toplu_zimmet_guncelle(sinav, ids, kullanici=request.user, **alanlar)
            messages.success(request, f"{adet} soru güncellendi.")
        elif action == "onceki_kopyala" and soru_id:
            soru = get_object_or_404(OlcumSoru, pk=soru_id, sinav=sinav)
            onceki = (
                sinav.olcme_sorulari.filter(soru_no=soru.soru_no - 1)
                .select_related("sinav_ders", "unite", "konu", "kazanim")
                .first()
            )
            if onceki:
                soru_zimmet_guncelle(
                    soru,
                    kullanici=request.user,
                    sinav_ders_id=onceki.sinav_ders_id,
                    unite_id=onceki.unite_id,
                    konu_id=onceki.konu_id,
                    kazanim_id=onceki.kazanim_id,
                    beceri_turu=onceki.beceri_turu,
                    zorluk=onceki.zorluk,
                )
                messages.success(request, f"Soru {soru.soru_no}: önceki zimmet kopyalandı.")
        return redirect(f"{request.path}?f={filtre}")

    sorulari_olustur(sinav, varsayilan_ders=sinav.ders)
    return render(
        request,
        "olcme/sinav_zimmet.html",
        {
            "sinav": sinav,
            "sorular": qs,
            "ozet": zimmet_ozet(sinav),
            "filtre": filtre,
            "ders_bloklari": sinav.olcme_dersleri.select_related("ders"),
            "beceri_secenekleri": OlcumSoru.BeceriTuru.choices,
            "zorluk_secenekleri": OlcumSoru.Zorluk.choices,
            "brans": ders_adindan_brans(sinav.ders.ad) or "",
        },
    )


@login_required
@require_GET
@require_permission("olcme", "view")
def olcme_konu_ara_api(request):
    sinif = request.GET.get("sinif", "7")
    brans = request.GET.get("brans", "")
    q = request.GET.get("q", "")
    if not brans and request.GET.get("ders_id"):
        ders = Ders.objects.filter(pk=request.GET.get("ders_id")).first()
        if ders:
            brans = ders_adindan_brans(ders.ad)
    return JsonResponse({"oneriler": konu_ara(sinif, brans, q)})


@login_required
@require_GET
@require_permission("olcme", "view")
def olcme_kazanim_ara_api(request):
    konu_id = request.GET.get("konu_id")
    if not konu_id:
        return JsonResponse({"oneriler": []})
    return JsonResponse({"oneriler": kazanim_ara(int(konu_id), request.GET.get("q", ""))})


@login_required
@require_permission("olcme", "view")
def olcme_sablon_listesi(request):
    sablonlar = OlcumSinavSablon.objects.order_by("-olusturulma")[:50]
    return render(
        request,
        "olcme/sablon_listesi.html",
        {
            "sablonlar": sablonlar,
            "olusturabilir": ktt_olusturabilir(request.user),
        },
    )


@login_required
@require_permission("olcme", "create")
@require_POST
def olcme_sinav_sablondan(request, pk):
    sinav = _sinav_or_404(request, pk)
    sablon = get_object_or_404(OlcumSinavSablon, pk=int(request.POST.get("sablon_id")))
    sablondan_sinav_kopyala(sinav, sablon, request.user)
    messages.success(request, "Şablon zimmetleri kopyalandı.")
    return redirect("olcme_sinav_zimmet", pk=pk)


@login_required
@require_permission("olcme", "manage_sablon")
@require_POST
def olcme_sinav_sablon_kaydet(request, pk):
    sinav = _sinav_or_404(request, pk)
    ad = request.POST.get("sablon_ad") or sinav.ad
    sinav_sablon_kaydet(sinav, ad, request.user)
    messages.success(request, f"Şablon kaydedildi: {ad}")
    return redirect("olcme_sablon_listesi")


@login_required
@require_permission("olcme", "view")
def olcme_konu_havuzu(request):
    sinif = request.GET.get("sinif", "7")
    brans = request.GET.get("brans", "")
    konular = konu_havuzu_listesi(sinif, brans)[:200]

    if request.method == "POST":
        from takip.permissions.service import can as perm_can

        if perm_can(request.user, "olcme", "manage_konu_havuzu"):
            islem = request.POST.get("islem")
            if islem == "unite":
                OlcumUnite.objects.get_or_create(
                    sinif_seviyesi=request.POST.get("sinif_seviyesi", sinif),
                    brans=request.POST.get("brans", brans or "turkce"),
                    unite_ad=request.POST.get("unite_ad", "").strip(),
                    defaults={"aktif": True},
                )
                messages.success(request, "Ünite eklendi.")
            elif islem == "kazanim":
                konu = get_object_or_404(KonuKatalogu, pk=int(request.POST.get("konu_id")))
                OlcumKazanim.objects.get_or_create(
                    konu=konu,
                    kazanim_ad=request.POST.get("kazanim_ad", "").strip(),
                    defaults={"kod": request.POST.get("kod", ""), "aktif": True},
                )
                messages.success(request, "Kazanım eklendi.")
        else:
            messages.error(request, "Konu havuzu düzenleme yetkiniz yok.")
        return redirect(f"{request.path}?sinif={sinif}&brans={brans}")

    from takip.permissions.service import can as perm_can

    return render(
        request,
        "olcme/konu_havuzu.html",
        {
            "konular": konular,
            "sinif": sinif,
            "brans": brans,
            "brans_secenekleri": KonuKatalogu.Brans.choices,
            "duzenleyebilir": perm_can(request.user, "olcme", "manage_konu_havuzu"),
        },
    )


@login_required
@require_permission("olcme", "edit")
def olcme_sinav_sonuc_soru(request, pk):
    sinav = _sinav_or_404(request, pk)
    talebeler = ktt_sonuc_talebeleri(request.user, sinav)
    talebe_id = request.GET.get("talebe") or request.POST.get("talebe_id")
    talebe = None
    if talebe_id:
        talebe = get_object_or_404(talebeler, pk=int(talebe_id))

    sorular = list(sinav.olcme_sorulari.order_by("soru_no"))
    mevcut = {}
    if talebe:
        mevcut = {
            c.soru.soru_no: c.secilen
            for c in sinav.talebe_cevaplari.filter(talebe=talebe).select_related("soru")
        }
    for s in sorular:
        s.secilen = mevcut.get(s.soru_no, "BOS")

    if request.method == "POST" and talebe:
        if request.POST.get("satir"):
            cevaplar = satir_cevap_parcala(request.POST["satir"], sinav.soru_sayisi)
        else:
            cevaplar = {}
            for s in sorular:
                cevaplar[s.soru_no] = request.POST.get(f"s_{s.soru_no}", "BOS")
        try:
            sonuc = talebe_cevaplari_kaydet(
                sinav,
                talebe,
                cevaplar,
                kitapcik=request.POST.get("kitapcik") or "A",
                kullanici=request.user,
            )
            if sonuc:
                messages.success(
                    request,
                    f"{talebe.ad_soyad}: {sonuc.dogru}D · {sonuc.yanlis}Y · {sonuc.bos}B · net {sonuc.net}",
                )
            else:
                messages.success(request, f"{talebe.ad_soyad}: cevaplar kaydedildi; tüm sorular tamamlanınca net hesaplanır.")
            return redirect(f"{request.path}?talebe={talebe.pk}")
        except Exception as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "olcme/sonuc_soru.html",
        {
            "sinav": sinav,
            "talebeler": talebeler,
            "talebe": talebe,
            "sorular": sorular,
            "mevcut": mevcut,
        },
    )


@login_required
@require_permission("olcme", "view")
def olcme_konu_analiz_sec(request):
    sinavlar = yetkili_olcme_sinavlari(request.user).order_by("-sinav_tarihi")[:30]
    return render(request, "olcme/konu_analiz_sec.html", {"sinavlar": sinavlar})


@login_required
@require_permission("olcme", "view")
def olcme_konu_analiz(request, pk):
    sinav = _sinav_or_404(request, pk)
    analiz = sinav_konu_analizi(sinav)
    kazanim_analiz = sinav_kazanim_analizi(sinav)
    soru_bazli = sinav.talebe_cevaplari.exists()
    return render(
        request,
        "olcme/konu_analiz.html",
        {
            "sinav": sinav,
            "analiz": analiz,
            "kazanim_analiz": kazanim_analiz,
            "soru_bazli": soru_bazli,
            "etut_aktarabilir": perm_can(request.user, "etut_plani", "edit"),
        },
    )


@login_required
@require_permission("olcme", "view")
@require_POST
def olcme_sinav_etut_aktar(request, pk):
    sinav = _sinav_or_404(request, pk)
    if not perm_can(request.user, "etut_plani", "edit"):
        messages.error(request, "Etüt planına aktarma yetkiniz yok.")
        return redirect("olcme_konu_analiz", pk=pk)

    sonuc = zayif_konulari_etut_planina_aktar(request.user, sinav)
    if sonuc.get("hata"):
        messages.error(request, sonuc["hata"])
    elif sonuc["atanan"]:
        mesaj = f"{sonuc['atanan']} zayıf konu etüt planına eklendi."
        if sonuc.get("bos_yetersiz"):
            mesaj += f" ({sonuc['zayif_sayisi']} zayıf konudan {sonuc['atanan']} boş slota sığdı.)"
        messages.success(request, mesaj)
    elif sonuc.get("mesaj"):
        messages.info(request, sonuc["mesaj"])
    else:
        messages.warning(request, "Aktarılacak zayıf konu bulunamadı.")
    return redirect("olcme_konu_analiz", pk=pk)


@login_required
@require_permission("olcme", "view")
def olcme_optik_sec(request):
    sinavlar = yetkili_olcme_sinavlari(request.user).order_by("-sinav_tarihi")[:50]
    return render(request, "olcme/optik_hub.html", {"sinavlar": sinavlar})


@login_required
@require_permission("olcme", "view")
def olcme_optik_form(request, pk):
    sinav = _sinav_or_404(request, pk)
    secenekler = ["A", "B", "C", "D"]
    if sinav.secenek_sayisi >= 5:
        secenekler.append("E")
    kitapcik = varsayilan_kitapcik(sinav)
    talebeler = ktt_sonuc_talebeleri(request.user, sinav)
    return render(
        request,
        "olcme/optik_form.html",
        {
            "sinav": sinav,
            "talebeler": talebeler,
            "optik_satirlar": optik_form_satirlari(
                sinav,
                talebeler,
                kitapcik,
                foto_base_url=_optik_foto_base_url(request, sinav.pk),
            ),
            "kitapcik": kitapcik,
            "soru_nolar": list(range(1, sinav.soru_sayisi + 1)),
            "secenekler": secenekler,
        },
    )


@login_required
@require_permission("olcme", "view")
def olcme_optik_oku_sec(request):
    return redirect("olcme_optik_sec")


@login_required
@require_permission("olcme", "edit")
def olcme_optik_oku(request, pk):
    return redirect("olcme_optik_foto", pk=pk)


@login_required
@require_permission("olcme", "edit")
def olcme_optik_mobil(request, pk):
    return redirect("olcme_optik_foto", pk=pk)


@login_required
@require_permission("olcme", "edit")
def olcme_optik_foto(request, pk):
    """Optik form fotoğrafından bubble tarama (client-side) + kayıt."""
    sinav = _sinav_or_404(request, pk)
    if not ktt_duzenleyebilir(request.user, sinav):
        messages.error(request, "Bu sınav için optik foto okuma yapamazsınız.")
        return redirect("olcme_sinav_detay", pk=pk)

    talebeler = ktt_sonuc_talebeleri(request.user, sinav)

    k_raw = request.GET.get("k") or request.GET.get("karekod")
    if k_raw and not request.GET.get("talebe"):
        parsed = optik_karekod_parse(k_raw)
        if parsed and parsed["sinav_id"] == sinav.pk:
            return redirect(
                f"{request.path}?talebe={parsed['talebe_id']}&kitapcik={parsed['kitapcik']}"
            )
        if parsed:
            messages.error(request, "Bu karekod başka bir sınava ait.")
        else:
            messages.error(request, "Karekod okunamadı. Metni veya bağlantıyı kontrol edin.")

    talebe_id = request.GET.get("talebe") or request.POST.get("talebe_id")
    talebe = None
    if talebe_id:
        talebe = get_object_or_404(talebeler, pk=int(talebe_id))

    sorular = list(sinav.olcme_sorulari.order_by("soru_no"))
    secenekler = ["A", "B", "C", "D"]
    if sinav.secenek_sayisi >= 5:
        secenekler.append("E")

    if request.method == "POST" and talebe:
        cevaplar = {}
        for s in sorular:
            cevaplar[s.soru_no] = request.POST.get(f"s_{s.soru_no}", "BOS")
        try:
            sonuc = talebe_cevaplari_kaydet(
                sinav,
                talebe,
                cevaplar,
                kitapcik=request.POST.get("kitapcik") or "A",
                kullanici=request.user,
            )
            if sonuc:
                messages.success(
                    request,
                    f"{talebe.ad_soyad}: {sonuc.dogru}D · {sonuc.yanlis}Y · net {sonuc.net}",
                )
            else:
                messages.success(request, f"{talebe.ad_soyad}: cevaplar kaydedildi.")
            return redirect(f"{request.path}?talebe={talebe.pk}")
        except Exception as exc:
            messages.error(request, str(exc))

    mevcut = {}
    if talebe:
        mevcut = {
            c.soru.soru_no: c.secilen
            for c in sinav.talebe_cevaplari.filter(talebe=talebe).select_related("soru")
        }
    for s in sorular:
        s.secilen = mevcut.get(s.soru_no, "BOS")

    kitapcik = request.GET.get("kitapcik") or varsayilan_kitapcik(sinav)

    return render(
        request,
        "olcme/optik_foto.html",
        {
            "sinav": sinav,
            "talebeler": talebeler,
            "talebe": talebe,
            "sorular": sorular,
            "secenekler": secenekler,
            "kitapcik": kitapcik.upper()[:1],
        },
    )


@login_required
@require_permission("olcme", "edit")
def olcme_sinav_sonuc_toplu(request, pk):
    sinav = _sinav_or_404(request, pk)
    talebeler = ktt_sonuc_talebeleri(request.user, sinav)
    ozet = sinav_sonuc_ozet(sinav, talebeler)

    if request.method == "POST":
        metin = request.POST.get("optik_metin", "")
        if request.FILES.get("optik_dosya"):
            metin = request.FILES["optik_dosya"].read().decode("utf-8", errors="ignore")
        if not metin.strip():
            messages.error(request, "Metin veya dosya gerekli.")
            return redirect("olcme_sinav_sonuc_toplu", pk=pk)
        if not ktt_duzenleyebilir(request.user, sinav):
            messages.error(request, "Sonuç kaydetme yetkiniz yok.")
        else:
            satirlar = optik_satirlar_parcala(metin, sinav.soru_sayisi)
            sonuc = toplu_optik_kaydet(
                sinav,
                talebeler,
                satirlar,
                kullanici=request.user,
                kitapcik=request.POST.get("kitapcik") or "A",
            )
            if sonuc["kaydedilen"]:
                messages.success(request, f"{sonuc['kaydedilen']} talebe kaydedildi.")
            for h in sonuc["hatalar"][:5]:
                messages.warning(request, h)
        return redirect("olcme_sinav_sonuc_toplu", pk=pk)

    tamam = sum(1 for o in ozet if o["tamam"])
    return render(
        request,
        "olcme/sonuc_toplu.html",
        {
            "sinav": sinav,
            "ozet": ozet,
            "tamam_sayisi": tamam,
            "toplam_sayisi": len(ozet),
        },
    )


@login_required
@require_permission("olcme", "view")
def olcme_rapor_sec(request):
    sinavlar = yetkili_olcme_sinavlari(request.user).order_by("-sinav_tarihi")[:30]
    return render(request, "olcme/rapor_sec.html", {"sinavlar": sinavlar})


@login_required
@require_permission("olcme", "export_excel")
def olcme_sinav_analiz_excel(request, pk):
    sinav = _sinav_or_404(request, pk)
    icerik = sinav_analiz_xlsx(sinav, request.user)
    ad = f"olcme-{sinav.pk}-analiz.xlsx"
    return excel_http_yanit(icerik, ad)


@login_required
@require_permission("olcme", "export_excel")
def olcme_sinav_sonuc_csv(request, pk):
    sinav = _sinav_or_404(request, pk)
    icerik = sinav_sonuc_csv(sinav, request.user)
    response = HttpResponse(
        "\ufeff" + icerik,
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="olcme-{sinav.pk}-sonuc.csv"'
    return response


@login_required
@require_permission("olcme", "export_pdf")
def olcme_optik_form_pdf(request, pk):
    sinav = _sinav_or_404(request, pk)
    secenekler = ["A", "B", "C", "D"]
    if sinav.secenek_sayisi >= 5:
        secenekler.append("E")
    kitapcik = varsayilan_kitapcik(sinav)
    talebeler = ktt_sonuc_talebeleri(request.user, sinav)
    html = render_to_string(
        "olcme/optik_form_pdf.html",
        {
            "sinav": sinav,
            "talebeler": talebeler,
            "optik_satirlar": optik_form_satirlari(
                sinav,
                talebeler,
                kitapcik,
                foto_base_url=_optik_foto_base_url(request, sinav.pk),
            ),
            "kitapcik": kitapcik,
            "soru_nolar": list(range(1, sinav.soru_sayisi + 1)),
            "secenekler": secenekler,
        },
    )
    pdf = html_to_pdf(html)
    if not pdf:
        return pdf_error_response("PDF oluşturulamadı.")
    return make_pdf_response(pdf, f"optik-{sinav.pk}.pdf")
