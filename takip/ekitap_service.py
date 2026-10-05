"""E-Kitap iş kuralları: PDF işleme, PIN ve yönetici şifresi doğrulama."""

from __future__ import annotations

import hmac
import io
import logging
import threading

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction

from takip.ekitap_models import EKitap, EKitapAyar, EKitapBolum, EKitapSayfa

logger = logging.getLogger(__name__)

OTURUM_YONETICI = "ekitap_yonetici"
OTURUM_PIN = "ekitap_pin_surumu"

KUCUK_GENISLIK = 480
WEBP_KALITE = 90


# —— Oturum ————————————————————————————————————————————————————————————————


def yonetici_mi(request) -> bool:
    return bool(request.session.get(OTURUM_YONETICI))


def pin_gecerli_mi(request) -> bool:
    """Yönetici her şeyi görür; diğerleri güncel PIN ile açılmış oturum ister."""
    if yonetici_mi(request):
        return True
    surum = request.session.get(OTURUM_PIN)
    if surum is None:
        return False
    ayar = EKitapAyar.al()
    return bool(ayar.pin_hash) and surum == ayar.pin_surumu


def _istemci_ip(request) -> str:
    # Render'ın proxy'si gerçek istemci IP'sini listenin SONUNA ekler; baştaki
    # değerleri istemci kendisi yazabilir (deneme sınırını atlatmak için).
    ileri = request.META.get("HTTP_X_FORWARDED_FOR", "")
    son = ileri.split(",")[-1].strip() if ileri else ""
    return son or request.META.get("REMOTE_ADDR", "?")


def deneme_kilitli_mi(request, tur: str, *, limit: int, sure_sn: int) -> bool:
    return int(cache.get(f"ekitap-deneme:{tur}:{_istemci_ip(request)}") or 0) >= limit


def hatali_deneme_kaydet(request, tur: str, *, sure_sn: int) -> None:
    anahtar = f"ekitap-deneme:{tur}:{_istemci_ip(request)}"
    if not cache.add(anahtar, 1, timeout=sure_sn):
        try:
            cache.incr(anahtar)
        except ValueError:
            cache.set(anahtar, 1, timeout=sure_sn)


def denemeleri_sifirla(request, tur: str) -> None:
    cache.delete(f"ekitap-deneme:{tur}:{_istemci_ip(request)}")


def yonetici_sifresi_tanimli_mi() -> bool:
    return bool((getattr(settings, "EKITAP_YONETICI_SIFRE", "") or "").strip())


def yonetici_sifresi_dogru_mu(sifre: str) -> bool:
    beklenen = (getattr(settings, "EKITAP_YONETICI_SIFRE", "") or "").strip()
    if not beklenen or not sifre:
        return False
    return hmac.compare_digest(sifre.encode("utf-8"), beklenen.encode("utf-8"))


def pin_belirle(pin: str) -> None:
    ayar = EKitapAyar.al()
    ayar.pin_hash = make_password(pin)
    ayar.pin_surumu += 1
    ayar.save()


def pin_dogru_mu(pin: str) -> int | None:
    """Doğruysa PIN sürümünü döner (oturuma yazılır), değilse None."""
    ayar = EKitapAyar.al()
    if not ayar.pin_hash or not pin:
        return None
    return ayar.pin_surumu if check_password(pin, ayar.pin_hash) else None


# —— PDF işleme —————————————————————————————————————————————————————————————


def pdf_dogrula(dosya) -> str:
    """Hata mesajı döner; geçerliyse boş metin."""
    maks = int(getattr(settings, "EKITAP_MAKS_PDF_MB", 80))
    if dosya.size > maks * 1024 * 1024:
        return f"{dosya.name}: dosya {maks} MB sınırını aşıyor."
    bas = dosya.read(5)
    dosya.seek(0)
    if bas != b"%PDF-":
        return f"{dosya.name}: geçerli bir PDF değil."
    return ""


def _bolum_gorsellerini_sil(bolum: EKitapBolum) -> None:
    for sayfa in bolum.sayfalar.all():
        sayfa.gorsel.delete(save=False)
        if sayfa.kucuk:
            sayfa.kucuk.delete(save=False)
    bolum.sayfalar.all().delete()


def bolum_dosyalarini_sil(bolum: EKitapBolum) -> None:
    _bolum_gorsellerini_sil(bolum)
    if bolum.pdf:
        bolum.pdf.delete(save=False)


def kitap_sil(kitap: EKitap) -> None:
    for bolum in kitap.bolumler.all():
        bolum_dosyalarini_sil(bolum)
    kitap.delete()


def _beyaz_zemin(gorsel):
    from PIL import Image

    if gorsel.mode in ("RGBA", "LA", "P"):
        rgba = gorsel.convert("RGBA")
        zemin = Image.new("RGB", rgba.size, (255, 255, 255))
        zemin.paste(rgba, mask=rgba.split()[-1])
        return zemin
    return gorsel.convert("RGB") if gorsel.mode != "RGB" else gorsel


