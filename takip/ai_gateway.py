"""Merkezi yapay zeka gateway — OpenAI, önbellek, JSON."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from takip.ai_models import AiUretimKaydi
from takip.asistan_llm import _openai_chat, openai_yapilandirildi_mi


def ai_platform_aktif_mi() -> bool:
    if not getattr(settings, "AI_ASSISTANT_ENABLED", True):
        return False
    if getattr(settings, "AI_PLATFORM_ENABLED", True) is False:
        return False
    return True


def ai_llm_aktif_mi() -> bool:
    return ai_platform_aktif_mi() and openai_yapilandirildi_mi()


def _json_cek(metin: str) -> dict[str, Any] | None:
    if not metin:
        return None
    metin = metin.strip()
    if metin.startswith("```"):
        metin = re.sub(r"^```(?:json)?\s*", "", metin)
        metin = re.sub(r"\s*```$", "", metin)
    try:
        return json.loads(metin)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", metin)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def ai_json_uret(
    *,
    system: str,
    user_prompt: str,
    temperature: float = 0.55,
    max_tokens: int | None = None,
) -> dict[str, Any] | None:
    if not ai_llm_aktif_mi():
        return None
    tokens = max_tokens or int(getattr(settings, "AI_PLATFORM_MAX_TOKENS", 1800))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    reply = _openai_chat(messages, temperature=temperature, max_tokens=tokens)
    if not reply:
        return None
    parsed = _json_cek(reply)
    return parsed if isinstance(parsed, dict) else None


def ai_metin_uret(
    *,
    system: str,
    user_prompt: str,
    temperature: float = 0.65,
    max_tokens: int | None = None,
) -> str | None:
    if not ai_llm_aktif_mi():
        return None
    tokens = max_tokens or int(getattr(settings, "AI_PLATFORM_MAX_TOKENS", 1200))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    return _openai_chat(messages, temperature=temperature, max_tokens=tokens)


def _cache_saat() -> int:
    return int(getattr(settings, "AI_CACHE_HOURS", 24))


def onbellekten_al(tur: str, anahtar: str, *, yenile: bool = False) -> dict[str, Any] | None:
    if yenile:
        return None
    kayit = AiUretimKaydi.objects.filter(tur=tur, anahtar=anahtar).first()
    if not kayit:
        return None
    sinir = timezone.now() - timedelta(hours=_cache_saat())
    if kayit.guncellenme < sinir:
        return None
    return kayit.icerik if isinstance(kayit.icerik, dict) else None


def onbellege_yaz(
    *,
    tur: str,
    anahtar: str,
    icerik: dict[str, Any],
    yapay_zeka: bool,
    user: User | None = None,
) -> None:
    AiUretimKaydi.objects.update_or_create(
        tur=tur,
        anahtar=anahtar,
        defaults={
            "icerik": icerik,
            "yapay_zeka": yapay_zeka,
            "olusturan": user,
        },
    )
