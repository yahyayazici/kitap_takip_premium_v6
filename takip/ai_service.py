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
    ai_json_istek,
    ai_llm_aktif_mi,
    ai_platform_aktif_mi,
    onbellekten_al,
    onbellege_yaz,
    yenile_izinli_mi,
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
    "dayanaklar": "notr",
    "belirsizlikler": "dikkat",
}

_ORTAK_ETIKET = {
    "dayanaklar": "Dayanaklar (Kullanılan Veriler)",
    "belirsizlikler": "Belirsizlikler ve Eksik Veri",
}


def ai_durumu() -> dict[str, str]:
    if ai_llm_aktif_mi():
        return {"aktif": True, "etiket": "Yapay Zeka", "uyari": ""}
    if ai_platform_aktif_mi():
        return {"aktif": False, "etiket": "Akıllı Analiz", "uyari": ""}
    return {"aktif": False, "etiket": "Kapalı", "uyari": "AI platformu devre dışı."}


def _veri_kapsami(baglam: dict[str, Any]) -> dict[str, Any]:
    """Boş gelen veri alanlarını listeler — modelin eksik veriyi açıkça belirtmesi için."""
    eksik: list[str] = []
    for anahtar, deger in baglam.items():
        if deger in (None, "", [], {}):
            eksik.append(anahtar)
        elif isinstance(deger, dict):
            for alt, alt_deger in deger.items():
                if alt_deger in (None, "", [], {}):
                    eksik.append(f"{anahtar}.{alt}")
    return {"eksik_alanlar": eksik}


def _llm_istem(aciklama: str, baglam: dict[str, Any]) -> str:
    paket = {
        "rapor_tarihi": localdate().isoformat(),
        "veri_kapsami": _veri_kapsami(baglam),
        "veri": baglam,
    }
    return f"{aciklama}\n\nVERİ:\n{baglam_json(paket)}"


def _llm_uyari(hata_mesaji: str) -> str:
    if not hata_mesaji:
        return ""
    return f"Yapay zeka analizi alınamadı: {hata_mesaji} Aşağıda kural tabanlı özet gösteriliyor."


