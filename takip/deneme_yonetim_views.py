"""Deneme — yönetim (oluşturma, Excel, önizleme)."""

from __future__ import annotations

import csv
from io import StringIO

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from decimal import Decimal

from takip.deneme_excel import (
    deneme_excel_onizle,
    deneme_sonuclari_aktar,
    session_key,
    DenemeImportOnizleme,
)
from takip.deneme_gap_pdf import (
    deneme_zayif_konular,
    gap_raporu_eslestir,
    gap_raporu_kaydet,
)
from takip.deneme_models import DenemeGapRaporu
from takip.deneme_service import (
    BRANS_ETIKETLERI,
    DENEME_DETAY_BRANSLAR,
    deneme_detay_satirlari,
    deneme_sonuclari,
    deneme_yukleyebilir,
)
from takip.forms import DenemeSinaviForm
from takip.models import DenemeSinavi, Talebe
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

    denemeler = DenemeSinavi.objects.annotate(
        sonuc_sayisi=Count("sonuclar"),
    ).order_by("-sinav_tarihi", "-id")
    return render(
        request,
        "yonetim/deneme_listesi.html",
        {
            "denemeler": denemeler,
            "yukleyebilir": deneme_yukleyebilir(request.user),
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
        deneme.save()
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
        if deneme.durum == DenemeSinavi.Durum.AKTIF:
            messages.error(request, "Aktif denemeye tekrar Excel yüklenemez.")
            return redirect("yonetim:deneme_detay", pk=pk)

        onizleme = deneme_excel_onizle(request.FILES["excel"])
        if onizleme.hatalar and not onizleme.satirlar:
            from takip.messages_util import hatalari_ozetle

            hatalari_ozetle(request, onizleme.hatalar, tek_baslik="Excel hatalı")
            return redirect("yonetim:deneme_detay", pk=pk)

        _onizleme_kaydet(request, pk, onizleme)
        return redirect("yonetim:deneme_onizleme", pk=pk)

    gap_raporlari = []
    zayif_konular = []
    if deneme.durum == DenemeSinavi.Durum.AKTIF:
        gap_raporlari = list(
            deneme.gap_raporlari.select_related("talebe")
            .prefetch_related("konu_satirlari")
            .order_by("-olusturulma")[:80]
        )
        zayif_konular = deneme_zayif_konular(deneme, esik=Decimal("70"), limit=30)

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
            "gap_raporlari": gap_raporlari,
            "zayif_konular": zayif_konular,
            "gap_bekleyen": sum(
                1
                for r in gap_raporlari
                if r.durum == DenemeGapRaporu.Durum.ESLESME_BEKLIYOR
            ),
            "talebeler": (
                Talebe.objects.filter(aktif=True).order_by("ad_soyad")
                if deneme.durum == DenemeSinavi.Durum.AKTIF
                else []
            ),
        },
    )


