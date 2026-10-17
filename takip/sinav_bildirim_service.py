"""Sınav başvurusu — uygulama (web push) bildirimleri ve zamanlanmış hatırlatmalar.

Bildirim anları:
- kayit: veli bildirimlere izin verdiği anda (bir kez)
- uc_gun: sınavdan 3 gün önce 19.00
- bir_gun: sınavdan 1 gün önce 19.00
- sabah: sınav başlangıcından 2,5 saat önce
- bitis: sınav bitişinden 15 dakika sonra

Uygulama bildirimi tüm anlarda gider; e-posta kayıt (takvim dosyası ekli), 1 gün kala
ve sınav bitince anlarında gider.

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
from django.core.mail import EmailMessage, get_connection
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from takip.bildirim_service import email_kanali_aktif
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

EPOSTA_ANLARI = frozenset({AN_KAYIT, AN_BIR_GUN, AN_BITIS})

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


def _tarih_yilli(an: dt.datetime) -> str:
    yerel = _yerel(an)
    return f"{yerel.day} {AYLAR[yerel.month - 1]} {yerel.year} {GUNLER[yerel.weekday()]}"


def guncel_takvim() -> SinavTakvim | None:
    from config.branding import SINAV_BASVURU_BASLIK

    return SinavTakvim.objects.filter(sinav_adi=SINAV_BASVURU_BASLIK).first()


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


# —— Takvim dosyası (.ics) ——

def _ics_metin(metin: str) -> str:
    return (
        (metin or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _ics_zaman(an: dt.datetime) -> str:
    return an.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ics_sure(fark: dt.timedelta) -> str:
    toplam_dk = int(fark.total_seconds() // 60)
    gun, kalan = divmod(toplam_dk, 24 * 60)
    saat, dakika = divmod(kalan, 60)
    sure = "-P"
    if gun:
        sure += f"{gun}D"
    if saat or dakika or not gun:
        sure += "T"
        if saat:
            sure += f"{saat}H"
        if dakika or not saat:
            sure += f"{dakika}M"
    return sure


def takvim_ics(takvim: SinavTakvim) -> str:
    alarm_metinleri = {
        AN_UC_GUN: "Sınava 3 gün kaldı",
        AN_BIR_GUN: "Sınav yarın",
        AN_SABAH: "Bugün sınav günü",
    }
    satirlar = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Cinili Saray//Sinav//TR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:sinav-{takvim.pk}@cinilisarayproje.com",
        f"DTSTAMP:{_ics_zaman(timezone.now())}",
        f"DTSTART:{_ics_zaman(takvim.baslangic)}",
        f"DTEND:{_ics_zaman(takvim.bitis)}",
        f"SUMMARY:{_ics_metin(takvim.sinav_adi)}",
        f"LOCATION:{_ics_metin(takvim.yer or 'Çinili Saray')}",
        f"DESCRIPTION:{_ics_metin('Kurşun kalem, silgi ve kalemtıraş getiriniz.')}",
    ]
    for an_kodu, plan in zamanlanmis_anlar(takvim):
        if an_kodu not in alarm_metinleri:
            continue
        satirlar += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_metin(alarm_metinleri[an_kodu])}",
            f"TRIGGER:{_ics_sure(takvim.baslangic - plan)}",
            "END:VALARM",
        ]
    satirlar += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(satirlar) + "\r\n"


# —— E-posta ——

def eposta_metni(an_kodu: str, basvuru: SinavBasvuru, takvim: SinavTakvim | None) -> tuple[str, str]:
    if takvim:
        bilgi = (
            f"Tarih: {_tarih_yilli(takvim.baslangic)}\n"
            f"Saat: {_saat_metni(takvim.baslangic)}\n"
            f"Yer: {takvim.yer or 'Çinili Saray'}\n"
        )
    else:
        bilgi = ""
    imza = "\nÇinili Saray\n"
    if an_kodu == AN_KAYIT:
        govde = (
            "Sayın Veli,\n\n"
            f"{basvuru.ad_soyad} için {basvuru.sinav_adi} başvurunuz alınmıştır.\n\n"
            f"{bilgi}\n"
            "Denemeye katılan her öğrenciye, her dersten 2 örnek yazılı hediye edilir.\n\n"
            "Sınavı telefonunuzun takvimine eklemek için ekteki \"sinav.ics\" dosyasına "
            "dokunabilirsiniz; takviminiz sınavdan önce size hatırlatma yapar.\n"
        )
        return f"Başvurunuz alındı · {basvuru.sinav_adi}", govde + imza
    if an_kodu == AN_BIR_GUN:
        govde = (
            "Sayın Veli,\n\n"
            f"{basvuru.ad_soyad} için {basvuru.sinav_adi} yarın yapılacaktır.\n\n"
            f"{bilgi}\n"
            "Lütfen kurşun kalem, silgi ve kalemtıraş getirmeyi unutmayınız.\n"
        )
        return f"Sınav yarın · {basvuru.sinav_adi}", govde + imza
    if an_kodu == AN_BITIS:
        govde = (
            "Sayın Veli,\n\n"
            f"{basvuru.ad_soyad} {basvuru.sinav_adi} sınavını tamamlamıştır. "
            "Katılımınız için teşekkür ederiz.\n\n"
            "Sınav neticeleri en geç 3 gün içerisinde açıklanacak ve tarafınıza bildirilecektir.\n"
        )
        return f"Sınav tamamlandı · {basvuru.sinav_adi}", govde + imza
    return "", ""


def sinav_eposta_aktif() -> bool:
    """Gerçekten e-posta gönderebilen bir yapılandırma var mı?

    Konsol/dosya backend'i e-postayı yalnızca sunucu kaydına yazar; veliye ulaşmaz,
    bu yüzden "gönderildi" sayılmaz. (locmem yalnızca testlerde kullanılır.)
    """
    if not email_kanali_aktif():
        return False
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    if "locmem" in backend:
        return True
    if "smtp" in backend:
        return bool((getattr(settings, "EMAIL_HOST", "") or "").strip())
    return False


def _eposta_gonder(an_kodu: str, basvuru: SinavBasvuru, takvim: SinavTakvim | None) -> bool:
    if an_kodu not in EPOSTA_ANLARI or not basvuru.veli_eposta or not sinav_eposta_aktif():
        return False
    konu, govde = eposta_metni(an_kodu, basvuru, takvim)
    if not konu:
        return False
    try:
        mesaj = EmailMessage(
            subject=konu,
            body=govde,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[basvuru.veli_eposta],
            connection=get_connection(timeout=15),
        )
        if an_kodu == AN_KAYIT and takvim:
            mesaj.attach("sinav.ics", takvim_ics(takvim), "text/calendar")
        mesaj.send(fail_silently=False)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("sınav e-postası gönderilemedi (basvuru=%s, an=%s)", basvuru.pk, an_kodu)
        return False


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


def abonelige_push(abonelik: SinavBasvuruPushAbonelik, *, baslik: str, mesaj: str) -> str:
    """Tek aboneliğe push gönderir. Başarılıysa "", değilse okunabilir hata metni döner."""
    if not push_bildirim_aktif():
        return "VAPID anahtarları tanımlı değil."

    from pywebpush import WebPushException, webpush

    payload = json.dumps(
        {"title": baslik, "body": mesaj, "url": basvuru_bildirim_url(abonelik.basvuru)}
    )
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
        return ""
    except WebPushException as exc:
        yanit = getattr(exc, "response", None)
        status = getattr(yanit, "status_code", None)
        govde = ""
        try:
            govde = (yanit.text or "")[:300] if yanit is not None else ""
        except Exception:  # noqa: BLE001
            govde = ""
        hata = f"Push servisi reddetti (HTTP {status}): {govde or exc}"[:500]
        if status in (404, 410):
            abonelik.delete()
            hata = f"Abonelik artık geçerli değil (HTTP {status}); silindi."
        logger.warning("sınav bildirimi gönderilemedi (abonelik=%s): %s", abonelik.pk, hata)
        return hata
    except Exception as exc:  # noqa: BLE001
        logger.exception("sınav bildirimi gönderilirken hata (abonelik=%s)", abonelik.pk)
        return f"{type(exc).__name__}: {exc}"[:500]


def _push_gonder(basvuru: SinavBasvuru, *, baslik: str, mesaj: str) -> tuple[int, str]:
    if not push_bildirim_aktif():
        return 0, ""
    ulasan = 0
    hatalar: list[str] = []
    for abonelik in list(SinavBasvuruPushAbonelik.objects.filter(basvuru=basvuru)):
        hata = abonelige_push(abonelik, baslik=baslik, mesaj=mesaj)
        if hata:
            hatalar.append(hata)
        else:
            ulasan += 1
    return ulasan, " | ".join(hatalar)[:1000]


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
    log.gonderilen, log.push_hata = _push_gonder(basvuru, baslik=baslik, mesaj=mesaj)
    log.eposta_gonderildi = _eposta_gonder(an_kodu, basvuru, takvim)
    log.save(update_fields=["gonderilen", "push_hata", "eposta_gonderildi"])
    return log


def zamani_gelenleri_gonder(simdi: dt.datetime | None = None) -> int:
    """Zamanı gelmiş hatırlatmaları gönderir; yeni gönderim kaydı sayısını döner."""
    push_acik = push_bildirim_aktif()
    eposta_acik = sinav_eposta_aktif()
    if not push_acik and not eposta_acik:
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
            kosullar = []
            if push_acik:
                kosullar.append(Q(push_abonelikleri__isnull=False))
            if eposta_acik and an_kodu in EPOSTA_ANLARI:
                kosullar.append(~Q(veli_eposta=""))
            if not kosullar:
                continue
            ulasilabilir = kosullar[0]
            for kosul in kosullar[1:]:
                ulasilabilir |= kosul
            basvurular = (
                SinavBasvuru.objects.filter(
                    ulasilabilir,
                    sinav_adi=takvim.sinav_adi,
                    olusturulma__lt=plan,
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
