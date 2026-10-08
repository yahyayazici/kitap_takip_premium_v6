"""Deneme — yönetim (oluşturma, Excel, önizleme)."""

from __future__ import annotations

import csv
from io import StringIO

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from takip.deneme_excel import (
    deneme_excel_onizle,
    deneme_sonuclari_aktar,
    dosya_hash_hesapla,
    excel_zaten_yuklendi_mi,
    session_key,
    DenemeImportOnizleme,
)
from takip.deneme_optik import (
    OptikHata,
    alan_metni,
    anahtar_temizle,
    dagilim_coz,
    form_alanlarini_coz,
    harita_from_form,
    kazanim_listesi,
    kazanim_metni,
    optik_oku,
    optik_onizleme,
    optik_sorulari_yaz,
)
from takip.deneme_kazanim_excel import import_kazanim_excel
from takip.deneme_models import DenemeKazanimSonucu, DenemeSoruSonucu
from takip.deneme_soru_karne import import_soru_karneleri
from takip.deneme_service import (
    BRANS_ETIKETLERI,
    DENEME_DETAY_BRANSLAR,
    deneme_detay_satirlari,
    deneme_silebilir,
    deneme_sinavini_sil,
    deneme_sonuclari,
    deneme_yukleyebilir,
)
from takip.forms import DenemeSinaviForm
from takip.models import DenemeOptik, DenemeSinavi, OptikForm, OptikFormAlani, Talebe
from takip.permissions.service import can

from .yonetim_views import yonetici_gerekli


def _onizleme_yukle(request, deneme_id: int) -> DenemeImportOnizleme | None:
    data = request.session.get(session_key(deneme_id))
    if not data:
        return None
    return DenemeImportOnizleme.from_session(data)


def _onizleme_kaydet(request, deneme_id: int, onizleme: DenemeImportOnizleme) -> None:
    request.session[session_key(deneme_id)] = onizleme.to_session()
    request.session.modified = True


@yonetici_gerekli
def deneme_listesi(request):
    if not can(request.user, "deneme", "view"):
        messages.error(request, "Deneme modülüne erişim yok.")
        return redirect("yonetim:dashboard")

    from takip.deneme_service import deneme_arsiv_filtre_secenekleri, deneme_arsiv_filtrele

    denemeler = DenemeSinavi.objects.exclude(
        durum=DenemeSinavi.Durum.ARSIV
    ).select_related("egitim_yili").annotate(
        sonuc_sayisi=Count("sonuclar"),
    ).order_by("-sinav_tarihi", "-id")
    denemeler, filtre = deneme_arsiv_filtrele(denemeler, request.GET)

    return render(
        request,
        "yonetim/deneme_listesi.html",
        {
            "denemeler": denemeler,
            "yukleyebilir": deneme_yukleyebilir(request.user),
            "sil_yetkisi": deneme_silebilir(request.user),
            "filtre": filtre,
            **deneme_arsiv_filtre_secenekleri(),
        },
    )


@yonetici_gerekli
def deneme_ekle(request):
    if not deneme_yukleyebilir(request.user):
        messages.error(request, "Deneme oluşturma yetkiniz yok.")
        return redirect("yonetim:deneme_listesi")

    form = DenemeSinaviForm(request.POST or None)
    if form.is_valid():
        deneme = form.save(commit=False)
        deneme.olusturan = request.user
        if deneme.tur == DenemeSinavi.Tur.GRUP and not deneme.sira_no:
            from takip.deneme_service import sira_no_ata

            deneme.sira_no = sira_no_ata(deneme.egitim_yili, deneme.sinif_seviyesi)
        deneme.save()
        form.save_m2m()
        messages.success(request, "Deneme oluşturuldu. Excel yükleyebilirsiniz.")
        return redirect("yonetim:deneme_detay", pk=deneme.pk)

    return render(
        request,
        "yonetim/deneme_form.html",
        {"form": form, "baslik": "Yeni Deneme"},
    )


