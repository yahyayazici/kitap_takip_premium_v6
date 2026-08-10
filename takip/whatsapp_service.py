"""WhatsApp Cloud API (Meta Business) gönderim yardımcıları."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppSonuc:
    ok: bool
    yanit: str = ""
    message_id: str = ""


def whatsapp_yapilandirilmis() -> bool:
    return bool(getattr(settings, "WHATSAPP_AKTIF", False))


def telefon_normalize(telefon: str) -> str:
    """TR numarayı E.164 benzeri 90… formatına çevirir."""
    digits = "".join(ch for ch in (telefon or "") if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("90") and len(digits) >= 12:
        return digits
    if digits.startswith("0") and len(digits) >= 11:
        return "90" + digits[1:]
    if len(digits) == 10 and digits.startswith("5"):
        return "90" + digits
    return digits


def _api_url() -> str:
    version = getattr(settings, "WHATSAPP_API_VERSION", "v21.0") or "v21.0"
    phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    return f"https://graph.facebook.com/{version}/{phone_id}/messages"


def _post(payload: dict) -> WhatsAppSonuc:
    if not whatsapp_yapilandirilmis():
        return WhatsAppSonuc(
            ok=False,
            yanit="WhatsApp yapılandırılmamış (WHATSAPP_AKTIF / token / phone id).",
        )

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _api_url(),
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body else {}
            msg_id = ""
            messages = parsed.get("messages") or []
            if messages:
                msg_id = str(messages[0].get("id") or "")
            return WhatsAppSonuc(ok=True, yanit=body[:2000], message_id=msg_id)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.warning("WhatsApp HTTP %s: %s", exc.code, err_body[:500])
        return WhatsAppSonuc(ok=False, yanit=f"HTTP {exc.code}: {err_body[:1500]}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("WhatsApp gönderim hatası")
        return WhatsAppSonuc(ok=False, yanit=str(exc)[:1500])


def mesaj_gonder_metin(telefon: str, metin: str) -> WhatsAppSonuc:
    to = telefon_normalize(telefon)
    if not to:
        return WhatsAppSonuc(ok=False, yanit="Geçersiz telefon.")
    if not (metin or "").strip():
        return WhatsAppSonuc(ok=False, yanit="Boş mesaj.")

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": metin.strip()[:4096]},
    }
    return _post(payload)


def mesaj_gonder_template(
    telefon: str,
    *,
    template_name: str,
    language: str = "tr",
    body_params: list[str] | None = None,
) -> WhatsAppSonuc:
    to = telefon_normalize(telefon)
    if not to:
        return WhatsAppSonuc(ok=False, yanit="Geçersiz telefon.")
    if not template_name:
        return WhatsAppSonuc(ok=False, yanit="Template adı boş.")

    components = []
    if body_params:
        components.append(
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(p)[:1024]} for p in body_params
                ],
            }
        )

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language or "tr"},
            "components": components,
        },
    }
    return _post(payload)
