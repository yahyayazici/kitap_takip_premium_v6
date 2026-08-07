"""KTT raporları — yapay zeka destekli akademik değerlendirme."""

from __future__ import annotations

import json
import re
from typing import Any

from django.conf import settings

from takip.asistan_llm import _openai_chat, openai_yapilandirildi_mi


def ktt_analiz_llm_aktif_mi() -> bool:
    if not getattr(settings, "AI_ASSISTANT_ENABLED", True):
        return False
    if getattr(settings, "AI_KTT_ANALYSIS_ENABLED", True) is False:
        return False
    return openai_yapilandirildi_mi()


_AKADEMIK_SISTEM = """Sen Türkiye'deki bir eğitim kurumunda görev yapan kıdemli bir ölçme-değerlendirme uzmanı,
eğitim bilimleri akademisyeni ve pedagojik danışmansın. KTT (Kazanım Tarama Testi) sonuçlarını
MEB ölçme-değerlendirme ilkeleri, Bloom taksonomisi ve sınıf içi öğrenme psikolojisi çerçevesinde yorumlarsın.

Yazım dili:
- Resmi ama anlaşılır akademik Türkçe; günlük konuşma dili kullanma.
- "Veriler şunu göstermektedir", "bu bulgu", "pedagojik müdahale", "kazanım düzeyi", "heterojenlik",
  "madde güçlüğü", "işlem hatası / bilgi eksikliği ayrımı" gibi ölçme-değerlendirme terminolojisi kullan.
- Somut sayılara atıf yap; veri setinde olmayan öğrenci adı, sınav adı veya istatistik uydurma.
- Doğru/yanlış/boş sayılarını tekrarlama — bunlar sonuç tablosunda zaten var.
- Odak: güçlü konular, zayıf konular, ne yapmalı (etüt/müdahale önerisi).
- Her KTT kaydının "ktt" alanı konu adını taşır — mutlaka «konu adı» şeklinde tırnak içinde yaz.
- Her bölüm en az 2–4 cümle; genel toplam metin kapsamlı ve derinlikli olsun (yüzeysel özet yazma).

Yanıtı yalnızca geçerli JSON olarak ver — markdown code fence kullanma:
{
  "ozet": "Kısa genel tablo — 2-3 cümle, puan ortalaması ve ana mesaj",
  "olcum_bulgulari": "Güçlü konular — ders + «konu adı» ve ne korunmalı",
  "pedagojik_yorum": "Zayıf konular — ders + «konu adı» ve gelişim alanı",
  "risk_ve_firsatlar": "Risk: acil müdahale gereken konular",
  "mudahale_onerileri": "Ne yapmalı — somut etüt ve çalışma önerileri (D/Y/B sayma)",
  "veli_iletisimi": "Veliye aktarılacak 1-2 cümle"
}"""


def _json_cek(metin: str) -> dict[str, str] | None:
    if not metin:
        return None
    metin = metin.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", metin, re.DOTALL)
    if fence:
        metin = fence.group(1)
    else:
        bas = metin.find("{")
        son = metin.rfind("}")
        if bas >= 0 and son > bas:
            metin = metin[bas : son + 1]
    try:
        veri = json.loads(metin)
    except json.JSONDecodeError:
        return None
    if not isinstance(veri, dict):
        return None
    alanlar = (
        "ozet",
        "olcum_bulgulari",
        "pedagojik_yorum",
        "risk_ve_firsatlar",
        "mudahale_onerileri",
        "veli_iletisimi",
    )
    return {
        alan: str(veri.get(alan) or "").strip()
        for alan in alanlar
        if str(veri.get(alan) or "").strip()
    }


def ktt_analiz_llm_uret(payload: dict[str, Any], *, tur: str) -> dict[str, str] | None:
    """tur: sinav_grup | rapor_grup | rapor_bireysel"""
    if not ktt_analiz_llm_aktif_mi():
        return None

    tur_etiket = {
        "sinav_grup": "Tek KTT sınavının sınıf/grup düzeyinde değerlendirmesi",
        "rapor_grup": "Filtrelenmiş KTT kayıtlarının grup/kohort düzeyinde değerlendirmesi",
        "rapor_bireysel": "Tek öğrencinin KTT geçmişinin bireysel değerlendirmesi",
    }.get(tur, "KTT değerlendirmesi")

    kullanici_istegi = f"""Analiz türü: {tur_etiket}

Aşağıdaki JSON veri setini kullanarak kapsamlı bir ölçme-değerlendirme raporu yaz.
Tüm bölümleri doldur; kısa kesme. Öğretmen kurulunda okunabilecek düzeyde geniş ve düşünceli ol.
Her paragrafta en az bir ders adı ve bir KTT/konu adı (ktt_gecmisi veya detay_kayitlar içinden) somut olarak geçsin.

VERİ:
{json.dumps(payload, ensure_ascii=False, indent=2)}"""

    cevap = _openai_chat(
        [
            {"role": "system", "content": _AKADEMIK_SISTEM},
            {"role": "user", "content": kullanici_istegi},
        ],
        temperature=0.35,
        max_tokens=int(getattr(settings, "AI_KTT_ANALYSIS_MAX_TOKENS", 2200)),
    )
    if not cevap:
        return None

    parsed = _json_cek(cevap)
    if parsed and len(parsed) >= 2:
        return parsed

    return {"ozet": cevap.strip()}
