"""KTT panel görünümleri."""

from __future__ import annotations

import csv
from io import StringIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.utils.timezone import localdate, now

from takip.forms import KttSinavForm
from takip.ktt_service import (
    hedef_siniflar_kaydet,
    ktt_duzenleyebilir,
    ktt_olusturabilir,
    ktt_rapor_filtre_dict,
    ktt_rapor_filtre_secenekleri,
    ktt_rapor_filtrele,
    ktt_rapor_istatistik,
    ktt_silebilir,
    ktt_sinif_secenekleri,
    ktt_sonuc_talebeleri,
    ktt_tam_yetki,
    yetkili_ktt_sinavlari,
    yetkili_ktt_sonuclari,
)
from takip.models import Ders, KttSinav, KttSonucu
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user


def _ktt_form_for_user(user, data=None, instance=None, liste_modu=False, initial=None):
    admin_modu = ktt_tam_yetki(user)
    kwargs = {"admin_modu": admin_modu}
    if initial is not None:
        kwargs["initial"] = initial
    form = KttSinavForm(data, instance=instance, **kwargs)
    form.fields["ders"].queryset = Ders.objects.filter(aktif=True).order_by(
        "sira", "ad"
    )

    if liste_modu:
        form.fields.pop("sinif_seviyesi", None)

    if not admin_modu:
        form.fields.pop("veliye_goster", None)

    if admin_modu and "etut_hocasi" in form.fields and not liste_modu:
        from takip.models import EtutHocasi

        form.fields["etut_hocasi"].queryset = EtutHocasi.objects.filter(
            aktif=True
        ).order_by("ad_soyad")

    return form


def _ktt_olustur_kaydet(request, form, sinif_etiketleri):
    hoca = etut_hocasi_for_user(request.user)
    ktt = form.save(commit=False)
    if hoca:
        ktt.etut_hocasi = hoca
    elif not ktt.etut_hocasi_id:
        return None, "Etüt hocası seçilmelidir."

    if sinif_etiketleri:
        hedef_siniflar_kaydet(ktt, sinif_etiketleri)
    else:
        hedef_siniflar_kaydet(ktt, [])
        if not ktt.hedef_siniflar and not ktt.sinif_seviyesi:
            return None, "En az bir sınıf seçin."

    ktt.olusturan = request.user
    ktt.save()
    return ktt, None


@login_required
@require_permission("ktt", "view")
def ktt_listesi(request):
    hoca = etut_hocasi_for_user(request.user)
    olusturabilir = ktt_olusturabilir(request.user)
    form = None

    if request.method == "POST" and olusturabilir:
        if not hoca and not ktt_tam_yetki(request.user):
            messages.error(request, "Etüt hocası kaydınız bulunamadı.")
            return redirect("ktt_listesi")

        form = _ktt_form_for_user(request.user, request.POST, liste_modu=True)
        sinif_etiketleri = request.POST.getlist("sinif_subeler")

        if form.is_valid():
            ktt, hata = _ktt_olustur_kaydet(request, form, sinif_etiketleri)
            if hata:
                messages.error(request, hata)
            else:
                messages.success(request, f"{ktt.ad} oluşturuldu.")
                return redirect("ktt_sonuc_gir", pk=ktt.pk)
    elif olusturabilir:
        baslangic = {
            "sinav_tarihi": localdate(),
            "sinif_seviyesi": "7",
        }
        form = _ktt_form_for_user(request.user, initial=baslangic, liste_modu=True)

    sinif_secenekleri = ktt_sinif_secenekleri(request.user)

    return render(
        request,
        "ktt_listesi.html",
        {
            "sinavlar": yetkili_ktt_sinavlari(request.user),
            "form": form,
            "sinif_secenekleri": sinif_secenekleri,
            "olusturabilir": olusturabilir,
            "silme_yetkisi": can(request.user, "ktt", "delete"),
        },
    )


