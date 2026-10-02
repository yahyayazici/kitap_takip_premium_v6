"""Merkezi yapay zeka gateway — Claude API, önbellek, JSON, kullanım sınırları."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone

from takip.ai_models import AiUretimKaydi
from takip.claude_client import claude_istek, claude_yapilandirildi_mi


def ai_platform_aktif_mi() -> bool:
    if not getattr(settings, "AI_ASSISTANT_ENABLED", True):
        return False
    if getattr(settings, "AI_PLATFORM_ENABLED", True) is False:
        return False
    return True


def ai_llm_aktif_mi() -> bool:
    return ai_platform_aktif_mi() and claude_yapilandirildi_mi()


# Her analiz yanıtına eklenen ortak alanlar: bulguların hangi veriye dayandığı ve
# verinin nerede eksik/belirsiz olduğu kullanıcıya açıkça gösterilir.
ORTAK_ANALIZ_ALANLARI = ("dayanaklar", "belirsizlikler")

ORTAK_ANALIZ_KURALLARI = """
Ortak analiz kuralları (her zaman geçerli):
- Yalnızca kullanıcı mesajındaki VERİ bölümüne dayan. Veride olmayan öğrenci adı, sayı, tarih, ders, konu
  veya eğilim uydurma. Çıkarım yapıyorsan "olası", "veriye göre" gibi ifadelerle bunun çıkarım olduğunu belirt.
- Bir bölüm için veri yoksa veya yetersizse o bölüme "Veri yetersiz: …" diye başla ve hangi verinin eksik
  olduğunu yaz; boşluğu genel tavsiyelerle doldurma. "veri_kapsami.eksik_alanlar" listesi boş gelen alanları gösterir.
- Her bulguda onu destekleyen somut değeri an (ör. "son deneme neti 42,5", "son 7 günde 0 soru kaydı").
- Öneriler uygulanabilir olsun: kim, ne sıklıkla, ne yapacak ve mümkünse ölçülebilir hedef (ör. "2 hafta boyunca
  günde 40 paragraf sorusu, haftalık kontrol etüt hocası tarafından").
- "dayanaklar": Bulguların dayandığı en önemli 3–8 veri noktası; her satır "• alan: değer" biçiminde.
- "belirsizlikler": Eksik veya boş alanlar, küçük örneklem, eski tarihli ya da çelişkili kayıtlar ve bunların
  sonuçları nasıl sınırladığı. Belirgin eksik yoksa "Belirgin bir veri eksikliği yok." yaz.
- Düz metin yaz; madde için "• " kullan. Markdown başlık (#), tablo veya kod bloğu kullanma.
- Türkçe yaz; tarih ve sayıları Türkçe biçimde (virgüllü ondalık) ver.
"""


@dataclass
class AiJsonSonuc:
    veri: dict[str, Any] | None = None
    hata_mesaji: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.veri is not None


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


def analiz_semasi(alanlar: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Yalnızca metin alanlarından oluşan analiz JSON şeması (+ ortak alanlar)."""
    tum = list(dict.fromkeys([*alanlar, *ORTAK_ANALIZ_ALANLARI]))
    return {
        "type": "object",
        "properties": {alan: {"type": "string"} for alan in tum},
        "required": tum,
        "additionalProperties": False,
    }


def ai_json_istek(
    *,
    system: str,
    user_prompt: str,
    alanlar: list[str] | tuple[str, ...] | None = None,
    max_tokens: int | None = None,
) -> AiJsonSonuc:
    """JSON yanıt üretir; hata halinde kullanıcıya gösterilebilir mesaj döner.

    alanlar verilirse yanıt yapılandırılmış çıktı (JSON şeması) ile garanti altına alınır ve
    ortak analiz kuralları (dayanak/belirsizlik, veri uydurmama) eklenir.
    """
    if not ai_platform_aktif_mi():
        return AiJsonSonuc(hata_mesaji="Yapay zeka platformu devre dışı.")
    if not claude_yapilandirildi_mi():
        return AiJsonSonuc(hata_mesaji="")

    schema = analiz_semasi(alanlar) if alanlar else None
    sistem = system + ("\n" + ORTAK_ANALIZ_KURALLARI if alanlar else "")
    if alanlar:
        tokens = max_tokens or int(getattr(settings, "AI_ANALIZ_MAX_TOKENS", 8000))
    else:
        # Serbest JSON görevleri: çağıranın istediği çıktı + düşünme payı
        tokens = (max_tokens or 2000) + int(getattr(settings, "AI_DUSUNME_PAYI", 3000))

    sonuc = claude_istek(
        gorev="analiz" if alanlar else "uretim",
        system=sistem,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=tokens,
        json_schema=schema,
    )
    meta = {"model": sonuc.model, "girdi_token": sonuc.girdi_token, "cikti_token": sonuc.cikti_token}
    if not sonuc.ok:
        return AiJsonSonuc(hata_mesaji=sonuc.mesaj, meta=meta)
    parsed = _json_cek(sonuc.metin)
    if not isinstance(parsed, dict):
        return AiJsonSonuc(hata_mesaji="Yapay zeka yanıtı beklenen biçimde değildi.", meta=meta)
    return AiJsonSonuc(veri=parsed, meta=meta)


def ai_json_uret(
    *,
    system: str,
    user_prompt: str,
    temperature: float | None = None,  # noqa: ARG001 — Claude Opus 5.5 örnekleme parametresi kabul etmez
    max_tokens: int | None = None,
    alanlar: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    """Geriye dönük uyumlu sarmalayıcı: yalnızca sözlük veya None döner."""
    return ai_json_istek(
        system=system,
        user_prompt=user_prompt,
        alanlar=alanlar,
        max_tokens=max_tokens,
    ).veri


def ai_metin_uret(
    *,
    system: str,
    user_prompt: str,
    temperature: float | None = None,  # noqa: ARG001
    max_tokens: int | None = None,
) -> str | None:
    if not ai_llm_aktif_mi():
        return None
    tokens = (max_tokens or 800) + int(getattr(settings, "AI_DUSUNME_PAYI", 3000))
    sonuc = claude_istek(
        gorev="uretim",
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=tokens,
    )
    return sonuc.metin if sonuc.ok and sonuc.metin else None


def kota_asildi_mi(anahtar: str, *, limit: int, sure_sn: int) -> bool:
    """Basit sabit pencere sayaç. True → sınır aşıldı (istek yapılmamalı)."""
    if limit <= 0:
        return False
    cache_anahtar = f"ai-kota:{anahtar}"
    if cache.add(cache_anahtar, 1, timeout=sure_sn):
        return False
    try:
        sayi = cache.incr(cache_anahtar)
    except ValueError:
        cache.set(cache_anahtar, 1, timeout=sure_sn)
        return False
    return sayi > limit


def yenile_izinli_mi(user: User | None) -> bool:
    """Önbelleği atlayan 'yenile' isteklerini kullanıcı başına günlük sınırla."""
    if user is None or not getattr(user, "pk", None):
        return True
    limit = int(getattr(settings, "AI_YENILE_GUNLUK_LIMIT", 30))
    return not kota_asildi_mi(f"yenile:{user.pk}", limit=limit, sure_sn=86400)


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