@yonetici_gerekli
def deneme_detay(request, pk):
    if not can(request.user, "deneme", "view"):
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    sonuclar = (
        list(deneme_sonuclari(request.user, deneme))
        if deneme.durum == "aktif"
        else []
    )

    if request.method == "POST" and request.FILES.get("excel"):
        if not deneme_yukleyebilir(request.user):
            messages.error(request, "Excel yükleme yetkiniz yok.")
            return redirect("yonetim:deneme_detay", pk=pk)

        dosya = request.FILES["excel"]
        dosya_hash = dosya_hash_hesapla(dosya)
        onizleme = deneme_excel_onizle(dosya)
        if onizleme.hatalar and not onizleme.satirlar:
            from takip.messages_util import hatalari_ozetle

            hatalari_ozetle(request, onizleme.hatalar, tek_baslik="Excel hatalı")
            return redirect("yonetim:deneme_detay", pk=pk)

        dosya.seek(0)
        deneme.excel_dosyasi = dosya
        if not deneme.toplam_soru:
            ilk_dolu = next((s for s in onizleme.satirlar if s.branslar), None)
            if ilk_dolu:
                deneme.toplam_soru = sum(
                    int(v.get("dogru", 0)) + int(v.get("yanlis", 0)) + int(v.get("bos", 0))
                    for v in ilk_dolu.branslar.values()
                )
        deneme.save(update_fields=["excel_dosyasi", "toplam_soru"])

        onizleme.dosya_hash = dosya_hash
        onizleme.dosya_adi = dosya.name or ""
        tekrar = excel_zaten_yuklendi_mi(deneme, dosya_hash)
        if tekrar:
            onizleme.tekrar_yukleme_uyarisi = (
                f"«{tekrar.dosya_adi or 'Bu dosya'}» {tekrar.olusturulma:%d.%m.%Y %H:%M} "
                "tarihinde bu denemeye zaten yüklenmiş görünüyor — yine de "
                "devam edebilirsiniz."
            )
            messages.warning(request, onizleme.tekrar_yukleme_uyarisi)

        _onizleme_kaydet(request, pk, onizleme)
        return redirect("yonetim:deneme_onizleme", pk=pk)

    return render(
        request,
        "yonetim/deneme_detay.html",
        {
            "deneme": deneme,
            "sonuclar": sonuclar,
            "detay_satirlari": deneme_detay_satirlari(sonuclar),
            "brans_etiketleri": BRANS_ETIKETLERI,
            "detay_branslar": DENEME_DETAY_BRANSLAR,
            "detay_brans_basliklari": [BRANS_ETIKETLERI[k] for k in DENEME_DETAY_BRANSLAR],
            "yukleyebilir": deneme_yukleyebilir(request.user),
            "optik_tanim": _optik_tanim(deneme),
            "optik_formlar": OptikForm.objects.all(),
            "sil_yetkisi": deneme_silebilir(request.user),
            "pdf_yetkisi": can(request.user, "deneme", "export_pdf"),
            "kazanim_satir": DenemeKazanimSonucu.objects.filter(deneme=deneme).count(),
            "kazanim_talebe": (
                DenemeKazanimSonucu.objects.filter(deneme=deneme)
                .values("talebe_id")
                .distinct()
                .count()
            ),
            "soru_satir": DenemeSoruSonucu.objects.filter(deneme=deneme).count(),
            "soru_talebe": (
                DenemeSoruSonucu.objects.filter(deneme=deneme)
                .values("talebe_id")
                .distinct()
                .count()
            ),
            "talebeler": (
                Talebe.objects.filter(aktif=True).order_by("ad_soyad")
                if deneme.durum == DenemeSinavi.Durum.AKTIF
                else []
            ),
        },
    )


@yonetici_gerekli
def deneme_sil(request, pk):
    if not deneme_silebilir(request.user):
        messages.error(request, "Deneme silme yetkiniz yok.")
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    if request.method != "POST":
        return redirect("yonetim:deneme_detay", pk=pk)
    ad = deneme.ad
    deneme_sinavini_sil(request.user, deneme)
    messages.success(request, f"«{ad}» arşive alındı. Sonuçlar ve kazanımlar duruyor.")
    return redirect("yonetim:deneme_listesi")


