"""E-Kitap iş kuralları: PDF işleme, PIN ve yönetici şifresi doğrulama."""

from __future__ import annotations

import hashlib
import hmac
import io
import logging
import threading

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction
from django.db.models import Q

from takip.ekitap_models import (
    EKitap,
    EKitapAyar,
    EKitapBolum,
    EKitapSayfa,
    EKitapSoru,
    EKitapSoruAlan,
)

logger = logging.getLogger(__name__)

OTURUM_YONETICI = "ekitap_yonetici"
OTURUM_PIN = "ekitap_pin_surumu"

KUCUK_GENISLIK = 480
WEBP_KALITE = 90
SORU_UZUN_KENAR = 2000  # soru görseli: uzun kenar piksel (sayfa görselinin ~2 katı netlik)
SORU_MAKS_OLCEK = 8.0
SORU_GORSEL_SURUMU = "1"

# pdfium iş parçacığı güvenli değildir; gunicorn iş parçacıkları ve arka plan
# işleme aynı süreçte çalışabildiği için tüm pdfium çağrıları bu kilitle sıralanır.
PDFIUM_KILIDI = threading.RLock()


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


def soru_gorsellerini_sil(sorular) -> None:
    for alan in EKitapSoruAlan.objects.filter(soru__in=sorular).exclude(gorsel=""):
        alan.gorsel.delete(save=False)


def bolum_dosyalarini_sil(bolum: EKitapBolum) -> None:
    _bolum_gorsellerini_sil(bolum)
    soru_gorsellerini_sil(bolum.sorular.all())
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


def _belge_ac(bolum: EKitapBolum):
    import pypdfium2 as pdfium

    try:
        return pdfium.PdfDocument(bolum.pdf.path)
    except (NotImplementedError, AttributeError):
        with bolum.pdf.open("rb") as f:
            return pdfium.PdfDocument(f.read())