def _webp(gorsel, *, kalite: int = WEBP_KALITE) -> bytes:
    tampon = io.BytesIO()
    gorsel.save(tampon, format="WEBP", quality=kalite, method=4)
    return tampon.getvalue()


def bolum_isle(bolum_id: int) -> None:
    """PDF'i sayfa sayfa WebP görsele çevirir. Hata durumunu bölüme yazar."""
    bolum = EKitapBolum.objects.filter(pk=bolum_id).first()
    if bolum is None:
        return
    try:
        import pypdfium2 as pdfium
    except ImportError:
        bolum.islem_durumu = EKitapBolum.IslemDurumu.HATA
        bolum.islem_notu = "Sunucuda pypdfium2 kurulu değil."
        bolum.save(update_fields=["islem_durumu", "islem_notu", "guncellenme"])
        return

    _bolum_gorsellerini_sil(bolum)
    try:
        with bolum.pdf.open("rb") as f:
            ham = f.read()
        belge = pdfium.PdfDocument(ham)
    except Exception as hata:  # noqa: BLE001
        logger.warning("E-kitap PDF açılamadı bolum=%s: %s", bolum.pk, hata)
        bolum.islem_durumu = EKitapBolum.IslemDurumu.HATA
        bolum.islem_notu = "PDF açılamadı. Dosya şifreli veya bozuk olabilir."
        bolum.save(update_fields=["islem_durumu", "islem_notu", "guncellenme"])
        return

    hedef_genislik = int(getattr(settings, "EKITAP_SAYFA_GENISLIK", 2000))
    maks_sayfa = int(getattr(settings, "EKITAP_MAKS_SAYFA", 300))
    toplam = len(belge)
    yazilan = 0
    try:
        for indeks in range(min(toplam, maks_sayfa)):
            sayfa = belge[indeks]
            olcek = max(0.5, min(6.0, hedef_genislik / (sayfa.get_width() or 1)))
            gorsel = _beyaz_zemin(
                sayfa.render(scale=olcek, fill_color=(255, 255, 255, 255)).to_pil()
            )
            sayfa.close()
            kucuk = gorsel.copy()
            kucuk.thumbnail((KUCUK_GENISLIK, KUCUK_GENISLIK * 2))
            kayit = EKitapSayfa(
                bolum=bolum, sira=indeks, genislik=gorsel.width, yukseklik=gorsel.height
            )
            kayit.gorsel.save(f"{bolum.pk}-{indeks + 1}.webp", ContentFile(_webp(gorsel)), save=False)
            kayit.kucuk.save(
                f"{bolum.pk}-{indeks + 1}-k.webp", ContentFile(_webp(kucuk, kalite=80)), save=False
            )
            kayit.save()
            yazilan += 1
    except Exception as hata:  # noqa: BLE001
        logger.exception("E-kitap sayfası işlenemedi bolum=%s", bolum.pk)
        bolum.islem_durumu = EKitapBolum.IslemDurumu.HATA
        bolum.islem_notu = f"Sayfa {yazilan + 1} işlenemedi: {type(hata).__name__}"
        bolum.sayfa_sayisi = yazilan
        bolum.save(update_fields=["islem_durumu", "islem_notu", "sayfa_sayisi", "guncellenme"])
        return
    finally:
        belge.close()

    bolum.sayfa_sayisi = yazilan
    bolum.islem_durumu = EKitapBolum.IslemDurumu.HAZIR if yazilan else EKitapBolum.IslemDurumu.HATA
    bolum.islem_notu = (
        f"Yalnızca ilk {maks_sayfa} sayfa alındı." if toplam > maks_sayfa else ("" if yazilan else "PDF'te sayfa yok.")
    )
    bolum.save(update_fields=["islem_durumu", "islem_notu", "sayfa_sayisi", "guncellenme"])


def _arka_planda_isle(bolum_ids: list[int]) -> None:
    try:
        for bolum_id in bolum_ids:
            bolum_isle(bolum_id)
    finally:
        close_old_connections()


def bolumleri_isle(bolum_ids: list[int]) -> None:
    """Yükleme isteğini bekletmemek için PDF'leri arka planda işler.

    Sunucu işlem sırasında yeniden başlarsa bölüm "İşleniyor" kalır;
    yönetim panelindeki "Yeniden işle" düğmesiyle tekrar başlatılır.
    """
    if not bolum_ids:
        return
    EKitapBolum.objects.filter(pk__in=bolum_ids).update(
        islem_durumu=EKitapBolum.IslemDurumu.BEKLIYOR, islem_notu=""
    )
    if not getattr(settings, "EKITAP_ARKA_PLAN_ISLEME", True):
        for bolum_id in bolum_ids:
            bolum_isle(bolum_id)
        return
    transaction.on_commit(
        lambda: threading.Thread(
            target=_arka_planda_isle, args=(list(bolum_ids),), daemon=True, name="ekitap-pdf"
        ).start()
    )