@login_required
@require_permission("ktt", "delete")
def ktt_sil(request, pk):
    ktt = get_object_or_404(yetkili_ktt_sinavlari(request.user), pk=pk)
    if not ktt_silebilir(request.user, ktt):
        messages.error(request, "Bu KTT'yi silme yetkiniz yok.")
        return redirect("ktt_listesi")

    if request.method != "POST":
        return redirect("ktt_listesi")

    ad = ktt.ad
    ktt.delete()
    messages.success(request, f"{ad} silindi.")
    return redirect("ktt_listesi")


@login_required
@require_permission("ktt", "create")
def ktt_ekle(request):
    return redirect("ktt_listesi")


@login_required
@require_permission("ktt", "edit")
def ktt_duzenle(request, pk):
    ktt = get_object_or_404(yetkili_ktt_sinavlari(request.user), pk=pk)

    if not ktt_duzenleyebilir(request.user, ktt):
        messages.error(request, "Bu KTT'yi düzenleme yetkiniz yok.")
        return redirect("ktt_listesi")

    form = _ktt_form_for_user(request.user, request.POST or None, instance=ktt)

    if form.is_valid():
        form.save()
        messages.success(request, "KTT güncellendi.")
        return redirect("ktt_detay", pk=ktt.pk)

    return render(
        request,
        "ktt_form.html",
        {
            "form": form,
            "ktt": ktt,
            "sayfa_basligi": "KTT Düzenle",
            "duzenleme": True,
        },
    )


@login_required
@require_permission("ktt", "view")
def ktt_detay(request, pk):
    ktt = get_object_or_404(
        yetkili_ktt_sinavlari(request.user).prefetch_related(
            "sonuclar__talebe"
        ),
        pk=pk,
    )
    sonuclar = list(ktt.sonuclar.select_related("talebe").order_by("-puan", "-net"))

    return render(
        request,
        "ktt_detay.html",
        {
            "ktt": ktt,
            "sonuclar": sonuclar,
            "duzenleyebilir": ktt_duzenleyebilir(request.user, ktt),
            "sonuc_girebilir": can(request.user, "ktt", "edit"),
            "pdf_yetkisi": can(request.user, "ktt", "export_pdf"),
        },
    )


@login_required
@require_permission("ktt", "edit")
def ktt_sonuc_gir(request, pk):
    ktt = get_object_or_404(yetkili_ktt_sinavlari(request.user), pk=pk)

    if not ktt_duzenleyebilir(request.user, ktt):
        messages.error(request, "Bu KTT için sonuç girişi yapamazsınız.")
        return redirect("ktt_listesi")

    talebeler = list(ktt_sonuc_talebeleri(request.user, ktt))
    toplam_soru = int(ktt.soru_sayisi or 0)

    if toplam_soru <= 0:
        messages.error(request, "KTT soru sayısı geçersiz.")
        return redirect("ktt_listesi")

    if request.method == "POST":
        hatalar = []
        kaydedilen = 0

        with transaction.atomic():
            for talebe in talebeler:
                try:
                    dogru = int(request.POST.get(f"dogru_{talebe.id}", 0) or 0)
                    yanlis = int(request.POST.get(f"yanlis_{talebe.id}", 0) or 0)
                    bos = int(request.POST.get(f"bos_{talebe.id}", 0) or 0)
                except (TypeError, ValueError):
                    hatalar.append(f"{talebe.ad_soyad}: Geçerli sayılar girin.")
                    continue

                if dogru + yanlis + bos != toplam_soru:
                    hatalar.append(
                        f"{talebe.ad_soyad}: Toplam {toplam_soru} olmalı."
                    )
                    continue

                if dogru == 0 and yanlis == 0 and bos == toplam_soru:
                    KttSonucu.objects.filter(ktt=ktt, talebe=talebe).delete()
                    continue

                KttSonucu.objects.update_or_create(
                    ktt=ktt,
                    talebe=talebe,
                    defaults={
                        "dogru": dogru,
                        "yanlis": yanlis,
                        "bos": bos,
                        "kaydeden": request.user,
                    },
                )
                kaydedilen += 1

            if hatalar:
                transaction.set_rollback(True)

        for hata in hatalar:
            messages.error(request, hata)

        if not hatalar:
            messages.success(
                request,
                f"{kaydedilen} öğrenci sonucu kaydedildi.",
            )
            return redirect("ktt_sonuc_gir", pk=ktt.pk)

    mevcut = {
        s.talebe_id: s
        for s in KttSonucu.objects.filter(ktt=ktt, talebe__in=talebeler)
    }

    satirlar = []
    for talebe in talebeler:
        sonuc = mevcut.get(talebe.id)
        satirlar.append(
            {
                "talebe": talebe,
                "sonuc": sonuc,
                "dogru": sonuc.dogru if sonuc else 0,
                "yanlis": sonuc.yanlis if sonuc else 0,
                "bos": sonuc.bos if sonuc else toplam_soru,
                "net": sonuc.net if sonuc else 0,
                "puan": sonuc.puan if sonuc else 0,
            }
        )

    return render(
        request,
        "ktt_sonuc_gir.html",
        {
            "ktt": ktt,
            "satirlar": satirlar,
            "toplam_soru": toplam_soru,
            "pdf_yetkisi": can(request.user, "ktt", "export_pdf"),
        },
    )