def _pdf_ozeti(bolum: EKitapBolum) -> str:
    ozet = hashlib.sha256()
    with bolum.pdf.open("rb") as f:
        for parca in iter(lambda: f.read(1024 * 1024), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def bolum_isle(bolum_id: int) -> None:
    """PDF'i sayfa sayfa WebP görsele çevirir, ardından soruları bulur.

    Hata durumunu bölüme yazar.
    """
    bolum = EKitapBolum.objects.filter(pk=bolum_id).first()
    if bolum is None:
        return
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        bolum.islem_durumu = EKitapBolum.IslemDurumu.HATA
        bolum.islem_notu = "Sunucuda pypdfium2 kurulu değil."
        bolum.save(update_fields=["islem_durumu", "islem_notu", "guncellenme"])
        return

    _bolum_gorsellerini_sil(bolum)
    try:
        with PDFIUM_KILIDI:
            belge = _belge_ac(bolum)
    except Exception as hata:  # noqa: BLE001
        logger.warning("E-kitap PDF açılamadı bolum=%s: %s", bolum.pk, hata)
        bolum.islem_durumu = EKitapBolum.IslemDurumu.HATA
        bolum.islem_notu = "PDF açılamadı. Dosya şifreli veya bozuk olabilir."
        bolum.tespit_durumu = EKitapBolum.TespitDurumu.YOK
        bolum.save(update_fields=["islem_durumu", "islem_notu", "tespit_durumu", "guncellenme"])
        return

    hedef_genislik = int(getattr(settings, "EKITAP_SAYFA_GENISLIK", 2000))
    maks_sayfa = int(getattr(settings, "EKITAP_MAKS_SAYFA", 300))
    toplam = len(belge)
    yazilan = 0
    try:
        for indeks in range(min(toplam, maks_sayfa)):
            with PDFIUM_KILIDI:
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
        bolum.tespit_durumu = EKitapBolum.TespitDurumu.YOK
        bolum.save(update_fields=["islem_durumu", "islem_notu", "sayfa_sayisi", "tespit_durumu", "guncellenme"])
        with PDFIUM_KILIDI:
            belge.close()
        return

    bolum.sayfa_sayisi = yazilan
    bolum.islem_durumu = EKitapBolum.IslemDurumu.HAZIR if yazilan else EKitapBolum.IslemDurumu.HATA
    bolum.islem_notu = (
        f"Yalnızca ilk {maks_sayfa} sayfa alındı." if toplam > maks_sayfa else ("" if yazilan else "PDF'te sayfa yok.")
    )
    bolum.save(update_fields=["islem_durumu", "islem_notu", "sayfa_sayisi", "guncellenme"])
    try:
        if yazilan:
            sorulari_bul(bolum.pk, belge=belge)
        else:
            EKitapBolum.objects.filter(pk=bolum.pk).update(tespit_durumu=EKitapBolum.TespitDurumu.YOK)
    finally:
        with PDFIUM_KILIDI:
            belge.close()


# —— Soru tespiti ——————————————————————————————————————————————————————————


def _alan_kutusu(alan: EKitapSoruAlan):
    from takip.ekitap_soru_tespit import Kutu

    return Kutu(alan.x0, alan.y0, alan.x1, alan.y1)


def _korunanla_cakisiyor(taslak, korunan_alanlar: list[EKitapSoruAlan], korunan_kimlikler: set) -> bool:
    if (taslak.test_no, taslak.no) in korunan_kimlikler:
        return True
    for sayfa_sira, kutu in taslak.alanlar:
        for alan in korunan_alanlar:
            if alan.sayfa_sira != sayfa_sira:
                continue
            ortak = kutu.kesisim(_alan_kutusu(alan))
            if ortak > 0.3 * min(kutu.alan(), _alan_kutusu(alan).alan() or 1):
                return True
    return False


def sorulari_bul(bolum_id: int, *, belge=None):
    """Bölümün sorularını (yeniden) bulur. Tekrar çalıştırılması güvenlidir.

    - Onaylı ya da elle eklenmiş sorular korunur; PDF değiştiyse
      "inceleme gerekli" olarak işaretlenir.
    - Otomatik sorular silinip yeniden oluşturulur (korunanlarla çakışanlar hariç).
    - Sayfa uyarıları ("Kontrol edin") ve bölüm tespit durumu güncellenir.
    - Eksik/eskimiş soru görselleri üretilir.
    """
    from takip.ekitap_soru_tespit import tespit_et

    bolum = EKitapBolum.objects.filter(pk=bolum_id).first()
    if bolum is None or bolum.islem_durumu != EKitapBolum.IslemDurumu.HAZIR:
        return None
    kendi_actik = belge is None
    try:
        ozet = _pdf_ozeti(bolum)
        with PDFIUM_KILIDI:
            if kendi_actik:
                belge = _belge_ac(bolum)
            sonuc = tespit_et(belge, maks_sayfa=bolum.sayfa_sayisi or None)
    except Exception as hata:  # noqa: BLE001
        logger.exception("E-kitap soru tespiti başarısız bolum=%s", bolum.pk)
        bolum.tespit_durumu = EKitapBolum.TespitDurumu.HATA
        bolum.tespit_notu = f"Soru tespiti yapılamadı: {type(hata).__name__}"
        bolum.save(update_fields=["tespit_durumu", "tespit_notu", "guncellenme"])
        if kendi_actik and belge is not None:
            with PDFIUM_KILIDI:
                belge.close()
        return None

    try:
        _tespiti_kaydet(bolum, sonuc, ozet)
        soru_gorsellerini_uret(bolum, belge=belge)
    finally:
        if kendi_actik:
            with PDFIUM_KILIDI:
                belge.close()
    return sonuc


@transaction.atomic
def _tespiti_kaydet(bolum: EKitapBolum, sonuc, ozet: str) -> None:
    korunan = list(
        bolum.sorular.filter(Q(onayli=True) | Q(kaynak=EKitapSoru.Kaynak.ELLE)).prefetch_related("alanlar")
    )
    for soru in korunan:
        if soru.pdf_ozeti and soru.pdf_ozeti != ozet and not soru.inceleme_gerekli:
            soru.inceleme_gerekli = True
            soru.save(update_fields=["inceleme_gerekli", "guncellenme"])
    # Otomatik sorular (test, numara) eşleşmesiyle yerinde güncellenir; böylece
    # soru kimlikleri (ders akışları bunlara bağlıdır) yeniden tespitte korunur.
    eskiler = {
        (s.test_no, s.no): s
        for s in bolum.sorular.exclude(pk__in=[s.pk for s in korunan]).prefetch_related("alanlar")
    }
    korunan_alanlar = [a for s in korunan for a in s.alanlar.all()]
    korunan_kimlikler = {(s.test_no, s.no) for s in korunan}
    kullanilan: set[int] = set()
    for taslak in sonuc.sorular:
        if _korunanla_cakisiyor(taslak, korunan_alanlar, korunan_kimlikler):
            continue
        yeni_alanlar = [(sayfa_sira, k.yuvarla()) for sayfa_sira, k in taslak.alanlar]
        siklar = taslak.siklar or (None, None)
        soru = eskiler.get((taslak.test_no, taslak.no))
        if soru is not None and soru.pk not in kullanilan:
            soru.sira, soru.guven, soru.pdf_ozeti = taslak.sira, taslak.guven, ozet
            soru.siklar_alan, soru.siklar_y = siklar
            soru.save(update_fields=["sira", "guven", "pdf_ozeti", "siklar_alan", "siklar_y", "guncellenme"])
            mevcut = [(a.sayfa_sira, (a.x0, a.y0, a.x1, a.y1)) for a in soru.alanlar.all()]
            if mevcut == yeni_alanlar:
                kullanilan.add(soru.pk)
                continue  # alanlar aynı: görseller de geçerli kalır
            soru_gorsellerini_sil([soru])
            soru.alanlar.all().delete()
        else:
            soru = EKitapSoru.objects.create(
                bolum=bolum,
                test_no=taslak.test_no,
                no=taslak.no,
                sira=taslak.sira,
                guven=taslak.guven,
                pdf_ozeti=ozet,
                siklar_alan=siklar[0],
                siklar_y=siklar[1],
            )
        kullanilan.add(soru.pk)
        EKitapSoruAlan.objects.bulk_create(
            [
                EKitapSoruAlan(soru=soru, sira=i, sayfa_sira=sayfa_sira, x0=x0, y0=y0, x1=x1, y1=y1)
                for i, (sayfa_sira, (x0, y0, x1, y1)) in enumerate(yeni_alanlar)
            ]
        )
    artanlar = [s.pk for s in eskiler.values() if s.pk not in kullanilan]
    if artanlar:
        soru_gorsellerini_sil(artanlar)
        EKitapSoru.objects.filter(pk__in=artanlar).delete()

    # Okuma sırası: ilk alanın sayfası → sütunu → yüksekliği
    sorular = list(bolum.sorular.prefetch_related("alanlar"))

    def anahtar(s: EKitapSoru):
        alanlar = sorted(s.alanlar.all(), key=lambda a: a.sira)
        if not alanlar:
            return (10**6, 0, 0.0, s.test_no, s.no)
        ilk = alanlar[0]
        return (ilk.sayfa_sira, sonuc.sutun_indeksi(ilk.x0 + 0.015), ilk.y0, s.test_no, s.no)

    sorular.sort(key=anahtar)
    for sira, soru in enumerate(sorular):
        if soru.sira != sira:
            soru.sira = sira
            soru.save(update_fields=["sira"])

    inceleme_sayfalari = {
        a.sayfa_sira for s in sorular if s.inceleme_gerekli for a in s.alanlar.all()
    }
    for sayfa in bolum.sayfalar.all():
        bilgi = sonuc.sayfalar.get(sayfa.sira)
        notlar = list(bilgi.notlar) if bilgi else []
        if sayfa.sira in inceleme_sayfalari:
            notlar.append("PDF değişti: elle düzeltilmiş alanları yeniden inceleyin.")
        sayfa.metinli = bilgi.metinli if bilgi else True
        sayfa.kontrol_gerekli = bool(notlar)
        sayfa.kontrol_notu = " · ".join(notlar)[:500]
        sayfa.save(update_fields=["metinli", "kontrol_gerekli", "kontrol_notu"])

    bolum.tespit_durumu = sonuc.durum
    bolum.tespit_notu = sonuc.not_[:255]
    bolum.pdf_ozeti = ozet
    bolum.save(update_fields=["tespit_durumu", "tespit_notu", "pdf_ozeti", "guncellenme"])


def _alan_imzasi(alan: EKitapSoruAlan, ozet: str) -> str:
    ham = f"{SORU_GORSEL_SURUMU}:{ozet}:{alan.sayfa_sira}:{alan.x0:.4f}:{alan.y0:.4f}:{alan.x1:.4f}:{alan.y1:.4f}"
    return hashlib.sha1(ham.encode()).hexdigest()[:16]


def _dogal_olcek(sayfa) -> float | None:
    """Taranmış sayfada gömülü görselin çözünürlüğü (piksel / pt)."""
    import pypdfium2.raw as pdfium_c

    en_iyi = None
    for nesne in sayfa.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,), max_depth=3):
        try:
            px = nesne.get_px_size() if hasattr(nesne, "get_px_size") else nesne.get_size()
            sol, alt, sag, ust = nesne.get_bounds() if hasattr(nesne, "get_bounds") else nesne.get_pos()
        except Exception:  # noqa: BLE001
            continue
        if sag - sol > 1 and px and px[0]:
            olcek = px[0] / (sag - sol)
            en_iyi = max(en_iyi or 0, olcek)
    return en_iyi


