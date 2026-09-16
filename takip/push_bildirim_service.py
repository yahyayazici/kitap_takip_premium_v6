"""Web Push gönderimi — sadece yönetimin elle tetiklediği bildirimler için.

Tüm mevcut Bildirim akışlarına (vazife/duyuru/program/sistem) OTOMATİK
bağlanmaz; yönetim panelindeki "Bildirim Gönder" ekranından çağrılır.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib.auth.models import User

from .models import EtutHocasi, PersonelProfili, Talebe
from .push_bildirim_models import PushAbonelik
from .talebe_panel_models import TalebeHesap
from .wave0_models import VeliHesap

logger = logging.getLogger("takip.push_bildirim")


def push_bildirim_aktif() -> bool:
    return bool(
        getattr(settings, "VAPID_PUBLIC_KEY", "")
        and getattr(settings, "VAPID_PRIVATE_KEY", "")
    )


def _kisi(user: User, etiket: str, rol: str) -> dict:
    return {"user_id": user.pk, "etiket": f"{etiket} ({rol})", "ad": etiket, "rol": rol}


def tum_gonderilebilir_kisiler() -> list[dict]:
    """Push/bildirim gönderilebilecek tüm kişiler — ad + rol etiketiyle, ad'a göre sıralı."""
    kisiler: dict[int, dict] = {}

    for profil in PersonelProfili.objects.filter(aktif=True).select_related("user"):
        if profil.user and profil.user.is_active and profil.user_id not in kisiler:
            kisiler[profil.user_id] = _kisi(profil.user, profil.ad_soyad, "Personel")

    for hoca in EtutHocasi.objects.filter(aktif=True).select_related("user"):
        if hoca.user and hoca.user.is_active and hoca.user_id not in kisiler:
            kisiler[hoca.user_id] = _kisi(hoca.user, hoca.ad_soyad, "Öğretmen")

    for veli in VeliHesap.objects.filter(aktif=True).select_related("user"):
        if veli.user and veli.user.is_active and veli.user_id not in kisiler:
            kisiler[veli.user_id] = _kisi(veli.user, veli.ad_soyad, "Veli")

    for hesap in (
        TalebeHesap.objects.filter(talebe__durum=Talebe.Durum.AKTIF)
        .select_related("user", "talebe")
    ):
        if hesap.user and hesap.user.is_active and hesap.user_id not in kisiler:
            kisiler[hesap.user_id] = _kisi(hesap.user, hesap.talebe.ad_soyad, "Talebe")

    return sorted(kisiler.values(), key=lambda k: k["ad"])


def abonelik_kaydet(user: User, data: dict, user_agent: str = "") -> PushAbonelik | None:
    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return None
    abonelik, _ = PushAbonelik.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": user_agent[:255],
        },
    )
    return abonelik


def abonelik_sil(user: User, endpoint: str) -> None:
    if endpoint:
        PushAbonelik.objects.filter(user=user, endpoint=endpoint).delete()


def _vapid_claims() -> dict:
    email = getattr(settings, "VAPID_CLAIM_EMAIL", "") or "mailto:destek@cinilisarayproje.com"
    return {"sub": email if email.startswith("mailto:") else f"mailto:{email}"}


def push_gonder(user: User, *, baslik: str, mesaj: str, url: str = "/panel/") -> int:
    """user'ın tüm aktif aboneliklerine push gönderir; geçersiz abonelikleri temizler.
    Gönderilen (başarılı) abonelik sayısını döner."""
    if not push_bildirim_aktif():
        return 0

    from pywebpush import WebPushException, webpush

    payload = json.dumps({"title": baslik, "body": mesaj, "url": url})
    gonderilen = 0
    for abonelik in PushAbonelik.objects.filter(user=user):
        try:
            webpush(
                subscription_info={
                    "endpoint": abonelik.endpoint,
                    "keys": {"p256dh": abonelik.p256dh, "auth": abonelik.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims=dict(_vapid_claims()),
            )
            gonderilen += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                abonelik.delete()
            else:
                logger.warning("push gönderilemedi (user=%s): %s", user.pk, exc)
        except Exception:
            logger.exception("push gönderilirken beklenmeyen hata (user=%s)", user.pk)
    return gonderilen


def push_gonder_coklu(users, *, baslik: str, mesaj: str, url: str = "/panel/") -> int:
    toplam = 0
    seen: set[int] = set()
    for user in users:
        if not user or not getattr(user, "pk", None) or user.pk in seen:
            continue
        seen.add(user.pk)
        toplam += push_gonder(user, baslik=baslik, mesaj=mesaj, url=url)
    return toplam