@login_required
@require_permission("ktt", "export_excel")
def ktt_excel_indir(request, pk):
    ktt = get_object_or_404(yetkili_ktt_sinavlari(request.user), pk=pk)
    sonuclar = ktt.sonuclar.select_related("talebe").order_by("-puan", "-net")

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "Talebe",
            "Talebe No",
            "Doğru",
            "Yanlış",
            "Boş",
            "Net",
            "Puan",
        ]
    )
    for sonuc in sonuclar:
        writer.writerow(
            [
                sonuc.talebe.ad_soyad,
                sonuc.talebe.talebe_no or "",
                sonuc.dogru,
                sonuc.yanlis,
                sonuc.bos,
                str(sonuc.net).replace(".", ","),
                str(sonuc.puan).replace(".", ","),
            ]
        )

    response = HttpResponse(
        "\ufeff" + buffer.getvalue(),
        content_type="text/csv; charset=utf-8",
    )
    dosya_adi = f"ktt_{ktt.id}_{localdate():%Y%m%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{dosya_adi}"'
    return response


def _ktt_sonuc_ozeti(sonuclar) -> dict:
    kayitlar = list(sonuclar)
    if not kayitlar:
        return {
            "ogrenci_sayisi": 0,
            "ortalama_net": "—",
            "ortalama_puan": "—",
            "en_yuksek_puan": "—",
        }

    toplam_net = sum(float(s.net or 0) for s in kayitlar)
    toplam_puan = sum(float(s.puan or 0) for s in kayitlar)
    en_yuksek = max(float(s.puan or 0) for s in kayitlar)
    adet = len(kayitlar)
    return {
        "ogrenci_sayisi": adet,
        "ortalama_net": round(toplam_net / adet, 2),
        "ortalama_puan": round(toplam_puan / adet, 2),
        "en_yuksek_puan": round(en_yuksek, 2),
    }


@login_required
@require_permission("ktt", "export_pdf")
def ktt_detay_pdf(request, pk):
    ktt = get_object_or_404(yetkili_ktt_sinavlari(request.user), pk=pk)
    sonuclar = ktt.sonuclar.select_related("talebe").order_by("-puan", "-net", "talebe__ad_soyad")

    html = render(
        request,
        "ktt_detay_pdf.html",
        {
            "ktt": ktt,
            "sonuclar": sonuclar,
            "ozet": _ktt_sonuc_ozeti(sonuclar),
            "olusturma_tarihi": now(),
        },
    ).content.decode("utf-8")

    pdf_verisi = html_to_pdf(html)
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    dosya_adi = slugify(ktt.ad) or f"ktt_{ktt.pk}"
    return make_pdf_response(
        pdf_verisi,
        f"ktt_{dosya_adi}_{localdate():%Y%m%d}.pdf",
    )