def _llm_bolumleri(llm: dict[str, str], etiketler: dict[str, str]) -> list[AiAnalizBolum]:
    bolumler: list[AiAnalizBolum] = []
    for anahtar, baslik in {**etiketler, **_ORTAK_ETIKET}.items():
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
    sinir_uyarisi = ""
    if yenile and not yenile_izinli_mi(user):
        yenile = False
        sinir_uyarisi = "Günlük yenileme sınırına ulaşıldı; kayıtlı analiz gösteriliyor."

    if ai_platform_aktif_mi():
        cached = onbellekten_al(tur, anahtar, yenile=yenile)
        if cached:
            sonuc = AiAnalizSonuc.from_dict(cached)
            if sinir_uyarisi:
                sonuc.uyari = sinir_uyarisi
            return sonuc

    sonuc = uretici()
    # Yapay zeka hatası nedeniyle üretilen yedek sonuç önbelleğe yazılmaz;
    # servis düzelince bir sonraki açılışta gerçek analiz denenir.
    if ai_platform_aktif_mi() and not (sonuc.uyari and ai_llm_aktif_mi()):
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
Öğrencinin akademik (deneme, KTT), okuma, devam, namaz ve soru takip verilerini bütüncül okursun.
Okuyucu: etüt hocası ve idareciler. Resmi ama sıcak Türkçe kullan.
Değerlendirirken:
- Deneme/KTT için tek sonuca değil eğilime bak (deneme_trend, son 3-5 kayıt); kayıt sayısı azsa bunu belirt.
- Branş bazında en zayıf ve en güçlü alanı sayıyla göster.
- Soru takibinde bu hafta ile bu ayı karşılaştır; kayıt girilmeyen günleri "çalışmadı" diye yorumlama, "kayıt yok" de.
- Risk sinyalini yalnızca veriyle destekleyebiliyorsan yaz.
JSON alanları:
- "ozet": 2-4 cümle genel tablo
- "guclu_yonler": Madde madde güçlü alanlar
- "gelisim_alanlari": Madde madde gelişim alanları
- "risk_sinyalleri": Varsa erken uyarı sinyalleri; yoksa "Veriyle desteklenen risk sinyali yok."
- "mudahale_onerileri": Somut, ölçülebilir etüt/çalışma önerileri (kim, ne sıklıkla, hangi hedef)
- "veli_mesaji": Veliye aktarılabilecek 1-2 cümle (disiplin ve rehberlik detayı yok)"""


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
        cevap = ai_json_istek(
            system=_GELISIM_SISTEM,
            user_prompt=_llm_istem("Öğrencinin bütüncül gelişim değerlendirmesini yaz.", baglam),
            alanlar=list(_GELISIM_ETIKET),
        )
        llm = cevap.veri
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
        sonuc = _fallback_gelisim(talebe, baglam)
        sonuc.uyari = _llm_uyari(cevap.hata_mesaji)
        return sonuc

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
Teknik terim (net, KTT, kazanım) kullanırsan bir kez kısaca açıkla. Suçlayıcı veya etiketleyici dil kullanma.
"dayanaklar" ve "belirsizlikler" alanlarını da veliye anlaşılır dille yaz.
JSON alanları:
- "ozet": 2-3 cümle haftalık özet
- "akademik": Deneme/KTT/soru durumu
- "aliskanliklar": Okuma ve katılım
- "veli_onerisi": Evde yapılabilecek 1-2 somut öneri"""


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

        cevap = ai_json_istek(
            system=_VELI_SISTEM,
            user_prompt=_llm_istem("Veliye bu haftanın özetini yaz.", baglam),
            alanlar=list(_VELI_ETIKET),
        )
        llm = cevap.veri
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
            uyari=_llm_uyari(cevap.hata_mesaji),
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
Öğrenci adı ve veli adını birlikte yaz. Listeleri kısaltırsan kaç kişinin dışarıda kaldığını belirt.
JSON alanları:
- "ozet": Kurum geneli 2-4 cümle özet
- "sinif_sinif": Her sınıf ayrı paragraf; başlık olarak sınıf adını yaz (örn. 5/A). Giriş yok / okunmamış / güncel listeleri madde madde
- "aksiyon": Aranacak veya hatırlatılacak veliler, öncelik sırasıyla"""


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
        cevap = ai_json_istek(
            system=_VELI_TAKIP_SISTEM,
            user_prompt=_llm_istem("Veli paneli takip raporunu sınıf sınıf yaz.", veri),
            alanlar=list(_VELI_TAKIP_ETIKET),
        )
        llm = cevap.veri
        if llm:
            return AiAnalizSonuc(
                baslik="Veli Takip Zekası · Sınıf Raporu",
                tur="veli_takip",
                bolumler=_llm_bolumleri(llm, _VELI_TAKIP_ETIKET),
                yapay_zeka=True,
                meta={"sinif_sayisi": veri.get("toplam_sinif", 0)},
            )
        sonuc = _fallback_veli_takip(veri)
        sonuc.uyari = _llm_uyari(cevap.hata_mesaji)
        return sonuc

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
    "konu_analizi": "Kazanım Analizi",
    "sinif_ozeti": "Sınıf Özeti",
    "etut_onerileri": "Etüt Önerileri",
    "risk_ve_firsatlar": "Risk ve Fırsatlar",
}

_DENEME_SISTEM = f"""Sen {PANEL_NAME} ölçme-değerlendirme uzmanısın.
Deneme sonuçlarını branş ve konu bazında yorumla. Veri uydurma.
Veride şunlar olabilir:
- sonuclar[].branslar: ders D/Y/B
- sonuclar[].kazanimlar: KonuKazanimDetay yüzde ve net (yüzde < 70 zayıf)
- sonuclar[].ktt_konular: aynı talebenin KTT konu/puan özeti
- kazanim_zayif_konular: sınıf geneli zayıf kazanımlar (ortalama yüzde)