@yonetici_gerekli
def deneme_kazanim_yukle(request, pk):
    if not deneme_yukleyebilir(request.user):
        messages.error(request, "Kazanım Excel yükleme yetkiniz yok.")
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    if deneme.durum != DenemeSinavi.Durum.AKTIF:
        messages.error(
            request,
            "KonuKazanimDetay yalnızca aktif (Excel’i işlenmiş) denemelere yüklenebilir.",
        )
        return redirect("yonetim:deneme_detay", pk=pk)

    if request.method != "POST":
        return redirect("yonetim:deneme_detay", pk=pk)

    dosya = request.FILES.get("kazanim_excel")
    if not dosya:
        messages.error(request, "Excel dosyası seçin.")
        return redirect("yonetim:deneme_detay", pk=pk)
    if not (dosya.name or "").lower().endswith((".xlsx", ".xlsm")):
        messages.error(request, "Lütfen .xlsx formatında KonuKazanimDetay dosyası yükleyin.")
        return redirect("yonetim:deneme_detay", pk=pk)

    try:
        stats = import_kazanim_excel(dosya, deneme=deneme)
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Kazanım Excel işlenemedi: {exc}")
        return redirect("yonetim:deneme_detay", pk=pk)

    messages.success(
        request,
        f"Kazanım Excel yüklendi: {stats.sonuc_yazilan} satır, "
        f"{stats.eslesen_talebe} talebe, {stats.konu_sayisi} konu.",
    )
    for uyari in stats.uyari[:3]:
        messages.warning(request, uyari)
    try:
        from takip.ai_service import deneme_zekasi_analizi

        sonuclar = list(deneme_sonuclari(request.user, deneme))
        deneme_zekasi_analizi(request.user, deneme, sonuclar, yenile=True)
    except Exception:  # noqa: BLE001
        pass
    return redirect("yonetim:deneme_detay", pk=pk)


@yonetici_gerekli
def deneme_soru_yukle(request, pk):
    if not deneme_yukleyebilir(request.user):
        messages.error(request, "Soru karnesi yükleme yetkiniz yok.")
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    if deneme.durum != DenemeSinavi.Durum.AKTIF:
        messages.error(request, "Soru karnesi yalnızca aktif denemelere yüklenebilir.")
        return redirect("yonetim:deneme_detay", pk=pk)
    if request.method != "POST":
        return redirect("yonetim:deneme_detay", pk=pk)

    dosyalar = request.FILES.getlist("soru_karne")
    if not dosyalar:
        messages.error(request, "Karne dosyası seçin.")
        return redirect("yonetim:deneme_detay", pk=pk)
    for dosya in dosyalar:
        if not (dosya.name or "").lower().endswith((".pdf", ".xlsx", ".xlsm", ".zip")):
            messages.error(request, "PDF, Excel (.xlsx) veya zip yükleyin.")
            return redirect("yonetim:deneme_detay", pk=pk)

    try:
        stats = import_soru_karneleri(dosyalar, deneme=deneme)
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Soru karnesi işlenemedi: {exc}")
        return redirect("yonetim:deneme_detay", pk=pk)

    messages.success(
        request,
        f"Soru karnesi yüklendi: {stats.soru_yazilan} soru, "
        f"{stats.eslesen_talebe} talebe, {stats.ders_sayisi} ders.",
    )
    for uyari in stats.uyari[:3]:
        messages.warning(request, uyari)
    return redirect("yonetim:deneme_detay", pk=pk)


def _optik_tanim(deneme):
    try:
        return deneme.optik
    except DenemeOptik.DoesNotExist:
        return None


@yonetici_gerekli
def deneme_optik_tanim(request, pk):
    if not deneme_yukleyebilir(request.user):
        messages.error(request, "Optik tanım yetkiniz yok.")
        return redirect("yonetim:deneme_listesi")
    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    if request.method != "POST":
        return redirect("yonetim:deneme_detay", pk=pk)
    form = get_object_or_404(OptikForm, pk=request.POST.get("form_id") or 0)
    try:
        harita = harita_from_form(form)
        dagilim = dagilim_coz(request.POST.get("dagilim", ""), harita.sik_sayisi)
        anahtar_a = anahtar_temizle(
            request.POST.get("anahtar_a", ""),
            harita.sik_sayisi,
            kitapcik="A",
        )
        ham_b = request.POST.get("anahtar_b", "")
        anahtar_b = ""
        if "".join(ham_b.split()):
            anahtar_b = anahtar_temizle(ham_b, harita.sik_sayisi, kitapcik="B")
        kazanimlar = kazanim_listesi(request.POST.get("kazanimlar", ""), harita.sik_sayisi)
    except OptikHata as exc:
        messages.error(request, str(exc))
        return redirect("yonetim:deneme_detay", pk=pk)
    DenemeOptik.objects.update_or_create(
        deneme=deneme,
        defaults={
            "form": form,
            "anahtar_a": anahtar_a,
            "anahtar_b": anahtar_b,
            "dagilim": "\n".join(f"{kod} {adet}" for kod, adet in dagilim),
            "kazanimlar": kazanim_metni(kazanimlar),
        },
    )
    messages.success(request, f"Optik tanımı kaydedildi: {form.ad}.")
    return redirect("yonetim:deneme_detay", pk=pk)


