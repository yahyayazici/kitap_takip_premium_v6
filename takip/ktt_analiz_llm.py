"""KTT raporları — Claude destekli akademik değerlendirme."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.conf import settings
from django.utils.timezone import localdate

from takip.ai_gateway import ai_json_istek, ai_platform_aktif_mi, onbellege_yaz, onbellekten_al
from takip.claude_client import claude_yapilandirildi_mi

KTT_ALANLARI = (
    "ozet",
    "olcum_bulgulari",
    "pedagojik_yorum",
    "risk_ve_firsatlar",
    "mudahale_onerileri",
    "veli_iletisimi",
)


def ktt_analiz_llm_aktif_mi() -> bool:
    if not ai_platform_aktif_mi():
        return False
    if getattr(settings, "AI_KTT_ANALYSIS_ENABLED", True) is False:
        return False
    return claude_yapilandirildi_mi()


_AKADEMIK_SISTEM = """Sen Türkiye'deki bir eğitim kurumunda görev yapan kıdemli bir ölçme-değerlendirme uzmanı
ve pedagojik danışmansın. KTT (Kazanım Tarama Testi) sonuçlarını MEB ölçme-değerlendirme ilkeleri ve
sınıf içi öğrenme bilgisi çerçevesinde yorumlarsın. Okuyucu: öğretmenler kurulu ve etüt hocaları.

Yazım dili:
- Resmi ama anlaşılır Türkçe; gereksiz jargon kullanma.
- Doğru/yanlış/boş sayılarını tablo gibi tekrarlama — bunlar sonuç tablosunda zaten var; bunun yerine
  ortalama, dağılım (en düşük/en yüksek, standart sapma varsa) ve sınıf farklarını yorumla.
- Her KTT kaydının "ktt" / "ad" alanı konu adını taşır — mutlaka «konu adı» şeklinde yaz.
- Öğrenci sayısı azsa (ör. 5'ten az) genelleme yapma ve bunu belirt.
- Her paragrafta veriden en az bir ders adı ve bir KTT/konu adı geçsin.

JSON alanları:
- "ozet": Genel tablo — 2-4 cümle, puan ortalaması, katılım ve ana mesaj
- "olcum_bulgulari": Güçlü konular — ders + «konu adı», dayanağıyla ve ne korunmalı
- "pedagojik_yorum": Geliştirilmesi gereken konular — ders + «konu adı» ve gelişim alanı
- "risk_ve_firsatlar": Acil müdahale gereken konular / öğrenci grupları
- "mudahale_onerileri": Ne yapmalı — somut etüt planı (kim, ne sıklıkla, hangi hedef)
- "veli_iletisimi": Veliye aktarılacak 1-2 cümle"""

_TUR_ETIKET = {
    "sinav_grup": "Tek KTT sınavının sınıf/grup düzeyinde değerlendirmesi",
    "rapor_grup": "Filtrelenmiş KTT kayıtlarının grup/kohort düzeyinde değerlendirmesi",
    "rapor_bireysel": "Tek öğrencinin KTT geçmişinin bireysel değerlendirmesi",
}


def _payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def ktt_analiz_llm_uret(
    payload: dict[str, Any],
    *,
    tur: str,
    yenile: bool = False,
) -> tuple[dict[str, str] | None, str]:
    """(bölümler, hata_mesajı) döner. tur: sinav_grup | rapor_grup | rapor_bireysel.

    Aynı veri seti için sonuç önbellekten gelir; veri değişince (yeni sonuç girilince) yeniden üretilir.
    """
    if not ktt_analiz_llm_aktif_mi():
        return None, ""

    veri_json = _payload_json(payload)
    anahtar = f"ktt:{tur}:" + hashlib.sha256(veri_json.encode("utf-8")).hexdigest()[:40]
    from takip.ai_models import AiUretimKaydi

    onbellek = onbellekten_al(AiUretimKaydi.Tur.KTT_ANALIZ, anahtar, yenile=yenile)
    if onbellek and isinstance(onbellek.get("bolumler"), dict):
        return onbellek["bolumler"], ""

    kullanici_istegi = (
        f"Analiz türü: {_TUR_ETIKET.get(tur, 'KTT değerlendirmesi')}\n"
        f"Rapor tarihi: {localdate().isoformat()}\n\n"
        "Aşağıdaki veri setini kullanarak ölçme-değerlendirme raporu yaz.\n\n"
        f"VERİ:\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}"
    )

    cevap = ai_json_istek(
        system=_AKADEMIK_SISTEM,
        user_prompt=kullanici_istegi,
        alanlar=KTT_ALANLARI,
        max_tokens=int(getattr(settings, "AI_KTT_ANALYSIS_MAX_TOKENS", 8000)),
    )
    if not cevap.veri:
        return None, cevap.hata_mesaji

    bolumler = {
        alan: str(deger).strip()
        for alan, deger in cevap.veri.items()
        if isinstance(deger, str) and deger.strip()
    }
    if len(bolumler) < 2:
        return None, "Yapay zeka yanıtı eksik geldi."

    onbellege_yaz(
        tur=AiUretimKaydi.Tur.KTT_ANALIZ,
        anahtar=anahtar,
        icerik={"bolumler": bolumler},
        yapay_zeka=True,
    )
    return bolumler, ""
