"""Sözel–sayısal deneme panel görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate
from django.utils.text import slugify

from takip.ktt_service import ktt_tam_yetki
from takip.pdf_utils import (
    coz_pdf_sayfa,
    html_to_pdf,
    make_pdf_response,
    pdf_engine_status,
    pdf_error_response,
)
from takip.permissions.decorators import require_permission
from takip.permissions.service import can
from takip.ss_deneme_forms import SozelSayisalDenemeForm
from takip.ss_deneme_models import (
    BRANS_ETIKETLERI,
    SAYISAL_BRANSLAR,
    SOZEL_BRANSLAR,
    TUM_BRANSLAR,
    SozelSayisalBransSonuc,
    SozelSayisalDeneme,
    SozelSayisalSonuc,
    brans_soru_sayisi,
)
from takip.ss_deneme_service import (
    bolum_etiket,
    bolum_kodlari,
    brans_map,
    sonuc_katildi,
    sonuc_toplamlari_guncelle,
    sirali_satirlar,
    ss_deneme_sonucu_soru_takibe_yansit,
    ss_duzenleyebilir,
    ss_hedef_siniflar_kaydet,
    ss_olusturabilir,
    ss_silebilir,
    ss_sinif_secenekleri,
    ss_sinif_secimlerini_dogrula,
    ss_sonuc_talebeleri,
    yetkili_ss_denemeler,
)
from takip.user_helpers import etut_hocasi_for_user


def _form_for_user(user, data=None, instance=None, liste_modu=False, initial=None):
    kwargs = {"admin_modu": ktt_tam_yetki(user), "liste_modu": liste_modu}
    if initial is not None:
        kwargs["initial"] = initial
    form = SozelSayisalDenemeForm(data, instance=instance, **kwargs)
    if ktt_tam_yetki(user) and "etut_hocasi" in form.fields and not liste_modu:
        from takip.models import EtutHocasi

        form.fields["etut_hocasi"].queryset = EtutHocasi.objects.filter(
            aktif=True
        ).order_by("ad_soyad")
    return form


def _olustur_kaydet(request, form, sinif_etiketleri):
    hoca = etut_hocasi_for_user(request.user)
    deneme = form.save(commit=False)
    if hoca:
        deneme.etut_hocasi = hoca
    elif not deneme.etut_hocasi_id:
        return None, "Etüt hocası seçilmelidir."

    if sinif_etiketleri:
        ss_hedef_siniflar_kaydet(deneme, sinif_etiketleri)
    else:
        ss_hedef_siniflar_kaydet(deneme, [])
        if not deneme.hedef_siniflar and not deneme.sinif_seviyesi:
            return None, "En az bir sınıf seçin."

    deneme.olusturan = request.user
    deneme.save()
    return deneme, None


def _bolum_param(request) -> str:
    bolum = (request.GET.get("bolum") or "hepsi").strip().lower()
    if bolum not in {"sozel", "sayisal", "hepsi"}:
        return "hepsi"
    return bolum


def _post_int(post, key: str) -> int:
    raw = post.get(key, "0")
    try:
        return max(0, int(str(raw).strip() or "0"))
    except (TypeError, ValueError):
        return 0


@login_required
@require_permission("ktt", "view")
def ss_deneme_listesi(request):
    hoca = etut_hocasi_for_user(request.user)
    olusturabilir = ss_olusturabilir(request.user)
    form = None

    if request.method == "POST" and olusturabilir:
        if not hoca and not ktt_tam_yetki(request.user):
            messages.error(request, "Etüt hocası kaydınız bulunamadı.")
            return redirect("ss_deneme_listesi")

        form = _form_for_user(request.user, request.POST, liste_modu=True)
        sinif_etiketleri, sinif_hata = ss_sinif_secimlerini_dogrula(
            request.user,
            request.POST.getlist("sinif_subeler"),
        )
        if sinif_hata:
            messages.error(request, sinif_hata)
        elif form.is_valid():
            deneme, hata = _olustur_kaydet(request, form, sinif_etiketleri)
            if hata:
                messages.error(request, hata)
            else:
                messages.success(request, f"{deneme.ad} oluşturuldu.")
                return redirect("ss_deneme_sonuc_gir", pk=deneme.pk)
    elif olusturabilir:
        form = _form_for_user(
            request.user,
            initial={"sinav_tarihi": localdate(), "soru_formati": 90, "sinif_seviyesi": "7"},
            liste_modu=True,
        )

    sinavlar = list(yetkili_ss_denemeler(request.user))
    for deneme in sinavlar:
        deneme.silebilir = ss_silebilir(request.user, deneme)

    return render(
        request,
        "ss_deneme_listesi.html",
        {
            "sinavlar": sinavlar,
            "form": form,
            "olusturabilir": olusturabilir,
            "sinif_secenekleri": ss_sinif_secenekleri(request.user),
        },
    )


@login_required
@require_permission("ktt", "edit")
def ss_deneme_sonuc_gir(request, pk):
    deneme = get_object_or_404(yetkili_ss_denemeler(request.user), pk=pk)
    if not ss_duzenleyebilir(request.user, deneme):
        messages.error(request, "Bu deneme için sonuç giremezsiniz.")
        return redirect("ss_deneme_listesi")

    talebeler = list(ss_sonuc_talebeleri(request.user, deneme))
    dagilim = {kod: brans_soru_sayisi(deneme, kod) for kod in TUM_BRANSLAR}

    if request.method == "POST":
        hatalar = []
        kaydedilen = 0
        with transaction.atomic():
            for talebe in talebeler:
                onceki = (
                    SozelSayisalSonuc.objects.filter(deneme=deneme, talebe=talebe)
                    .prefetch_related("brans_satirlari")
                    .first()
                )
                onceki_brans = {
                    b.brans: (int(b.dogru), int(b.yanlis), int(b.bos))
                    for b in (onceki.brans_satirlari.all() if onceki else [])
                }

                yeni_brans = {}
                satir_hata = None
                hepsi_bos = True
                for kod in TUM_BRANSLAR:
                    hedef = dagilim[kod]
                    dogru = _post_int(request.POST, f"{kod}_{talebe.id}_dogru")
                    yanlis = _post_int(request.POST, f"{kod}_{talebe.id}_yanlis")
                    if dogru + yanlis > hedef:
                        satir_hata = (
                            f"{talebe.ad_soyad}: {BRANS_ETIKETLERI[kod]} "
                            f"doğru + yanlış {hedef} soruyu aşamaz."
                        )
                        break
                    bos = max(0, hedef - dogru - yanlis)
                    yeni_brans[kod] = (dogru, yanlis, bos)
                    if dogru or yanlis:
                        hepsi_bos = False

                if satir_hata:
                    hatalar.append(satir_hata)
                    continue

                if hepsi_bos:
                    if onceki:
                        onceki.delete()
                        ss_deneme_sonucu_soru_takibe_yansit(
                            user=request.user,
                            deneme=deneme,
                            talebe=talebe,
                            onceki_brans=onceki_brans,
                            silindi=True,
                        )
                    continue

                sonuc, _ = SozelSayisalSonuc.objects.update_or_create(
                    deneme=deneme,
                    talebe=talebe,
                    defaults={"kaydeden": request.user},
                )
                for kod, (dogru, yanlis, bos) in yeni_brans.items():
                    SozelSayisalBransSonuc.objects.update_or_create(
                        sonuc=sonuc,
                        brans=kod,
                        defaults={"dogru": dogru, "yanlis": yanlis, "bos": bos},
                    )
                sonuc_toplamlari_guncelle(sonuc)
                ss_deneme_sonucu_soru_takibe_yansit(
                    user=request.user,
                    deneme=deneme,
                    talebe=talebe,
                    yeni_brans=yeni_brans,
                    onceki_brans=onceki_brans,
                )
                kaydedilen += 1

            if hatalar:
                transaction.set_rollback(True)

        if hatalar:
            from takip.messages_util import hatalari_ozetle

            hatalari_ozetle(request, hatalar, tek_baslik="Sonuç kaydı hatalı")
        else:
            messages.success(
                request,
                f"{kaydedilen} öğrenci sonucu kaydedildi; "
                f"günlük soru takibe işlendi ({deneme.sinav_tarihi:%d.%m.%Y}).",
            )
            return redirect("ss_deneme_sonuc_gir", pk=deneme.pk)

    mevcut = {
        s.talebe_id: s
        for s in SozelSayisalSonuc.objects.filter(
            deneme=deneme, talebe__in=talebeler
        ).prefetch_related("brans_satirlari")
    }
    satirlar = []
    for talebe in talebeler:
        sonuc = mevcut.get(talebe.id)
        bmap = brans_map(sonuc)
        hucreler = []
        for kod in TUM_BRANSLAR:
            hedef = dagilim[kod]
            br = bmap.get(kod)
            hucreler.append(
                {
                    "kod": kod,
                    "etiket": BRANS_ETIKETLERI[kod],
                    "hedef": hedef,
                    "dogru": br.dogru if br else 0,
                    "yanlis": br.yanlis if br else 0,
                    "bos": br.bos if br else hedef,
                    "net": br.net if br else 0,
                    "bolum": "sozel" if kod in SOZEL_BRANSLAR else "sayisal",
                }
            )
        satirlar.append(
            {
                "talebe": talebe,
                "sonuc": sonuc,
                "hucreler": hucreler,
                "katilmayan": not sonuc_katildi(sonuc, deneme),
            }
        )

    return render(
        request,
        "ss_deneme_sonuc_gir.html",
        {
            "deneme": deneme,
            "satirlar": satirlar,
            "sozel_branslar": SOZEL_BRANSLAR,
            "sayisal_branslar": SAYISAL_BRANSLAR,
            "dagilim": dagilim,
            "brans_etiketleri": BRANS_ETIKETLERI,
            "silebilir": ss_silebilir(request.user, deneme),
            "pdf_yetkisi": can(request.user, "ktt", "export_pdf"),
        },
    )


@login_required
@require_permission("ktt", "view")
def ss_deneme_detay(request, pk):
    deneme = get_object_or_404(yetkili_ss_denemeler(request.user), pk=pk)
    bolum = _bolum_param(request)
    satirlar, kolonlar = sirali_satirlar(request.user, deneme, bolum)
    return render(
        request,
        "ss_deneme_detay.html",
        {
            "deneme": deneme,
            "satirlar": satirlar,
            "kolonlar": kolonlar,
            "bolum": bolum,
            "bolum_etiket": bolum_etiket(bolum),
            "silebilir": ss_silebilir(request.user, deneme),
            "pdf_yetkisi": can(request.user, "ktt", "export_pdf"),
            "duzenleyebilir": ss_duzenleyebilir(request.user, deneme),
        },
    )


@login_required
@require_permission("ktt", "view")
def ss_deneme_sil(request, pk):
    deneme = get_object_or_404(yetkili_ss_denemeler(request.user), pk=pk)
    if not ss_silebilir(request.user, deneme):
        messages.error(request, "Bu denemeyi silemezsiniz.")
        return redirect("ss_deneme_listesi")
    if request.method != "POST":
        return redirect("ss_deneme_detay", pk=deneme.pk)
    ad = deneme.ad
    sonuclar = list(
        SozelSayisalSonuc.objects.filter(deneme=deneme).prefetch_related(
            "brans_satirlari", "talebe"
        )
    )
    for sonuc in sonuclar:
        onceki_brans = {
            b.brans: (int(b.dogru), int(b.yanlis), int(b.bos))
            for b in sonuc.brans_satirlari.all()
        }
        ss_deneme_sonucu_soru_takibe_yansit(
            user=request.user,
            deneme=deneme,
            talebe=sonuc.talebe,
            onceki_brans=onceki_brans,
            silindi=True,
        )
    deneme.delete()
    messages.success(request, f"{ad} silindi.")
    return redirect("ss_deneme_listesi")


def _pdf_yanit(request, html, dosya_adi: str):
    pdf_verisi = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )
    return make_pdf_response(pdf_verisi, dosya_adi)


@login_required
@require_permission("ktt", "export_pdf")
def ss_deneme_detay_pdf(request, pk):
    deneme = get_object_or_404(yetkili_ss_denemeler(request.user), pk=pk)
    bolum = _bolum_param(request)
    satirlar, kolonlar = sirali_satirlar(request.user, deneme, bolum)
    pdf_sayfa = coz_pdf_sayfa(request)
    html = render(
        request,
        "ss_deneme_detay_pdf.html",
        {
            "deneme": deneme,
            "satirlar": satirlar,
            "kolonlar": kolonlar,
            "bolum": bolum,
            "bolum_etiket": bolum_etiket(bolum),
            "pdf_sayfa": pdf_sayfa,
        },
    ).content.decode("utf-8")
    ad = (deneme.ad or "").strip() or f"SS Deneme {deneme.pk}"
    suffix = {"sozel": "_sozel", "sayisal": "_sayisal"}.get(bolum, "")
    return _pdf_yanit(request, html, f"{ad}{suffix}.pdf")


@login_required
@require_permission("ktt", "export_pdf")
def ss_deneme_bireysel_pdf(request, pk, talebe_id=None):
    deneme = get_object_or_404(yetkili_ss_denemeler(request.user), pk=pk)
    bolum = _bolum_param(request)
    satirlar, kolonlar = sirali_satirlar(request.user, deneme, "hepsi")
    if not satirlar:
        messages.error(request, "Bu denemeye ait sonuç bulunamadı.")
        return redirect("ss_deneme_detay", pk=deneme.pk)

    if talebe_id is not None:
        satirlar = [s for s in satirlar if s["talebe"].id == int(talebe_id)]
        if not satirlar:
            messages.error(request, "Talebe sonucu bulunamadı.")
            return redirect("ss_deneme_detay", pk=deneme.pk)

    if bolum != "hepsi":
        kodlar = set(bolum_kodlari(bolum))
        kolonlar = [k for k in kolonlar if k["kod"] in kodlar]
        for satir in satirlar:
            satir["hucreler"] = [h for h in satir["hucreler"] if h["kod"] in kodlar]

    html = render(
        request,
        "ss_deneme_bireysel_pdf.html",
        {
            "deneme": deneme,
            "satirlar": satirlar,
            "kolonlar": kolonlar,
            "bolum": bolum,
            "bolum_etiket": bolum_etiket(bolum),
            "sozel_branslar": SOZEL_BRANSLAR,
            "sayisal_branslar": SAYISAL_BRANSLAR,
        },
    ).content.decode("utf-8")
    safe = slugify(deneme.ad) or f"ss_deneme_{deneme.pk}"
    suffix = f"_t{talebe_id}" if talebe_id else "_tum"
    bolum_ek = {"sozel": "_sozel", "sayisal": "_sayisal"}.get(bolum, "")
    return _pdf_yanit(
        request,
        html,
        f"{safe}_bireysel{bolum_ek}{suffix}_{localdate():%Y%m%d}.pdf",
    )