@yonetici_gerekli
def deneme_optik_yukle(request, pk):
    if not deneme_yukleyebilir(request.user):
        messages.error(request, "Optik dosya yükleme yetkiniz yok.")
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    if request.method != "POST":
        return redirect("yonetim:deneme_detay", pk=pk)

    dosya = request.FILES.get("optik_dosya")
    if not dosya:
        messages.error(request, "Optik dosyası seçin (.dat).")
        return redirect("yonetim:deneme_detay", pk=pk)
    if dosya.size > 2_000_000:
        messages.error(request, "Optik dosyası 2 MB sınırını aşıyor.")
        return redirect("yonetim:deneme_detay", pk=pk)

    tanim = _optik_tanim(deneme)
    if tanim is None or not (tanim.anahtar_a or "").strip():
        messages.error(request, "Önce optik formunu ve cevap anahtarını kaydedin.")
        return redirect("yonetim:deneme_detay", pk=pk)

    try:
        harita = harita_from_form(tanim.form)
        optik = optik_oku(dosya.read(), harita)
        dagilim = dagilim_coz(tanim.dagilim, optik.cevap_sayisi)
        anahtar_b = tanim.anahtar_b or ""
        kazanimlar = kazanim_listesi(tanim.kazanimlar, optik.cevap_sayisi)
    except OptikHata as exc:
        messages.error(request, str(exc))
        return redirect("yonetim:deneme_detay", pk=pk)

    onizleme = optik_onizleme(
        optik, dagilim, tanim.anahtar_a, anahtar_b, kazanimlar
    )
    onizleme.dosya_hash = dosya_hash_hesapla(dosya)
    onizleme.dosya_adi = (dosya.name or "")[:255]
    tekrar = excel_zaten_yuklendi_mi(deneme, onizleme.dosya_hash)
    if tekrar:
        onizleme.tekrar_yukleme_uyarisi = (
            f"«{tekrar.dosya_adi or 'Bu dosya'}» {tekrar.olusturulma:%d.%m.%Y %H:%M} "
            "tarihinde bu denemeye zaten yüklenmiş görünüyor — yine de "
            "devam edebilirsiniz."
        )
        messages.warning(request, onizleme.tekrar_yukleme_uyarisi)
    _onizleme_kaydet(request, pk, onizleme)
    messages.success(
        request,
        f"{len(onizleme.satirlar)} optik satır okundu. Eşleşmeyi kontrol edip aktarın.",
    )
    return redirect("yonetim:deneme_onizleme", pk=pk)


@yonetici_gerekli
def optik_form_listesi(request):
    if not deneme_yukleyebilir(request.user):
        return redirect("yonetim:deneme_listesi")
    formlar = OptikForm.objects.prefetch_related("alanlar")
    return render(
        request,
        "yonetim/optik_form_listesi.html",
        {"formlar": formlar},
    )