def _ktt_rapor_sonuclar(request):
    filtre = ktt_rapor_filtre_dict(request)
    qs = yetkili_ktt_sonuclari(request.user)
    qs = ktt_rapor_filtrele(
        qs,
        sinif_sube_id=filtre["sinif_sube"] or None,
        ders_id=filtre["ders"] or None,
        ktt_id=filtre["ktt"] or None,
        talebe_id=filtre["talebe"] or None,
        baslangic=filtre["baslangic"] or None,
        bitis=filtre["bitis"] or None,
    )
    return qs.order_by("-ktt__sinav_tarihi", "-puan", "talebe__ad_soyad"), filtre


@login_required
@require_permission("ktt", "view")
def ktt_rapor(request):
    if request.GET.get("format") == "excel" and can(request.user, "ktt", "export_excel"):
        return ktt_rapor_excel(request)
    if request.GET.get("format") == "pdf" and can(request.user, "ktt", "export_pdf"):
        return ktt_rapor_pdf(request)

    sonuclar, filtre = _ktt_rapor_sonuclar(request)
    sonuclar_list = list(sonuclar[:500])
    secenekler = ktt_rapor_filtre_secenekleri(request.user)
    istatistik = ktt_rapor_istatistik(sonuclar)

    export_params = request.GET.copy()
    export_params.pop("format", None)
    export_qs = export_params.urlencode()
    export_tail = f"&{export_qs}" if export_qs else ""

    return render(
        request,
        "ktt_rapor.html",
        {
            "sonuclar": sonuclar_list,
            "istatistik": istatistik,
            "filtre": filtre,
            "sinif_subeler": secenekler["sinif_subeler"],
            "dersler": secenekler["dersler"],
            "ktt_sinavlari": secenekler["ktt_sinavlari"],
            "talebeler": secenekler["talebeler"],
            "excel_yetkisi": can(request.user, "ktt", "export_excel"),
            "pdf_yetkisi": can(request.user, "ktt", "export_pdf"),
            "excel_url": f"{request.path}?format=excel{export_tail}",
            "pdf_url": f"{request.path}?format=pdf{export_tail}",
        },
    )


@login_required
@require_permission("ktt", "export_excel")
def ktt_rapor_excel(request):
    sonuclar, _ = _ktt_rapor_sonuclar(request)

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "Tarih",
            "KTT",
            "Talebe",
            "Sınıf",
            "Ders",
            "Doğru",
            "Yanlış",
            "Boş",
            "Net",
            "Puan",
        ]
    )
    for sonuc in sonuclar[:2000]:
        writer.writerow(
            [
                sonuc.ktt.sinav_tarihi.strftime("%d.%m.%Y"),
                sonuc.ktt.ad,
                sonuc.talebe.ad_soyad,
                str(sonuc.talebe.sinif_sube or sonuc.ktt.sinif_goster),
                sonuc.ktt.ders.ad,
                sonuc.dogru,
                sonuc.yanlis,
                sonuc.bos,
                str(sonuc.net).replace(".", ","),
                str(sonuc.puan).replace(".", ","),
            ]
        )

    response = HttpResponse(
        "\ufeff" + buffer.getvalue(),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="ktt_rapor_{localdate():%Y%m%d}.csv"'
    )
    return response


@login_required
@require_permission("ktt", "export_pdf")
def ktt_rapor_pdf(request):
    sonuclar, filtre = _ktt_rapor_sonuclar(request)
    istatistik = ktt_rapor_istatistik(sonuclar)

    html = render(
        request,
        "ktt_rapor_pdf.html",
        {
            "sonuclar": list(sonuclar[:300]),
            "istatistik": istatistik,
            "filtre": filtre,
        },
    ).content.decode("utf-8")

    pdf_verisi = html_to_pdf(html)
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )

    return make_pdf_response(
        pdf_verisi,
        f"ktt_rapor_{localdate():%Y%m%d}.pdf",
    )
