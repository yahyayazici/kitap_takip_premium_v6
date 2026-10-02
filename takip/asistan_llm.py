"""Panel asistanı — Claude sohbet katmanı.

Claude, panel verisine yalnızca aşağıdaki sunucu tarafı araçlarla erişir. Her araç
kullanıcının mevcut yetkileriyle çalışır (yetkili_talebeler, can, talebe_ai_erisebilir);
asistan bu yetkilerin dışına çıkamaz ve veri değiştiremez.
"""

from __future__ import annotations

import json
import time
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.utils.timezone import localdate

from config.branding import PANEL_NAME
from takip.asistan_analyzer import AnalizSonuc, siniflari_coz, site_bilgisi_ozeti
from takip.asistan_types import AsistanAction, AsistanYanit
from takip.claude_client import HATA_MESAJLARI, claude_istek, claude_yapilandirildi_mi

_GECMIS_MESAJ_SAYISI = 12
_GECMIS_MESAJ_MAX_KARAKTER = 4000
_ARAC_SONUC_MAX_KARAKTER = 30_000
_MAX_ARAC_TURU = 3

# Araç işlem adı → kural tabanlı panel yanıtındaki niyet kodu
_ISLEM_NIYET = {
    "okuma_raporu_pdf": "pdf_okuma",
    "talebe_listesi_pdf": "pdf_talebe_liste",
    "talebe_kitap_karnesi_pdf": "pdf_profil",
    "son_sinav_sonuc_pdf": "pdf_sinav",
    "kurum_programi_pdf": "pdf_program",
    "imam_muezzin_pdf": "pdf_imam",
    "temizlik_pdf": "pdf_temizlik",
    "yemekcilik_pdf": "pdf_yemek",
    "talebe_sayisi": "veri_talebe_say",
    "okuma_durumu": "veri_okuma",
    "talebe_kunyesi": "talebe_bilgi",
}