Kazanım detayını esas al. KTT varsa yalnızca örtüşen konuları destek olarak an.
Konu adı yoksa uydurma; yalnızca verilen listeleri kullan. Kazanım detayı yoksa konu_analizi alanında bunu belirt.
Ortalama yüzdeyi verirken kaç talebenin katıldığını da yaz; az katılımlı kazanımlar için temkinli ol.
JSON alanları:
- "ozet": Sınıf geneli 2-3 cümle; kazanım varsa konu düzeyine de değin
- "brans_analizi": Türkçe/Mat/Fen/Sos/İng zayıf-güçlü branşlar (sayılarla)
- "konu_analizi": Kazanım detayından zayıf ve güçlü konular
- "sinif_ozeti": Üst ve destek gerektiren gruplar
- "etut_onerileri": Somut etüt planı — mümkünse kazanım adı, süre ve hedef ver
- "risk_ve_firsatlar": Acil müdahale gereken kazanımlar"""


def deneme_zekasi_analizi(
    user: User,
    deneme,
    sonuclar,
    *,
    yenile: bool = False,
) -> AiAnalizSonuc:
    anahtar = f"deneme:{deneme.id}:kazanim"

    def uret():
        baglam = deneme_baglam(deneme, sonuclar)
        cevap = ai_json_istek(
            system=_DENEME_SISTEM,
            user_prompt=_llm_istem("Deneme sınavının sınıf düzeyinde analizini yaz.", baglam),
            alanlar=list(_DENEME_ETIKET),
        )
        llm = cevap.veri
        if llm:
            return AiAnalizSonuc(
                baslik=f"{deneme.ad} · Deneme Zekası",
                tur="deneme_analiz",
                bolumler=_llm_bolumleri(llm, _DENEME_ETIKET),
                yapay_zeka=True,
            )

        ogrenci_s = baglam["deneme"]["ogrenci_sayisi"]
        kazanim_s = baglam["deneme"].get("kazanim_satir_sayisi") or 0
        zayif = baglam.get("kazanim_zayif_konular") or []
        zayif_metin = "\n".join(
            f"• {z['ders']} · «{z['konu']}» ortalama %{z['ortalama']:.0f} ({z['katilan']} talebe)"
            for z in zayif[:12]
        )
        bolumler = [
            AiAnalizBolum(
                "Genel Tablo",
                f"{ogrenci_s} öğrencinin branş sonuçları değerlendirildi."
                + (
                    f" {kazanim_s} kazanım satırı yüklü."
                    if kazanim_s
                    else " Kazanım detayı henüz yüklenmedi."
                ),
                "notr",
            ),
        ]
        if zayif_metin:
            bolumler.append(
                AiAnalizBolum(
                    "Kazanım Analizi",
                    zayif_metin,
                    "zayif",
                )
            )
        else:
            bolumler.append(
                AiAnalizBolum(
                    "Kazanım Analizi",
                    (
                        "Yüklenen kazanımlarda %70 altında sınıf ortalaması yok."
                        if kazanim_s
                        else "Kazanım detayı yok. KonuKazanimDetay dosyasını yükleyin."
                    ),
                    "notr",
                )
            )
        bolumler.append(
            AiAnalizBolum(
                "Etüt Önerileri",
                "Yüzdesi %70 altındaki kazanımlar için hedefli etüt grupları oluşturulmalı.",
                "aksiyon",
            )
        )
        return AiAnalizSonuc(
            baslik=f"{deneme.ad} · Deneme Zekası",
            tur="deneme_analiz",
            bolumler=bolumler,
            yapay_zeka=False,
            uyari=_llm_uyari(cevap.hata_mesaji),
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
Görüşme kaydını yapılandırılmış özet haline getir. Karar verme, tanı koyma — sadece özetle ve takip öner.
Kayıtta yazmayan duygu, neden veya aile bilgisi ekleme.
JSON alanları:
- "ozet": Görüşmenin 2-4 cümle özeti
- "temalar": Ana temalar madde madde
- "takip_maddeleri": Yapılacaklar / takip (kim, ne zaman)
- "oneri": Rehber öğretmen için kısa öneri"""


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
        cevap = ai_json_istek(
            system=_REHBERLIK_SISTEM,
            user_prompt=_llm_istem("Rehberlik görüşme kaydını özetle.", veri),
            alanlar=list(_REHBERLIK_ETIKET),
        )
        llm = cevap.veri
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
            uyari=_llm_uyari(cevap.hata_mesaji),
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
Kurum geneli metrikleri yorumla; somut idari öneriler sun. Okuyucu: kurum yöneticisi.
risk_adaylari listesindeki skor ve nedenler sistemin kural tabanlı hesabıdır; bunları olduğu gibi aktar,
yeni neden ekleme. Veri kapsamı (kaç talebenin soru kaydı var) düşükse oranları genelleme.
JSON alanları:
- "kurum_ozeti": Genel tablo 2-4 cümle
- "oncelikli_talebeler": Risk adayları hakkında yorum (ad, sınıf, skor, neden)
- "sinif_analizi": Sınıf dağılımı yorumu
- "mudahale_onerileri": Kurumsal aksiyon önerileri (sorumlu ve süre ile)"""


def kurum_zekasi_ozet(
    user: User,
    *,
    yenile: bool = False,
) -> AiAnalizSonuc:
    hafta = localdate().isocalendar()[1]
    anahtar = f"kurum:{user.id}:w{hafta}"

    def uret():
        baglam = kurum_baglam(user)
        cevap = ai_json_istek(
            system=_KURUM_SISTEM,
            user_prompt=_llm_istem("Kurum geneli durum değerlendirmesini yaz.", baglam),
            alanlar=list(_KURUM_ETIKET),
        )
        llm = cevap.veri
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
            uyari=_llm_uyari(cevap.hata_mesaji),
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
    talebeler = Talebe.objects.in_bulk(a["talebe_id"] for a in adaylar)
    for aday in adaylar:
        talebe = talebeler.get(aday["talebe_id"])
        if talebe:
            aday["oneriler"] = _mudahale_metni_uret(
                talebe, aday["skor"], aday.get("nedenler") or []
            ).split("\n")
    return adaylar


_SORU_SISTEM = f"""Sen {PANEL_NAME} ölçme-değerlendirme uzmanısın. Günlük soru takip verisini yorumlarsın.
Kayıt girilmeyen günleri "çalışmadı" diye yorumlama; "kayıt yok" de. Başarı oranını toplam soru sayısıyla birlikte ver.
JSON alanları:
- "ozet": 2-3 cümle genel durum
- "trend": Hafta/ay veya ders bazında karşılaştırma (yalnızca veride varsa)
- "oneri": Somut, ölçülebilir öneriler"""


def _kurum_soru_verisi(user: User) -> dict[str, Any]:
    """Kurum geneli soru takip içgörüsü için son 30 günün gerçek verisi."""
    from takip.soru_takip_service import rapor_ders_ozeti, rapor_istatistik, yetkili_soru_kayitlari

    bugun = localdate()
    baslangic = bugun - timedelta(days=29)
    kayitlar = yetkili_soru_kayitlari(user).filter(tarih__gte=baslangic, tarih__lte=bugun)
    hafta_kayit = kayitlar.filter(tarih__gte=bugun - timedelta(days=6))
    return {
        "donem": {"baslangic": baslangic.isoformat(), "bitis": bugun.isoformat()},
        "yetkili_talebe_sayisi": yetkili_talebeler(user).count(),
        "son_30_gun": rapor_istatistik(kayitlar),
        "son_7_gun": rapor_istatistik(hafta_kayit),
        "ders_bazinda_30_gun": rapor_ders_ozeti(kayitlar),
    }


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
            soru = _kurum_soru_verisi(user)

        cevap = ai_json_istek(
            system=_SORU_SISTEM,
            user_prompt=_llm_istem("Soru takip verisini yorumla.", {"soru": soru}),
            alanlar=["ozet", "trend", "oneri"],
        )
        llm = cevap.veri
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
            ay = soru.get("son_30_gun") or {}
            hafta = soru.get("son_7_gun") or {}
            icerik = (
                f"Son 30 günde {ay.get('talebe_sayisi', 0)}/{soru.get('yetkili_talebe_sayisi', 0)} talebe için "
                f"{ay.get('kayit_sayisi', 0)} günlük kayıt var: {ay.get('toplam_soru', 0)} soru, "
                f"başarı %{ay.get('basari_orani', 0)}. Son 7 günde {hafta.get('toplam_soru', 0)} soru."
            )
        return AiAnalizSonuc(
            baslik=baslik,
            tur="soru_takip",
            bolumler=[AiAnalizBolum("Özet", icerik, "notr")],
            yapay_zeka=False,
            uyari=_llm_uyari(cevap.hata_mesaji),
        )

    return _analiz_getir(
        tur=AiUretimKaydi.Tur.SORU_TAKIP,
        anahtar=anahtar,
        uretici=uret,
        user=user,
        yenile=yenile,
    )
