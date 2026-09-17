"""Dijital Duyuru Ekranı — yönetim paneli görünümleri."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Prefetch, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from takip.ekran_forms import (
    AcilDuyuruForm,
    CihazDuzenleForm,
    CihazEslestirmeForm,
    KonumForm,
    OynatmaListesiForm,
    TasarimForm,
    YayinPlaniForm,
)
from takip.ekran_media_service import (
    MedyaHatasi,
    medya_silinebilir_mi,
    medya_yukle,
)
from takip.ekran_models import (
    EkranAcilDuyuru,
    EkranCihaz,
    EkranCihazOlayi,
    EkranIslemKaydi,
    EkranKonumu,
    EkranMedya,
    EkranMedyaKlasoru,
    EkranOynatmaListesi,
    EkranOynatmaOgesi,
    EkranOynatmaRaporu,
    EkranProje,
    EkranProjeSurumu,
    EkranSablon,
    EkranSahne,
    EkranYayinHedefi,
    EkranYayinPaketi,
    EkranYayinPlani,
)
from takip.ekran_service import (
    YayinHatasi,
    pano_getir,
    pano_yayin_durumu,
    panoyu_ekranlara_gonder,
    cakisan_planlar,
    islem_kaydet,
    istek_ip,
    oge_katalogu_verisi,
    paket_derle,
    proje_verisi,
    sahne_getir,
    sahne_kaydet,
    sahne_verisi,
    surum_geri_yukle,
    surum_olustur,
    uygun_planlar,
)
from takip.ekran_viewer_views import VARLIK_SURUMU
from takip.permissions.decorators import require_permission
from takip.permissions.service import can

SAYFA_BOYUTU = 24


def _yetki(request, islem: str) -> bool:
    return can(request.user, "ekran", islem)


def _temel_baglam(request, **ek) -> dict:
    """Her ekran sayfasının paylaştığı bağlam — üst menü ve yetki bayrakları."""
    baglam = {
        "aktif_bolum": "",
        "varlik_surumu": VARLIK_SURUMU,
        "yetki_duzenle": _yetki(request, "edit"),
        "yetki_yayin": _yetki(request, "publish"),
        "yetki_plan": _yetki(request, "schedule"),
        "yetki_acil": _yetki(request, "emergency"),
        "yetki_cihaz": _yetki(request, "manage_device"),
        "yetki_medya": _yetki(request, "upload_media"),
        "yetki_sablon": _yetki(request, "manage_template"),
        "yetki_sil": _yetki(request, "delete"),
        "yetki_gecmis": _yetki(request, "view_history"),
    }
    baglam.update(ek)
    return baglam


def _json_govde(request) -> dict:
    try:
        veri = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return veri if isinstance(veri, dict) else {}


# ---------------------------------------------------------------------------
# Genel bakış
# ---------------------------------------------------------------------------


@login_required
@require_permission("ekran", "view")
def dashboard(request):
    """Modülün giriş ekranı = panonun kendisi.

    Kullanıcı panele girdiğinde liste, özet ya da menü değil, doğrudan
    çalışma alanını görmeli: üstüne içerik sürükleyip ekranlara gönderdiği
    beyaz tahtayı. Eski özet ekranı ``ozet`` adresine taşındı.
    """
    proje = pano_getir(kullanici=request.user)
    return redirect("ekran:pano", pk=proje.pk)


@login_required
@require_permission("ekran", "view")
def ozet(request):
    cihazlar = list(
        EkranCihaz.objects.select_related("konum").exclude(durum=EkranCihaz.Durum.BEKLIYOR)
    )
    cevrimici = [c for c in cihazlar if c.cevrimici_mi]

    acil = (
        EkranAcilDuyuru.objects.filter(aktif=True)
        .order_by("-baslangic")
        .first()
    )

    baglam = _temel_baglam(
        request,
        aktif_bolum="ozet",
        cihaz_sayisi=len(cihazlar),
        cevrimici_sayisi=len(cevrimici),
        cevrimdisi_sayisi=len(cihazlar) - len(cevrimici),
        bekleyen_cihaz=EkranCihaz.objects.filter(durum=EkranCihaz.Durum.BEKLIYOR).count(),
        aktif_yayinlar=(
            EkranYayinPlani.objects.filter(durum=EkranYayinPlani.Durum.YAYINDA)
            .select_related("liste", "aktif_paket")
            .order_by("-oncelik")[:6]
        ),
        son_tasarimlar=EkranProje.objects.exclude(durum=EkranProje.Durum.ARSIV).order_by(
            "-guncellenme"
        )[:6],
        acil_duyuru=acil if (acil and acil.yayinda_mi) else None,
        medya_sayisi=EkranMedya.objects.count(),
        son_olaylar=EkranCihazOlayi.objects.select_related("cihaz__konum")[:8],
    )
    return render(request, "ekran/dashboard.html", baglam)


# ---------------------------------------------------------------------------
# Tasarımlar
# ---------------------------------------------------------------------------


@login_required
@require_permission("ekran", "view")
def tasarim_listesi(request):
    arama = (request.GET.get("q") or "").strip()
    durum = (request.GET.get("durum") or "").strip()

    sorgu = EkranProje.objects.annotate(sahne_sayisi=Count("sahneler")).select_related(
        "olusturan", "son_duzenleyen"
    )
    if arama:
        sorgu = sorgu.filter(Q(ad__icontains=arama) | Q(aciklama__icontains=arama))
    if durum in dict(EkranProje.Durum.choices):
        sorgu = sorgu.filter(durum=durum)

    sayfalar = Paginator(sorgu.order_by("-guncellenme"), SAYFA_BOYUTU)
    sayfa = sayfalar.get_page(request.GET.get("sayfa"))

    return render(
        request,
        "ekran/tasarim_listesi.html",
        _temel_baglam(
            request,
            aktif_bolum="tasarimlar",
            sayfa=sayfa,
            arama=arama,
            durum=durum,
            durum_secenekleri=EkranProje.Durum.choices,
            form=TasarimForm(),
        ),
    )


@login_required
@require_permission("ekran", "create")
def tasarim_olustur(request):
    if request.method != "POST":
        return redirect("ekran:tasarim_listesi")

    form = TasarimForm(request.POST)
    if not form.is_valid():
        for hatalar in form.errors.values():
            for hata in hatalar:
                messages.error(request, hata)
        return redirect("ekran:tasarim_listesi")

    proje = form.kaydet(kullanici=request.user)
    EkranSahne.objects.create(proje=proje, ad="Sahne 1", sira=0)
    islem_kaydet(
        request.user,
        EkranIslemKaydi.Eylem.TASARIM_OLUSTUR,
        nesne=proje,
        aciklama=proje.ad,
        ip=istek_ip(request),
    )
    messages.success(request, f"“{proje.ad}” oluşturuldu. Şimdi ekranı tasarlayabilirsiniz.")
    return redirect("ekran:studyo", pk=proje.pk)


@login_required
@require_permission("ekran", "view")
def studyo(request, pk: int):
    proje = get_object_or_404(EkranProje, pk=pk)
    sahneler = list(EkranSahne.objects.filter(proje=proje).order_by("sira", "id"))
    if not sahneler:
        sahneler = [EkranSahne.objects.create(proje=proje, ad="Sahne 1", sira=0)]

    secili_id = request.GET.get("sahne")
    secili = next((s for s in sahneler if str(s.pk) == secili_id), sahneler[0])

    baslangic = {
        "proje": {
            "id": proje.pk,
            "ad": proje.ad,
            "tuval": {"g": proje.tuval_genislik, "y": proje.tuval_yukseklik},
            "durum": proje.durum,
            "kaydedilmemis": proje.kaydedilmemis_degisiklik,
        },
        "sahneler": [{"id": s.pk, "ad": s.ad, "sira": s.sira} for s in sahneler],
        "sahne": sahne_verisi(sahne_getir(secili.pk)),
        "katalog": oge_katalogu_verisi(),
        "salt_okunur": not _yetki(request, "edit"),
        "adresler": {
            "kaydet": reverse("ekran:sahne_kaydet", args=[secili.pk]),
            "sahne_veri": reverse("ekran:sahne_veri", args=[0])[:-2],
            "medya_liste": reverse("ekran:medya_liste"),
            "medya_yukle": reverse("ekran:medya_yukle"),
            "onizleme": reverse("ekran:tasarim_onizleme", args=[proje.pk]),
            "sablonlar": reverse("ekran:sablon_listesi"),
        },
    }

    return render(
        request,
        "ekran/studyo.html",
        _temel_baglam(
            request,
            aktif_bolum="tasarimlar",
            proje=proje,
            sahneler=sahneler,
            secili_sahne=secili,
            baslangic=baslangic,
            sablonlar=EkranSablon.objects.filter(aktif=True),
        ),
    )


@login_required
@require_permission("ekran", "edit")
@require_POST
def sahne_kaydet_api(request, pk: int):
    sahne = get_object_or_404(EkranSahne.objects.select_related("proje"), pk=pk)
    veri = _json_govde(request)
    if not veri:
        return JsonResponse({"tamam": False, "mesaj": "Kaydedilecek veri alınamadı."}, status=400)

    sahne_kaydet(sahne, veri, kullanici=request.user)
    islem_kaydet(
        request.user,
        EkranIslemKaydi.Eylem.TASARIM_DUZENLE,
        nesne=sahne.proje,
        aciklama=f"“{sahne.ad}” kaydedildi",
        ip=istek_ip(request),
    )
    return JsonResponse(
        {
            "tamam": True,
            "kaydedilme": timezone.localtime().strftime("%H:%M:%S"),
            "sahne": sahne_verisi(sahne_getir(sahne.pk)),
        }
    )


@login_required
@require_permission("ekran", "view")
def sahne_veri_api(request, pk: int):
    sahne = get_object_or_404(EkranSahne, pk=pk)
    return JsonResponse({"tamam": True, "sahne": sahne_verisi(sahne_getir(sahne.pk))})


@login_required
@require_permission("ekran", "edit")
@require_POST
def sahne_ekle(request, pk: int):
    proje = get_object_or_404(EkranProje, pk=pk)
    son_sira = (
        EkranSahne.objects.filter(proje=proje).aggregate(models.Max("sira")).get("sira__max") or 0
    )
    sahne = EkranSahne.objects.create(
        proje=proje,
        ad=(request.POST.get("ad") or "").strip()[:160] or f"Sahne {son_sira + 2}",
        sira=son_sira + 1,
    )
    messages.success(request, f"“{sahne.ad}” eklendi.")
    return redirect(f"{reverse('ekran:studyo', args=[proje.pk])}?sahne={sahne.pk}")


@login_required
@require_permission("ekran", "delete")
@require_POST
def sahne_sil(request, pk: int):
    sahne = get_object_or_404(EkranSahne.objects.select_related("proje"), pk=pk)
    proje = sahne.proje
    if EkranSahne.objects.filter(proje=proje).count() <= 1:
        messages.error(request, "Tasarımın son sahnesi silinemez. Tasarımı silmek isterseniz listeden silin.")
        return redirect("ekran:studyo", pk=proje.pk)

    if sahne.oynatma_ogeleri.exists():
        listeler = ", ".join(sorted({o.liste.ad for o in sahne.oynatma_ogeleri.select_related("liste")}))
        messages.error(request, f"Bu sahne şu oynatma listelerinde kullanılıyor: {listeler}. Önce oradan çıkarın.")
        return redirect("ekran:studyo", pk=proje.pk)

    ad = sahne.ad
    sahne.delete()
    messages.success(request, f"“{ad}” silindi.")
    return redirect("ekran:studyo", pk=proje.pk)


@login_required
@require_permission("ekran", "delete")
@require_POST
def tasarim_sil(request, pk: int):
    proje = get_object_or_404(EkranProje, pk=pk)
    kullanan = EkranOynatmaOgesi.objects.filter(sahne__proje=proje).select_related("liste")
    if kullanan.exists():
        listeler = ", ".join(sorted({o.liste.ad for o in kullanan}))
        messages.error(
            request,
            f"“{proje.ad}” şu oynatma listelerinde kullanılıyor: {listeler}. Önce oradan çıkarın.",
        )
        return redirect("ekran:tasarim_listesi")

    ad = proje.ad
    islem_kaydet(
        request.user,
        EkranIslemKaydi.Eylem.TASARIM_SIL,
        nesne=proje,
        aciklama=ad,
        ip=istek_ip(request),
    )
    proje.delete()
    messages.success(request, f"“{ad}” silindi.")
    return redirect("ekran:tasarim_listesi")


@login_required
@require_permission("ekran", "create")
@require_POST
def tasarim_kopyala(request, pk: int):
    kaynak = get_object_or_404(EkranProje, pk=pk)
    veri = proje_verisi(kaynak)

    kopya = EkranProje.objects.create(
        ad=f"{kaynak.ad} (kopya)"[:160],
        aciklama=kaynak.aciklama,
        tuval_genislik=kaynak.tuval_genislik,
        tuval_yukseklik=kaynak.tuval_yukseklik,
        olusturan=request.user,
        son_duzenleyen=request.user,
    )
    for sira, ham_sahne in enumerate(veri.get("sahneler") or []):
        sahne = EkranSahne.objects.create(proje=kopya, ad=ham_sahne.get("ad") or f"Sahne {sira + 1}", sira=sira)
        sahne_kaydet(sahne, ham_sahne, kullanici=request.user)

    messages.success(request, f"“{kopya.ad}” oluşturuldu.")
    return redirect("ekran:studyo", pk=kopya.pk)


@login_required
@require_permission("ekran", "view")
def tasarim_onizleme(request, pk: int):
    """Tasarımı televizyon görünümünde, gerçek render motoruyla gösterir."""
    proje = get_object_or_404(EkranProje, pk=pk)
    veri = proje_verisi(proje)
    paket = {
        "bos": not veri.get("sahneler"),
        "damga": f"onizleme-{proje.pk}",
        "sahneler": veri.get("sahneler") or [],
        "varliklar": [],
        "dongu": True,
        "acil": None,
        "onizleme": True,
        "sunucu_zamani": timezone.localtime().isoformat(),
        "cihaz": {"ad": "Ön izleme", "konum": "", "yonelim": "yatay"},
    }
    return render(
        request,
        "ekran/onizleme.html",
        {"proje": proje, "paket": paket, "varlik_surumu": VARLIK_SURUMU},
    )


@login_required
@require_permission("ekran", "view")
def surum_listesi(request, pk: int):
    proje = get_object_or_404(EkranProje, pk=pk)
    surumler = EkranProjeSurumu.objects.filter(proje=proje).select_related("olusturan")
    return render(
        request,
        "ekran/surumler.html",
        _temel_baglam(
            request,
            aktif_bolum="tasarimlar",
            proje=proje,
            surumler=surumler,
        ),
    )


@login_required
@require_permission("ekran", "edit")
@require_POST
def surum_geri_yukle_view(request, pk: int):
    surum = get_object_or_404(EkranProjeSurumu.objects.select_related("proje"), pk=pk)
    surum_geri_yukle(surum, kullanici=request.user)
    messages.success(
        request,
        f"v{surum.surum_no} taslağa geri yüklendi. Ekranlara çıkması için yeniden yayınlamalısınız.",
    )
    return redirect("ekran:studyo", pk=surum.proje_id)


# ---------------------------------------------------------------------------
# Şablonlar
# ---------------------------------------------------------------------------


@login_required
@require_permission("ekran", "view")
def sablon_listesi(request):
    sablonlar = EkranSablon.objects.filter(aktif=True)
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(
            {
                "tamam": True,
                "sablonlar": [
                    {
                        "id": s.pk,
                        "ad": s.ad,
                        "aciklama": s.aciklama,
                        "kategori": s.kategori,
                        "anahtar": s.anahtar,
                        "veri": s.veri,
                        "yerlesik": s.yerlesik_mi,
                    }
                    for s in sablonlar
                ],
            }
        )
    return render(
        request,
        "ekran/sablonlar.html",
        _temel_baglam(request, aktif_bolum="sablonlar", sablonlar=sablonlar),
    )


def _sahneye_don(request, sahne: EkranSahne):
    """Sahne üzerinde işlem yapan formlar geldikleri ekrana dönmeli.

    Aynı görünümler hem sade Pano'dan hem gelişmiş stüdyodan kullanılıyor;
    ``donus`` alanı hangisine döneceğini söyler.
    """
    if request.POST.get("donus") == "studyo":
        return redirect(f"{reverse('ekran:studyo', args=[sahne.proje_id])}?sahne={sahne.pk}")
    return redirect("ekran:pano", pk=sahne.proje_id)


@login_required
@require_permission("ekran", "edit")
@require_POST
def sablon_uygula(request, pk: int):
    """Şablonu seçili sahneye kopyalar. Hiçbir alan kilitli kalmaz."""
    sablon = get_object_or_404(EkranSablon, pk=pk, aktif=True)
    sahne_id = request.POST.get("sahne")
    sahne = get_object_or_404(EkranSahne.objects.select_related("proje"), pk=sahne_id)

    veri = dict(sablon.veri or {})
    veri["ad"] = sahne.ad  # sahnenin kendi adı korunur
    sahne_kaydet(sahne, veri, kullanici=request.user)

    messages.success(request, f"“{sablon.ad}” taslağı uygulandı. Artık istediğin gibi değiştirebilirsin.")
    return _sahneye_don(request, sahne)


@login_required
@require_permission("ekran", "manage_template")
@require_POST
def sablon_olarak_kaydet(request, pk: int):
    sahne = get_object_or_404(EkranSahne, pk=pk)
    ad = (request.POST.get("ad") or "").strip()[:160]
    if not ad:
        messages.error(request, "Şablona bir ad verin.")
        return redirect("ekran:studyo", pk=sahne.proje_id)

    anahtar = slugify(ad)[:70] or "sablon"
    benzersiz, sayac = anahtar, 2
    while EkranSablon.objects.filter(anahtar=benzersiz).exists():
        benzersiz = f"{anahtar}-{sayac}"[:80]
        sayac += 1

    EkranSablon.objects.create(
        ad=ad,
        aciklama=(request.POST.get("aciklama") or "").strip()[:400],
        kategori="Kurum şablonları",
        anahtar=benzersiz,
        veri=sahne_verisi(sahne_getir(sahne.pk)),
        olusturan=request.user,
    )
    messages.success(request, f"“{ad}” şablon olarak kaydedildi.")
    return redirect("ekran:studyo", pk=sahne.proje_id)


@login_required
@require_permission("ekran", "manage_template")
@require_POST
def sablon_sil(request, pk: int):
    sablon = get_object_or_404(EkranSablon, pk=pk)
    if sablon.yerlesik_mi:
        messages.error(request, "Yerleşik şablonlar silinemez; gizlemek için pasife alın.")
        return redirect("ekran:sablon_listesi")
    ad = sablon.ad
    sablon.delete()
    messages.success(request, f"“{ad}” şablonu silindi.")
    return redirect("ekran:sablon_listesi")


# ---------------------------------------------------------------------------
# Medya kütüphanesi
# ---------------------------------------------------------------------------


def _medya_sorgusu(request):
    sorgu = EkranMedya.objects.select_related("yukleyen", "klasor")
    arama = (request.GET.get("q") or "").strip()
    tur = (request.GET.get("tur") or "").strip()
    klasor = (request.GET.get("klasor") or "").strip()

    if arama:
        sorgu = sorgu.filter(Q(ad__icontains=arama) | Q(orijinal_ad__icontains=arama))
    if tur in dict(EkranMedya.Tur.choices):
        sorgu = sorgu.filter(tur=tur)
    if klasor.isdigit():
        sorgu = sorgu.filter(klasor_id=int(klasor))
    return sorgu, arama, tur, klasor


@login_required
@require_permission("ekran", "view")
def medya_kutuphanesi(request):
    sorgu, arama, tur, klasor = _medya_sorgusu(request)
    sayfalar = Paginator(sorgu.order_by("-olusturulma"), SAYFA_BOYUTU)
    sayfa = sayfalar.get_page(request.GET.get("sayfa"))

    return render(
        request,
        "ekran/medya.html",
        _temel_baglam(
            request,
            aktif_bolum="medya",
            sayfa=sayfa,
            arama=arama,
            tur=tur,
            secili_klasor=klasor,
            tur_secenekleri=EkranMedya.Tur.choices,
            klasorler=EkranMedyaKlasoru.objects.annotate(medya_sayisi=Count("medyalar")),
        ),
    )


def _medya_ozeti(medya: EkranMedya) -> dict:
    """Stüdyonun beklediği medya sözleşmesi.

    PDF'lerde sayfa adresleri de gönderilir; stüdyo tuvali bu görselleri
    doğrudan çizer ve televizyonla birebir aynı görüntüyü üretir.
    """
    ozet = {
        "id": medya.pk,
        "ad": medya.ad,
        "tur": medya.tur,
        "url": medya.dosya.url if medya.dosya else "",
        "onizleme": medya.onizleme_url,
        "g": medya.genislik,
        "y": medya.yukseklik,
        "sure": medya.sure_sn,
        "sayfa_sayisi": medya.sayfa_sayisi,
        "boyut": medya.boyut_okunabilir,
        "durum": medya.islem_durumu,
        "not": medya.islem_notu,
    }
    if medya.tur == EkranMedya.Tur.PDF:
        ozet["sayfalar"] = [
            {"no": s.sira, "url": s.gorsel.url, "g": s.genislik, "y": s.yukseklik}
            for s in medya.sayfalar.all()
        ]
    return ozet


@login_required
@require_permission("ekran", "view")
def medya_liste_api(request):
    """Stüdyonun medya seçiciye beslediği JSON."""
    sorgu, _, _, _ = _medya_sorgusu(request)
    kayitlar = sorgu.prefetch_related("sayfalar").order_by("-olusturulma")[:120]

    return JsonResponse({"tamam": True, "medyalar": [_medya_ozeti(m) for m in kayitlar]})


@login_required
@require_permission("ekran", "upload_media")
@require_POST
def medya_yukle_api(request):
    """Hem stüdyonun JSON çağrısına hem kütüphanedeki klasik forma yanıt verir.

    Stüdyo ``X-Requested-With`` başlığıyla gelir ve JSON bekler; medya
    kütüphanesi sayfasındaki form ise normal bir gönderimdir ve mesajla
    birlikte listeye dönmelidir.
    """
    json_bekleniyor = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def yanitla(tamam: bool, mesaj: str, ek: dict | None = None, kod: int = 200):
        if json_bekleniyor:
            govde = {"tamam": tamam, "mesaj": mesaj}
            govde.update(ek or {})
            return JsonResponse(govde, status=kod)
        if tamam:
            if mesaj:
                messages.info(request, mesaj)
            else:
                messages.success(request, "Dosya yüklendi.")
        else:
            messages.error(request, mesaj)
        return redirect("ekran:medya_kutuphanesi")

    dosya = request.FILES.get("dosya")
    if dosya is None:
        return yanitla(False, "Dosya seçilmedi.", kod=400)

    klasor = None
    klasor_id = request.POST.get("klasor")
    if klasor_id and str(klasor_id).isdigit():
        klasor = EkranMedyaKlasoru.objects.filter(pk=int(klasor_id)).first()

    try:
        sure = float(request.POST.get("sure") or 0)
    except (TypeError, ValueError):
        sure = 0.0

    try:
        sonuc = medya_yukle(
            dosya,
            kullanici=request.user,
            ad=(request.POST.get("ad") or "").strip(),
            klasor=klasor,
            video_sure_sn=sure,
        )
    except MedyaHatasi as hata:
        return yanitla(False, str(hata), kod=400)

    medya = sonuc.medya
    if sonuc.yeni_mi:
        islem_kaydet(
            request.user,
            EkranIslemKaydi.Eylem.MEDYA_YUKLE,
            nesne=medya,
            aciklama=f"{medya.ad} ({medya.boyut_okunabilir})",
            ip=istek_ip(request),
        )

    return yanitla(
        True,
        "" if sonuc.yeni_mi else "Bu dosya kütüphanede zaten vardı, yeniden yüklenmedi.",
        {"yeni": sonuc.yeni_mi, "medya": _medya_ozeti(medya)}
    )


@login_required
@require_permission("ekran", "delete")
@require_POST
def medya_sil(request, pk: int):
    medya = get_object_or_404(EkranMedya, pk=pk)
    silinebilir, sebep = medya_silinebilir_mi(medya)
    if not silinebilir:
        messages.error(request, sebep)
        return redirect("ekran:medya_kutuphanesi")

    ad = medya.ad
    for sayfa in medya.sayfalar.all():
        sayfa.gorsel.delete(save=False)
    if medya.onizleme:
        medya.onizleme.delete(save=False)
    medya.dosya.delete(save=False)
    islem_kaydet(
        request.user,
        EkranIslemKaydi.Eylem.MEDYA_SIL,
        nesne=medya,
        aciklama=ad,
        ip=istek_ip(request),
    )
    medya.delete()
    messages.success(request, f"“{ad}” silindi.")
    return redirect("ekran:medya_kutuphanesi")


@login_required
@require_permission("ekran", "edit")
@require_POST
def medya_duzenle(request, pk: int):
    medya = get_object_or_404(EkranMedya, pk=pk)
    ad = (request.POST.get("ad") or "").strip()[:200]
    if ad:
        medya.ad = ad
    klasor_id = request.POST.get("klasor")
    if klasor_id == "":
        medya.klasor = None
    elif klasor_id and str(klasor_id).isdigit():
        medya.klasor = EkranMedyaKlasoru.objects.filter(pk=int(klasor_id)).first()
    medya.save(update_fields=["ad", "klasor", "guncellenme"])
    messages.success(request, "Medya güncellendi.")
    return redirect("ekran:medya_kutuphanesi")


@login_required
@require_permission("ekran", "upload_media")
@require_POST
def klasor_ekle(request):
    ad = (request.POST.get("ad") or "").strip()[:120]
    if not ad:
        messages.error(request, "Klasöre bir ad verin.")
        return redirect("ekran:medya_kutuphanesi")
    if EkranMedyaKlasoru.objects.filter(ust__isnull=True, ad=ad).exists():
        messages.error(request, f"“{ad}” adında bir klasör zaten var.")
        return redirect("ekran:medya_kutuphanesi")

    EkranMedyaKlasoru.objects.create(ad=ad, olusturan=request.user)
    messages.success(request, f"“{ad}” klasörü oluşturuldu.")
    return redirect("ekran:medya_kutuphanesi")


# ---------------------------------------------------------------------------
# Cihazlar ve konumlar
# ---------------------------------------------------------------------------


@login_required
@require_permission("ekran", "view")
def cihaz_listesi(request):
    cihazlar = (
        EkranCihaz.objects.select_related("konum")
        .exclude(durum=EkranCihaz.Durum.BEKLIYOR)
        .order_by("konum__sira", "konum__ad", "ad")
    )
    bekleyenler = EkranCihaz.objects.filter(
        durum=EkranCihaz.Durum.BEKLIYOR,
        eslestirme_kodu_bitis__gt=timezone.now(),
    ).order_by("-olusturulma")

    an = timezone.localtime()
    satirlar = []
    for cihaz in cihazlar:
        planlar = uygun_planlar(cihaz, an)
        satirlar.append(
            {
                "cihaz": cihaz,
                "plan": planlar[0] if planlar else None,
                "cakisan": planlar[1:],
            }
        )

    return render(
        request,
        "ekran/cihazlar.html",
        _temel_baglam(
            request,
            aktif_bolum="cihazlar",
            satirlar=satirlar,
            bekleyenler=bekleyenler,
            eslestirme_formu=CihazEslestirmeForm(),
            konumlar=EkranKonumu.objects.filter(aktif=True),
        ),
    )


@login_required
@require_permission("ekran", "view")
def cihaz_durum_api(request):
    """Cihaz listesi sayfasının canlı yenilemesi için hafif JSON."""
    cihazlar = EkranCihaz.objects.select_related("konum").exclude(durum=EkranCihaz.Durum.BEKLIYOR)
    return JsonResponse(
        {
            "tamam": True,
            "zaman": timezone.localtime().strftime("%H:%M:%S"),
            "cihazlar": [
                {
                    "id": c.pk,
                    "cevrimici": c.cevrimici_mi,
                    "son_baglanti": (
                        timezone.localtime(c.son_baglanti).strftime("%d.%m.%Y %H:%M")
                        if c.son_baglanti
                        else ""
                    ),
                }
                for c in cihazlar
            ],
            "bekleyen": EkranCihaz.objects.filter(
                durum=EkranCihaz.Durum.BEKLIYOR,
                eslestirme_kodu_bitis__gt=timezone.now(),
            ).count(),
        }
    )


@login_required
@require_permission("ekran", "manage_device")
@require_POST
def cihaz_eslestir(request):
    form = CihazEslestirmeForm(request.POST)
    if not form.is_valid():
        for hatalar in form.errors.values():
            for hata in hatalar:
                messages.error(request, hata)
        return redirect("ekran:cihaz_listesi")

    cihaz = form.cihaz
    cihaz.ad = form.cleaned_data["ad"]
    cihaz.konum = form.cleaned_data.get("konum")
    cihaz.durum = EkranCihaz.Durum.AKTIF
    cihaz.eslestiren = request.user
    cihaz.eslestirme_zamani = timezone.now()
    # Kod tek kullanımlık: eşleştirme biter bitmez geçersizleşir.
    cihaz.eslestirme_kodu = ""
    cihaz.eslestirme_kodu_bitis = None
    cihaz.save()

    EkranCihazOlayi.objects.create(cihaz=cihaz, tur=EkranCihazOlayi.Tur.ESLESTIRILDI)
    islem_kaydet(
        request.user,
        EkranIslemKaydi.Eylem.CIHAZ_ESLESTIR,
        nesne=cihaz,
        aciklama=f"{cihaz.ad} · {cihaz.konum or 'konum yok'}",
        ip=istek_ip(request),
    )
    messages.success(request, f"“{cihaz.ad}” eşleştirildi. Ekran birkaç saniye içinde yayına geçecek.")
    return redirect("ekran:cihaz_detay", pk=cihaz.pk)


@login_required
@require_permission("ekran", "view")
def cihaz_detay(request, pk: int):
    cihaz = get_object_or_404(EkranCihaz.objects.select_related("konum"), pk=pk)

    if request.method == "POST":
        if not _yetki(request, "manage_device"):
            messages.error(request, "Bu işlem için yetkiniz bulunmuyor.")
            return redirect("ekran:cihaz_detay", pk=cihaz.pk)
        form = CihazDuzenleForm(request.POST, instance=cihaz)
        if form.is_valid():
            form.save()
            messages.success(request, "Ekran bilgileri güncellendi.")
            return redirect("ekran:cihaz_detay", pk=cihaz.pk)
    else:
        form = CihazDuzenleForm(instance=cihaz)

    an = timezone.localtime()
    planlar = uygun_planlar(cihaz, an)

    return render(
        request,
        "ekran/cihaz_detay.html",
        _temel_baglam(
            request,
            aktif_bolum="cihazlar",
            cihaz=cihaz,
            form=form,
            aktif_plan=planlar[0] if planlar else None,
            cakisan_planlar=planlar[1:],
            olaylar=cihaz.olaylar.all()[:25],
            raporlar=cihaz.oynatma_raporlari.select_related("paket__plan")[:15],
        ),
    )


@login_required
@require_permission("ekran", "manage_device")
@require_POST
def cihaz_yenile(request, pk: int):
    """Ekranın sayfayı yeniden yüklemesini ister."""
    cihaz = get_object_or_404(EkranCihaz, pk=pk)
    cihaz.yeniden_yukle_istegi = True
    cihaz.save(update_fields=["yeniden_yukle_istegi", "guncellenme"])
    messages.success(request, f"“{cihaz.gorunen_ad}” en geç bir dakika içinde yeniden yüklenecek.")
    return redirect("ekran:cihaz_detay", pk=cihaz.pk)


@login_required
@require_permission("ekran", "manage_device")
@require_POST
def cihaz_sil(request, pk: int):
    cihaz = get_object_or_404(EkranCihaz, pk=pk)
    ad = cihaz.gorunen_ad
    islem_kaydet(
        request.user,
        EkranIslemKaydi.Eylem.CIHAZ_SIL,
        nesne=cihaz,
        aciklama=ad,
        ip=istek_ip(request),
    )
    cihaz.delete()
    messages.success(
        request,
        f"“{ad}” kaydı silindi. Televizyon yeniden açıldığında yeni bir eşleştirme kodu gösterecek.",
    )
    return redirect("ekran:cihaz_listesi")


@login_required
@require_permission("ekran", "view")
def konum_listesi(request):
    if request.method == "POST":
        if not _yetki(request, "manage_device"):
            messages.error(request, "Bu işlem için yetkiniz bulunmuyor.")
            return redirect("ekran:konum_listesi")
        form = KonumForm(request.POST)
        if form.is_valid():
            konum = form.save()
            messages.success(request, f"“{konum.ad}” eklendi.")
            return redirect("ekran:konum_listesi")
    else:
        form = KonumForm()

    return render(
        request,
        "ekran/konumlar.html",
        _temel_baglam(
            request,
            aktif_bolum="cihazlar",
            form=form,
            konumlar=EkranKonumu.objects.annotate(cihaz_sayisi=Count("cihazlar")),
        ),
    )


@login_required
@require_permission("ekran", "manage_device")
@require_POST
def konum_sil(request, pk: int):
    konum = get_object_or_404(EkranKonumu, pk=pk)
    if konum.cihazlar.exists():
        messages.error(
            request,
            f"“{konum.ad}” konumunda ekran var. Önce ekranları başka konuma taşıyın.",
        )
        return redirect("ekran:konum_listesi")
    ad = konum.ad
    konum.delete()
    messages.success(request, f"“{ad}” silindi.")
    return redirect("ekran:konum_listesi")


# ---------------------------------------------------------------------------
# Oynatma listeleri
# ---------------------------------------------------------------------------


@login_required
@require_permission("ekran", "view")
def liste_listesi(request):
    if request.method == "POST":
        if not _yetki(request, "create"):
            messages.error(request, "Bu işlem için yetkiniz bulunmuyor.")
            return redirect("ekran:liste_listesi")
        form = OynatmaListesiForm(request.POST)
        if form.is_valid():
            liste = form.save(commit=False)
            liste.olusturan = request.user
            liste.son_duzenleyen = request.user
            liste.save()
            messages.success(request, f"“{liste.ad}” oluşturuldu.")
            return redirect("ekran:liste_detay", pk=liste.pk)
    else:
        form = OynatmaListesiForm()

    listeler = EkranOynatmaListesi.objects.annotate(
        oge_sayisi=Count("ogeler", filter=Q(ogeler__aktif=True)),
        plan_sayisi=Count("yayin_planlari", distinct=True),
    ).order_by("ad")

    return render(
        request,
        "ekran/listeler.html",
        _temel_baglam(request, aktif_bolum="listeler", listeler=listeler, form=form),
    )


@login_required
@require_permission("ekran", "view")
def liste_detay(request, pk: int):
    liste = get_object_or_404(EkranOynatmaListesi, pk=pk)

    if request.method == "POST":
        if not _yetki(request, "edit"):
            messages.error(request, "Bu işlem için yetkiniz bulunmuyor.")
            return redirect("ekran:liste_detay", pk=liste.pk)

        eylem = request.POST.get("eylem")

        if eylem == "bilgi":
            form = OynatmaListesiForm(request.POST, instance=liste)
            if form.is_valid():
                form.save()
                messages.success(request, "Liste güncellendi.")
            return redirect("ekran:liste_detay", pk=liste.pk)

        if eylem == "sahne_ekle":
            sahne = EkranSahne.objects.filter(pk=request.POST.get("sahne")).first()
            if sahne is None:
                messages.error(request, "Sahne bulunamadı.")
            else:
                son = (
                    EkranOynatmaOgesi.objects.filter(liste=liste)
                    .aggregate(models.Max("sira"))
                    .get("sira__max")
                )
                EkranOynatmaOgesi.objects.create(
                    liste=liste,
                    sahne=sahne,
                    sira=(son or -1) + 1,
                )
                messages.success(request, f"“{sahne.ad}” listeye eklendi.")
            return redirect("ekran:liste_detay", pk=liste.pk)

        if eylem == "oge_sil":
            EkranOynatmaOgesi.objects.filter(pk=request.POST.get("oge"), liste=liste).delete()
            messages.success(request, "Sahne listeden çıkarıldı.")
            return redirect("ekran:liste_detay", pk=liste.pk)

        if eylem == "sirala":
            # Sürükle-bırak sonrası gelen sıra dizisi
            sira_listesi = request.POST.getlist("sira[]") or request.POST.getlist("sira")
            for yeni_sira, oge_id in enumerate(sira_listesi):
                EkranOynatmaOgesi.objects.filter(pk=oge_id, liste=liste).update(sira=yeni_sira)
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"tamam": True})
            return redirect("ekran:liste_detay", pk=liste.pk)

        if eylem == "sure":
            oge = EkranOynatmaOgesi.objects.filter(pk=request.POST.get("oge"), liste=liste).first()
            if oge:
                try:
                    oge.sure_sn = max(0, min(86400, int(request.POST.get("sure") or 0)))
                except ValueError:
                    oge.sure_sn = 0
                oge.save(update_fields=["sure_sn"])
                messages.success(request, "Süre güncellendi.")
            return redirect("ekran:liste_detay", pk=liste.pk)

    ogeler = (
        EkranOynatmaOgesi.objects.filter(liste=liste)
        .select_related("sahne__proje")
        .order_by("sira", "id")
    )
    eklenebilir = (
        EkranSahne.objects.filter(aktif=True)
        .select_related("proje")
        .exclude(proje__durum=EkranProje.Durum.ARSIV)
        .order_by("proje__ad", "sira")
    )

    return render(
        request,
        "ekran/liste_detay.html",
        _temel_baglam(
            request,
            aktif_bolum="listeler",
            liste=liste,
            ogeler=ogeler,
            eklenebilir=eklenebilir,
            form=OynatmaListesiForm(instance=liste),
        ),
    )


@login_required
@require_permission("ekran", "delete")
@require_POST
def liste_sil(request, pk: int):
    liste = get_object_or_404(EkranOynatmaListesi, pk=pk)
    if liste.yayin_planlari.exists():
        planlar = ", ".join(sorted(p.ad for p in liste.yayin_planlari.all()[:5]))
        messages.error(request, f"Bu liste şu yayınlarda kullanılıyor: {planlar}. Önce yayınları silin.")
        return redirect("ekran:liste_listesi")
    ad = liste.ad
    liste.delete()
    messages.success(request, f"“{ad}” silindi.")
    return redirect("ekran:liste_listesi")


# ---------------------------------------------------------------------------
# Yayın planları
# ---------------------------------------------------------------------------


def _hedefleri_kaydet(plan: EkranYayinPlani, form: YayinPlaniForm) -> None:
    plan.gunler = [int(g) for g in form.cleaned_data.get("gun_secimi") or []]
    plan.save(update_fields=["gunler", "guncellenme"])

    EkranYayinHedefi.objects.filter(plan=plan).delete()
    if plan.tum_ekranlar:
        return
    for konum in form.cleaned_data.get("hedef_konumlar") or []:
        EkranYayinHedefi.objects.create(plan=plan, konum=konum)
    for cihaz in form.cleaned_data.get("hedef_cihazlar") or []:
        EkranYayinHedefi.objects.create(plan=plan, cihaz=cihaz)


@login_required
@require_permission("ekran", "view")
def yayin_listesi(request):
    if request.method == "POST":
        if not _yetki(request, "schedule"):
            messages.error(request, "Bu işlem için yetkiniz bulunmuyor.")
            return redirect("ekran:yayin_listesi")
        form = YayinPlaniForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.olusturan = request.user
            plan.son_duzenleyen = request.user
            plan.save()
            _hedefleri_kaydet(plan, form)
            messages.success(
                request,
                f"“{plan.ad}” taslak olarak kaydedildi. Ekranlara çıkması için “Yayınla” demelisiniz.",
            )
            return redirect("ekran:yayin_detay", pk=plan.pk)
    else:
        form = YayinPlaniForm()

    planlar = (
        EkranYayinPlani.objects.select_related("liste", "aktif_paket")
        .prefetch_related(
            Prefetch("hedefler", queryset=EkranYayinHedefi.objects.select_related("konum", "cihaz"))
        )
        .order_by("-oncelik", "ad")
    )

    return render(
        request,
        "ekran/yayinlar.html",
        _temel_baglam(request, aktif_bolum="yayinlar", planlar=planlar, form=form),
    )


@login_required
@require_permission("ekran", "view")
def yayin_detay(request, pk: int):
    plan = get_object_or_404(
        EkranYayinPlani.objects.select_related("liste", "aktif_paket"), pk=pk
    )

    if request.method == "POST":
        if not _yetki(request, "schedule"):
            messages.error(request, "Bu işlem için yetkiniz bulunmuyor.")
            return redirect("ekran:yayin_detay", pk=plan.pk)
        form = YayinPlaniForm(request.POST, instance=plan)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.son_duzenleyen = request.user
            plan.save()
            _hedefleri_kaydet(plan, form)
            messages.success(
                request,
                "Plan güncellendi. Değişikliklerin ekranlara gitmesi için “Yayınla” demelisiniz.",
            )
            return redirect("ekran:yayin_detay", pk=plan.pk)
    else:
        form = YayinPlaniForm(instance=plan)

    hedef_cihazlar = _plan_hedef_cihazlari(plan)
    cakismalar = []
    for cihaz in hedef_cihazlar[:20]:
        rakipler = [p for p in uygun_planlar(cihaz) if p.pk != plan.pk]
        if rakipler:
            cakismalar.append({"cihaz": cihaz, "rakipler": rakipler})

    return render(
        request,
        "ekran/yayin_detay.html",
        _temel_baglam(
            request,
            aktif_bolum="yayinlar",
            plan=plan,
            form=form,
            hedef_cihazlar=hedef_cihazlar,
            cakismalar=cakismalar,
            paketler=plan.paketler.select_related("yayinlayan")[:10],
            sahneler=plan.liste.ogeler.filter(aktif=True).select_related("sahne__proje").order_by("sira"),
        ),
    )


def _plan_hedef_cihazlari(plan: EkranYayinPlani) -> list[EkranCihaz]:
    temel = EkranCihaz.objects.filter(durum=EkranCihaz.Durum.AKTIF).select_related("konum")
    if plan.tum_ekranlar:
        return list(temel)
    return list(
        temel.filter(
            Q(yayin_hedefleri__plan=plan) | Q(konum__yayin_hedefleri__plan=plan)
        ).distinct()
    )


@login_required
@require_permission("ekran", "publish")
@require_POST
def yayin_yayinla(request, pk: int):
    plan = get_object_or_404(EkranYayinPlani.objects.select_related("liste"), pk=pk)
    try:
        paket = paket_derle(plan, kullanici=request.user)
    except YayinHatasi as hata:
        messages.error(request, str(hata))
        return redirect("ekran:yayin_detay", pk=plan.pk)

    hedefler = _plan_hedef_cihazlari(plan)
    messages.success(
        request,
        f"“{plan.ad}” yayınlandı — {paket.varlik_sayisi} dosya, {len(hedefler)} ekran. "
        "Ekranlar en geç bir dakika içinde güncellenecek.",
    )
    return redirect("ekran:yayin_detay", pk=plan.pk)


@login_required
@require_permission("ekran", "publish")
@require_POST
def yayin_durdur(request, pk: int):
    plan = get_object_or_404(EkranYayinPlani, pk=pk)
    plan.durum = EkranYayinPlani.Durum.DURDURULDU
    plan.save(update_fields=["durum", "guncellenme"])
    islem_kaydet(
        request.user,
        EkranIslemKaydi.Eylem.YAYIN_DURDUR,
        nesne=plan,
        aciklama=plan.ad,
        ip=istek_ip(request),
    )
    messages.success(request, f"“{plan.ad}” durduruldu.")
    return redirect("ekran:yayin_detay", pk=plan.pk)


@login_required
@require_permission("ekran", "delete")
@require_POST
def yayin_sil(request, pk: int):
    plan = get_object_or_404(EkranYayinPlani, pk=pk)
    ad = plan.ad
    plan.delete()
    messages.success(request, f"“{ad}” silindi.")
    return redirect("ekran:yayin_listesi")


# ---------------------------------------------------------------------------
# Acil duyuru
# ---------------------------------------------------------------------------


@login_required
@require_permission("ekran", "view")
def acil_listesi(request):
    if request.method == "POST":
        if not _yetki(request, "emergency"):
            messages.error(request, "Acil duyuru gönderme yetkiniz bulunmuyor.")
            return redirect("ekran:acil_listesi")
        form = AcilDuyuruForm(request.POST)
        if form.is_valid():
            duyuru = form.save(commit=False)
            duyuru.baslatan = request.user
            duyuru.baslangic = timezone.now()
            duyuru.aktif = True
            duyuru.save()
            duyuru.konumlar.set(form.cleaned_data.get("hedef_konumlar") or [])
            duyuru.cihazlar.set(form.cleaned_data.get("hedef_cihazlar") or [])

            islem_kaydet(
                request.user,
                EkranIslemKaydi.Eylem.ACIL_BASLAT,
                nesne=duyuru,
                aciklama=duyuru.baslik,
                ip=istek_ip(request),
            )
            messages.success(
                request,
                "Acil duyuru başlatıldı. Ekranlar en geç bir dakika içinde duyuruya geçecek.",
            )
            return redirect("ekran:acil_listesi")
    else:
        form = AcilDuyuruForm()

    duyurular = EkranAcilDuyuru.objects.select_related("baslatan", "kapatan").prefetch_related(
        "konumlar", "cihazlar"
    )[:40]

    return render(
        request,
        "ekran/acil.html",
        _temel_baglam(
            request,
            aktif_bolum="acil",
            form=form,
            duyurular=duyurular,
            yayinda=[d for d in duyurular if d.yayinda_mi],
        ),
    )


@login_required
@require_permission("ekran", "emergency")
@require_POST
def acil_kapat(request, pk: int):
    duyuru = get_object_or_404(EkranAcilDuyuru, pk=pk)
    duyuru.aktif = False
    duyuru.kapatan = request.user
    duyuru.kapatma_zamani = timezone.now()
    duyuru.save(update_fields=["aktif", "kapatan", "kapatma_zamani"])

    islem_kaydet(
        request.user,
        EkranIslemKaydi.Eylem.ACIL_KAPAT,
        nesne=duyuru,
        aciklama=duyuru.baslik,
        ip=istek_ip(request),
    )
    messages.success(request, "Acil duyuru kapatıldı. Ekranlar normal yayına dönecek.")
    return redirect("ekran:acil_listesi")


# ---------------------------------------------------------------------------
# Geçmiş
# ---------------------------------------------------------------------------


@login_required
@require_permission("ekran", "view_history")
def gecmis(request):
    sekme = request.GET.get("sekme") or "islem"

    if sekme == "rapor":
        sorgu = EkranOynatmaRaporu.objects.select_related("cihaz__konum", "paket__plan")
    elif sekme == "olay":
        sorgu = EkranCihazOlayi.objects.select_related("cihaz__konum")
    elif sekme == "paket":
        sorgu = EkranYayinPaketi.objects.select_related("plan", "yayinlayan")
    else:
        sekme = "islem"
        sorgu = EkranIslemKaydi.objects.select_related("kullanici")

    sayfalar = Paginator(sorgu, 50)
    sayfa = sayfalar.get_page(request.GET.get("sayfa"))

    return render(
        request,
        "ekran/gecmis.html",
        _temel_baglam(request, aktif_bolum="gecmis", sekme=sekme, sayfa=sayfa),
    )


# ---------------------------------------------------------------------------
# Pano — modülün ana ekranı
# ---------------------------------------------------------------------------


@login_required
@require_permission("ekran", "view")
def pano(request, pk: int):
    """Beyaz tahta: içerik sürükle, yerleştir, ekranlara gönder."""
    proje = get_object_or_404(EkranProje, pk=pk)

    sahneler = list(EkranSahne.objects.filter(proje=proje).order_by("sira", "id"))
    if not sahneler:
        sahneler = [EkranSahne.objects.create(proje=proje, ad="Ekran 1", sira=0)]
    sahne = sahneler[0]

    sahne_json = sahne_verisi(sahne_getir(sahne.pk))
    bos_mu = not sahne_json.get("ogeler")

    baslangic = {
        "proje": {
            "id": proje.pk,
            "ad": proje.ad,
            "tuval": {"g": proje.tuval_genislik, "y": proje.tuval_yukseklik},
        },
        "sahne": sahne_json,
        "katalog": oge_katalogu_verisi(),
        "salt_okunur": not _yetki(request, "edit"),
        "bos": bos_mu,
        "adresler": {
            "kaydet": reverse("ekran:sahne_kaydet", args=[sahne.pk]),
            "medya_liste": reverse("ekran:medya_liste"),
            "medya_yukle": reverse("ekran:medya_yukle"),
            "onizleme": reverse("ekran:tasarim_onizleme", args=[proje.pk]),
            "gonder": reverse("ekran:pano_gonder", args=[proje.pk]),
        },
    }

    cihazlar = list(
        EkranCihaz.objects.filter(durum=EkranCihaz.Durum.AKTIF).select_related("konum")
    )

    return render(
        request,
        "ekran/pano.html",
        _temel_baglam(
            request,
            aktif_bolum="pano",
            proje=proje,
            sahne=sahne,
            baslangic=baslangic,
            bos_mu=bos_mu,
            sablonlar=EkranSablon.objects.filter(aktif=True),
            cihazlar=cihazlar,
            konumlar=EkranKonumu.objects.filter(aktif=True),
            yayin=pano_yayin_durumu(proje),
            bekleyen_ekran=EkranCihaz.objects.filter(
                durum=EkranCihaz.Durum.BEKLIYOR,
                eslestirme_kodu_bitis__gt=timezone.now(),
            ).count(),
        ),
    )


@login_required
@require_permission("ekran", "publish")
@require_POST
def pano_gonder(request, pk: int):
    """Tek tıkla yayın: hedefleri al, paketi derle, ekranlara gönder."""
    proje = get_object_or_404(EkranProje, pk=pk)

    tum_ekranlar = request.POST.get("hedef") == "tum"
    cihazlar = EkranCihaz.objects.filter(
        pk__in=request.POST.getlist("cihaz"), durum=EkranCihaz.Durum.AKTIF
    )
    konumlar = EkranKonumu.objects.filter(pk__in=request.POST.getlist("konum"), aktif=True)

    try:
        paket, hedefler = panoyu_ekranlara_gonder(
            proje,
            tum_ekranlar=tum_ekranlar,
            cihazlar=cihazlar,
            konumlar=konumlar,
            kullanici=request.user,
        )
    except YayinHatasi as hata:
        messages.error(request, str(hata))
        return redirect("ekran:pano", pk=proje.pk)

    if hedefler:
        messages.success(
            request,
            f"Pano {len(hedefler)} ekrana gönderildi. "
            "Televizyonlar en geç bir dakika içinde güncellenecek.",
        )
    else:
        messages.warning(
            request,
            "Pano hazırlandı ama şu an bağlı ekran yok. "
            "Televizyonu bağladığınızda yayın kendiliğinden görünecek.",
        )
    return redirect("ekran:pano", pk=proje.pk)