PANEL_ARACLARI: list[dict[str, Any]] = [
    {
        "name": "panel_islemi",
        "description": (
            "Paneldeki hazır rapor/PDF bağlantılarını ve temel sayıları kullanıcının yetkisiyle getirir. "
            "Dönen butonlar sohbet balonunun altında kullanıcıya gösterilir. "
            "islem değerleri: okuma_raporu_pdf (siniflar boşsa kurum geneli), talebe_listesi_pdf, "
            "talebe_kitap_karnesi_pdf (talebe_adi gerekli), son_sinav_sonuc_pdf (talebe_adi verilirse "
            "bireysel karne de eklenir), kurum_programi_pdf, imam_muezzin_pdf, temizlik_pdf, yemekcilik_pdf, "
            "talebe_sayisi (sınıf dağılımıyla), okuma_durumu (aktif kitap zimmeti sayısı), "
            "talebe_kunyesi (sınıf, etüt hocası, okuduğu kitap, son sınav; talebe_adi gerekli)."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "islem": {"type": "string", "enum": list(_ISLEM_NIYET)},
                "siniflar": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Sınıf/şube etiketleri, örn. ['5-A'] veya seviye için ['5']. Yoksa boş liste.",
                },
                "talebe_adi": {
                    "type": "string",
                    "description": "Talebe adı veya ad soyadı; gerekmiyorsa boş metin.",
                },
            },
            "required": ["islem", "siniflar", "talebe_adi"],
            "additionalProperties": False,
        },
    },
    {
        "name": "talebe_gelisim_verisi",
        "description": (
            "Bir talebenin deneme, KTT, soru takip, devam/namaz, okuma ve akademik müdahale verilerini getirir. "
            "Talebenin durumu, başarısı veya ona yönelik öneri sorulduğunda kullan."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"talebe_adi": {"type": "string"}},
            "required": ["talebe_adi"],
            "additionalProperties": False,
        },
    },
    {
        "name": "kurum_ozeti",
        "description": (
            "Kullanıcının yetki kapsamındaki kurum geneli özet: talebe sayısı, sınıf dağılımı, aktif kitap "
            "zimmeti, bu ay çözülen soru ve kural tabanlı risk adayları."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
]


def _sistem_istemi(user: User, *, rol_metni: str, ek_baglam: str, araclar_var: bool) -> str:
    ad = (user.get_full_name() or user.get_username() or "").strip()
    arac_kurali = (
        "- Sayı, isim, tarih veya öğrenci/sınıf bilgisi gerektiren her soruda önce araçları kullan. "
        "Araç sonucunda olmayan bir veriyi söyleme. Araç bilgiyi döndürmediyse bunu açıkça söyle ve "
        "panelde nereye bakılacağını tarif et.\n"
        "- Rapor, PDF veya liste istendiğinde panel_islemi aracını çağır. Butonlar yanıtın altında "
        "görünür; araç buton döndürmediyse \"hazırladım\" deme, nedenini (yetki yok, kayıt yok) söyle.\n"
        "- Talebe adı birden fazla kişiyle eşleşirse adayları sıralayıp hangisi olduğunu sor.\n"
        if araclar_var
        else "- Bu panelde veri araçlarına erişimin yok; yalnızca aşağıdaki panel bilgisini kullan. "
        "Sayı veya kişisel veri uydurma; kullanıcıyı ilgili menüye yönlendir.\n"
    )
    return f"""Sen {PANEL_NAME} eğitim takip panelinin yapay zeka asistanısın.
Bugünün tarihi: {localdate().isoformat()}. Kullanıcı: {ad or "panel kullanıcısı"} ({rol_metni}).

Nasıl yanıt verirsin:
- Türkçe, sade, samimi ve profesyonel yaz. Selamlaşma ve teşekkür gibi mesajlara kısa ve sıcak karşılık ver.
- Kısa sorulara kısa yanıt ver; gerekmedikçe 180 kelimeyi aşma. Biçim olarak yalnızca **kalın** ve "• " maddeleri kullan.
- Önceki mesajlardaki bağlamı kullan (ör. önce okuma raporu istenip sonra "sadece 5. sınıflar" yazılırsa ikisini birleştir).
{arac_kurali}- Yapamadığın işlemler: kayıt ekleme, silme veya düzenleme; not/yoklama girme; veli veya öğrenciye mesaj,
  SMS, WhatsApp ya da bildirim gönderme; ayar ve yetki değiştirme. Bunlar istenirse yapmadığını açıkça söyle ve
  panelde hangi menüden yapılacağını tarif et. Bu işlemleri yapmış gibi "gönderdim", "kaydettim", "güncelledim" deme.
- URL veya bağlantı adresi yazma; kullanıcıyı butonlara ya da menü adlarına yönlendir.
- Pedagojik sorularda somut ve uygulanabilir öneri ver. Öğrenci verisine dayanıyorsan hangi veriye dayandığını
  kısaca belirt; veri yoksa önerinin genel olduğunu söyle.
- Kişisel verileri gereğinden fazla tekrar etme; yalnızca sorulan bilgiyi ver.

Panel bilgisi:
{ek_baglam}"""


def _gecmis_mesajlari(history: list[dict], message: str) -> list[dict[str, Any]]:
    mesajlar: list[dict[str, Any]] = []
    for item in history[-_GECMIS_MESAJ_SAYISI:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content") or "").strip()[:_GECMIS_MESAJ_MAX_KARAKTER]
        if role in {"user", "assistant"} and content:
            mesajlar.append({"role": role, "content": content})
    # Ön yüz geçmişi son kullanıcı mesajını zaten içeriyor olabilir
    if mesajlar and mesajlar[-1]["role"] == "user" and mesajlar[-1]["content"] == message:
        mesajlar.pop()
    # API ilk mesajın kullanıcıdan gelmesini bekler
    while mesajlar and mesajlar[0]["role"] != "user":
        mesajlar.pop(0)
    mesajlar.append({"role": "user", "content": message})
    return mesajlar


def _talebe_adaylari_metni(user: User, ad: str) -> str:
    from takip.asistan_service import _talebe_adaylari

    adaylar = _talebe_adaylari(user, ad)
    if not adaylar:
        return f"'{ad}' adıyla yetki kapsamında talebe bulunamadı."
    return "Birden fazla eşleşme var: " + ", ".join(
        f"{t.ad_soyad} ({t.sinif_sube or t.sinif or '—'})" for t in adaylar
    )


def _arac_panel_islemi(user: User, girdi: dict[str, Any]) -> tuple[dict[str, Any], list[AsistanAction]]:
    from takip.asistan_service import _yanit_uret

    islem = str(girdi.get("islem") or "")
    niyet = _ISLEM_NIYET.get(islem)
    if not niyet:
        return {"durum": "hata", "aciklama": "Bilinmeyen işlem."}, []
    talebe_adi = str(girdi.get("talebe_adi") or "").strip() or None
    etiketler = [str(e) for e in (girdi.get("siniflar") or []) if str(e).strip()]
    siniflar = siniflari_coz(user, etiketler) if etiketler else []
    if etiketler and not siniflar:
        return {
            "durum": "bulunamadi",
            "aciklama": f"{', '.join(etiketler)} için yetki kapsamında sınıf bulunamadı.",
        }, []

    analiz = AnalizSonuc(
        birlesik_mesaj="",
        niyet=niyet,
        siniflar=siniflar,
        talebe_adi=talebe_adi,
        guven=1.0,
    )
    yanit = _yanit_uret(user, analiz)
    if yanit is None:
        if talebe_adi:
            return {"durum": "bulunamadi", "aciklama": _talebe_adaylari_metni(user, talebe_adi)}, []
        return {
            "durum": "bulunamadi",
            "aciklama": "Bu işlem için sonuç üretilemedi (yetki veya kayıt yok).",
        }, []
    return {
        "durum": "tamam" if yanit.actions or niyet.startswith("veri_") or niyet == "talebe_bilgi" else "bilgi",
        "panel_yaniti": yanit.reply,
        "arayuzde_gosterilen_butonlar": [a.label for a in yanit.actions[:6]],
    }, list(yanit.actions)


def _arac_talebe_gelisim(user: User, girdi: dict[str, Any]) -> tuple[dict[str, Any], list[AsistanAction]]:
    from django.urls import reverse

    from takip.ai_context import talebe_zengin_baglam
    from takip.ai_permissions import rehberlik_ai_erisebilir, talebe_ai_erisebilir
    from takip.asistan_service import _talebe_bul

    ad = str(girdi.get("talebe_adi") or "").strip()
    if not ad:
        return {"durum": "hata", "aciklama": "talebe_adi gerekli."}, []
    talebe = _talebe_bul(user, ad)
    if talebe is None:
        return {"durum": "bulunamadi", "aciklama": _talebe_adaylari_metni(user, ad)}, []
    if not talebe_ai_erisebilir(user, talebe):
        return {"durum": "yetki_yok", "aciklama": "Bu talebenin gelişim verisine erişim yetkiniz yok."}, []

    baglam = talebe_zengin_baglam(talebe)
    if not rehberlik_ai_erisebilir(user):
        baglam.pop("gorusmeler", None)
    eylem = AsistanAction(
        type="link",
        label=f"{talebe.ad_soyad} — Profil",
        url=reverse("talebe_detay", kwargs={"talebe_id": talebe.pk}),
    )
    return {"durum": "tamam", "veri": baglam}, [eylem]


def _arac_kurum_ozeti(user: User, girdi: dict[str, Any]) -> tuple[dict[str, Any], list[AsistanAction]]:
    from takip.ai_context import kurum_baglam
    from takip.ai_permissions import kurum_ai_erisebilir

    if not kurum_ai_erisebilir(user):
        return {"durum": "yetki_yok", "aciklama": "Kurum geneli özete erişim yetkiniz yok."}, []
    return {"durum": "tamam", "veri": kurum_baglam(user)}, []


_ARACLAR = {
    "panel_islemi": _arac_panel_islemi,
    "talebe_gelisim_verisi": _arac_talebe_gelisim,
    "kurum_ozeti": _arac_kurum_ozeti,
}


def arac_calistir(user: User, ad: str, girdi: Any) -> tuple[str, list[AsistanAction], bool]:
    """(sonuç metni, eklenecek butonlar, hata mı) döner."""
    fonksiyon = _ARACLAR.get(ad)
    if fonksiyon is None or not isinstance(girdi, dict):
        return json.dumps({"durum": "hata", "aciklama": "Geçersiz araç çağrısı."}, ensure_ascii=False), [], True
    try:
        sonuc, eylemler = fonksiyon(user, girdi)
    except Exception:  # noqa: BLE001 — araç hatası modele bildirilir, sohbet sürer
        import logging

        logging.getLogger(__name__).exception("Asistan aracı hata verdi arac=%s", ad)
        return json.dumps({"durum": "hata", "aciklama": "Veri alınırken hata oluştu."}, ensure_ascii=False), [], True
    metin = json.dumps(sonuc, ensure_ascii=False, default=str)
    if len(metin) > _ARAC_SONUC_MAX_KARAKTER:
        metin = json.dumps(
            {"durum": "hata", "aciklama": "Sonuç çok büyük; soruyu daraltın (ör. tek sınıf veya tek talebe)."},
            ensure_ascii=False,
        )
        return metin, [], True
    return metin, eylemler, sonuc.get("durum") == "hata"


def _sohbet_dongusu(
    user: User,
    *,
    system: str,
    mesajlar: list[dict[str, Any]],
    araclar: list[dict[str, Any]] | None,
) -> tuple[str | None, list[AsistanAction], str]:
    """(yanıt, butonlar, hata mesajı). Araç çağrılarını en fazla _MAX_ARAC_TURU tur yürütür."""
    toplam_sure = float(getattr(settings, "AI_SOHBET_TOPLAM_SURE", 70))
    tek_istek = float(getattr(settings, "AI_SOHBET_TIMEOUT", 40))
    max_tokens = int(getattr(settings, "AI_SOHBET_MAX_TOKENS", 3000))
    son_an = time.monotonic() + toplam_sure
    eylemler: list[AsistanAction] = []

    for _ in range(_MAX_ARAC_TURU + 1):
        kalan = son_an - time.monotonic()
        if kalan < 5:
            return None, eylemler, HATA_MESAJLARI["zaman_asimi"]
        sonuc = claude_istek(
            gorev="sohbet",
            system=system,
            messages=mesajlar,
            max_tokens=max_tokens,
            tools=araclar,
            timeout=min(tek_istek, kalan),
            max_retries=0,
        )
        if not sonuc.ok and sonuc.hata != "kesildi":
            return None, eylemler, sonuc.mesaj

        if sonuc.stop_reason == "tool_use" and araclar:
            # Düşünme blokları dahil yanıt olduğu gibi geri gönderilir.
            mesajlar.append({"role": "assistant", "content": sonuc.content})
            sonuclar = []
            for blok in sonuc.tool_uses():
                metin, yeni, hata = arac_calistir(user, blok.name, blok.input)
                eylemler.extend(yeni)
                sonuclar.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": blok.id,
                        "content": metin,
                        **({"is_error": True} if hata else {}),
                    }
                )
            mesajlar.append({"role": "user", "content": sonuclar})
            continue

        if sonuc.hata == "kesildi":
            if not sonuc.metin:
                return None, eylemler, sonuc.mesaj
            return sonuc.metin + "\n\n(Yanıt uzunluk sınırına ulaştığı için kısaltıldı.)", eylemler, ""
        return sonuc.metin, eylemler, ""

    return None, eylemler, "Yapay zeka yanıtı çok fazla adım gerektirdi. Soruyu daraltıp tekrar deneyin."


