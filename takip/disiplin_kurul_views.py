"""Disiplin Kurulu premium panel görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from takip.disiplin_kurul_forms import (
    DisiplinKurulAyarForm,
    DisiplinKurulKararDurumForm,
    DisiplinKurulKararForm,
    DisiplinKurulOlusturForm,
    DisiplinKurulRaporForm,
    DisiplinKurulVarsayilanGundemForm,
    DisiplinKurulVarsayilanUyeForm,
)
from takip.disiplin_kurul_models import DisiplinKurulKarar, DisiplinKurulu
from takip.disiplin_kurul_service import (
    ayar_kaydet,
    ayarlar_baglami,
    filtre_secenekleri,
    filtreli_kurullar,
    karar_durum_guncelle,
    karar_ekle,
    kontrol_merkezi,
    kurul_ayarlari,
    kurul_detay_verisi,
    kurul_durum_ilerlet,
    kurul_duzenleyebilir,
    kurul_gorebilir,
    kurul_olustur,
    kurul_tam_yetki,
    panel_istatistikleri,
    pdf_baglam,
    rapor_csv,
    rapor_ozet,
    seed_demo_kurul,
    varsayilan_gundem_kaydet,
    varsayilan_gundem_sil,
    varsayilan_gundem_pdf_baglam,
    varsayilan_katilimcilar,
    varsayilan_uye_kaydet,
    varsayilan_uye_sil,
    yetkili_kurullar,
)
from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_error_response
from takip.permissions.decorators import require_permission


def _kurul_erisim(user, pk: int) -> DisiplinKurulu:
    kurul = get_object_or_404(
        DisiplinKurulu.objects.select_related("talebe", "talebe__sinif_sube", "talebe__etut_hocasi"),
        pk=pk,
        arsivlandi=False,
    )
    if not yetkili_kurullar(user).filter(pk=pk).exists():
        raise Http404
    return kurul


@login_required
@require_permission("disiplin_kurulu", "view")
def disiplin_kurul_panel(request):
    if not kurul_gorebilir(request.user):
        raise Http404

    seed_demo_kurul(request.user)
    params = request.GET.copy()
    context = {
        "istatistikler": panel_istatistikleri(request.user),
        "kurullar": filtreli_kurullar(request.user, params),
        "kontrol": kontrol_merkezi(request.user),
        "filtreler": filtre_secenekleri(request.user),
        "secili": params,
        "duzenleyebilir": kurul_duzenleyebilir(request.user),
        "tam_yetki": kurul_tam_yetki(request.user),
        "kurul_adi": kurul_ayarlari().kurul_adi,
    }
    return render(request, "disiplin_kurul_panel.html", context)


@login_required
@require_permission("disiplin_kurulu", "view")
def disiplin_kurul_detay(request, pk: int):
    kurul = _kurul_erisim(request.user, pk)
    karar_form = DisiplinKurulKararForm()
    context = {
        **kurul_detay_verisi(request.user, kurul),
        "duzenleyebilir": kurul_duzenleyebilir(request.user),
        "tam_yetki": kurul_tam_yetki(request.user),
        "karar_form": karar_form,
        "durum_form": DisiplinKurulKararDurumForm(),
        "durum_secenekleri": DisiplinKurulu.Durum.choices,
    }
    return render(request, "disiplin_kurul_detay.html", context)


@login_required
@require_permission("disiplin_kurulu", "create")
def disiplin_kurul_olustur(request):
    ayar = kurul_ayarlari()
    form = DisiplinKurulOlusturForm(request.user, request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            kurul = kurul_olustur(
                request.user,
                {
                    "talebe_id": form.cleaned_data["talebe"].pk,
                    "kurul_turu": DisiplinKurulu.KurulTuru.ISTISARE_DISIPLIN,
                    "toplanti_tarihi": form.cleaned_data.get("toplanti_tarihi"),
                    "toplanti_saati": form.cleaned_data.get("toplanti_saati"),
                    "toplanti_yeri": form.cleaned_data.get("toplanti_yeri", ""),
                    "genel_aciklama": form.cleaned_data.get("genel_aciklama", ""),
                    "gundem": form.temiz_gundem(),
                },
                taslak=request.POST.get("action") == "taslak",
            )
            messages.success(
                request,
                f"{ayar.kurul_adi} toplantısı ({kurul.kurul_no}) oluşturuldu.",
            )
            return redirect("disiplin_kurul_detay", pk=kurul.pk)
        except (PermissionError, ValueError) as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "disiplin_kurul_olustur.html",
        {
            "form": form,
            "kurul_adi": ayar.kurul_adi,
            "varsayilan_uyeler": varsayilan_katilimcilar(),
            "tam_yetki": kurul_tam_yetki(request.user),
        },
    )


@login_required
@require_permission("disiplin_kurulu", "edit")
def disiplin_kurul_ayarlar(request):
    if not kurul_tam_yetki(request.user):
        messages.error(request, "Kurul ayarlarını yalnızca yönetici düzenleyebilir.")
        return redirect("disiplin_kurul_panel")

    baglam = ayarlar_baglami()
    ayar_form = DisiplinKurulAyarForm(
        request.POST or None,
        initial={
            "kurul_adi": baglam["ayar"].kurul_adi,
            "varsayilan_toplanti_yeri": baglam["ayar"].varsayilan_toplanti_yeri,
        },
    )
    uye_form = DisiplinKurulVarsayilanUyeForm(request.POST or None, prefix="uye")
    gundem_form = DisiplinKurulVarsayilanGundemForm(request.POST or None, prefix="gundem")

    if request.method == "POST":
        aksiyon = request.POST.get("aksiyon")

        if aksiyon == "ayar_kaydet" and ayar_form.is_valid():
            ayar_kaydet(
                kurul_adi=ayar_form.cleaned_data["kurul_adi"],
                varsayilan_yer=ayar_form.cleaned_data.get("varsayilan_toplanti_yeri", ""),
            )
            messages.success(request, "Kurul ayarları kaydedildi.")
            return redirect("disiplin_kurul_ayarlar")

        if aksiyon == "uye_kaydet" and uye_form.is_valid():
            uye_id = request.POST.get("uye_id") or None
            varsayilan_uye_kaydet(
                uye_id=int(uye_id) if uye_id else None,
                personel_id=uye_form.cleaned_data["personel"].pk,
                kurul_gorevi=uye_form.cleaned_data["kurul_gorevi"],
                sira=uye_form.cleaned_data.get("sira"),
                aktif=uye_form.cleaned_data.get("aktif", True),
            )
            messages.success(request, "Kurul üyesi kaydedildi.")
            return redirect("disiplin_kurul_ayarlar")

        if aksiyon == "uye_sil" and request.POST.get("uye_id"):
            varsayilan_uye_sil(int(request.POST["uye_id"]))
            messages.success(request, "Kurul üyesi silindi.")
            return redirect("disiplin_kurul_ayarlar")

        if aksiyon == "gundem_kaydet" and gundem_form.is_valid():
            madde_id = request.POST.get("madde_id") or None
            try:
                varsayilan_gundem_kaydet(
                    madde_id=int(madde_id) if madde_id else None,
                    baslik=gundem_form.cleaned_data["baslik"],
                    sira=gundem_form.cleaned_data.get("sira"),
                    aktif=gundem_form.cleaned_data.get("aktif", True),
                )
                messages.success(request, "Gündem maddesi kaydedildi.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect("disiplin_kurul_ayarlar")

        if aksiyon == "gundem_sil" and request.POST.get("madde_id"):
            varsayilan_gundem_sil(int(request.POST["madde_id"]))
            messages.success(request, "Gündem maddesi silindi.")
            return redirect("disiplin_kurul_ayarlar")

    return render(
        request,
        "disiplin_kurul_ayarlar.html",
        {
            **baglam,
            "ayar_form": ayar_form,
            "uye_form": uye_form,
            "gundem_form": gundem_form,
        },
    )


@login_required
@require_permission("disiplin_kurulu", "edit")
@require_POST
def disiplin_kurul_karar_ekle(request, pk: int):
    kurul = _kurul_erisim(request.user, pk)
    form = DisiplinKurulKararForm(request.POST)
    if form.is_valid():
        karar_ekle(
            request.user,
            kurul,
            {
                "metin": form.cleaned_data["metin"],
                "kategori": form.cleaned_data["kategori"],
                "sorumlu_id": form.cleaned_data["sorumlu"].pk if form.cleaned_data["sorumlu"] else None,
                "baslangic_tarihi": form.cleaned_data.get("baslangic_tarihi"),
                "kontrol_tarihi": form.cleaned_data.get("kontrol_tarihi"),
                "durum": form.cleaned_data["durum"],
                "iliskili_modul": form.cleaned_data["iliskili_modul"],
                "notlar": form.cleaned_data.get("notlar", ""),
            },
        )
        messages.success(request, "Karar eklendi.")
    else:
        messages.error(request, "Karar kaydedilemedi. Alanları kontrol edin.")
    return redirect("disiplin_kurul_detay", pk=pk)


@login_required
@require_permission("disiplin_kurulu", "edit")
@require_POST
def disiplin_kurul_karar_durum(request, pk: int, karar_pk: int):
    kurul = _kurul_erisim(request.user, pk)
    karar = get_object_or_404(DisiplinKurulKarar, pk=karar_pk, kurul=kurul, arsivlandi=False)
    if not kurul_tam_yetki(request.user) and karar.sorumlu_id != request.user.pk:
        messages.error(request, "Bu kararı güncelleme yetkiniz yok.")
        return redirect("disiplin_kurul_detay", pk=pk)

    form = DisiplinKurulKararDurumForm(request.POST)
    if form.is_valid():
        karar_durum_guncelle(
            request.user,
            karar,
            form.cleaned_data["durum"],
            form.cleaned_data.get("not_metni", ""),
        )
        messages.success(request, "Karar durumu güncellendi.")
    return redirect("disiplin_kurul_detay", pk=pk)


@login_required
@require_permission("disiplin_kurulu", "edit")
@require_POST
def disiplin_kurul_durum_ilerlet(request, pk: int):
    kurul = _kurul_erisim(request.user, pk)
    yeni = request.POST.get("durum")
    if yeni in dict(DisiplinKurulu.Durum.choices):
        kurul_durum_ilerlet(request.user, kurul, yeni)
        messages.success(request, "Kurul durumu güncellendi.")
    return redirect("disiplin_kurul_detay", pk=pk)


@login_required
@require_permission("disiplin_kurulu", "export_pdf")
def disiplin_kurul_gundem_pdf(request):
    if not kurul_tam_yetki(request.user):
        messages.error(request, "Gündem PDF için yönetici yetkisi gerekir.")
        return redirect("disiplin_kurul_ayarlar")

    baglam = varsayilan_gundem_pdf_baglam()
    html = render_to_string(
        "disiplin_kurul_gundem_pdf.html",
        baglam,
        request=request,
    )
    pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf:
        return pdf_error_response("PDF oluşturulamadı.")
    from django.utils.text import slugify

    ad = slugify(baglam["kurul_adi"]) or "kurul"
    return make_pdf_response(pdf, f"{ad}-gundem-sablonu.pdf")


@login_required
@require_permission("disiplin_kurulu", "export_pdf")
def disiplin_kurul_pdf(request, pk: int):
    kurul = _kurul_erisim(request.user, pk)
    html = render_to_string("disiplin_kurul_pdf.html", pdf_baglam(request.user, kurul), request=request)
    pdf = html_to_pdf(html)
    if not pdf:
        return pdf_error_response("PDF oluşturulamadı.")
    filename = f"{kurul.kurul_no.replace('/', '-')}_tutanak.pdf"
    if not kurul.tutanak_pdf:
        kurul.tutanak_pdf.save(filename, ContentFile(pdf), save=True)
        kurul.son_duzenleyen = request.user
        kurul.save(update_fields=["son_duzenleyen", "guncellenme"])
    return make_pdf_response(pdf, filename)


@login_required
@require_permission("disiplin_kurulu", "view")
def disiplin_kurul_arsiv(request):
    kurullar = (
        yetkili_kurullar(request.user)
        .filter(durum=DisiplinKurulu.Durum.SONUCLANDI)
        .order_by("-toplanti_tarihi")[:100]
    )
    return render(
        request,
        "disiplin_kurul_arsiv.html",
        {"kurullar": [k for k in kurullar], "duzenleyebilir": kurul_duzenleyebilir(request.user)},
    )


@login_required
@require_permission("disiplin_kurulu", "view")
def disiplin_kurul_rapor(request):
    form = DisiplinKurulRaporForm(request.user, request.GET or None)
    params = {}
    if form.is_valid():
        for key in ("tarih_bas", "tarih_bit"):
            val = form.cleaned_data.get(key)
            if val:
                params[key] = val.strftime("%Y-%m-%d")
    ozet = rapor_ozet(request.user, params)
    return render(
        request,
        "disiplin_kurul_rapor.html",
        {
            "form": form,
            "ozet": ozet,
            "duzenleyebilir": kurul_duzenleyebilir(request.user),
        },
    )


@login_required
@require_permission("disiplin_kurulu", "export_excel")
def disiplin_kurul_excel(request):
    from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit
    from django.utils.timezone import localdate

    params = {
        k: request.GET.get(k)
        for k in ("tarih_bas", "tarih_bit")
        if request.GET.get(k)
    }
    ozet = rapor_ozet(request.user, params)
    satirlar = [
        [
            k["kurul_no"],
            (k["talebe"] or "").upper(),
            k["sinif"],
            k["durum_etiket"],
            k["toplanti_tarihi"],
            k["karar_sayisi"],
        ]
        for k in ozet["kurullar"]
    ]
    icerik = basit_rapor_xlsx(
        baslik="Disiplin Kurulu Raporu",
        alt_baslik=localdate().strftime("%d.%m.%Y"),
        kolon_basliklari=["Kurul No", "Ad-Soyad", "Sınıf", "Durum", "Toplantı", "Karar Sayısı"],
        satirlar=satirlar,
        sayfa_adi="Disiplin",
        durum_kolonlari=[3],
        ortala_kolonlari=[0, 2, 4, 5],
        genislikler=[14, 26, 10, 14, 14, 12],
    )
    return excel_http_yanit(icerik, f"disiplin_kurul_rapor_{localdate():%Y%m%d}.xlsx")
