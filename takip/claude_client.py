"""Claude API istemcisi — tüm yapay zeka çağrılarının tek çıkış noktası.

- API anahtarı yalnızca sunucuda, ``ANTHROPIC_API_KEY`` ortam değişkeninden okunur.
- Loglara anahtar, istem metni veya öğrenci verisi yazılmaz; yalnızca model, süre,
  token sayısı, hata sınıfı ve request-id yazılır.
- Hatalar istisna fırlatmak yerine ``ClaudeSonuc.hata`` / ``ClaudeSonuc.mesaj`` ile
  döner; arayüz bu mesajı kullanıcıya gösterir.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Sunucu tarafı ret yedeği: güvenlik sınıflandırıcısı yanlışlıkla bir isteği
# reddederse API aynı isteği önerilen yedek modelde yeniden çalıştırır.
_RET_YEDEK_BETA = "server-side-fallback-2026-07-01"

HATA_MESAJLARI = {
    "yapilandirilmamis": "Yapay zeka servisi yapılandırılmamış (sunucuda ANTHROPIC_API_KEY tanımlı değil).",
    "zaman_asimi": "Yapay zeka servisi zamanında yanıt vermedi (zaman aşımı). Lütfen biraz sonra tekrar deneyin.",
    "baglanti": "Yapay zeka servisine bağlanılamadı. İnternet bağlantısı veya servis erişimi kontrol edilmeli.",
    "kota": "Yapay zeka servisinde istek sınırına ulaşıldı. Birkaç dakika sonra tekrar deneyin.",
    "yetki": "Yapay zeka servisi API anahtarını kabul etmedi. Sistem yöneticisine bildirin.",
    "model": "Yapılandırılan yapay zeka modeli bulunamadı. Sistem yöneticisine bildirin.",
    "istek": "Yapay zeka isteği geçersiz bulundu. Sistem yöneticisine bildirin.",
    "sunucu": "Yapay zeka servisi şu an yoğun veya geçici olarak kullanılamıyor. Biraz sonra tekrar deneyin.",
    "ret": "Yapay zeka bu isteği güvenlik politikası gereği yanıtlamadı.",
    "kesildi": "Yapay zeka yanıtı çıktı sınırına ulaştığı için tamamlanamadı.",
    "bos": "Yapay zeka boş yanıt döndürdü.",
    "girdi_buyuk": "Gönderilecek veri çok büyük. Filtreyi daraltıp tekrar deneyin.",
    "beklenmeyen": "Yapay zeka yanıtı işlenirken beklenmeyen bir hata oluştu.",
}


@dataclass
class ClaudeSonuc:
    metin: str = ""
    hata: str = ""
    stop_reason: str = ""
    content: list[Any] = field(default_factory=list)
    model: str = ""
    girdi_token: int = 0
    cikti_token: int = 0
    sure_ms: int = 0

    @property
    def ok(self) -> bool:
        return not self.hata

    @property
    def mesaj(self) -> str:
        return HATA_MESAJLARI.get(self.hata, "") if self.hata else ""

    def tool_uses(self) -> list[Any]:
        return [b for b in self.content if getattr(b, "type", "") == "tool_use"]


def claude_yapilandirildi_mi() -> bool:
    return bool((getattr(settings, "ANTHROPIC_API_KEY", "") or "").strip())


# gorev: "analiz" (raporlar), "sohbet" (panel asistanı), "uretim" (soru seti, mesaj taslağı gibi
# art arda çok sayıda çağrı yapılan serbest üretim işleri — hız için düşük düşünme derinliği)
_GOREV_AYARLARI = {
    "analiz": ("AI_ANALIZ_MODEL", "AI_ANALIZ_EFFORT", "medium", "AI_ANALIZ_TIMEOUT"),
    "sohbet": ("AI_SOHBET_MODEL", "AI_SOHBET_EFFORT", "low", "AI_SOHBET_TIMEOUT"),
    "uretim": ("AI_URETIM_MODEL", "AI_URETIM_EFFORT", "low", "AI_ANALIZ_TIMEOUT"),
}


def gorev_modeli(gorev: str) -> str:
    model_ayari = _GOREV_AYARLARI.get(gorev, _GOREV_AYARLARI["analiz"])[0]
    return getattr(settings, model_ayari, "claude-opus-5-5")


def _gorev_effort(gorev: str) -> str:
    _, effort_ayari, varsayilan, _ = _GOREV_AYARLARI.get(gorev, _GOREV_AYARLARI["analiz"])
    return getattr(settings, effort_ayari, varsayilan)


_client = None


def _istemci():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY.strip(),
            max_retries=0,
        )
    return _client


def _hata_kodu(exc: Exception) -> str:
    import anthropic

    if isinstance(exc, anthropic.APITimeoutError):
        return "zaman_asimi"
    if isinstance(exc, anthropic.APIConnectionError):
        return "baglanti"
    if isinstance(exc, anthropic.RateLimitError):
        return "kota"
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return "yetki"
    if isinstance(exc, anthropic.NotFoundError):
        return "model"
    if isinstance(exc, anthropic.BadRequestError):
        return "istek"
    if isinstance(exc, anthropic.APIStatusError):
        return "sunucu" if exc.status_code >= 500 else "istek"
    return "beklenmeyen"


def claude_istek(
    *,
    gorev: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    json_schema: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    timeout: float | None = None,
    max_retries: int = 1,
) -> ClaudeSonuc:
    """Tek bir Messages API çağrısı.

    gorev: "analiz" (raporlar), "sohbet" (panel asistanı) veya "uretim" (serbest JSON/metin üretimi).
    max_tokens: düşünme + yanıt için toplam çıktı sınırı (maliyet tavanı).
    """
    if not claude_yapilandirildi_mi():
        return ClaudeSonuc(hata="yapilandirilmamis")

    model = gorev_modeli(gorev)
    girdi_sinir = int(getattr(settings, "AI_MAX_GIRDI_KARAKTER", 120_000))
    girdi_boyu = len(system) + sum(
        len(m["content"]) if isinstance(m.get("content"), str) else 2_000 for m in messages
    )
    if girdi_boyu > girdi_sinir:
        logger.warning("Claude isteği girdi sınırını aştı gorev=%s karakter=%s", gorev, girdi_boyu)
        return ClaudeSonuc(hata="girdi_buyuk", model=model)

    output_config: dict[str, Any] = {}
    if not model.startswith("claude-haiku"):
        output_config["effort"] = _gorev_effort(gorev)
    if json_schema:
        output_config["format"] = {"type": "json_schema", "schema": json_schema}

    params: dict[str, Any] = {
        "model": model,
        "max_tokens": int(max_tokens),
        "system": system,
        "messages": messages,
        # Uzun sistem istemi + sohbet geçmişi tekrar okunduğunda önbellekten ucuza gelir.
        "cache_control": {"type": "ephemeral"},
    }
    if output_config:
        params["output_config"] = output_config
    if tools:
        params["tools"] = tools

    if timeout is None:
        timeout_ayari = _GOREV_AYARLARI.get(gorev, _GOREV_AYARLARI["analiz"])[3]
        timeout = float(getattr(settings, timeout_ayari, 60))

    baslangic = time.monotonic()
    # SDK'nın kendi yeniden denemesi kapalı (zaman aşımını da tekrarlar ve gunicorn süresini
    # aşabilir). Bunun yerine yalnızca hızlı düşen aşırı yük / bağlantı hatalarında, kısa bir
    # beklemeyle en fazla max_retries kez yeniden denenir.
    deneme = 0
    while True:
        try:
            client = _istemci().with_options(timeout=timeout, max_retries=0)
            if getattr(settings, "AI_RET_YEDEK", True):
                yanit = client.beta.messages.create(
                    betas=[_RET_YEDEK_BETA],
                    fallbacks="default",
                    **params,
                )
            else:
                yanit = client.messages.create(**params)
            break
        except Exception as exc:  # noqa: BLE001 — tüm SDK hataları kullanıcı mesajına çevrilir
            kod = _hata_kodu(exc)
            gecen = time.monotonic() - baslangic
            logger.warning(
                "Claude isteği başarısız gorev=%s model=%s hata=%s sinif=%s durum=%s request_id=%s",
                gorev,
                model,
                kod,
                type(exc).__name__,
                getattr(exc, "status_code", "-"),
                getattr(exc, "request_id", None) or "-",
            )
            if kod in {"sunucu", "baglanti"} and deneme < max_retries and gecen < 10:
                deneme += 1
                time.sleep(1.5)
                continue
            return ClaudeSonuc(hata=kod, model=model, sure_ms=int(gecen * 1000))

    sure_ms = int((time.monotonic() - baslangic) * 1000)
    usage = getattr(yanit, "usage", None)
    sonuc = ClaudeSonuc(
        stop_reason=yanit.stop_reason or "",
        content=list(yanit.content or []),
        model=getattr(yanit, "model", model) or model,
        girdi_token=int(getattr(usage, "input_tokens", 0) or 0)
        + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        + int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        cikti_token=int(getattr(usage, "output_tokens", 0) or 0),
        sure_ms=sure_ms,
    )
    sonuc.metin = "".join(
        b.text for b in sonuc.content if getattr(b, "type", "") == "text"
    ).strip()

    logger.info(
        "Claude yanıtı gorev=%s model=%s stop=%s girdi_token=%s cikti_token=%s sure_ms=%s request_id=%s",
        gorev,
        sonuc.model,
        sonuc.stop_reason,
        sonuc.girdi_token,
        sonuc.cikti_token,
        sure_ms,
        getattr(yanit, "_request_id", None) or "-",
    )

    if sonuc.stop_reason == "refusal":
        sonuc.hata = "ret"
    elif sonuc.stop_reason == "max_tokens":
        sonuc.hata = "kesildi"
    elif not sonuc.metin and not sonuc.tool_uses():
        sonuc.hata = "bos"
    return sonuc
