"""Televizyon ↔ sunucu API'si.

Bu uçlar oturum açmış bir kullanıcıyla değil, cihazın kendi gizli anahtarıyla
kimliklenir. Anahtar televizyonun tarayıcısında ``localStorage``'da durur ve
``X-Ekran-Anahtar`` başlığıyla gönderilir.

Güvenlik
--------
* Anahtar 32 baytlık rastgele bir değerdir; tahmin edilemez.
* Eşleştirme kodu **süreli** (15 dk) ve **tek kullanımlıktır**; kullanılınca
  temizlenir.
* Eşleşmemiş cihaz yayın paketi alamaz — yalnız "eşleştirme bekleniyor"
  yanıtı döner.
* Kayıt ucu IP başına saatlik sınırlıdır; aksi hâlde kaydolmamış cihaz
  tablosu dışarıdan şişirilebilirdi.
* Tüm uçlar CSRF'den muaftır (oturum çerezi kullanmazlar) ve yalnız kendi
  cihazının verisini döndürür.
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.db import transaction
from django.http import HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from takip.ekran_models import (
    EkranCihaz,
    EkranCihazOlayi,
    EkranOynatmaRaporu,
    EkranYayinPaketi,
)
from takip.ekran_service import (
    YOKLAMA_ARALIGI_SN,
    cihaz_durumu,
    istek_ip,
    nabiz_isle,
    yayin_alindi_bildir,
    yayin_paketi_verisi,
)

ANAHTAR_BASLIGI = "HTTP_X_EKRAN_ANAHTAR"

# Aynı IP'den saatte en fazla bu kadar yeni (eşleşmemiş) cihaz kaydı.
KAYIT_SINIRI_SAATLIK = 8


def _hata(mesaj: str, kod: int = 400, **ek) -> JsonResponse:
    return JsonResponse({"tamam": False, "mesaj": mesaj, **ek}, status=kod)


def _cihaz_bul(request) -> EkranCihaz | None:
    anahtar = (request.META.get(ANAHTAR_BASLIGI) or "").strip()
    if not anahtar or len(anahtar) > 64:
        return None
    return (
        EkranCihaz.objects.select_related("konum", "aktif_sahne")
        .filter(cihaz_anahtari=anahtar)
        .first()
    )


def _govde(request) -> dict:
    if not request.body:
        return {}
    try:
        veri = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return veri if isinstance(veri, dict) else {}


def _cozunurluk(veri: dict) -> tuple[int, int] | None:
    try:
        g = int(veri.get("genislik") or 0)
        y = int(veri.get("yukseklik") or 0)
    except (TypeError, ValueError):
        return None
    if 0 < g <= 10000 and 0 < y <= 10000:
        return g, y
    return None


# ---------------------------------------------------------------------------
# Kayıt ve eşleştirme
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
@transaction.atomic
def cihaz_kayit(request):
    """Yeni televizyon kendini tanıtır; anahtar ve eşleştirme kodu alır."""
    ip = istek_ip(request)

    if ip:
        son_bir_saat = timezone.now() - timedelta(hours=1)
        taze_kayit = EkranCihaz.objects.filter(
            son_ip=ip,
            durum=EkranCihaz.Durum.BEKLIYOR,
            olusturulma__gte=son_bir_saat,
        ).count()
        if taze_kayit >= KAYIT_SINIRI_SAATLIK:
            return _hata(
                "Bu ağdan çok fazla yeni ekran kaydı yapıldı. Lütfen bir süre sonra tekrar deneyin.",
                kod=429,
            )

    veri = _govde(request)
    cihaz = EkranCihaz(
        son_ip=ip,
        tarayici=(request.META.get("HTTP_USER_AGENT") or "")[:255],
        uygulama_surumu=str(veri.get("surum") or "")[:40],
        son_baglanti=timezone.now(),
    )
    cozunurluk = _cozunurluk(veri)
    if cozunurluk:
        cihaz.cozunurluk_genislik, cihaz.cozunurluk_yukseklik = cozunurluk
        cihaz.yonelim = (
            EkranCihaz.Yonelim.DIKEY if cozunurluk[1] > cozunurluk[0] else EkranCihaz.Yonelim.YATAY
        )
    cihaz.save()
    kod = cihaz.yeni_eslestirme_kodu()

    return JsonResponse(
        {
            "tamam": True,
            "anahtar": cihaz.cihaz_anahtari,
            "eslestirme_kodu": kod,
            "gecerlilik": cihaz.eslestirme_kodu_bitis.isoformat(),
            "yoklama_sn": YOKLAMA_ARALIGI_SN,
        }
    )


@csrf_exempt
@require_POST
def eslestirme_kodu_yenile(request):
    """Kodun süresi dolduğunda televizyon yenisini ister."""
    cihaz = _cihaz_bul(request)
    if cihaz is None:
        return _hata("Cihaz tanınmadı.", kod=404, yeniden_kaydol=True)
    if cihaz.durum != EkranCihaz.Durum.BEKLIYOR:
        return JsonResponse({"tamam": True, "eslestirildi": True})

    kod = cihaz.yeni_eslestirme_kodu()
    return JsonResponse(
        {
            "tamam": True,
            "eslestirme_kodu": kod,
            "gecerlilik": cihaz.eslestirme_kodu_bitis.isoformat(),
        }
    )


# ---------------------------------------------------------------------------
# Yoklama ve yayın
# ---------------------------------------------------------------------------


@csrf_exempt
def cihaz_yoklama(request):
    """Televizyonun ~10 saniyede bir sorduğu hafif uç.

    Yalnız bir damga döner. Damga değişmediyse televizyon hiçbir şey
    indirmez; bu, WebSocket kurmadan neredeyse anlık güncelleme sağlar ve
    2 worker'lık WSGI sunucusunu meşgul etmez.
    """
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])

    cihaz = _cihaz_bul(request)
    if cihaz is None:
        return _hata("Cihaz tanınmadı.", kod=404, yeniden_kaydol=True)

    veri = _govde(request)
    nabiz_isle(
        cihaz,
        ip=istek_ip(request),
        tarayici=request.META.get("HTTP_USER_AGENT") or "",
        surum=str(veri.get("surum") or ""),
        cozunurluk=_cozunurluk(veri),
    )

    if cihaz.durum == EkranCihaz.Durum.BEKLIYOR:
        if not cihaz.kod_gecerli_mi:
            cihaz.yeni_eslestirme_kodu()
        return JsonResponse(
            {
                "tamam": True,
                "eslestirildi": False,
                "eslestirme_kodu": cihaz.eslestirme_kodu,
                "gecerlilik": cihaz.eslestirme_kodu_bitis.isoformat(),
                "yoklama_sn": YOKLAMA_ARALIGI_SN,
            }
        )

    if cihaz.durum == EkranCihaz.Durum.PASIF:
        return JsonResponse(
            {
                "tamam": True,
                "eslestirildi": True,
                "pasif": True,
                "mesaj": "Bu ekran yönetim panelinden pasife alınmış.",
                "yoklama_sn": YOKLAMA_ARALIGI_SN,
            }
        )

    durum = cihaz_durumu(cihaz)
    yanit = durum.sozluk(timezone.localtime())
    yanit.update({"tamam": True, "eslestirildi": True, "pasif": False})
    return JsonResponse(yanit)


@csrf_exempt
@require_GET
def cihaz_yayini(request):
    """Damga değiştiğinde çekilen tam yayın paketi."""
    cihaz = _cihaz_bul(request)
    if cihaz is None:
        return _hata("Cihaz tanınmadı.", kod=404, yeniden_kaydol=True)
    if cihaz.durum != EkranCihaz.Durum.AKTIF:
        return _hata("Bu ekran henüz eşleştirilmemiş.", kod=403)

    return JsonResponse(yayin_paketi_verisi(cihaz))


@csrf_exempt
@require_POST
def cihaz_raporu(request):
    """Televizyon yayını aldığını ya da bir sorun yaşadığını bildirir."""
    cihaz = _cihaz_bul(request)
    if cihaz is None:
        return _hata("Cihaz tanınmadı.", kod=404, yeniden_kaydol=True)

    veri = _govde(request)
    damga = str(veri.get("damga") or "")[:64]
    sonuc = veri.get("sonuc")
    mesaj = str(veri.get("mesaj") or "")[:400]

    if sonuc not in dict(EkranOynatmaRaporu.Sonuc.choices):
        sonuc = EkranOynatmaRaporu.Sonuc.ALINDI

    paket = None
    paket_damgasi = str(veri.get("paket_damgasi") or "")[:64]
    if paket_damgasi:
        paket = EkranYayinPaketi.objects.filter(damga=paket_damgasi).first()

    if sonuc == EkranOynatmaRaporu.Sonuc.ALINDI:
        yayin_alindi_bildir(cihaz, damga, paket)
    else:
        EkranCihazOlayi.objects.create(
            cihaz=cihaz,
            tur=EkranCihazOlayi.Tur.HATA,
            mesaj=mesaj,
            yayin_damgasi=damga,
        )

    # Rapor satırı yalnız hata veya yeni paket için yazılır; her nabızda değil.
    if sonuc != EkranOynatmaRaporu.Sonuc.ALINDI or (paket and cihaz.son_yayin_damgasi == damga):
        EkranOynatmaRaporu.objects.create(cihaz=cihaz, paket=paket, sonuc=sonuc, mesaj=mesaj)

    return JsonResponse({"tamam": True})