def _alan_gorseli(belge, alan: EKitapSoruAlan, metinli: bool):
    sayfa = belge[alan.sayfa_sira]
    try:
        W, H = sayfa.get_size()
        g_pt = max((alan.x1 - alan.x0) * W, 1.0)
        y_pt = max((alan.y1 - alan.y0) * H, 1.0)
        olcek = SORU_UZUN_KENAR / max(g_pt, y_pt)
        if not metinli:
            # Taranmış kaynakta görselin kendi çözünürlüğü korunur (büyütme/küçültme yok).
            olcek = _dogal_olcek(sayfa) or olcek
        olcek = max(1.0, min(SORU_MAKS_OLCEK, olcek))
        kirp = (alan.x0 * W, (1 - alan.y1) * H, (1 - alan.x1) * W, alan.y0 * H)
        return _beyaz_zemin(
            sayfa.render(scale=olcek, crop=kirp, fill_color=(255, 255, 255, 255)).to_pil()
        )
    finally:
        sayfa.close()


def soru_gorsellerini_uret(bolum: EKitapBolum, *, belge=None) -> int:
    """Eksik ya da koordinatı değişmiş soru alanlarının yüksek çözünürlüklü görselini üretir."""
    ozet = bolum.pdf_ozeti
    alanlar = [
        a for a in EKitapSoruAlan.objects.filter(soru__bolum=bolum).order_by("pk")
        if not a.gorsel or a.gorsel_imza != _alan_imzasi(a, ozet)
    ]
    if not alanlar:
        return 0
    metinsiz = set(bolum.sayfalar.filter(metinli=False).values_list("sira", flat=True))
    kendi_actik = belge is None
    uretilen = 0
    try:
        if kendi_actik:
            with PDFIUM_KILIDI:
                belge = _belge_ac(bolum)
        toplam = len(belge)
        for alan in alanlar:
            if alan.sayfa_sira >= toplam or alan.x1 <= alan.x0 or alan.y1 <= alan.y0:
                continue
            metinli = alan.sayfa_sira not in metinsiz
            with PDFIUM_KILIDI:
                gorsel = _alan_gorseli(belge, alan, metinli)
            imza = _alan_imzasi(alan, ozet)
            if alan.gorsel:
                alan.gorsel.delete(save=False)
            alan.gorsel.save(
                f"{alan.pk}-{imza[:10]}.webp",
                ContentFile(_webp(gorsel, kalite=88 if metinli else 92)),
                save=False,
            )
            alan.gorsel_imza = imza
            alan.genislik, alan.yukseklik = gorsel.width, gorsel.height
            alan.save(update_fields=["gorsel", "gorsel_imza", "genislik", "yukseklik"])
            uretilen += 1
    except Exception:  # noqa: BLE001
        logger.exception("E-kitap soru görseli üretilemedi bolum=%s", bolum.pk)
    finally:
        if kendi_actik and belge is not None:
            with PDFIUM_KILIDI:
                belge.close()
    return uretilen


def _arka_planda_soru_bul(bolum_ids: list[int]) -> None:
    try:
        for bolum_id in bolum_ids:
            sorulari_bul(bolum_id)
    finally:
        close_old_connections()


def sorulari_bul_baslat(bolum_ids: list[int]) -> None:
    """Yönetimdeki "Soruları bul" düğmesi: isteği bekletmeden arka planda çalışır."""
    if not bolum_ids:
        return
    EKitapBolum.objects.filter(pk__in=bolum_ids).update(
        tespit_durumu=EKitapBolum.TespitDurumu.ARANIYOR, tespit_notu=""
    )
    if not getattr(settings, "EKITAP_ARKA_PLAN_ISLEME", True):
        for bolum_id in bolum_ids:
            sorulari_bul(bolum_id)
        return
    transaction.on_commit(
        lambda: threading.Thread(
            target=_arka_planda_soru_bul, args=(list(bolum_ids),), daemon=True, name="ekitap-soru"
        ).start()
    )


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
        islem_durumu=EKitapBolum.IslemDurumu.BEKLIYOR,
        islem_notu="",
        tespit_durumu=EKitapBolum.TespitDurumu.ARANIYOR,
        tespit_notu="",
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
