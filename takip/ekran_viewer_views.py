"""Televizyon görüntüleyici sayfası ve service worker.

Görüntüleyici oturum açmaz: cihaz kendini ``localStorage``'daki anahtarla
tanıtır. Sayfa günlerce açık kalacağı için HTML'e hiçbir dinamik veri
gömülmez — bütün içerik API'den gelir ve service worker tarafından
önbelleğe alınır. Böylece sayfanın kendisi yeniden yüklenmeden yayın
değişebilir.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static as static_url
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt

from takip.ekran_service import YOKLAMA_ARALIGI_SN

# Ekran modülünün statik dosya sürümü — TEK KAYNAK.
# Ekranın CSS/JS dosyalarından biri değiştiğinde burayı artırın:
#   * şablonlar varlık adreslerine ?v=<sürüm> ekler,
#   * service worker aynı adresleri ön belleğe alır (ikisi eşleşmezse
#     ön yükleme boşa giderdi),
#   * televizyonlardaki eski önbellek temizlenir.
VARLIK_SURUMU = "e11"

# Service worker önbellek adı; sürümle birlikte değişir.
ONBELLEK_SURUMU = f"ekran-{VARLIK_SURUMU}"


def temel_yol(request) -> str:
    """Görüntüleyicinin kökü — sonunda eğik çizgiyle.

    Sayfa iki yerde birden yayınlanır:
      * ``ekran.<domain>/``      → ``/``
      * ``<domain>/tv/``         → ``/tv/``

    Cihaz API adresleri ve service worker kapsamı bu köke göre kurulur.
    ``reverse`` isteğin aktif urlconf'una baktığı için doğru olanı üretir.
    """
    from django.urls import reverse

    kok = reverse("ekran_viewer")
    return kok if kok.endswith("/") else kok + "/"


@never_cache
@xframe_options_exempt
def viewer(request):
    """Televizyonun açtığı sayfa."""
    return render(
        request,
        "ekran/viewer.html",
        {
            "yoklama_sn": YOKLAMA_ARALIGI_SN,
            "onbellek_surumu": ONBELLEK_SURUMU,
            "varlik_surumu": VARLIK_SURUMU,
            "temel_yol": temel_yol(request),
        },
    )


@never_cache
@xframe_options_exempt
def tani(request):
    """Televizyon tarayıcısının neyi desteklediğini gösteren teşhis sayfası.

    Akıllı televizyon tarayıcıları çok eski olabiliyor ve konsollarına
    erişilemiyor. Bu sayfa hiçbir modern özelliğe dayanmaz; ekranda
    okunup fotoğraflanabilir.
    """
    return render(request, "ekran/tani.html")


@never_cache
def offline(request):
    """Ağ yokken ve önbellekte yayın yokken gösterilen kurumsal bekleme ekranı."""
    return render(
        request,
        "ekran/offline.html",
        {"varlik_surumu": VARLIK_SURUMU, "temel_yol": temel_yol(request)},
    )


@never_cache
def service_worker(request):
    """Service worker'ı kök kapsamda servis eder.

    Statik dosya olarak ``/static/...`` altından verilseydi kapsamı
    ``/static/`` ile sınırlı kalır, ana sayfayı önbelleğe alamazdı.
    """
    def damgali(yol: str) -> str:
        # Şablonun istediği adresin BİREBİR aynısı olmalı; Cache API
        # anahtarı sorgu dizesini de içerir.
        return f"{static_url(yol)}?v={VARLIK_SURUMU}"

    kok = temel_yol(request)
    icerik = (
        f"self.EKRAN_SURUM = '{ONBELLEK_SURUMU}';\n"
        f"self.EKRAN_TEMEL = '{kok}';\n"
        f"self.EKRAN_KABUK = [\n"
        f"  '{kok}',\n"
        f"  '{damgali('ekran/css/viewer.css')}',\n"
        f"  '{damgali('ekran/js/engine.js')}',\n"
        f"  '{damgali('ekran/js/viewer.js')}',\n"
        f"  '{static_url('images/cinili-saray-logo-white.png')}'\n"
        f"];\n"
        f"importScripts('{static_url('ekran/js/viewer-sw.js')}');\n"
    )
    yanit = HttpResponse(icerik, content_type="application/javascript; charset=utf-8")
    yanit["Service-Worker-Allowed"] = kok
    yanit["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return yanit


@xframe_options_exempt
def qr_kodu(request):
    """Öğe için QR kodu üretir (segno — mevcut bağımlılık, dış servis yok).

    ``segno`` yalnız burada, istek anında içeri alınır: uygulama açılışını
    yavaşlatmaz ve kurulu olmasa bile panelin geri kalanı çalışır.
    """
    import io

    veri = (request.GET.get("veri") or "").strip()[:900]
    if not veri:
        veri = "https://cinilisarayproje.com"

    try:
        import segno

        tampon = io.StringIO()
        segno.make(veri, error="m").save(
            tampon,
            kind="svg",
            scale=8,
            border=2,
            dark="#0f203c",
            light=None,
        )
        govde = tampon.getvalue()
    except Exception:  # pragma: no cover — kütüphane yok / bozuk girdi
        # Ekranda teknik hata gösterilmez; yerine sade bir çerçeve çizilir.
        govde = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<rect x="2" y="2" width="96" height="96" rx="8" fill="none" '
            'stroke="#0f203c" stroke-width="3"/></svg>'
        )

    yanit = HttpResponse(govde, content_type="image/svg+xml")
    # QR içeriği adrese bağlıdır; uzun süre önbelleklenebilir.
    yanit["Cache-Control"] = "public, max-age=86400"
    return yanit


# ---------------------------------------------------------------------------
# Medya servisi
# ---------------------------------------------------------------------------

_MEDYA_ONBELLEK_SN = 60 * 60 * 24 * 30  # dosya adları içerik özetli; uzun tutulabilir


def _dosya_parcasi(dosya, uzunluk: int, parca: int = 64 * 1024):
    """Dosyadan yalnız istenen kadarını akıtır (Range yanıtı için)."""
    try:
        kalan = uzunluk
        while kalan > 0:
            veri = dosya.read(min(parca, kalan))
            if not veri:
                break
            kalan -= len(veri)
            yield veri
    finally:
        dosya.close()


@xframe_options_exempt
def ekran_medyasi(request, path: str):
    """Ekran modülünün medya dosyalarını **Range destekli** servis eder.

    Django'nun ``FileResponse``'u byte-range isteklerini karşılamaz. Akıllı
    televizyon tarayıcılarının çoğu WebKit tabanlıdır ve ``<video>`` için
    sunucudan 206 (Partial Content) bekler; range olmadan video hiç
    başlamayabilir. Bu yüzden aramayı elle uyguluyoruz.

    Yol güvenliği ``safe_join`` ile sağlanır: disk kökünün dışına çıkan
    istekler reddedilir.
    """
    import mimetypes
    import os
    import re

    from django.conf import settings
    from django.core.exceptions import SuspiciousFileOperation
    from django.http import (
        FileResponse,
        Http404,
        HttpResponse,
        HttpResponseNotModified,
        StreamingHttpResponse,
    )
    from django.utils._os import safe_join
    from django.utils.http import http_date
    from django.views.static import was_modified_since

    try:
        tam_yol = safe_join(str(settings.EKRAN_MEDIA_ROOT), path)
    except (SuspiciousFileOperation, ValueError):
        raise Http404("Dosya bulunamadı.")

    if not os.path.isfile(tam_yol):
        raise Http404("Dosya bulunamadı.")

    durum = os.stat(tam_yol)
    boyut = durum.st_size
    tur, kodlama = mimetypes.guess_type(tam_yol)
    tur = tur or "application/octet-stream"

    if not was_modified_since(request.META.get("HTTP_IF_MODIFIED_SINCE"), durum.st_mtime):
        yanit = HttpResponseNotModified()
        yanit["Accept-Ranges"] = "bytes"
        return yanit

    def baslikla(yanit):
        yanit["Accept-Ranges"] = "bytes"
        yanit["Last-Modified"] = http_date(durum.st_mtime)
        yanit["Cache-Control"] = f"public, max-age={_MEDYA_ONBELLEK_SN}"
        if kodlama:
            yanit["Content-Encoding"] = kodlama
        return yanit

    aralik = request.META.get("HTTP_RANGE", "")
    eslesme = re.match(r"bytes=(\d*)-(\d*)$", aralik.strip()) if aralik else None

    if eslesme:
        bas_ham, son_ham = eslesme.groups()
        if bas_ham:
            bas = int(bas_ham)
            son = int(son_ham) if son_ham else boyut - 1
        elif son_ham:
            # "bytes=-500" → son 500 bayt
            bas = max(0, boyut - int(son_ham))
            son = boyut - 1
        else:
            bas, son = 0, boyut - 1

        son = min(son, boyut - 1)
        if bas > son or bas >= boyut:
            yanit = HttpResponse(status=416)
            yanit["Content-Range"] = f"bytes */{boyut}"
            return baslikla(yanit)

        uzunluk = son - bas + 1
        dosya = open(tam_yol, "rb")
        dosya.seek(bas)
        yanit = StreamingHttpResponse(
            _dosya_parcasi(dosya, uzunluk), status=206, content_type=tur
        )
        yanit["Content-Length"] = str(uzunluk)
        yanit["Content-Range"] = f"bytes {bas}-{son}/{boyut}"
        return baslikla(yanit)

    yanit = FileResponse(open(tam_yol, "rb"), content_type=tur)
    yanit["Content-Length"] = str(boyut)
    return baslikla(yanit)