@yonetici_gerekli
def optik_form_kaydet(request, pk=None):
    if not deneme_yukleyebilir(request.user):
        return redirect("yonetim:deneme_listesi")
    kayit = get_object_or_404(OptikForm, pk=pk) if pk else None
    if request.method == "POST" and request.POST.get("aksiyon") == "sil" and kayit:
        if kayit.denemeler.exists():
            messages.error(request, "Bu formu kullanan deneme var. Silinmez.")
            return redirect("yonetim:optik_form_kaydet", pk=kayit.pk)
        kayit.delete()
        messages.success(request, "Optik form silindi.")
        return redirect("yonetim:optik_form_listesi")

    posted = {
        "ad": (request.POST.get("ad") or (kayit.ad if kayit else "")).strip(),
        "aciklama": request.POST.get("aciklama") if request.method == "POST" else (kayit.aciklama if kayit else ""),
        "satir_uzunluk": request.POST.get("satir_uzunluk") if request.method == "POST" else (kayit.satir_uzunluk if kayit else ""),
        "kodlama": request.POST.get("kodlama") if request.method == "POST" else (kayit.kodlama if kayit else "cp1254"),
        "alanlar": request.POST.get("alanlar") if request.method == "POST" else (alan_metni(harita_from_form(kayit).alanlar) if kayit else ""),
    }
    if request.method == "POST" and request.POST.get("aksiyon") != "sil":
        try:
            uzunluk = int(posted["satir_uzunluk"] or 0)
        except ValueError:
            uzunluk = 0
        kodlama = posted["kodlama"] if posted["kodlama"] in {"cp1254", "utf-8"} else "cp1254"
        try:
            if not posted["ad"]:
                raise OptikHata("Formun adını yazın.")
            if OptikForm.objects.exclude(pk=getattr(kayit, "pk", None)).filter(ad=posted["ad"]).exists():
                raise OptikHata("Bu adda bir form zaten var.")
            alanlar = form_alanlarini_coz(posted["alanlar"], uzunluk)
        except OptikHata as exc:
            messages.error(request, str(exc))
        else:
            from django.db import transaction

            with transaction.atomic():
                if kayit is None:
                    kayit = OptikForm.objects.create(
                        ad=posted["ad"],
                        aciklama=(posted["aciklama"] or "").strip(),
                        satir_uzunluk=uzunluk,
                        kodlama=kodlama,
                    )
                else:
                    kayit.ad = posted["ad"]
                    kayit.aciklama = (posted["aciklama"] or "").strip()
                    kayit.satir_uzunluk = uzunluk
                    kayit.kodlama = kodlama
                    kayit.save()
                    kayit.alanlar.all().delete()
                OptikFormAlani.objects.bulk_create(
                    [
                        OptikFormAlani(
                            form=kayit,
                            tur=alan.tur,
                            baslangic=alan.baslangic,
                            bitis=alan.bitis,
                            sira=sira,
                        )
                        for sira, alan in enumerate(alanlar)
                    ]
                )
            messages.success(request, f"«{kayit.ad}» kaydedildi.")
            return redirect("yonetim:optik_form_listesi")

    return render(
        request,
        "yonetim/optik_form_form.html",
        {"kayit": kayit, "posted": posted},
    )


@yonetici_gerekli
def deneme_onizleme(request, pk):
    if not deneme_yukleyebilir(request.user):
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    onizleme = _onizleme_yukle(request, pk)
    if not onizleme:
        messages.error(request, "Önizleme verisi bulunamadı. Dosyayı tekrar yükleyin.")
        return redirect("yonetim:deneme_detay", pk=pk)

    if request.method == "POST":
        aksiyon = request.POST.get("aksiyon")
        satir_no = int(request.POST.get("satir_no") or 0)

        if aksiyon == "onayla" and satir_no:
            for satir in onizleme.satirlar:
                if satir.satir_no != satir_no:
                    continue
                hedef_id = request.POST.get("talebe_id") or satir.oneri_talebe_id
                if hedef_id:
                    satir.talebe_id = int(hedef_id)
                    satir.eslesme = "manuel"
                    satir.hatalar = []
                    messages.success(
                        request,
                        f"«{satir.excel_ad_soyad}» eşleştirmesi onaylandı.",
                    )
            _onizleme_kaydet(request, pk, onizleme)
            return redirect("yonetim:deneme_onizleme", pk=pk)

        if aksiyon == "atla" and satir_no:
            for satir in onizleme.satirlar:
                if satir.satir_no != satir_no:
                    continue
                satir.talebe_id = None
                satir.eslesme = "atla"
                satir.hatalar = []
                messages.info(
                    request,
                    f"«{satir.excel_ad_soyad}» atlandı (aktarılmayacak).",
                )
            _onizleme_kaydet(request, pk, onizleme)
            return redirect("yonetim:deneme_onizleme", pk=pk)

        if aksiyon == "eslestir":
            talebe_id = request.POST.get("talebe_id")
            for satir in onizleme.satirlar:
                if satir.satir_no == satir_no and talebe_id:
                    satir.talebe_id = int(talebe_id)
                    satir.eslesme = "manuel"
                    satir.hatalar = []
            _onizleme_kaydet(request, pk, onizleme)
            messages.success(request, "Eşleştirme kaydedildi.")
            return redirect("yonetim:deneme_onizleme", pk=pk)

        if aksiyon == "aktar":
            adet, hatalar = deneme_sonuclari_aktar(
                deneme,
                onizleme,
                request.user,
                dosya_hash=onizleme.dosya_hash,
                dosya_adi=onizleme.dosya_adi,
            )
            if hatalar and not adet:
                from takip.messages_util import hatalari_ozetle

                hatalari_ozetle(request, hatalar, tek_baslik="Aktarım hatası")
            elif adet:
                if onizleme.format == "optik":
                    optik_sorulari_yaz(deneme, onizleme)
                request.session.pop(session_key(pk), None)
                messages.success(request, f"{adet} öğrenci sonucu aktarıldı.")
                if hatalar:
                    for h in hatalar:
                        messages.warning(request, h)
                return redirect("yonetim:deneme_detay", pk=pk)

    talebeler = Talebe.objects.filter(aktif=True).order_by("ad_soyad")
    oneri_satirlari = [
        s for s in onizleme.satirlar if s.eslesme == "oneri" and not s.talebe_id
    ]
    eslesmeyen = [
        s
        for s in onizleme.satirlar
        if not s.talebe_id and s.eslesme not in {"oneri", "atla"}
    ]
    atlanan = [s for s in onizleme.satirlar if s.eslesme == "atla"]

    return render(
        request,
        "yonetim/deneme_onizleme.html",
        {
            "deneme": deneme,
            "onizleme": onizleme,
            "oneri_satirlari": oneri_satirlari,
            "eslesmeyen": eslesmeyen,
            "atlanan": atlanan,
            "talebeler": talebeler,
        },
    )


