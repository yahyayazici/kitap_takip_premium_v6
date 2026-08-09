"""Yönetim — tek sayfadan personel / talebe / öğretmen ekleme."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from takip.pdf_utils import pdf_error_response
from takip.hizli_kayit_service import (
    ogretmen_pasif_et,
    personel_pasif_et,
    son_kayitlar,
    talebe_pasif_et,
)
from takip.models import DiniDersSeviyesi, EtutHocasi, PersonelProfili, SinifSube, Talebe
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
    ("personel", "Personel", "Kurum personeli — etüt mesulü, idareci vb."),
    ("talebe", "Talebe", "Talebe kaydı — veli bilgisi aynı formda veya Excel ile"),
    ("ogretmen", "Öğretmen", "Ana ders öğretmeni — branş ve ders ücreti"),
)

SESSION_GIRIS_ANAHTAR = "yk_son_giris"


def _talebe_form_meta() -> dict:
    from django.db.models import Prefetch

    aktif_hocalar = EtutHocasi.objects.filter(aktif=True).only("pk", "ad_soyad")
    sinif_etut: dict[str, list[int]] = {}
    for ss in SinifSube.objects.filter(aktif=True).prefetch_related(
        Prefetch(
            "etut_hocalari",
            queryset=aktif_hocalar.order_by("ad_soyad"),
        )
    ).only("pk"):
        sinif_etut[str(ss.pk)] = [h.pk for h in ss.etut_hocalari.all()]

    seviye_hocalar: dict[str, list[int]] = {}
    for seviye in DiniDersSeviyesi.objects.filter(aktif=True).prefetch_related(
        Prefetch("hocalar", queryset=aktif_hocalar.order_by("ad_soyad"))
    ).only("pk"):
        seviye_hocalar[str(seviye.pk)] = [h.pk for h in seviye.hocalar.all()]

    hocalar = {str(h.pk): h.ad_soyad for h in aktif_hocalar.order_by("ad_soyad")}
    return {
        "sinif_etut": sinif_etut,
        "seviye_hocalar": seviye_hocalar,
        "hocalar": hocalar,
    }


def _giris_bilgisi_kaydet(
    request,
    kayit: PersonelGirisKaydi | OgretmenGirisKaydi,
    *,
    tur: str,
) -> None:
    request.session[SESSION_GIRIS_ANAHTAR] = {
        "tur": tur,
        "ad_soyad": kayit.ad_soyad,
        "kullanici_adi": kayit.kullanici_adi,
        "sifre": kayit.sifre,
        "rol_etiket": kayit.rol_etiket,
        "personel_id": getattr(kayit, "personel", None) and kayit.personel.pk,
        "hoca_id": getattr(kayit, "hoca", None) and kayit.hoca.pk,
    }


def _render_context(
    *,
    request,
    tur: str,
    form,
    excel_form,
    excel_sonuc,
    toplu_personel_form,
    toplu_ogretmen_form,
) -> dict:
    ctx = {
        "tur": tur,
        "tur_secenekleri": TUR_SECENEKLERI,
        "form": form,
        "excel_form": excel_form,
        "excel_sonuc": excel_sonuc,
        "toplu_personel_form": toplu_personel_form,
        "toplu_ogretmen_form": toplu_ogretmen_form,
        "son_kayitlar": son_kayitlar(tur),
        "giris_bilgisi": request.session.get(SESSION_GIRIS_ANAHTAR),
    }
    if tur == "talebe":
        ctx["talebe_form_meta"] = _talebe_form_meta()
    return ctx


def _form_for_tur(tur: str, data=None, files=None):
    if tur == "personel":
        return HizliPersonelForm(data)
    if tur == "ogretmen":
        return HizliOgretmenForm(data)
    return HizliTalebeForm(data, files)


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
@require_POST
def kayit_sil(request):
    tur = (request.POST.get("tur") or "talebe").strip()
    pk = request.POST.get("pk")
    next_url = (request.POST.get("next") or "").strip()

    if tur == "talebe":
        talebe = get_object_or_404(Talebe, pk=pk, aktif=True)
        ad = talebe.ad_soyad
        talebe_pasif_et(talebe)
        messages.success(request, f"{ad} pasif edildi (listeden kaldırıldı).")
    elif tur == "personel":
        personel = get_object_or_404(PersonelProfili, pk=pk, aktif=True)
        ad = personel.ad_soyad
        personel_pasif_et(personel)
        messages.success(request, f"{ad} pasif edildi (giriş kapatıldı).")
    elif tur == "ogretmen":
        hoca = get_object_or_404(
            EtutHocasi,
            pk=pk,
            aktif=True,
            personel_kaydi__isnull=True,
        )
        ad = hoca.ad_soyad
        ogretmen_pasif_et(hoca)
        messages.success(request, f"{ad} pasif edildi (giriş kapatıldı).")
    else:
        messages.error(request, "Geçersiz kayıt türü.")
        tur = "talebe"

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        return redirect(next_url)
    return redirect(f"{reverse('yonetim:hizli_kayit')}?tur={tur}")


@yonetici_gerekli
def hizli_kayit_giris_pdf(request):
    data = request.session.get(SESSION_GIRIS_ANAHTAR)
    if not data:
        messages.error(request, "Giriş bilgisi bulunamadı veya süresi doldu.")
        return redirect("yonetim:hizli_kayit")

    tur = data.get("tur")
    if tur == "personel" and data.get("personel_id"):
        personel = get_object_or_404(PersonelProfili, pk=data["personel_id"])
        kayit = PersonelGirisKaydi(
            personel=personel,
            kullanici_adi=data["kullanici_adi"],
            sifre=data["sifre"],
        )
    elif tur == "ogretmen" and data.get("hoca_id"):
        hoca = get_object_or_404(EtutHocasi, pk=data["hoca_id"])
        kayit = OgretmenGirisKaydi(
            hoca=hoca,
            kullanici_adi=data["kullanici_adi"],
            sifre=data["sifre"],
        )
    else:
        messages.error(request, "PDF oluşturulamadı.")
        return redirect(f"{reverse('yonetim:hizli_kayit')}?tur={tur or 'personel'}")

    return _giris_pdf_yanit(request, kayit)


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
            _render_context(
                request=request,
                tur=tur,
                form=form,
                excel_form=excel_form,
                excel_sonuc=excel_sonuc,
                toplu_personel_form=toplu_personel_form,
                toplu_ogretmen_form=toplu_ogretmen_form,
            ),
        )

    if request.method == "POST" and request.POST.get("islem") == "toplu_ogretmen":
        toplu_ogretmen_form = TopluOgretmenForm(request.POST)
        if toplu_ogretmen_form.is_valid():
            kayitlar, hatalar = toplu_ogretmen_olustur(
                toplu_ogretmen_form.cleaned_data["isim_listesi"],
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
            _render_context(
                request=request,
                tur=tur,
                form=form,
                excel_form=excel_form,
                excel_sonuc=excel_sonuc,
                toplu_personel_form=toplu_personel_form,
                toplu_ogretmen_form=toplu_ogretmen_form,
            ),
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
                dini_ders_seviyeleri=list(
                    toplu_personel_form.cleaned_data.get("dini_ders_seviyeleri") or []
                ),
            )
            if hatalar:
                from takip.messages_util import hatalari_ozetle

                hatalari_ozetle(request, hatalar, tek_baslik="Toplu personel kaydı")

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
            _render_context(
                request=request,
                tur=tur,
                form=form,
                excel_form=excel_form,
                excel_sonuc=excel_sonuc,
                toplu_personel_form=toplu_personel_form,
                toplu_ogretmen_form=toplu_ogretmen_form,
            ),
        )

    form = _form_for_tur(tur, request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        if tur == "personel":
            personel = form.save()
            kayit = PersonelGirisKaydi(
                personel=personel,
                kullanici_adi=form.cleaned_data["kullanici_adi"],
                sifre=form.cleaned_data["sifre"],
            )
            _giris_bilgisi_kaydet(request, kayit, tur="personel")
            messages.success(request, f"{personel.ad_soyad} eklendi.")
            return redirect(f"{reverse('yonetim:hizli_kayit')}?tur=personel")

        if tur == "ogretmen":
            kayit = form.save()
            _giris_bilgisi_kaydet(request, kayit, tur="ogretmen")
            messages.success(request, f"{kayit.ad_soyad} eklendi.")
            return redirect(f"{reverse('yonetim:hizli_kayit')}?tur=ogretmen")

        talebe, veli = form.save_with_veli()
        mesaj = f"{talebe.ad_soyad} eklendi (No: {talebe.talebe_no})."
        if veli:
            mesaj += f" Veli hesabı: {veli.user.username}"
        messages.success(request, mesaj)
        return redirect(f"{reverse('yonetim:hizli_kayit')}?tur=talebe")

    return render(
        request,
        "yonetim/hizli_kayit.html",
        _render_context(
            request=request,
            tur=tur,
            form=form,
            excel_form=excel_form,
            excel_sonuc=excel_sonuc,
            toplu_personel_form=toplu_personel_form,
            toplu_ogretmen_form=toplu_ogretmen_form,
        ),
    )