@yonetici_gerekli
def deneme_gap_yukle(request, pk):
    if not deneme_yukleyebilir(request.user):
        messages.error(request, "Gap raporu yükleme yetkiniz yok.")
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    if deneme.durum != DenemeSinavi.Durum.AKTIF:
        messages.error(
            request,
            "Gap / konu raporu yalnızca Excel aktarılmış (aktif) denemelere yüklenebilir.",
        )
        return redirect("yonetim:deneme_detay", pk=pk)

    if request.method != "POST":
        return redirect("yonetim:deneme_detay", pk=pk)

    dosyalar = request.FILES.getlist("gap_pdf")
    if not dosyalar:
        messages.error(request, "En az bir PDF seçin.")
        return redirect("yonetim:deneme_detay", pk=pk)

    ok = 0
    bekleyen = 0
    hatali = 0
    for dosya in dosyalar:
        ad = (dosya.name or "gap.pdf").lower()
        if not ad.endswith(".pdf"):
            hatali += 1
            messages.warning(request, f"«{dosya.name}» PDF değil, atlandı.")
            continue
        try:
            icerik = dosya.read()
            rapor = gap_raporu_kaydet(
                deneme,
                icerik,
                dosya.name or "gap.pdf",
                yukleyen=request.user,
            )
        except Exception as exc:  # noqa: BLE001
            hatali += 1
            messages.error(request, f"«{dosya.name}» işlenemedi: {exc}")
            continue

        if rapor.durum == DenemeGapRaporu.Durum.ISLENDI:
            ok += 1
        elif rapor.durum == DenemeGapRaporu.Durum.ESLESME_BEKLIYOR:
            bekleyen += 1
        else:
            hatali += 1
            if rapor.hata_mesaji:
                messages.warning(
                    request,
                    f"«{dosya.name}»: {rapor.hata_mesaji}",
                )

    if ok:
        messages.success(request, f"{ok} Gap raporu işlendi ve eşleştirildi.")
        try:
            from takip.ai_service import deneme_zekasi_analizi

            sonuclar = list(deneme_sonuclari(request.user, deneme))
            deneme_zekasi_analizi(request.user, deneme, sonuclar, yenile=True)
        except Exception:  # noqa: BLE001
            pass
    if bekleyen:
        messages.info(
            request,
            f"{bekleyen} raporda isim onayı bekleniyor — aşağıdan eşleştirin.",
        )
    if hatali and not ok and not bekleyen:
        messages.error(request, "Hiçbir Gap raporu işlenemedi.")

    return redirect("yonetim:deneme_detay", pk=pk)


@yonetici_gerekli
def deneme_gap_eslestir(request, pk, rapor_id):
    if not deneme_yukleyebilir(request.user):
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    rapor = get_object_or_404(DenemeGapRaporu, pk=rapor_id, deneme=deneme)

    if request.method != "POST":
        return redirect("yonetim:deneme_detay", pk=pk)

    talebe_id = request.POST.get("talebe_id") or rapor.oneri_talebe_id
    if not talebe_id:
        messages.error(request, "Talebe seçin.")
        return redirect("yonetim:deneme_detay", pk=pk)

    try:
        gap_raporu_eslestir(rapor, int(talebe_id))
        messages.success(
            request,
            f"«{rapor.ham_ad or rapor.dosya_adi}» eşleştirildi.",
        )
        try:
            from takip.ai_service import deneme_zekasi_analizi

            sonuclar = list(deneme_sonuclari(request.user, deneme))
            deneme_zekasi_analizi(request.user, deneme, sonuclar, yenile=True)
        except Exception:  # noqa: BLE001
            pass
    except ValueError as exc:
        messages.error(request, str(exc))

    return redirect("yonetim:deneme_detay", pk=pk)


@yonetici_gerekli
def deneme_gap_sil(request, pk, rapor_id):
    if not deneme_yukleyebilir(request.user):
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    rapor = get_object_or_404(DenemeGapRaporu, pk=rapor_id, deneme=deneme)
    if request.method == "POST":
        ad = rapor.ham_ad or rapor.dosya_adi
        rapor.delete()
        messages.success(request, f"«{ad}» Gap raporu silindi.")
    return redirect("yonetim:deneme_detay", pk=pk)


@yonetici_gerekli
def deneme_onizleme(request, pk):
    if not deneme_yukleyebilir(request.user):
        return redirect("yonetim:deneme_listesi")

    deneme = get_object_or_404(DenemeSinavi, pk=pk)
    onizleme = _onizleme_yukle(request, pk)
    if not onizleme:
        messages.error(request, "Önizleme verisi bulunamadı. Excel'i tekrar yükleyin.")
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
            adet, hatalar = deneme_sonuclari_aktar(deneme, onizleme, request.user)
            if hatalar and not adet:
                from takip.messages_util import hatalari_ozetle

                hatalari_ozetle(request, hatalar, tek_baslik="Aktarım hatası")
            elif adet:
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
