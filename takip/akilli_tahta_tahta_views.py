"""Akıllı tahta hesaplarının kendi ekranı — giriş sonrası tek durak.

Bu görünümler yalnızca ``AkilliTahtaHesap`` sahibi kullanıcılar içindir.
Sınıf seviyesi HER ZAMAN ``request.user.akilli_tahta_hesabi.sinif_seviyesi``
üzerinden okunur — URL/query parametresinden asla; bu, bir tahta hesabının
adres çubuğunu değiştirerek başka bir sınıfın dosyalarına erişmesini
yapısal olarak imkânsız kılar.
"""

from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from takip.akilli_tahta_models import AkilliTahtaDosya
from takip.akilli_tahta_service import kullanici_tahta_mi, yayindaki_dosyalar


def tahta_hesabi_gerekli(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not kullanici_tahta_mi(request.user):
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)

    return _wrapped


_GORSEL_TURLERI = {"jpg", "jpeg", "png", "webp"}


def _bolumler_baglami(hesap, arama: str = "") -> dict:
    """Ekran ve içerik-yenileme (canlı güncelleme) için paylaşılan bağlam."""
    dosyalar = list(yayindaki_dosyalar(hesap.sinif_seviyesi))
    if arama:
        dosyalar = [d for d in dosyalar if arama.lower() in d.baslik.lower()]

    bugun = timezone.localdate()
    bugun_eklenenler = [d for d in dosyalar if timezone.localtime(d.olusturulma).date() == bugun]
    pdfler = [d for d in dosyalar if d.dosya_turu == "pdf"]
    gorseller = [d for d in dosyalar if d.dosya_turu in _GORSEL_TURLERI]
    videolar = [d for d in dosyalar if d.dosya_turu == "mp4"]
    testler = [d for d in dosyalar if d.icerik_turu == AkilliTahtaDosya.IcerikTuru.TEST]
    denemeler = [d for d in dosyalar if d.icerik_turu == AkilliTahtaDosya.IcerikTuru.DENEME]

    arsiv = list(
        AkilliTahtaDosya.objects.filter(durum=AkilliTahtaDosya.Durum.ARSIVLENDI)
        .select_related("ders", "yukleyen")
        .order_by("-guncellenme")[:60]
    )
    arsiv = [d for d in arsiv if d.hedefliyor_mu(hesap.sinif_seviyesi)]

    bolumler = [
        ("Bugün Eklenenler", bugun_eklenenler),
        ("PDF'ler", pdfler),
        ("Görseller", gorseller),
        ("Videolar", videolar),
        ("Testler", testler),
        ("Denemeler", denemeler),
        ("Arşiv", arsiv),
    ]
    return {"bolumler": bolumler}


def _son_guncelleme_damgasi(hesap) -> str:
    """Bu sınıf seviyesinin gördüğü içerikteki en güncel değişiklik zamanı.

    Poll uçları bu değeri karşılaştırarak "değişen bir şey var mı?" sorusunu
    tam içerik sorgusu çalıştırmadan, tek bir hafif sorguyla yanıtlar.
    """
    son = (
        AkilliTahtaDosya.objects.filter(guncellenme__isnull=False)
        .order_by("-guncellenme")
        .values_list("guncellenme", flat=True)
        .first()
    )
    return son.isoformat() if son else ""


@login_required
@tahta_hesabi_gerekli
def ekran(request):
    hesap = request.user.akilli_tahta_hesabi
    arama = (request.GET.get("q") or "").strip()

    baglam = _bolumler_baglami(hesap, arama)
    baglam.update(
        {
            "hesap": hesap,
            "arama": arama,
            "son_guncelleme": _son_guncelleme_damgasi(hesap),
        }
    )
    return render(request, "akilli_tahta_tahta/ekran.html", baglam)


@login_required
@tahta_hesabi_gerekli
def durum(request):
    """Canlı güncelleme (aşama 7): istemci bunu periyodik yoklar (polling)."""
    hesap = request.user.akilli_tahta_hesabi
    return JsonResponse({"son_guncelleme": _son_guncelleme_damgasi(hesap)})


@login_required
@tahta_hesabi_gerekli
def icerik(request):
    """Değişiklik algılandığında tam sayfa yenilemeden çekilen bölüm HTML'i."""
    hesap = request.user.akilli_tahta_hesabi
    baglam = _bolumler_baglami(hesap)
    return render(request, "akilli_tahta_tahta/_bolumler.html", baglam)


@login_required
@tahta_hesabi_gerekli
def goruntule(request, pk):
    hesap = request.user.akilli_tahta_hesabi
    dosya = get_object_or_404(AkilliTahtaDosya, pk=pk)
    if dosya.gorunur_durum != "yayinda" or not dosya.hedefliyor_mu(hesap.sinif_seviyesi):
        raise Http404("Dosya bulunamadı.")

    return render(
        request,
        "akilli_tahta_tahta/goruntule.html",
        {"dosya": dosya, "hesap": hesap},
    )
