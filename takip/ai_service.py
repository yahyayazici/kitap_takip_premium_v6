"""Yapay zeka platformu — gelişim zekası, müdahale, veli, deneme, rehberlik, kurum."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.utils.timezone import localdate

from config.branding import PANEL_NAME

from takip.ai_context import (
    baglam_json,
    deneme_baglam,
    kurum_baglam,
    talebe_risk_skoru,
    talebe_zengin_baglam,
    _mudahale_adaylari,
)
from takip.ai_gateway import (
    ai_json_uret,
    ai_llm_aktif_mi,
    ai_platform_aktif_mi,
    onbellekten_al,
    onbellege_yaz,
)
from takip.ai_models import AiUretimKaydi
from takip.ai_types import AiAnalizBolum, AiAnalizSonuc
from takip.models import Talebe
from takip.permissions.scope import yetkili_talebeler
from takip.rehberlik_models import OgrenciGorusmesi


_BOLUM_TON = {
    "ozet": "notr",
    "guclu_yonler": "guclu",
    "gelisim_alanlari": "zayif",
    "risk_sinyalleri": "dikkat",
    "mudahale_onerileri": "aksiyon",
    "veli_mesaji": "notr",
    "sinif_ozeti": "notr",
    "brans_analizi": "zayif",
    "etut_onerileri": "aksiyon",
    "takip_maddeleri": "aksiyon",
    "kurum_ozeti": "notr",
    "oncelikli_talebeler": "dikkat",
    "sinif_sinif": "notr",
    "aksiyon": "aksiyon",
}


def ai_durumu() -> dict[str, str]:
    if ai_llm_aktif_mi():
        return {"aktif": True, "etiket": "Yapay Zeka", "uyari": ""}
    if ai_platform_aktif_mi():
        return {"aktif": False, "etiket": "Akıllı Analiz", "uyari": ""}
    return {"aktif": False, "etiket": "Kapalı", "uyari": "AI platformu devre dışı."}


def _llm_bolumleri(llm: dict[str, str], etiketler: dict[str, str]) -> list[AiAnalizBolum]:
    bolumler: list[AiAnalizBolum] = []
    for anahtar, baslik in etiketler.items():
        icerik = (llm.get(anahtar) or "").strip()
        if icerik:
            bolumler.append(
                AiAnalizBolum(
                    baslik=baslik,
                    icerik=icerik,
                    ton=_BOLUM_TON.get(anahtar, "notr"),
                )
            )
    return bolumler


def _analiz_getir(
    *,
    tur: str,
    anahtar: str,
    uretici,
    user: User | None = None,
    yenile: bool = False,
) -> AiAnalizSonuc:
    if ai_platform_aktif_mi():
        cached = onbellekten_al(tur, anahtar, yenile=yenile)
        if cached:
            return AiAnalizSonuc.from_dict(cached)

    sonuc = uretici()
    if ai_platform_aktif_mi():
        onbellege_yaz(
            tur=tur,
            anahtar=anahtar,
            icerik=sonuc.as_dict(),
            yapay_zeka=sonuc.yapay_zeka,
            user=user,
        )
    return sonuc


_GELISIM_ETIKET = {
    "ozet": "Genel Tablo",
    "guclu_yonler": "Güçlü Yönler",
    "gelisim_alanlari": "Gelişim Alanları",
    "risk_sinyalleri": "Risk Sinyalleri",
    "mudahale_onerileri": "Önerilen Müdahaleler",
    "veli_mesaji": "Veli İletişim Notu",
}

_GELISIM_SISTEM = f"""Sen {PANEL_NAME} eğitim kurumunun kıdemli gelişim danışmanısın.
Öğrencinin akademik, okuma, devam, namaz ve soru takip verilerini bütüncül okursun.
Veri setinde olmayan bilgi uydurma. Resmi ama sıcak Türkçe kullan.
Yanıtı yalnızca geçerli JSON ver:
{{
  "ozet": "2-4 cümle genel tablo",
  "guclu_yonler": "Madde madde güçlü alanlar",
  "gelisim_alanlari": "Madde madde gelişim alanları",
  "risk_sinyalleri": "Varsa erken uyarı sinyalleri",
  "mudahale_onerileri": "Somut etüt/çalışma önerileri",
  "veli_mesaji": "Veliye aktarılabilecek 1-2 cümle (disiplin detayı yok)"
}}"""


def _fallback_gelisim(talebe: Talebe, baglam: dict) -> AiAnalizSonuc:
    skor, nedenler = talebe_risk_skoru(talebe)
    denemeler = baglam.get("denemeler") or []
    son_deneme = denemeler[0] if denemeler else None
    ay_soru = (baglam.get("soru_takip") or {}).get("bu_ay") or {}

    ozet = (
        f"{talebe.ad_soyad} için bütüncül gelişim özeti. "
        f"Risk skoru: {skor}/100."
    )
    if son_deneme:
        ozet += f" Son deneme neti: {son_deneme.get('net', '—')}."

    guclu = []
    if son_deneme and float(son_deneme.get("net", 0)) >= 50:
        guclu.append("• Deneme performansı kabul edilebilir düzeyde")
    if ay_soru.get("toplam_soru", 0) >= 100:
        guclu.append(f"• Bu ay {ay_soru['toplam_soru']} soru çözülmüş")
    devam = baglam.get("devam") or {}
    if devam.get("namaz_katilim_orani", 0) >= 85:
        guclu.append("• Namaz katılımı iyi")

    zayif = []
    if nedenler:
        zayif.extend(f"• {n}" for n in nedenler)

    return AiAnalizSonuc(
        baslik=f"{talebe.ad_soyad} · Gelişim Zekası",
        tur="gelisim_zekasi",
        bolumler=[
            AiAnalizBolum("Genel Tablo", ozet, "notr"),
            AiAnalizBolum(
                "Güçlü Yönler",
                "\n".join(guclu) or "Belirgin güçlü alan ayrımı için daha fazla veri gerekli.",
                "guclu",
            ),
            AiAnalizBolum(
                "Gelişim Alanları",
                "\n".join(zayif) or "Kritik gelişim alanı tespit edilmedi.",
                "zayif",
            ),
            AiAnalizBolum(
                "Önerilen Müdahaleler",
                _mudahale_metni_uret(talebe, skor, nedenler),
                "aksiyon",
            ),
        ],
        yapay_zeka=False,
        meta={"risk_skoru": skor},
    )


def _mudahale_metni_uret(talebe: Talebe, skor: int, nedenler: list[str]) -> str:
    satirlar = []
    if skor >= 60:
        satirlar.append("• Etüt hocası ile acil birebir görüşme planlanmalı")
        satirlar.append("• Akademik müdahale kaydı açılmalı")
    elif skor >= 40:
        satirlar.append("• Haftalık soru hedefi belirlenmeli")
        satirlar.append("• Zayıf branş için ek etüt önerilmeli")
    else:
        satirlar.append("• Rutin takip yeterli; mevcut program sürdürülmeli")
    for n in nedenler[:2]:
        if "deneme" in n.lower() or "net" in n.lower():
            satirlar.append("• Deneme branş analizi ve hedefli konu tekrarı")
        if "soru" in n.lower():
            satirlar.append("• Günlük soru takip hedefi artırılmalı")
        if "okuma" in n.lower():
            satirlar.append("• Haftalık okuma planı gözden geçirilmeli")
    return "\n".join(dict.fromkeys(satirlar))


def gelisim_zekasi_analizi(
    user: User,
    talebe: Talebe,
    *,
    yenile: bool = False,
) -> AiAnalizSonuc:
    anahtar = f"talebe:{talebe.id}:{localdate().isocalendar()[1]}"

    def uret():
        baglam = talebe_zengin_baglam(talebe)
        llm = ai_json_uret(
            system=_GELISIM_SISTEM,
            user_prompt=f"Öğrenci veri seti:\n{baglam_json(baglam)}",
            max_tokens=2000,
        )
        if llm:
            bolumler = _llm_bolumleri(llm, _GELISIM_ETIKET)
            skor, _ = talebe_risk_skoru(talebe)
            return AiAnalizSonuc(
                baslik=f"{talebe.ad_soyad} · Gelişim Zekası",
                tur="gelisim_zekasi",
                bolumler=bolumler,
                yapay_zeka=True,
                meta={"risk_skoru": skor},
            )
        return _fallback_gelisim(talebe, baglam)

    return _analiz_getir(
        tur=AiUretimKaydi.Tur.GELISIM_ZEKASI,
        anahtar=anahtar,
        uretici=uret,
        user=user,
        yenile=yenile,
    )


_VELI_ETIKET = {
    "ozet": "Bu Haftanın Özeti",
    "akademik": "Akademik Durum",
    "aliskanliklar": "Alışkanlıklar",
    "veli_onerisi": "Evde Destek Önerisi",
}

_VELI_SISTEM = f"""Sen {PANEL_NAME} veli iletişim uzmanısın.
Veliye sıcak, anlaşılır Türkçe ile haftalık özet yazarsın.
Disiplin ve rehberlik detayı verme; sadece paylaşılan KPI'ları kullan.
JSON yanıt:
{{
  "ozet": "2-3 cümle haftalık özet",
  "akademik": "Deneme/KTT/soru durumu",
  "aliskanliklar": "Okuma ve katılım",
  "veli_onerisi": "Evde yapılabilecek 1-2 somut öneri"
}}"""


def veli_haftalik_ozet(
    talebe: Talebe,
    *,
    user: User | None = None,
    yenile: bool = False,
) -> AiAnalizSonuc:
    hafta = localdate().isocalendar()[1]
    anahtar = f"veli:{talebe.id}:w{hafta}"

    def uret():
        baglam = talebe_zengin_baglam(talebe, veli_modu=True)
        kpi = {
            "haftalik_soru": baglam["soru_takip"]["bu_hafta"],
            "okuma": baglam["okuma"],
        }
        baglam["veli_kpi"] = kpi

        llm = ai_json_uret(
            system=_VELI_SISTEM,
            user_prompt=f"Veli özeti için veri:\n{baglam_json(baglam)}",
        )
        if llm:
            return AiAnalizSonuc(
                baslik=f"{talebe.ad_soyad} · Haftalık Özet",
                tur="veli_haftalik",
                bolumler=_llm_bolumleri(llm, _VELI_ETIKET),
                yapay_zeka=True,
            )

        hafta_s = baglam["soru_takip"]["bu_hafta"]
        return AiAnalizSonuc(
            baslik=f"{talebe.ad_soyad} · Haftalık Özet",
            tur="veli_haftalik",
            bolumler=[
                AiAnalizBolum(
                    "Bu Haftanın Özeti",
                    f"Bu hafta {hafta_s.get('toplam_soru', 0)} soru çözüldü, "
                    f"başarı oranı %{hafta_s.get('basari_orani', 0)}.",
                    "notr",
                ),
                AiAnalizBolum(
                    "Evde Destek Önerisi",
                    "Çocuğunuzla haftalık hedef belirleyip birlikte takip edebilirsiniz.",
                    "aksiyon",
                ),
            ],
            yapay_zeka=False,
        )

    return _analiz_getir(
        tur=AiUretimKaydi.Tur.VELI_HAFTALIK,
        anahtar=anahtar,
        uretici=uret,
        user=user,
        yenile=yenile,
    )


_NOT_VELI_SISTEM = f"""Sen {PANEL_NAME} öğretmen-veli iletişim asistanısın.
Öğretmenin haftalık ders değerlendirmesinden veliye sıcak, kısa bir mesaj taslağı yaz.
Disiplin detayı ve olumsuz etiketleme yapma. 3-5 cümle, yalnızca düz metin (JSON değil)."""


def veli_not_mesaj_taslagi(
    talebe: Talebe,
    *,
    katilim,
    takip,
    disiplin,
    aciklama: str,
    ders_ad: str,
    hafta_no: int,
    hoca_ad: str,
) -> str:
    """Öğretmen notundan veliye iletilecek kısa mesaj taslağı."""
    veri = {
        "ogrenci": talebe.ad_soyad,
        "ders": ders_ad,
        "hafta": hafta_no,
        "ogretmen": hoca_ad,
        "katilim": str(katilim),
        "takip": str(takip),
        "disiplin": str(disiplin),
        "degerlendirme": aciklama,
    }

    from takip.ai_gateway import ai_metin_uret

    llm = ai_metin_uret(
        system=_NOT_VELI_SISTEM,
        user_prompt=f"Değerlendirme verisi:\n{baglam_json(veri)}",
        max_tokens=400,
    )
    if llm:
        return llm.strip()[:800]

    return (
        f"Sayın veli, {talebe.ad_soyad} {hafta_no}. hafta {ders_ad} dersinde "
        f"değerlendirildi. Öğretmen notu: {aciklama[:200]}"
    )


_VELI_TAKIP_ETIKET = {
    "ozet": "Genel Durum",
    "sinif_sinif": "Sınıf Sınıf Rapor",
    "aksiyon": "Önerilen Adımlar",
}

_VELI_TAKIP_SISTEM = f"""Sen {PANEL_NAME} veli iletişim koordinatörüsün.
Veli paneli görüntüleme verisini sınıf sınıf özetlersin.
Her sınıf için giriş yapmayan, okumayan ve güncel velileri net listele.
Öğrenci adı ve veli adını birlikte yaz. Veri uydurma.
JSON:
{{
  "ozet": "Kurum geneli 2-4 cümle özet",
  "sinif_sinif": "Her sınıf ayrı paragraf; başlık olarak sınıf adını yaz (örn. 5/A). Giriş yok / okunmamış / güncel listeleri madde madde",
  "aksiyon": "Aranacak veya hatırlatılacak veliler, öncelik sırasıyla"
}}"""


def _fallback_veli_takip(veri: dict) -> AiAnalizSonuc:
    siniflar = veri.get("siniflar") or []
    toplam_giris_yok = sum(s.get("giris_yok_sayisi", 0) for s in siniflar)
    toplam_eksik = sum(s.get("eksik_sayisi", 0) for s in siniflar)
    toplam_guncel = sum(s.get("guncel_sayisi", 0) for s in siniflar)

    ozet = (
        f"{len(siniflar)} sınıfta veli takibi incelendi. "
        f"{toplam_giris_yok} veli henüz panele girmemiş, "
        f"{toplam_eksik} velide okunmamış içerik var, "
        f"{toplam_guncel} veli güncel."
    )

    sinif_metinleri: list[str] = []
    aksiyon_satirlar: list[str] = []

    for blok in siniflar:
        satirlar = [f"{blok['sinif']} ({blok['toplam']} öğrenci)"]
        if blok.get("veli_yok"):
            satirlar.append(
                "Veli hesabı yok: " + ", ".join(blok["veli_yok"][:12])
                + (f" (+{len(blok['veli_yok']) - 12})" if len(blok["veli_yok"]) > 12 else "")
            )
        if blok.get("giris_yok"):
            satirlar.append(
                "Henüz giriş yok: " + ", ".join(blok["giris_yok"][:15])
                + (f" (+{len(blok['giris_yok']) - 15})" if len(blok["giris_yok"]) > 15 else "")
            )
            for etiket in blok["giris_yok"][:5]:
                aksiyon_satirlar.append(f"• {blok['sinif']}: {etiket} — acil aranmalı")
        if blok.get("eksik"):
            satirlar.append(
                "Okunmamış içerik: " + ", ".join(blok["eksik"][:15])
                + (f" (+{len(blok['eksik']) - 15})" if len(blok["eksik"]) > 15 else "")
            )
        if blok.get("guncel"):
            satirlar.append(f"Güncel: {blok['guncel_sayisi']} veli")
        sinif_metinleri.append("\n".join(satirlar))

    return AiAnalizSonuc(
        baslik="Veli Takip Zekası · Sınıf Raporu",
        tur="veli_takip",
        bolumler=[
            AiAnalizBolum("Genel Durum", ozet, "notr"),
            AiAnalizBolum(
                "Sınıf Sınıf Rapor",
                "\n\n".join(sinif_metinleri) or "Aktif sınıf bulunamadı.",
                "notr",
            ),
            AiAnalizBolum(
                "Önerilen Adımlar",
                "\n".join(aksiyon_satirlar[:20])
                or "Öncelikli müdahale gerektiren veli yok.",
                "aksiyon",
            ),
        ],
        yapay_zeka=False,
        meta={"sinif_sayisi": len(siniflar)},
    )


def veli_takip_zekasi_raporu(
    user: User,
    *,
    yenile: bool = False,
) -> AiAnalizSonuc:
    hafta = localdate().isocalendar()[1]
    anahtar = f"veli_takip:w{hafta}"

    def uret():
        from takip.veli_goruntuleme_service import sinif_bazli_veli_takip_verisi

        veri = sinif_bazli_veli_takip_verisi()
        llm = ai_json_uret(
            system=_VELI_TAKIP_SISTEM,
            user_prompt=f"Veli takip verisi:\n{baglam_json(veri)}",
            max_tokens=2500,
        )
        if llm:
            return AiAnalizSonuc(
                baslik="Veli Takip Zekası · Sınıf Raporu",
                tur="veli_takip",
                bolumler=_llm_bolumleri(llm, _VELI_TAKIP_ETIKET),
                yapay_zeka=True,
                meta={"sinif_sayisi": veri.get("toplam_sinif", 0)},
            )
        return _fallback_veli_takip(veri)

    return _analiz_getir(
        tur=AiUretimKaydi.Tur.VELI_TAKIP,
        anahtar=anahtar,
        uretici=uret,
        user=user,
        yenile=yenile,
    )


_DENEME_ETIKET = {
    "ozet": "Genel Tablo",
    "brans_analizi": "Branş Analizi",
    "sinif_ozeti": "Sınıf Özeti",
    "etut_onerileri": "Etüt Önerileri",
    "risk_ve_firsatlar": "Risk ve Fırsatlar",
}

_DENEME_SISTEM = f"""Sen {PANEL_NAME} ölçme-değerlendirme uzmanısın.
Deneme sonuçlarını branş bazında yorumla. Veri uydurma.
JSON:
{{
  "ozet": "Sınıf geneli 2-3 cümle",
  "brans_analizi": "Türkçe/Mat/Fen/Sos/İng zayıf-güçlü branşlar",
  "sinif_ozeti": "Üst ve destek gerektiren gruplar",
  "etut_onerileri": "Somut etüt planı önerileri",
  "risk_ve_firsatlar": "Acil müdahale gereken alanlar"
}}"""


def deneme_zekasi_analizi(
    user: User,
    deneme,
    sonuclar,
    *,
    yenile: bool = False,
) -> AiAnalizSonuc:
    anahtar = f"deneme:{deneme.id}"

    def uret():
        baglam = deneme_baglam(deneme, sonuclar)
        llm = ai_json_uret(
            system=_DENEME_SISTEM,
            user_prompt=f"Deneme verisi:\n{baglam_json(baglam)}",
            max_tokens=2200,
        )
        if llm:
            return AiAnalizSonuc(
                baslik=f"{deneme.ad} · Deneme Zekası",
                tur="deneme_analiz",
                bolumler=_llm_bolumleri(llm, _DENEME_ETIKET),
                yapay_zeka=True,
            )

        ogrenci_s = baglam["deneme"]["ogrenci_sayisi"]
        return AiAnalizSonuc(
            baslik=f"{deneme.ad} · Deneme Zekası",
            tur="deneme_analiz",
            bolumler=[
                AiAnalizBolum(
                    "Genel Tablo",
                    f"{ogrenci_s} öğrencinin sonuçları değerlendirildi.",
                    "notr",
                ),
                AiAnalizBolum(
                    "Etüt Önerileri",
                    "Zayıf branşlar için hedefli etüt grupları oluşturulmalı.",
                    "aksiyon",
                ),
            ],
            yapay_zeka=False,
        )

    return _analiz_getir(
        tur=AiUretimKaydi.Tur.DENEME_ANALIZ,
        anahtar=anahtar,
        uretici=uret,
        user=user,
        yenile=yenile,
    )


_REHBERLIK_ETIKET = {
    "ozet": "Görüşme Özeti",
    "temalar": "Tespit Edilen Temalar",
    "takip_maddeleri": "Takip Maddeleri",
    "oneri": "Profesyonel Öneri",
}

_REHBERLIK_SISTEM = f"""Sen {PANEL_NAME} rehberlik uzmanısın.
Görüşme kaydını yapılandırılmış özet haline getir. Karar verme — sadece özetle ve takip öner.
JSON:
{{
  "ozet": "Görüşmenin 2-4 cümle özeti",
  "temalar": "Ana temalar madde madde",
  "takip_maddeleri": "Yapılacaklar / takip",
  "oneri": "Rehber öğretmen için kısa öneri"
}}"""


def rehberlik_gorusme_ozeti(
    gorusme: OgrenciGorusmesi,
    *,
    user: User | None = None,
    yenile: bool = False,
) -> AiAnalizSonuc:
    anahtar = f"gorusme:{gorusme.id}"

    def uret():
        veri = {
            "talebe": gorusme.talebe.ad_soyad,
            "tur": gorusme.tur.ad,
            "tarih": gorusme.tarih.isoformat(),
            "ozet": gorusme.ozet,
            "detay": (gorusme.detay or "")[:2000],
            "kararlar": (gorusme.kararlar or "")[:1000],
            "yapilacaklar": gorusme.yapilacaklar or [],
            "genel_durum": gorusme.get_genel_durum_display(),
        }
        llm = ai_json_uret(
            system=_REHBERLIK_SISTEM,
            user_prompt=f"Görüşme kaydı:\n{baglam_json(veri)}",
        )
        if llm:
            return AiAnalizSonuc(
                baslik=f"{gorusme.tur.ad} · AI Özet",
                tur="rehberlik_ozet",
                bolumler=_llm_bolumleri(llm, _REHBERLIK_ETIKET),
                yapay_zeka=True,
            )

        return AiAnalizSonuc(
            baslik=f"{gorusme.tur.ad} · Özet",
            tur="rehberlik_ozet",
            bolumler=[
                AiAnalizBolum("Görüşme Özeti", gorusme.ozet, "notr"),
                AiAnalizBolum(
                    "Takip Maddeleri",
                    gorusme.kararlar or "Takip maddesi kaydedilmemiş.",
                    "aksiyon",
                ),
            ],
            yapay_zeka=False,
        )

    return _analiz_getir(
        tur=AiUretimKaydi.Tur.REHBERLIK_OZET,
        anahtar=anahtar,
        uretici=uret,
        user=user,
        yenile=yenile,
    )


_KURUM_ETIKET = {
    "kurum_ozeti": "Kurum Özeti",
    "oncelikli_talebeler": "Öncelikli Talebeler",
    "sinif_analizi": "Sınıf Analizi",
    "mudahale_onerileri": "Kurumsal Öneriler",
}

_KURUM_SISTEM = f"""Sen {PANEL_NAME} eğitim kurumu danışmanısın.
Kurum geneli metrikleri yorumla; somut idari öneriler sun.
JSON:
{{
  "kurum_ozeti": "Genel tablo 2-4 cümle",
  "oncelikli_talebeler": "Risk adayları hakkında yorum",
  "sinif_analizi": "Sınıf dağılımı yorumu",
  "mudahale_onerileri": "Kurumsal aksiyon önerileri"
}}"""


def kurum_zekasi_ozet(
    user: User,
    *,
    yenile: bool = False,
) -> AiAnalizSonuc:
    hafta = localdate().isocalendar()[1]
    anahtar = f"kurum:{user.id}:w{hafta}"

    def uret():
        baglam = kurum_baglam(user)
        llm = ai_json_uret(
            system=_KURUM_SISTEM,
            user_prompt=f"Kurum verisi:\n{baglam_json(baglam)}",
            max_tokens=1800,
        )
        if llm:
            return AiAnalizSonuc(
                baslik="Kurum Zekası",
                tur="kurum_zekasi",
                bolumler=_llm_bolumleri(llm, _KURUM_ETIKET),
                yapay_zeka=True,
                meta={"risk_adaylari": baglam.get("risk_adaylari", [])},
            )

        risk = baglam.get("risk_adaylari") or []
        risk_metin = "\n".join(
            f"• {r['ad_soyad']} ({r['sinif']}) — skor {r['skor']}"
            for r in risk[:5]
        ) or "Belirgin risk adayı yok."

        return AiAnalizSonuc(
            baslik="Kurum Zekası",
            tur="kurum_zekasi",
            bolumler=[
                AiAnalizBolum(
                    "Kurum Özeti",
                    f"Yetkiniz dahilinde {baglam['talebe_sayisi']} talebe, "
                    f"{baglam['aktif_zimmet']} aktif kitap zimmeti.",
                    "notr",
                ),
                AiAnalizBolum("Öncelikli Talebeler", risk_metin, "dikkat"),
            ],
            yapay_zeka=False,
            meta={"risk_adaylari": risk},
        )

    return _analiz_getir(
        tur=AiUretimKaydi.Tur.KURUM_ZEKASI,
        anahtar=anahtar,
        uretici=uret,
        user=user,
        yenile=yenile,
    )


def mudahale_oneri_listesi(user: User) -> list[dict[str, Any]]:
    """Proaktif müdahale adayları — dashboard kartı için."""
    adaylar = _mudahale_adaylari(user, limit=12)
    for aday in adaylar:
        talebe = Talebe.objects.filter(pk=aday["talebe_id"]).first()
        if talebe:
            aday["oneriler"] = _mudahale_metni_uret(
                talebe, aday["skor"], aday.get("nedenler") or []
            ).split("\n")
    return adaylar


def soru_takip_insight(
    user: User,
    talebe: Talebe | None = None,
    *,
    yenile: bool = False,
) -> AiAnalizSonuc:
    if talebe:
        anahtar = f"soru:talebe:{talebe.id}:{localdate().isocalendar()[1]}"
        baslik = f"{talebe.ad_soyad} · Soru Takip"
    else:
        anahtar = f"soru:kurum:{user.id}:{localdate().isocalendar()[1]}"
        baslik = "Soru Takip İçgörüsü"

    def uret():
        if talebe:
            baglam = talebe_zengin_baglam(talebe)
            soru = baglam["soru_takip"]
        else:
            qs = yetkili_talebeler(user)
            soru = {"kurum_talebe": qs.count()}

        llm = ai_json_uret(
            system="Günlük soru takip verisini yorumla. JSON: ozet, trend, oneri",
            user_prompt=baglam_json({"soru": soru}),
        )
        if llm:
            etiket = {"ozet": "Özet", "trend": "Trend", "oneri": "Öneri"}
            return AiAnalizSonuc(
                baslik=baslik,
                tur="soru_takip",
                bolumler=_llm_bolumleri(llm, etiket),
                yapay_zeka=True,
            )

        if talebe:
            ay = talebe_zengin_baglam(talebe)["soru_takip"]["bu_ay"]
            icerik = f"Bu ay {ay.get('toplam_soru', 0)} soru, net {ay.get('toplam_net', 0)}."
        else:
            icerik = "Kurum geneli soru takip özeti için talebe detayına bakın."
        return AiAnalizSonuc(
            baslik=baslik,
            tur="soru_takip",
            bolumler=[AiAnalizBolum("Özet", icerik, "notr")],
            yapay_zeka=False,
        )

    return _analiz_getir(
        tur=AiUretimKaydi.Tur.SORU_TAKIP,
        anahtar=anahtar,
        uretici=uret,
        user=user,
        yenile=yenile,
    )
