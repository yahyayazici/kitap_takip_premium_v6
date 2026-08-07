"""Panel asistanı — OpenAI sohbet katmanı."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count

from config.branding import PANEL_NAME
from takip.asistan_analyzer import AnalizSonuc, site_bilgisi_ozeti
from takip.asistan_types import AsistanAction, AsistanYanit
from takip.models import Sinav, Zimmet
from takip.permissions.scope import yetkili_talebeler


def openai_yapilandirildi_mi() -> bool:
    return bool(getattr(settings, "OPENAI_API_KEY", "").strip())


def _canli_ozet(user: User) -> str:
    talebeler = yetkili_talebeler(user)
    toplam = talebeler.count()
    aktif_zimmet = Zimmet.objects.filter(talebe__in=talebeler, durum="okunuyor").count()
    sinif_dagilim = (
        talebeler.values("sinif_sube__sinif", "sinif_sube__sube")
        .annotate(adet=Count("id"))
        .order_by("-adet")[:6]
    )
    sinif_satir = ", ".join(
        f"{row['sinif_sube__sinif']}/{row['sinif_sube__sube']}: {row['adet']}"
        for row in sinif_dagilim
        if row["sinif_sube__sinif"]
    )
    son_sinav = Sinav.objects.order_by("-sinav_tarihi").first()
    sinav_metni = son_sinav.ad if son_sinav else "—"
    return (
        f"Aktif talebe: {toplam}\n"
        f"Devam eden kitap zimmeti: {aktif_zimmet}\n"
        f"Sınıf dağılımı: {sinif_satir or '—'}\n"
        f"Son kayıtlı sınav: {sinav_metni}"
    )


def _panel_eylem_ozeti(panel_yanit: AsistanYanit | None) -> str:
    if not panel_yanit or not panel_yanit.actions:
        return "Hazır panel eylemi yok."
    satirlar = []
    for action in panel_yanit.actions[:6]:
        if action.type == "pdf":
            satirlar.append(f"- PDF: {action.label}")
        else:
            satirlar.append(f"- Link: {action.label}")
    return "\n".join(satirlar)


def _oneri_onerileri(analiz: AnalizSonuc) -> list[str]:
    if analiz.niyet == "sohbet_danisman":
        return [
            "5-A okuma raporu gönder",
            "Kaç aktif talebe var?",
            "Başarı analizi için ne önerirsin?",
        ]
    if analiz.niyet == "pdf_okuma":
        return ["5. sınıfların okuma raporu", "Bu hafta okuma özeti"]
    if analiz.niyet == "veri_talebe_say":
        return ["Okuma raporu PDF", "Ahmet hakkında bilgi ver"]
    return [
        "Öğrenci başarısı için hangi analizleri önerirsin?",
        "5-A okuma raporu gönder",
        "Kaç aktif talebe var?",
    ]


def _openai_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.65,
    max_tokens: int = 900,
) -> str | None:
    api_key = getattr(settings, "OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    payload = {
        "model": getattr(settings, "AI_ASSISTANT_MODEL", "gpt-4o-mini"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        json.JSONDecodeError,
        IndexError,
        TypeError,
    ):
        return None


def llm_sohbet_cevabi(
    user: User,
    message: str,
    history: list[dict],
    analiz: AnalizSonuc,
    panel_yanit: AsistanYanit | None = None,
) -> AsistanYanit | None:
    """Doğal Türkçe sohbet yanıtı; panel eylemlerini korur."""
    site = site_bilgisi_ozeti(user)
    canli = _canli_ozet(user)
    eylem_ozet = _panel_eylem_ozeti(panel_yanit)

    system = f"""Sen {PANEL_NAME} eğitim panelinin yapay zeka asistanısın.
Kullanıcıyla sıcak, samimi ve profesyonel Türkçe sohbet et — ChatGPT gibi doğal konuş.
Selamlaşma, hal hatır, teşekkür gibi günlük mesajlara kısa ve sıcak cevap ver; hemen ardından
panelde yardımcı olabileceğin konuları nazikçe hatırlatabilirsin ama her cümleyi madde listesine çevirme.

Görevlerin:
1. Günlük sohbet (merhaba, naber, nasılsın, teşekkür vb.) — önce insani karşılık, sonra isteğe bağlı panel teklifi.
2. Pedagojik sorulara (başarı analizi, takip stratejisi, veli görüşmesi vb.) somut öneriler sun.
3. Panel kullanımını açıkla; veri uydurma — aşağıdaki canlı özet dışında sayı uydurma.
4. PDF / rapor / talebe bilgisi istendiğinde kısa onay ver; indirme butonları arayüzde ayrıca gösterilecek.
5. Kısa takip mesajlarını (ör. "5. sınıfların sadece") önceki bağlamla birleştirerek anla.

Panel bağlamı:
{site}

Canlı özet:
{canli}

Algılanan niyet: {analiz.niyet} (güven: {analiz.guven:.0%})
Hazır panel eylemleri:
{eylem_ozet}

Kurallar:
- Markdown kullanabilirsin (**kalın**, madde işaretleri).
- 2–6 paragraf veya kısa maddeler; gereksiz uzatma.
- Panelde olmayan modül için "panelden X modülüne bakabilirsiniz" de.
- Hazır PDF/link varsa "Aşağıdaki butonlardan indirebilirsiniz" de, URL yazma."""

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in history[-14:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    if not history or history[-1].get("content") != message:
        messages.append({"role": "user", "content": message})

    reply = _openai_chat(messages)
    if not reply:
        return None

    actions = panel_yanit.actions if panel_yanit else []
    suggestions = _oneri_onerileri(analiz)

    if panel_yanit and panel_yanit.suggestions:
        for item in panel_yanit.suggestions:
            if item not in suggestions:
                suggestions.insert(0, item)

    return AsistanYanit(
        reply=reply,
        actions=actions[:6],
        suggestions=suggestions[:4],
    )
