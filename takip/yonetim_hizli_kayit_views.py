"""Yönetim — tek sayfadan personel / talebe / öğretmen ekleme."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from takip.pdf_utils import pdf_error_response
from takip.personel_giris_service import (
    OgretmenGirisKaydi,
    PersonelGirisKaydi,
    personel_giris_pdf_olustur,
    personel_giris_zip_olustur,
    toplu_ogretmen_olustur,
    toplu_personel_olustur,
)
from takip.talebe_excel import talebe_excel_ice_aktar
from takip.yonetim_forms import TalebeExcelForm
from takip.yonetim_hizli_kayit_forms import (
    HizliOgretmenForm,
    HizliPersonelForm,
    HizliTalebeForm,
    TopluOgretmenForm,
    TopluPersonelForm,
)
from takip.yonetim_views import yonetici_gerekli

TUR_SECENEKLERI = (
    ("personel", "Personel", "Personel kaydı — giriş bilgileri otomatik PDF"),
    ("talebe", "Talebe", "Talebe kaydı — veli bilgisi aynı formda veya Excel ile"),
    ("ogretmen", "Öğretmen", "Etüt hocası — giriş bilgileri otomatik PDF"),
)


def _form_for_tur(tur: str, data=None):
    if tur == "personel":
        return HizliPersonelForm(data)
    if tur == "ogretmen":
        return HizliOgretmenForm(data)
    return HizliTalebeForm(data)


def _excel_sonuc_mesajlari(request, sonuc) -> None:
    if sonuc.eklenen:
        messages.success(request, f"{sonuc.eklenen} talebe eklendi.")
    if sonuc.guncellenen:
        messages.success(request, f"{sonuc.guncellenen} talebe güncellendi.")
    if sonuc.veli_hesap:
        messages.success(
            request,
            f"{sonuc.veli_hesap} veli paneli hazır "
            "(giriş: talebe TC · şifre: TC son 4 hane).",
        )
    if sonuc.atlanan:
        messages.warning(request, f"{sonuc.atlanan} satır atlandı.")
    for mesaj in sonuc.bilgi[:6]:
        messages.info(request, mesaj)
    if sonuc.hatalar:
        from takip.messages_util import hatalari_ozetle

        hatalari_ozetle(request, list(sonuc.hatalar), tek_baslik="Excel satır hatası")


def _giris_pdf_yanit(request, kayit: PersonelGirisKaydi | OgretmenGirisKaydi) -> HttpResponse:
    pdf = personel_giris_pdf_olustur(kayit, request=request)
    if not pdf:
        return pdf_error_response("Giriş PDF'i oluşturulamadı.")
    dosya = kayit.ad_soyad.lower().replace(" ", "-")
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="giris-{dosya}.pdf"'
    return response


@yonetici_gerekli
def hizli_kayit(request):
    tur = request.GET.get("tur") or request.POST.get("tur") or "talebe"
    if tur not in {t[0] for t in TUR_SECENEKLERI}:
        tur = "talebe"

    excel_form = TalebeExcelForm()
    excel_sonuc = None
    toplu_personel_form = TopluPersonelForm()
    toplu_ogretmen_form = TopluOgretmenForm()

    if request.method == "POST" and request.POST.get("islem") == "excel_yukle":
        excel_form = TalebeExcelForm(request.POST, request.FILES)
        if excel_form.is_valid():
            try:
                excel_sonuc = talebe_excel_ice_aktar(
                    excel_form.cleaned_data["excel_dosyasi"]
                )
                _excel_sonuc_mesajlari(request, excel_sonuc)
            except ImportError:
                messages.error(request, "Excel yükleme için openpyxl gerekli.")
        tur = "talebe"
        form = _form_for_tur(tur)
        return render(
            request,
            "yonetim/hizli_kayit.html",
            {
                "tur": tur,
                "tur_secenekleri": TUR_SECENEKLERI,
                "form": form,
                "excel_form": excel_form,
                "excel_sonuc": excel_sonuc,
                "toplu_personel_form": toplu_personel_form,
                "toplu_ogretmen_form": toplu_ogretmen_form,
            },
        )

    if request.method == "POST" and request.POST.get("islem") == "toplu_ogretmen":
        toplu_ogretmen_form = TopluOgretmenForm(request.POST)
        if toplu_ogretmen_form.is_valid():
            kayitlar, hatalar = toplu_ogretmen_olustur(
                toplu_ogretmen_form.cleaned_data["isim_listesi"],
                siniflar=list(
                    toplu_ogretmen_form.cleaned_data.get("sorumlu_sinif_subeler") or []
                ),
                brans=toplu_ogretmen_form.cleaned_data.get("brans"),
                saatlik_ucret=toplu_ogretmen_form.cleaned_data.get("saatlik_ucret"),
            )
            if hatalar:
                from takip.messages_util import hatalari_ozetle

                hatalari_ozetle(request, hatalar, tek_baslik="Toplu öğretmen kaydı")

            if kayitlar:
                zip_dosya = personel_giris_zip_olustur(kayitlar, request=request)
                if zip_dosya:
                    response = HttpResponse(
                        zip_dosya,
                        content_type="application/zip",
                    )
                    response["Content-Disposition"] = (
                        'attachment; filename="ogretmen-giris-bilgileri.zip"'
                    )
                    return response
                messages.error(request, "PDF arşivi oluşturulamadı.")
            else:
                messages.error(request, "Hiç öğretmen eklenemedi.")

        tur = "ogretmen"
        form = _form_for_tur(tur)
        return render(
            request,
            "yonetim/hizli_kayit.html",
            {
                "tur": tur,
                "tur_secenekleri": TUR_SECENEKLERI,
                "form": form,
                "excel_form": excel_form,
                "excel_sonuc": excel_sonuc,
                "toplu_personel_form": toplu_personel_form,
                "toplu_ogretmen_form": toplu_ogretmen_form,
            },
        )

    if request.method == "POST" and request.POST.get("islem") == "toplu_personel":
        toplu_personel_form = TopluPersonelForm(request.POST)
        if toplu_personel_form.is_valid():
            kayitlar, hatalar = toplu_personel_olustur(
                toplu_personel_form.cleaned_data["isim_listesi"],
                ana_rol=toplu_personel_form.cleaned_data["ana_rol"],
                aktif=toplu_personel_form.cleaned_data.get("aktif", True),
                siniflar=list(
                    toplu_personel_form.cleaned_data.get("sorumlu_sinif_subeler") or []
                ),
            )
            if hatalar:
                from takip.messages_util import hatalari_ozetle

                hatalari_ozetle(request, hatalar, tek_baslik="Toplu öğretmen kaydı")

            if kayitlar:
                zip_dosya = personel_giris_zip_olustur(kayitlar, request=request)
                if zip_dosya:
                    response = HttpResponse(
                        zip_dosya,
                        content_type="application/zip",
                    )
                    response["Content-Disposition"] = (
                        'attachment; filename="personel-giris-bilgileri.zip"'
                    )
                    return response
                messages.error(request, "PDF arşivi oluşturulamadı.")
            else:
                messages.error(request, "Hiç personel eklenemedi.")

        tur = "personel"
        form = _form_for_tur(tur)
        return render(
            request,
            "yonetim/hizli_kayit.html",
            {
                "tur": tur,
                "tur_secenekleri": TUR_SECENEKLERI,
                "form": form,
                "excel_form": excel_form,
                "excel_sonuc": excel_sonuc,
                "toplu_personel_form": toplu_personel_form,
                "toplu_ogretmen_form": toplu_ogretmen_form,
            },
        )

    form = _form_for_tur(tur, request.POST or None)

    if request.method == "POST" and form.is_valid():
        if tur == "personel":
            personel = form.save()
            kayit = PersonelGirisKaydi(
                personel=personel,
                kullanici_adi=form.cleaned_data["kullanici_adi"],
                sifre=form.cleaned_data["sifre"],
            )
            return _giris_pdf_yanit(request, kayit)

        if tur == "ogretmen":
            kayit = form.save()
            return _giris_pdf_yanit(request, kayit)

        talebe, veli = form.save_with_veli()
        mesaj = f"{talebe.ad_soyad} eklendi (No: {talebe.talebe_no})."
        if veli:
            mesaj += f" Veli hesabı: {veli.user.username}"
        messages.success(request, mesaj)
        return redirect(f"{reverse('yonetim:hizli_kayit')}?tur=talebe")

    return render(
        request,
        "yonetim/hizli_kayit.html",
        {
            "tur": tur,
            "tur_secenekleri": TUR_SECENEKLERI,
            "form": form,
            "excel_form": excel_form,
            "excel_sonuc": excel_sonuc,
            "toplu_personel_form": toplu_personel_form,
            "toplu_ogretmen_form": toplu_ogretmen_form,
        },
    )
