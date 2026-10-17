"""Sınav başvurusu — uygulama (web push) bildirimleri ve zamanlanmış hatırlatmalar.

Bildirim anları:
- kayit: veli bildirimlere izin verdiği anda (bir kez)
- uc_gun: sınavdan 3 gün önce 19.00
- bir_gun: sınavdan 1 gün önce 19.00
- sabah: sınav başlangıcından 2,5 saat önce
- bitis: sınav bitişinden 15 dakika sonra

Aynı başvuruya aynı an için yalnızca bir kez gönderilir (SinavBildirimLog tekil kısıtı).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import random
import sys
import threading
import time

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, close_old_connections, transaction
from django.urls import reverse
from django.utils import timezone

from takip.push_bildirim_service import _vapid_claims, push_bildirim_aktif
from takip.sinav_basvuru_models import SinavBasvuru
from takip.sinav_bildirim_models import (
    SinavBasvuruPushAbonelik,
    SinavBildirimLog,
    SinavTakvim,
)

logger = logging.getLogger("takip.sinav_bildirim")

TOKEN_SALT = "sinav-basvuru-bildirim"

AN_KAYIT = "kayit"
AN_UC_GUN = "uc_gun"
AN_BIR_GUN = "bir_gun"
AN_SABAH = "sabah"
AN_BITIS = "bitis"

AN_ETIKETLERI = {
    AN_KAYIT: "Kayıt alındı",
    AN_UC_GUN: "3 gün kala",
    AN_BIR_GUN: "1 gün kala",
    AN_SABAH: "Sınav sabahı",
    AN_BITIS: "Sınav bitince",
}

# Zamanı gelen bir hatırlatma en fazla bu kadar gecikmeyle gönderilir;
# site uzun süre kapalı kalırsa eski hatırlatmalar sonradan topluca gitmez.
GONDERIM_PENCERESI = dt.timedelta(hours=6)

AYLAR = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)
GUNLER = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


# —— Başvuru bağlantı anahtarı ——

def basvuru_token(basvuru: SinavBasvuru) -> str:
    return signing.dumps({"b": basvuru.pk}, salt=TOKEN_SALT)


def tokendan_basvuru(token: str) -> SinavBasvuru | None:
    try:
        veri = signing.loads(token or "", salt=TOKEN_SALT)
    except signing.BadSignature:
        return None
    pk = veri.get("b") if isinstance(veri, dict) else None
    if not isinstance(pk, int):
        return None
    return SinavBasvuru.objects.filter(pk=pk).first()


def basvuru_bildirim_url(basvuru: SinavBasvuru) -> str:
    return f"{reverse('sinav_basvuru_tesekkur')}?t={basvuru_token(basvuru)}"


# —— Takvim ve metinler ——

def takvim_bul(basvuru: SinavBasvuru) -> SinavTakvim | None:
    return SinavTakvim.objects.filter(sinav_adi=basvuru.sinav_adi).first()


def _yerel(an: dt.datetime) -> dt.datetime:
    return timezone.localtime(an)


def _tarih_metni(an: dt.datetime) -> str:
    yerel = _yerel(an)
    return f"{yerel.day} {AYLAR[yerel.month - 1]} {GUNLER[yerel.weekday()]}"


def _saat_metni(an: dt.datetime) -> str:
    return _yerel(an).strftime("%H.%M")


def zamanlanmis_anlar(takvim: SinavTakvim) -> list[tuple[str, dt.datetime]]:
    baslangic = _yerel(takvim.baslangic)
    tz = baslangic.tzinfo
    gun = baslangic.date()

    def aksam(gun_once: int) -> dt.datetime:
        return dt.datetime.combine(gun - dt.timedelta(days=gun_once), dt.time(19, 0), tzinfo=tz)

    return [
        (AN_UC_GUN, aksam(3)),
        (AN_BIR_GUN, aksam(1)),
        (AN_SABAH, baslangic - dt.timedelta(minutes=150)),
        (AN_BITIS, _yerel(takvim.bitis) + dt.timedelta(minutes=15)),
    ]


def _ilk_ad(basvuru: SinavBasvuru) -> str:
    parcalar = (basvuru.ad_soyad or "").split()
    return parcalar[0] if parcalar else "Öğrencimiz"


def bildirim_metni(an_kodu: str, basvuru: SinavBasvuru, takvim: SinavTakvim | None) -> tuple[str, str]:
    ad = _ilk_ad(basvuru)
    if takvim:
        tarih = _tarih_metni(takvim.baslangic)
        saat = _saat_metni(takvim.baslangic)
        yer = takvim.yer or "Çinili Saray"
    else:
        tarih, saat, yer = "", "", "Çinili Saray"

    if an_kodu == AN_KAYIT:
        detay = f" Sınav: {tarih}, saat {saat}." if takvim else ""
        return "Başvurunuz alındı", f"{ad} için {basvuru.sinav_adi} başvurusu alındı.{detay}"
    if an_kodu == AN_UC_GUN:
        return "Sınava 3 gün kaldı", f"{ad} için geri sayım başladı: {tarih}, saat {saat}. {yer}."
    if an_kodu == AN_BIR_GUN:
        return "Sınav yarın", f"Yarın saat {saat}, {yer}. Kurşun kalem ve silgiyi unutmayın."
    if an_kodu == AN_SABAH:
        return "Bugün sınav günü", f"Sınav saat {saat}. Başarılar {ad}!"
    if an_kodu == AN_BITIS:
        return (
            "Sınav tamamlandı",
            "Katılımınız için teşekkür ederiz. Sonuçlar en geç 3 gün içinde velilere bildirilecek.",
        )
    return "Çinili Saray", ""


# —— Abonelik ve gönderim ——

def abonelik_kaydet(basvuru: SinavBasvuru, data: dict, user_agent: str = "") -> SinavBasvuruPushAbonelik | None:
    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint.startswith("https://") or not p256dh or not auth:
        return None
    abonelik, _ = SinavBasvuruPushAbonelik.objects.update_or_create(
        basvuru=basvuru,
        endpoint=endpoint,
        defaults={"p256dh": p256dh, "auth": auth, "user_agent": user_agent[:255]},
    )
    return abonelik


def _push_gonder(basvuru: SinavBasvuru, *, baslik: str, mesaj: str) -> int:
    if not push_bildirim_aktif():
        return 0

    from pywebpush import WebPushException, webpush

    payload = json.dumps({"title": baslik, "body": mesaj, "url": basvuru_bildirim_url(basvuru)})
    ulasan = 0
    for abonelik in SinavBasvuruPushAbonelik.objects.filter(basvuru=basvuru):
        try:
            webpush(
                subscription_info={
                    "endpoint": abonelik.endpoint,
                    "keys": {"p256dh": abonelik.p256dh, "auth": abonelik.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims=dict(_vapid_claims()),
                ttl=6 * 60 * 60,
            )
            ulasan += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                abonelik.delete()
            else:
                logger.warning("sınav bildirimi gönderilemedi (basvuru=%s): %s", basvuru.pk, exc)
        except Exception:  # noqa: BLE001
            logger.exception("sınav bildirimi gönderilirken hata (basvuru=%s)", basvuru.pk)
    return ulasan


def bildirim_gonder(basvuru: SinavBasvuru, an_kodu: str, takvim: SinavTakvim | None = None) -> SinavBildirimLog | None:
    """Bu başvuruya bu an için daha önce gönderilmediyse gönderir; gönderildiyse None."""
    if takvim is None:
        takvim = takvim_bul(basvuru)
    baslik, mesaj = bildirim_metni(an_kodu, basvuru, takvim)
    try:
        with transaction.atomic():
            log = SinavBildirimLog.objects.create(
                basvuru=basvuru, an_kodu=an_kodu, baslik=baslik, mesaj=mesaj
            )
    except IntegrityError:
        return None
    log.gonderilen = _push_gonder(basvuru, baslik=baslik, mesaj=mesaj)
    log.save(update_fields=["gonderilen"])
    return log


def zamani_gelenleri_gonder(simdi: dt.datetime | None = None) -> int:
    """Zamanı gelmiş hatırlatmaları gönderir; yeni gönderim kaydı sayısını döner."""
    if not push_bildirim_aktif():
        return 0
    simdi = simdi or timezone.now()
    toplam = 0
    takvimler = SinavTakvim.objects.filter(
        bildirim_aktif=True,
        bitis__gte=simdi - dt.timedelta(days=1),
    )
    for takvim in takvimler:
        for an_kodu, plan in zamanlanmis_anlar(takvim):
            if not (plan <= simdi < plan + GONDERIM_PENCERESI):
                continue
            basvurular = (
                SinavBasvuru.objects.filter(
                    sinav_adi=takvim.sinav_adi,
                    olusturulma__lt=plan,
                    push_abonelikleri__isnull=False,
                )
                .exclude(bildirim_loglari__an_kodu=an_kodu)
                .distinct()
            )
            for basvuru in basvurular:
                if bildirim_gonder(basvuru, an_kodu, takvim):
                    toplam += 1
    return toplam


# —— Site içi zamanlayıcı ——

_zamanlayici_basladi = False
_kilit = threading.Lock()
ZAMANLAYICI_ARALIK_SN = 300


def _zamanlayici_dongusu() -> None:
    time.sleep(60 + random.randint(0, 60))
    while True:
        close_old_connections()
        try:
            adet = zamani_gelenleri_gonder()
            if adet:
                logger.info("sınav hatırlatması gönderildi: %s", adet)
        except Exception:  # noqa: BLE001
            logger.exception("sınav hatırlatma zamanlayıcısı hata verdi")
        finally:
            close_old_connections()
        time.sleep(ZAMANLAYICI_ARALIK_SN)


def zamanlayiciyi_baslat() -> bool:
    """Gunicorn işçisinde arka plan zamanlayıcısını bir kez başlatır.

    SINAV_BILDIRIM_ZAMANLAYICI=0 ile kapatılabilir. Birden fazla işçi aynı anda
    çalışsa bile tekil kayıt kısıtı aynı bildirimin iki kez gitmesini engeller.
    """
    global _zamanlayici_basladi
    if os.environ.get("SINAV_BILDIRIM_ZAMANLAYICI", "1").strip() == "0":
        return False
    if "gunicorn" not in os.path.basename(sys.argv[0] if sys.argv else ""):
        return False
    with _kilit:
        if _zamanlayici_basladi:
            return False
        _zamanlayici_basladi = True
    threading.Thread(
        target=_zamanlayici_dongusu, name="sinav-bildirim-zamanlayici", daemon=True
    ).start()
    return True