@yonetici_gerekli
def deneme_rapor(request):
    if not can(request.user, "deneme", "view"):
        return redirect("yonetim:deneme_listesi")

    if request.GET.get("format") == "excel" and can(request.user, "deneme", "export_excel"):
        return deneme_excel_export(request)

    deneme_id = request.GET.get("deneme")
    sinif_id = request.GET.get("sinif_sube")
    sonuclar = []
    if deneme_id:
        deneme = get_object_or_404(DenemeSinavi, pk=deneme_id)
        sonuclar = deneme_sonuclari(request.user, deneme)
        if sinif_id:
            sonuclar = sonuclar.filter(talebe__sinif_sube_id=sinif_id)

    return render(
        request,
        "yonetim/deneme_rapor.html",
        {
            "denemeler": DenemeSinavi.objects.filter(durum="aktif").order_by("-sinav_tarihi"),
            "sonuclar": sonuclar[:300],
            "filtre": {"deneme": deneme_id or "", "sinif_sube": sinif_id or ""},
        },
    )


@yonetici_gerekli
def deneme_excel_export(request):
    from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit

    deneme_id = request.GET.get("deneme")
    if not deneme_id:
        return redirect("yonetim:deneme_rapor")

    deneme = get_object_or_404(DenemeSinavi, pk=deneme_id)
    sonuclar = deneme_sonuclari(request.user, deneme)

    satirlar = [
        [
            sira,
            (sonuc.talebe.ad_soyad or "").upper(),
            str(sonuc.talebe.sinif_sube or ""),
            str(sonuc.toplam_net).replace(".", ","),
            str(sonuc.puan).replace(".", ","),
        ]
        for sira, sonuc in enumerate(sonuclar, start=1)
    ]
    icerik = basit_rapor_xlsx(
        baslik=f"Deneme Sıralama — {deneme.ad}",
        alt_baslik=str(getattr(deneme, "tarih", "") or ""),
        kolon_basliklari=["Sıra", "Ad-Soyad", "Sınıf", "Toplam Net", "Puan"],
        satirlar=satirlar,
        sayfa_adi="Deneme",
        vurgu_kolonlari=[4],
        ortala_kolonlari=[0, 2, 3],
        genislikler=[8, 28, 12, 12, 12],
    )
    return excel_http_yanit(icerik, f"deneme_{deneme.pk}_siralama.xlsx")


@yonetici_gerekli
def deneme_yonetici_ozeti(request):
    if not can(request.user, "deneme", "view"):
        messages.error(request, "Deneme modülüne erişim yok.")
        return redirect("yonetim:dashboard")

    from takip.deneme_yonetim_ozet_service import yonetici_deneme_ozeti

    sinif_seviyesi = (request.GET.get("sinif_seviyesi") or "").strip()
    ozet = yonetici_deneme_ozeti(sinif_seviyesi)
    return render(
        request,
        "yonetim/deneme_yonetici_ozeti.html",
        {"ozet": ozet, "sinif_seviyesi": sinif_seviyesi},
    )
