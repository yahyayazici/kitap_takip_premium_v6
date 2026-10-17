"""Seviye Tespit — sonuç Excel'i, karne dosyaları ve veliye gönderim.

Akış:
1. Optik okumanın Excel çıktısı (deneme yüklemesiyle aynı formatlar) yüklenir;
   satırlar ad + sınıfa göre bu sınavın başvurularıyla eşleştirilir.
2. Her öğrenciye PDF/PNG karne yüklenir (tek tek ya da toplu; toplu yüklemede
   dosya adı öğrencinin adıdır).
3. Gönder: uygulama bildirimi (dokununca karne açılır) + e-posta (karne ekte).
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import threading
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import IntegrityError, close_old_connections, transaction
from django.urls import reverse
from django.utils import timezone

from takip.deneme_excel import _benzerlik_orani, deneme_excel_onizle, normalize_ad
from takip.sinav_basvuru_models import SinavBasvuru
from takip.sinav_bildirim_models import SinavBildirimLog, SinavTakvim
from takip.sinav_bildirim_service import (
    _ilk_ad,
    _push_gonder,
    basvuru_token,
    sinav_eposta_aktif,
)
from takip.sinav_sonuc_models import SinavSonuc

logger = logging.getLogger("takip.sinav_sonuc")

KARNE_UZANTILARI = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
KARNE_MAKS_MB = 10
OTOMATIK_ESIK = 0.9
ONERI_ESIK = 0.72

DERSLER = (
    ("turkce", "Türkçe", "Tür"),
    ("matematik", "Matematik", "Mat"),
    ("fen", "Fen Bilimleri", "Fen"),
    ("sosyal", "Sosyal Bilgiler", "Sos"),
    ("din", "Din Kültürü", "Din"),
    ("ingilizce", "İngilizce", "İng"),
)

VARSAYILAN_MESAJ = (
    "Sayın Veli,\n\n"
    "{ad_soyad} için {sinav_adi} sonucu ekte yer almaktadır.\n\n"
    "Katılımınız için teşekkür ederiz."
)


class KarneHatasi(Exception):
    pass


# —— Eşleştirme ——

def _sinif_rakami(metin: str) -> str:
    bul = re.search(r"[4-8]", metin or "")
    return bul.group(0) if bul else ""


def basvuru_eslestir(excel_ad: str, sinif: str, adaylar: list[SinavBasvuru]) -> tuple[SinavBasvuru | None, str, int]:
    """Dönüş: (başvuru, eşleşme: otomatik|oneri|yok, benzerlik yüzdesi)."""
    norm = normalize_ad(excel_ad)
    if not norm:
        return None, "yok", 0
    rakam = _sinif_rakami(sinif)
    uygun = [a for a in adaylar if not rakam or not a.sinif or a.sinif == rakam]

    tam = [a for a in uygun if normalize_ad(a.ad_soyad) == norm]
    if len(tam) == 1:
        return tam[0], "otomatik", 100

    puanli = sorted(
        ((_benzerlik_orani(excel_ad, a.ad_soyad), a) for a in uygun),
        key=lambda t: t[0],
        reverse=True,
    )
    if not puanli:
        return None, "yok", 0
    en_iyi, aday = puanli[0]
    ikinci = puanli[1][0] if len(puanli) > 1 else 0
    if en_iyi >= OTOMATIK_ESIK and en_iyi - ikinci >= 0.08:
        return aday, "otomatik", round(en_iyi * 100)
    if en_iyi >= ONERI_ESIK:
        return aday, "oneri", round(en_iyi * 100)
    return None, "yok", 0


def excel_onizle(dosya, sinav_adi: str) -> dict:
    onizleme = deneme_excel_onizle(dosya, talebe_eslestir_mi=False)
    if onizleme.hatalar and not onizleme.satirlar:
        return {"hatalar": onizleme.hatalar, "satirlar": []}
    adaylar = list(SinavBasvuru.objects.filter(sinav_adi=sinav_adi))
    satirlar = []
    kullanilan: set[int] = set()
    for s in onizleme.satirlar:
        basvuru, eslesme, oran = basvuru_eslestir(s.excel_ad_soyad, s.sinif, adaylar)
        if basvuru and basvuru.pk in kullanilan:
            basvuru, eslesme = None, "yok"
        if basvuru and eslesme == "otomatik":
            kullanilan.add(basvuru.pk)
        satirlar.append(
            {
                "satir_no": s.satir_no,
                "excel_ad": s.excel_ad_soyad,
                "sinif": s.sinif,
                "branslar": s.branslar,
                "toplam": s.toplam,
                "puan": s.puan,
                "basvuru_id": basvuru.pk if basvuru else None,
                "basvuru_ad": basvuru.ad_soyad if basvuru else "",
                "eslesme": eslesme,
                "oran": oran,
            }
        )
    return {"hatalar": onizleme.hatalar, "satirlar": satirlar, "dosya_adi": getattr(dosya, "name", "")}


def _ondalik(deger, varsayilan=None):
    try:
        metin = str(deger).replace(",", ".").strip()
        return Decimal(metin) if metin else varsayilan
    except Exception:  # noqa: BLE001
        return varsayilan


@transaction.atomic
def sonuclari_kaydet(sinav_adi: str, satirlar: list[dict], secimler: dict[int, int | None]) -> int:
    """secimler: satir_no -> basvuru_id (None = atla). Kaydedilen sonuç sayısını döner."""
    gecerli = set(SinavBasvuru.objects.filter(sinav_adi=sinav_adi).values_list("pk", flat=True))
    kaydedilen = 0
    atanan: set[int] = set()
    for satir in satirlar:
        basvuru_id = secimler.get(satir["satir_no"])
        if not basvuru_id or basvuru_id not in gecerli or basvuru_id in atanan:
            continue
        atanan.add(basvuru_id)
        toplam = satir.get("toplam") or {}
        net = _ondalik(toplam.get("net"), Decimal("0"))
        SinavSonuc.objects.update_or_create(
            basvuru_id=basvuru_id,
            defaults={
                "veri_var": True,
                "excel_ad": satir.get("excel_ad", "")[:150],
                "toplam_dogru": int(toplam.get("dogru") or 0),
                "toplam_yanlis": int(toplam.get("yanlis") or 0),
                "toplam_bos": int(toplam.get("bos") or 0),
                "toplam_net": net,
                "puan": _ondalik(satir.get("puan")),
                "branslar": satir.get("branslar") or {},
            },
        )
        kaydedilen += 1
    siralari_hesapla(sinav_adi)
    return kaydedilen


def _siralama_anahtari(s: SinavSonuc):
    return (s.puan if s.puan is not None else Decimal("-1"), s.toplam_net)


def siralari_hesapla(sinav_adi: str) -> None:
    sonuclar = list(
        SinavSonuc.objects.filter(basvuru__sinav_adi=sinav_adi, veri_var=True).select_related("basvuru")
    )
    sonuclar.sort(key=_siralama_anahtari, reverse=True)

    def sirala(liste):
        sira = {}
        onceki, onceki_sira = None, 0
        for i, s in enumerate(liste, start=1):
            anahtar = _siralama_anahtari(s)
            if anahtar != onceki:
                onceki, onceki_sira = anahtar, i
            sira[s.pk] = onceki_sira
        return sira

    genel = sirala(sonuclar)
    sinif_sira: dict[int, int] = {}
    for rakam in {s.basvuru.sinif for s in sonuclar}:
        sinif_sira.update(sirala([s for s in sonuclar if s.basvuru.sinif == rakam]))
    for s in sonuclar:
        s.genel_sira = genel[s.pk]
        s.sinif_sira = sinif_sira.get(s.pk)
    SinavSonuc.objects.bulk_update(sonuclar, ["genel_sira", "sinif_sira"])


# —— Karne dosyaları ——

def karne_kaydet(basvuru: SinavBasvuru, dosya) -> SinavSonuc:
    ad = getattr(dosya, "name", "") or "karne"
    uzanti = os.path.splitext(ad)[1].lower()
    if uzanti not in KARNE_UZANTILARI:
        raise KarneHatasi(f"{ad}: yalnızca PDF, PNG veya JPG yüklenebilir.")
    if getattr(dosya, "size", 0) > KARNE_MAKS_MB * 1024 * 1024:
        raise KarneHatasi(f"{ad}: dosya {KARNE_MAKS_MB} MB'tan büyük.")
    sonuc, _ = SinavSonuc.objects.get_or_create(basvuru=basvuru)
    eski = sonuc.karne.name if sonuc.karne else ""
    sonuc.karne_surum += 1
    sonuc.karne_adi = os.path.basename(ad)[:200]
    sonuc.karne_yuklenme = timezone.now()
    sonuc.karne.save(ad, dosya, save=False)
    sonuc.save()
    if eski and eski != sonuc.karne.name:
        try:
            sonuc.karne.storage.delete(eski)
        except Exception:  # noqa: BLE001
            pass
    return sonuc


def _dosya_adindan_ad(dosya_adi: str) -> str:
    kok = os.path.splitext(os.path.basename(dosya_adi))[0]
    kok = re.sub(r"[_\-\.]+", " ", kok)
    # "12 Ahmet Yılmaz", "Ahmet Yılmaz karne", "Ahmet Yilmaz (6)" gibi adları sadeleştir.
    kok = re.sub(r"\(.*?\)", " ", kok)
    kelimeler = [k for k in kok.split() if not k.isdigit() and normalize_ad(k) not in {"karne", "sonuc", "sinav"}]
    return " ".join(kelimeler)


def toplu_karne_kaydet(sinav_adi: str, dosyalar) -> dict:
    adaylar = list(SinavBasvuru.objects.filter(sinav_adi=sinav_adi))
    yuklenen, eslesmeyen, hatali = [], [], []
    for dosya in dosyalar:
        ad = _dosya_adindan_ad(dosya.name)
        basvuru, eslesme, _ = basvuru_eslestir(ad, "", adaylar)
        if not basvuru or eslesme != "otomatik":
            eslesmeyen.append(dosya.name)
            continue
        try:
            karne_kaydet(basvuru, dosya)
        except KarneHatasi as exc:
            hatali.append(str(exc))
            continue
        yuklenen.append(basvuru.ad_soyad)
    return {"yuklenen": yuklenen, "eslesmeyen": eslesmeyen, "hatali": hatali}


# —— Gönderim ——

def sonuc_sayfasi_url(basvuru: SinavBasvuru) -> str:
    return f"{reverse('sinav_basvuru_sonuc')}?t={basvuru_token(basvuru)}"


def sonuc_mesaji_sablonu(sinav_adi: str) -> str:
    takvim = SinavTakvim.objects.filter(sinav_adi=sinav_adi).first()
    return (takvim.sonuc_mesaji if takvim and takvim.sonuc_mesaji.strip() else VARSAYILAN_MESAJ)


def mesaj_doldur(sablon: str, basvuru: SinavBasvuru) -> str:
    degerler = {
        "ad_soyad": basvuru.ad_soyad,
        "ad": _ilk_ad(basvuru),
        "sinav_adi": basvuru.sinav_adi,
        "sinif": f"{basvuru.sinif}. sınıf" if basvuru.sinif else "",
    }
    metin = sablon
    for anahtar, deger in degerler.items():
        metin = metin.replace("{" + anahtar + "}", deger)
    return metin


def _sonuc_epostasi(sonuc: SinavSonuc, govde: str) -> bool:
    basvuru = sonuc.basvuru
    if not basvuru.veli_eposta or not sinav_eposta_aktif():
        return False
    try:
        mesaj = EmailMessage(
            subject=f"Sınav sonucu · {basvuru.sinav_adi}",
            body=govde.rstrip() + "\n\nÇinili Saray\n",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[basvuru.veli_eposta],
            connection=get_connection(timeout=20),
        )
        with sonuc.karne.open("rb") as f:
            icerik = f.read()
        uzanti = os.path.splitext(sonuc.karne.name)[1].lower()
        dosya_adi = f"{basvuru.ad_soyad} - Sonuç{uzanti}"
        mesaj.attach(dosya_adi, icerik, mimetypes.guess_type(dosya_adi)[0] or "application/octet-stream")
        mesaj.send(fail_silently=False)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("sonuç e-postası gönderilemedi (basvuru=%s)", basvuru.pk)
        return False


def sonuc_gonder(sonuc: SinavSonuc, sablon: str | None = None) -> SinavBildirimLog | None:
    """Karnenin bu sürümü daha önce gönderilmediyse veliye gönderir."""
    if not sonuc.karne or not sonuc.karne_surum:
        return None
    basvuru = sonuc.basvuru
    an_kodu = f"sonuc-{sonuc.karne_surum}"
    govde = mesaj_doldur(sablon or sonuc_mesaji_sablonu(basvuru.sinav_adi), basvuru)
    baslik = "Sınav sonucu açıklandı"
    kisa = f"{_ilk_ad(basvuru)} için {basvuru.sinav_adi} sonucu hazır. Görmek için dokunun."
    try:
        with transaction.atomic():
            log = SinavBildirimLog.objects.create(basvuru=basvuru, an_kodu=an_kodu, baslik=baslik, mesaj=kisa)
    except IntegrityError:
        return None
    # Sonuç sayfası gönderimden itibaren açılır.
    sonuc.gonderim_zamani = timezone.now()
    sonuc.gonderilen_surum = sonuc.karne_surum
    sonuc.save(update_fields=["gonderim_zamani", "gonderilen_surum", "guncellenme"])
    log.gonderilen, log.push_hata = _push_gonder(
        basvuru, baslik=baslik, mesaj=kisa, url=sonuc_sayfasi_url(basvuru)
    )
    log.eposta_gonderildi = _sonuc_epostasi(sonuc, govde)
    log.save(update_fields=["gonderilen", "push_hata", "eposta_gonderildi"])
    return log


def sonuclari_gonder(sonuc_idleri: list[int]) -> int:
    adet = 0
    sablonlar: dict[str, str] = {}
    for sonuc in SinavSonuc.objects.filter(pk__in=sonuc_idleri).select_related("basvuru"):
        sinav = sonuc.basvuru.sinav_adi
        if sinav not in sablonlar:
            sablonlar[sinav] = sonuc_mesaji_sablonu(sinav)
        if sonuc_gonder(sonuc, sablonlar[sinav]):
            adet += 1
    return adet


def sonuclari_arka_planda_gonder(sonuc_idleri: list[int]) -> None:
    """Çok sayıda e-posta isteği uzatmasın diye gönderim arka planda yapılır."""
    if not getattr(settings, "SINAV_SONUC_ARKA_PLAN", True):
        sonuclari_gonder(sonuc_idleri)
        return

    def calis():
        close_old_connections()
        try:
            sonuclari_gonder(sonuc_idleri)
        except Exception:  # noqa: BLE001
            logger.exception("sonuç gönderimi hata verdi")
        finally:
            close_old_connections()

    threading.Thread(target=calis, name="sinav-sonuc-gonderim", daemon=True).start()