def _benzersiz_eylemler(eylemler: list[AsistanAction]) -> list[AsistanAction]:
    gorulen = set()
    sonuc = []
    for e in eylemler:
        anahtar = (e.type, e.url, e.label)
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        sonuc.append(e)
    return sonuc[:6]


def _oneri_onerileri(analiz: AnalizSonuc | None) -> list[str]:
    niyet = analiz.niyet if analiz else ""
    if niyet == "pdf_okuma":
        return ["5. sınıfların okuma raporu", "Bu hafta okuma özeti"]
    if niyet == "veri_talebe_say":
        return ["Okuma raporu PDF", "Kurum genelinde öne çıkan riskler neler?"]
    if niyet == "talebe_bilgi":
        return ["Bu talebe için ne önerirsin?", "Kitap karnesi PDF"]
    return [
        "Kurum genelinde öne çıkan riskler neler?",
        "5-A okuma raporu gönder",
        "Kaç aktif talebe var?",
    ]


def llm_sohbet_cevabi(
    user: User,
    message: str,
    history: list[dict],
    analiz: AnalizSonuc | None = None,
) -> tuple[AsistanYanit | None, str]:
    """Yönetim/personel kullanıcısı için araçlı Claude sohbeti. (yanıt, hata mesajı) döner."""
    if not claude_yapilandirildi_mi():
        return None, ""
    from takip.panel_permissions import rol_etiketi

    system = _sistem_istemi(
        user,
        rol_metni=rol_etiketi(user) or "personel",
        ek_baglam=site_bilgisi_ozeti(user),
        araclar_var=True,
    )
    yanit, eylemler, hata = _sohbet_dongusu(
        user,
        system=system,
        mesajlar=_gecmis_mesajlari(history, message),
        araclar=PANEL_ARACLARI,
    )
    if yanit is None:
        return None, hata
    return (
        AsistanYanit(
            reply=yanit,
            actions=_benzersiz_eylemler(eylemler),
            suggestions=_oneri_onerileri(analiz)[:4],
        ),
        "",
    )


def llm_ozel_panel_cevabi(
    user: User,
    message: str,
    history: list[dict],
    *,
    rol_metni: str,
    panel_rehberi: str,
    suggestions: list[str] | None = None,
) -> tuple[AsistanYanit | None, str]:
    """Veli / öğretmen / talebe paneli: veri aracı yok, yalnızca panel rehberi ve verilen özet."""
    if not claude_yapilandirildi_mi():
        return None, ""
    system = _sistem_istemi(user, rol_metni=rol_metni, ek_baglam=panel_rehberi, araclar_var=False)
    yanit, _, hata = _sohbet_dongusu(
        user,
        system=system,
        mesajlar=_gecmis_mesajlari(history, message),
        araclar=None,
    )
    if yanit is None:
        return None, hata
    return AsistanYanit(reply=yanit, suggestions=(suggestions or [])[:4]), ""
