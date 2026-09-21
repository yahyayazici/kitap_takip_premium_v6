"""Akıllı tahta hesaplarının kendi ekranı — giriş sonrası tek durak.

Bu görünümler yalnızca ``AkilliTahtaHesap`` sahibi kullanıcılar içindir.
Sınıf seviyesi HER ZAMAN ``request.user.akilli_tahta_hesabi.sinif_seviyesi``
üzerinden okunur — URL/query parametresinden asla; bu, bir tahta hesabının
adres çubuğunu değiştirerek başka bir sınıfın dosyalarına erişmesini
yapısal olarak imkânsız kılar.
"""

from __future__ import annotations

from functools import wraps

from django.contrib.auth import logout, views as auth_views
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from takip.akilli_tahta_models import AkilliTahtaDosya
from takip.akilli_tahta_service import kullanici_tahta_mi, yayindaki_dosyalar
from takip.rate_limit import (
    basarili_giris_sifirla,
    basarisiz_deneme_kaydet,
    limit_asildi_mi,
)


def tahta_hesabi_gerekli(view_func):
    """Kimliksiz ziyaretçiyi tahtaya özel giriş sayfasına gönderir (kurumun
    genel ``/giris/`` sayfasını tahta cihazına asla göstermemek için);
    başka bir hesapla giriş yapmış kullanıcıyı kendi paneline yönlendirir.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("akilli_tahta_tahta:giris")
        if not kullanici_tahta_mi(request.user):
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)

    return _wrapped


_GORSEL_TURLERI = {"jpg", "jpeg", "png", "webp"}

TAHTA_RATE_LIMIT_MESAJI = (
    "Çok fazla başarısız giriş denemesi yapıldı. Lütfen birkaç dakika sonra tekrar deneyin."
)


class TahtaLoginView(auth_views.LoginView):
    """Akıllı tahta cihazlarına özel giriş sayfası.

    Kurumun genel ``/giris/`` sayfasından KASITLI olarak ayrıdır: etüt
    salonundaki tahtaya bağlı tarayıcı hiçbir zaman kurumun ana giriş
    ekranını, menüsünü ya da diğer panellerini görmemeli — cihazda sadece
    bu kısıtlı giriş formu ve ardından tahta ekranı açılmalı. Bu yüzden bu
    sayfa yalnızca aktif bir akıllı tahta hesabıyla girişi kabul eder;
    başka bir hesapla (öğretmen, veli vb.) giriş denenirse reddedilir ve
    oturum hemen kapatılır.
    """

    template_name = "akilli_tahta_tahta/giris.html"
    redirect_authenticated_user = False

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and kullanici_tahta_mi(request.user):
            return redirect("akilli_tahta_tahta:ekran")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        kullanici_adi = (request.POST.get("username") or "").strip()
        if limit_asildi_mi(request, kullanici_adi):
            self._rate_limited = True
            form = self.get_form()
            form.is_valid()
            form.add_error(None, TAHTA_RATE_LIMIT_MESAJI)
            return self.form_invalid(form)

        self._rate_limited = False
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if not kullanici_tahta_mi(form.get_user()):
            # Doğru şifre ama tahta hesabı değil — bu sayfadan asla içeri
            # alınmaz. Oturumu hemen kapatıp giriş hatası gibi göster.
            basarisiz_deneme_kaydet(self.request, form.cleaned_data.get("username", ""))
            form.add_error(None, "Bu giriş sayfası yalnızca akıllı tahta hesapları içindir.")
            return self.form_invalid(form)

        basarili_giris_sifirla(self.request, form.cleaned_data.get("username", ""))
        return super().form_valid(form)

    def form_invalid(self, form):
        if not getattr(self, "_rate_limited", False):
            kullanici_adi = (self.request.POST.get("username") or "").strip()
            basarisiz_deneme_kaydet(self.request, kullanici_adi)
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse("akilli_tahta_tahta:ekran")


giris = TahtaLoginView.as_view()


def cikis(request):
    logout(request)
    return redirect("akilli_tahta_tahta:giris")


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


@tahta_hesabi_gerekli
def durum(request):
    """Canlı güncelleme (aşama 7): istemci bunu periyodik yoklar (polling)."""
    hesap = request.user.akilli_tahta_hesabi
    return JsonResponse({"son_guncelleme": _son_guncelleme_damgasi(hesap)})


@tahta_hesabi_gerekli
def icerik(request):
    """Değişiklik algılandığında tam sayfa yenilemeden çekilen bölüm HTML'i."""
    hesap = request.user.akilli_tahta_hesabi
    baglam = _bolumler_baglami(hesap)
    return render(request, "akilli_tahta_tahta/_bolumler.html", baglam)


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
