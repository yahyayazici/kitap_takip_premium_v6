"""KTT rapor analizi — istatistik derleme, yapay zeka ve yedek metin."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from takip.ktt_analiz_llm import ktt_analiz_llm_aktif_mi, ktt_analiz_llm_uret
from takip.models import KttSinav, KttSonucu, Talebe


@dataclass
class KttAnalizBolum:
    baslik: str
    icerik: str
    ton: str = "notr"


@dataclass
class KttAnalizSonuc:
    baslik: str
    tur: str
    bolumler: list[KttAnalizBolum] = field(default_factory=list)
    yapay_zeka: bool = False
    uyari: str = ""

    @property
    def tam_metin(self) -> str:
        parcalar = [f"{b.baslik}\n{b.icerik}" for b in self.bolumler if b.icerik.strip()]
        return "\n\n".join(parcalar)


_BOLUM_ETIKETLERI = {
    "ozet": "Genel Tablo",
    "olcum_bulgulari": "Güçlü Konular",
    "pedagojik_yorum": "Geliştirilmesi Gereken Konular",
    "risk_ve_firsatlar": "Risk Alanları",
    "mudahale_onerileri": "Ne Yapmalı?",
    "veli_iletisimi": "Veli İletişimi",
}

_BOLUM_TONLARI = {
    "ozet": "notr",
    "olcum_bulgulari": "guclu",
    "pedagojik_yorum": "zayif",
    "risk_ve_firsatlar": "dikkat",
    "mudahale_onerileri": "aksiyon",
    "veli_iletisimi": "notr",
}

_BASLIK_TONLARI = {
    "Genel Tablo": "notr",
    "Güçlü Konular": "guclu",
    "Geliştirilmesi Gereken Konular": "zayif",
    "Zayıf Konular (Sınıf Geneli)": "zayif",
    "Güçlü Performanslar": "guclu",
    "Ne Yapmalı?": "aksiyon",
    "Risk Alanları": "dikkat",
    "Sınıf İçin Öneri": "dikkat",
    "Destek Gerektiren Öğrenciler": "zayif",
    "Veli İletişimi": "notr",
}


def _float(deger) -> float:
    if deger is None:
        return 0.0
    if isinstance(deger, Decimal):
        return float(deger)
    return float(deger)


def _sonuc_listesi(sonuclar) -> list[KttSonucu]:
    if isinstance(sonuclar, list):
        return sonuclar
    return list(sonuclar)


def _puan_bantlari(puanlar: list[float]) -> dict[str, int]:
    bantlar = {"ust": 0, "iyi": 0, "orta": 0, "destek": 0}
    for puan in puanlar:
        if puan >= 85:
            bantlar["ust"] += 1
        elif puan >= 70:
            bantlar["iyi"] += 1
        elif puan >= 50:
            bantlar["orta"] += 1
        else:
            bantlar["destek"] += 1
    return bantlar


def _genis_istatistik(sonuclar: list[KttSonucu]) -> dict[str, Any]:
    if not sonuclar:
        return {}

    puanlar = [_float(s.puan) for s in sonuclar]
    netler = [_float(s.net) for s in sonuclar]
    dogrular = [int(s.dogru or 0) for s in sonuclar]
    yanlislari = [int(s.yanlis or 0) for s in sonuclar]
    boslar = [int(s.bos or 0) for s in sonuclar]
    soru = sonuclar[0].ktt.soru_sayisi if sonuclar else 0

    ort_d = round(statistics.mean(dogrular), 2) if dogrular else 0
    ort_y = round(statistics.mean(yanlislari), 2) if yanlislari else 0
    ort_b = round(statistics.mean(boslar), 2) if boslar else 0

    veri: dict[str, Any] = {
        "ogrenci_sayisi": len(sonuclar),
        "ortalama_puan": round(statistics.mean(puanlar), 2),
        "ortalama_net": round(statistics.mean(netler), 2),
        "medyan_puan": round(statistics.median(puanlar), 2),
        "en_yuksek_puan": round(max(puanlar), 2),
        "en_dusuk_puan": round(min(puanlar), 2),
        "puan_std_sapma": round(statistics.pstdev(puanlar), 2) if len(puanlar) > 1 else 0,
        "ortalama_dogru": ort_d,
        "ortalama_yanlis": ort_y,
        "ortalama_bos": ort_b,
        "bos_orani_yuzde": round((ort_b / soru * 100), 1) if soru else 0,
        "yanlis_orani_yuzde": round((ort_y / soru * 100), 1) if soru else 0,
        "puan_bantlari": _puan_bantlari(puanlar),
    }

    sirali = sorted(sonuclar, key=lambda s: (_float(s.puan), _float(s.net)), reverse=True)
    veri["ust_performans"] = [
        {
            "talebe": s.talebe.ad_soyad,
            "sinif": str(s.talebe.sinif_sube or "—"),
            "puan": _float(s.puan),
            "net": _float(s.net),
        }
        for s in sirali[:3]
    ]
    veri["destek_gerektiren"] = [
        {
            "talebe": s.talebe.ad_soyad,
            "sinif": str(s.talebe.sinif_sube or "—"),
            "puan": _float(s.puan),
            "net": _float(s.net),
            "bos": int(s.bos or 0),
        }
        for s in sorted(sonuclar, key=lambda s: _float(s.puan))[:3]
    ]
    return veri


def _sinif_kirilimi(sonuclar: list[KttSonucu]) -> list[dict[str, Any]]:
    gruplar: dict[str, list[float]] = {}
    for sonuc in sonuclar:
        anahtar = str(sonuc.talebe.sinif_sube or sonuc.ktt.sinif_goster or "Belirsiz")
        gruplar.setdefault(anahtar, []).append(_float(sonuc.puan))

    satirlar = []
    for sinif, puanlar in sorted(gruplar.items()):
        satirlar.append(
            {
                "sinif": sinif,
                "ogrenci": len(puanlar),
                "ortalama_puan": round(statistics.mean(puanlar), 2),
            }
        )
    return satirlar


def _ders_kirilimi(sonuclar: list[KttSonucu]) -> list[dict[str, Any]]:
    gruplar: dict[str, list[float]] = {}
    for sonuc in sonuclar:
        ders = sonuc.ktt.ders.ad if sonuc.ktt.ders_id else "—"
        gruplar.setdefault(ders, []).append(_float(sonuc.puan))

    return [
        {
            "ders": ders,
            "kayit": len(puanlar),
            "ortalama_puan": round(statistics.mean(puanlar), 2),
        }
        for ders, puanlar in sorted(gruplar.items())
    ]


def _sinav_kirilimi(sonuclar: list[KttSonucu]) -> list[dict[str, Any]]:
    gruplar: dict[int, list[KttSonucu]] = {}
    for sonuc in sonuclar:
        gruplar.setdefault(sonuc.ktt_id, []).append(sonuc)

    satirlar = []
    for _, kayitlar in sorted(
        gruplar.items(),
        key=lambda item: item[1][0].ktt.sinav_tarihi,
        reverse=True,
    ):
        ktt = kayitlar[0].ktt
        puanlar = [_float(s.puan) for s in kayitlar]
        satirlar.append(
            {
                "ktt": ktt.ad,
                "ders": ktt.ders.ad if ktt.ders_id else "—",
                "tarih": ktt.sinav_tarihi.isoformat(),
                "puan": round(statistics.mean(puanlar), 2),
                "net": round(statistics.mean([_float(s.net) for s in kayitlar]), 2),
            }
        )
    return satirlar


def _ogrenci_satirlari(sonuclar: list[KttSonucu], *, limit: int = 40) -> list[dict[str, Any]]:
    sirali = sorted(sonuclar, key=lambda s: (_float(s.puan), _float(s.net)), reverse=True)
    satirlar = []
    for sira, sonuc in enumerate(sirali[:limit], start=1):
        satirlar.append(
            {
                "sira": sira,
                "talebe": sonuc.talebe.ad_soyad,
                "sinif": str(sonuc.talebe.sinif_sube or sonuc.ktt.sinif_goster or "—"),
                "ktt": sonuc.ktt.ad,
                "ders": sonuc.ktt.ders.ad if sonuc.ktt.ders_id else "—",
                "tarih": sonuc.ktt.sinav_tarihi.isoformat(),
                "dogru": int(sonuc.dogru or 0),
                "yanlis": int(sonuc.yanlis or 0),
                "bos": int(sonuc.bos or 0),
                "net": _float(sonuc.net),
                "puan": _float(sonuc.puan),
            }
        )
    return satirlar


def _llm_bolumleri(llm: dict[str, str]) -> list[KttAnalizBolum]:
    bolumler: list[KttAnalizBolum] = []
    for anahtar, baslik in _BOLUM_ETIKETLERI.items():
        icerik = llm.get(anahtar, "").strip()
        if icerik:
            bolumler.append(
                KttAnalizBolum(
                    baslik=baslik,
                    icerik=icerik,
                    ton=_BOLUM_TONLARI.get(anahtar, "notr"),
                )
            )
    return bolumler


def _kayit_sirala(sonuclar: list[KttSonucu]) -> list[KttSonucu]:
    return sorted(
        sonuclar,
        key=lambda s: (s.ktt.sinav_tarihi, s.ktt.ad),
        reverse=True,
    )


def _konu_satir(sonuc: KttSonucu) -> str:
    ders = sonuc.ktt.ders.ad if sonuc.ktt.ders_id else "—"
    tarih = sonuc.ktt.sinav_tarihi.strftime("%d.%m.%Y")
    return (
        f"• {ders} — «{sonuc.ktt.ad}» ({tarih}): "
        f"{_fmt(sonuc.puan)} puan, {_fmt(sonuc.net)} net "
        f"(D:{int(sonuc.dogru or 0)} Y:{int(sonuc.yanlis or 0)} B:{int(sonuc.bos or 0)})"
    )


def _ders_bazli_konu_ozet(sonuclar: list[KttSonucu]) -> list[dict[str, Any]]:
    gruplar: dict[str, list[KttSonucu]] = {}
    for sonuc in sonuclar:
        ders = sonuc.ktt.ders.ad if sonuc.ktt.ders_id else "Belirsiz"
        gruplar.setdefault(ders, []).append(sonuc)

    satirlar = []
    for ders, kayitlar in sorted(gruplar.items()):
        puanlar = [_float(s.puan) for s in kayitlar]
        en_zayif = min(kayitlar, key=lambda s: _float(s.puan))
        en_guclu = max(kayitlar, key=lambda s: _float(s.puan))
        satirlar.append(
            {
                "ders": ders,
                "ktt_sayisi": len(kayitlar),
                "ortalama_puan": round(statistics.mean(puanlar), 2),
                "en_guclu_konu": en_guclu.ktt.ad,
                "en_guclu_puan": _float(en_guclu.puan),
                "en_zayif_konu": en_zayif.ktt.ad,
                "en_zayif_puan": _float(en_zayif.puan),
                "konular": [
                    {"ad": s.ktt.ad, "puan": _float(s.puan), "net": _float(s.net)}
                    for s in sorted(kayitlar, key=lambda x: _float(x.puan), reverse=True)
                ],
            }
        )
    return sorted(satirlar, key=lambda x: x["ortalama_puan"])


def _konu_onerisi(sonuc: KttSonucu) -> str:
    puan = _float(sonuc.puan)
    ders = sonuc.ktt.ders.ad if sonuc.ktt.ders_id else "—"
    konu = sonuc.ktt.ad
    if puan >= 85:
        return f"«{konu}» ({ders}): Derinleştirici sorularla seviye korunmalı."
    if puan >= 70:
        return f"«{konu}» ({ders}): Kısa tekrar ve hedefli soru çözümü yeterli."
    if puan >= 50:
        return f"«{konu}» ({ders}): Konu tekrarı + etüt hocası eşliğinde soru çözümü planlanmalı."
    return f"«{konu}» ({ders}): Acil etüt; temel kavram tekrarı ve birebir takip gerekli."


def _somut_bireysel_bolumler(talebe: Talebe, sonuclar: list[KttSonucu]) -> list[KttAnalizBolum]:
    kayitlar = _kayit_sirala(sonuclar)
    ders_ozet = _ders_bazli_konu_ozet(kayitlar)
    genis = _genis_istatistik(kayitlar)

    esik = 70.0
    zayif_kayitlar = [s for s in sorted(kayitlar, key=lambda s: _float(s.puan)) if _float(s.puan) < esik]
    if not zayif_kayitlar:
        zayif_kayitlar = sorted(kayitlar, key=lambda s: _float(s.puan))[:2]
    guclu_kayitlar = sorted(kayitlar, key=lambda s: _float(s.puan), reverse=True)[:3]

    en_zayif_ders = ders_ozet[0]["ders"] if ders_ozet else "—"
    en_guclu_ders = ders_ozet[-1]["ders"] if ders_ozet else "—"

    guclu_metin = "\n".join(
        f"• {_konu_onerisi(s)}"
        for s in guclu_kayitlar
    )
    zayif_metin = "\n".join(
        f"• {_konu_onerisi(s)}"
        for s in zayif_kayitlar
    )
    etut_plani = "\n".join(
        f"• {_konu_onerisi(s)}"
        for s in zayif_kayitlar
    )

    return [
        KttAnalizBolum(
            baslik="Genel Tablo",
            ton="notr",
            icerik=(
                f"{talebe.ad_soyad} — {len(kayitlar)} KTT değerlendirildi, "
                f"ortalama {_fmt(genis.get('ortalama_puan'))} puan. "
                f"En güçlü alan: {en_guclu_ders}. "
                f"Öncelikli gelişim alanı: {en_zayif_ders}."
            ),
        ),
        KttAnalizBolum(
            baslik="Güçlü Konular",
            ton="guclu",
            icerik=guclu_metin or "Belirgin güçlü konu ayrımı yok; genel tablo dengeli.",
        ),
        KttAnalizBolum(
            baslik="Geliştirilmesi Gereken Konular",
            ton="zayif",
            icerik=zayif_metin or "Kritik zayıf konu görülmüyor; rutin pekiştirme yeterli.",
        ),
        KttAnalizBolum(
            baslik="Ne Yapmalı?",
            ton="aksiyon",
            icerik=etut_plani or "Mevcut seviye iyi; haftalık tekrar programı sürdürülmeli.",
        ),
    ]


def _somut_sinav_grup_bolumler(ktt: KttSinav, sonuclar: list[KttSonucu], istatistik: dict) -> list[KttAnalizBolum]:
    kayitlar = _sonuc_listesi(sonuclar)
    zayif = sorted(kayitlar, key=lambda s: _float(s.puan))[:5]
    ort = istatistik.get("ortalama_puan", 0)

    destek_liste = "\n".join(
        f"• {s.talebe.ad_soyad} — «{ktt.ad}» için {_konu_onerisi(s)}"
        for s in zayif
    )

    sinif_oneri = (
        f"{ktt.ders.ad} dersinde «{ktt.ad}» konusu sınıfça tekrar anlatılmalı; "
        f"örnek soru çözümü ve hedefli etüt planlanmalı."
        if ort < 70
        else f"«{ktt.ad}» konusunda sınıf geneli iyi; seçilmiş öğrencilerde bireysel pekiştirme yeterli."
    )

    return [
        KttAnalizBolum(
            baslik="Genel Tablo",
            ton="notr",
            icerik=(
                f"«{ktt.ad}» ({ktt.ders.ad}) — {istatistik.get('ogrenci_sayisi', 0)} öğrenci, "
                f"sınıf ortalaması {_fmt(ort)} puan."
            ),
        ),
        KttAnalizBolum(
            baslik="Sınıf İçin Öneri",
            ton="dikkat",
            icerik=sinif_oneri,
        ),
        KttAnalizBolum(
            baslik="Destek Gerektiren Öğrenciler",
            ton="zayif",
            icerik=destek_liste or "Tüm öğrenciler yeterli düzeyde.",
        ),
    ]


def _somut_kohort_bolumler(
    sonuclar: list[KttSonucu],
    filtre: dict,
    istatistik: dict,
) -> list[KttAnalizBolum]:
    ders_ozet = _ders_bazli_konu_ozet(sonuclar)

    zayif_kayitlar = sorted(sonuclar, key=lambda s: _float(s.puan))[:8]
    guclu_kayitlar = sorted(sonuclar, key=lambda s: _float(s.puan), reverse=True)[:5]

    zayif_konular: dict[str, list[float]] = {}
    for sonuc in sonuclar:
        anahtar = f"{sonuc.ktt.ders.ad if sonuc.ktt.ders_id else '—'} · «{sonuc.ktt.ad}»"
        zayif_konular.setdefault(anahtar, []).append(_float(sonuc.puan))
    konu_ortalama = sorted(
        ((k, statistics.mean(v)) for k, v in zayif_konular.items()),
        key=lambda x: x[1],
    )
    zayif_konu_liste = "\n".join(
        f"• {ad}: ortalama {_fmt(ort)} puan — sınıf etüdü ve konu tekrarı önerilir."
        for ad, ort in konu_ortalama[:5]
    )
    guclu_liste = "\n".join(
        f"• {s.talebe.ad_soyad}: {_konu_onerisi(s)}"
        for s in guclu_kayitlar
    )
    destek_liste = "\n".join(
        f"• {s.talebe.ad_soyad}: {_konu_onerisi(s)}"
        for s in zayif_kayitlar
    )

    en_zayif_ders = ders_ozet[0]["ders"] if ders_ozet else "—"
    toplam = istatistik.get("toplam_sonuc") or len(sonuclar)

    return [
        KttAnalizBolum(
            baslik="Genel Tablo",
            ton="notr",
            icerik=(
                f"{toplam} KTT sonucu, ortalama {_fmt(istatistik.get('ortalama_puan'))} puan. "
                f"Öncelikli gelişim alanı: {en_zayif_ders}."
            ),
        ),
        KttAnalizBolum(
            baslik="Zayıf Konular (Sınıf Geneli)",
            ton="zayif",
            icerik=zayif_konu_liste or "—",
        ),
        KttAnalizBolum(
            baslik="Güçlü Performanslar",
            ton="guclu",
            icerik=guclu_liste or "—",
        ),
        KttAnalizBolum(
            baslik="Ne Yapmalı?",
            ton="aksiyon",
            icerik=destek_liste or "Genel tablo yeterli; rutin pekiştirme devam etmeli.",
        ),
    ]


def _fallback_uyari() -> str:
    return ""


def _fallback_sinav_grup(ktt: KttSinav, istatistik: dict[str, Any], sonuclar: list[KttSonucu]) -> KttAnalizSonuc:
    return KttAnalizSonuc(
        baslik=f"{ktt.ad} · Grup Değerlendirmesi",
        tur="sinav_grup",
        bolumler=_somut_sinav_grup_bolumler(ktt, sonuclar, istatistik),
        yapay_zeka=False,
        uyari=_fallback_uyari(),
    )


def _fallback_rapor_bireysel(talebe: Talebe, sonuclar: list[KttSonucu]) -> KttAnalizSonuc:
    return KttAnalizSonuc(
        baslik=f"{talebe.ad_soyad} · Bireysel KTT Değerlendirmesi",
        tur="rapor_bireysel",
        bolumler=_somut_bireysel_bolumler(talebe, sonuclar),
        yapay_zeka=False,
        uyari=_fallback_uyari(),
    )


def _fallback_rapor_grup(sonuclar: list[KttSonucu], filtre: dict, istatistik: dict) -> KttAnalizSonuc:
    return KttAnalizSonuc(
        baslik="KTT Kohort Değerlendirmesi",
        tur="rapor_grup",
        bolumler=_somut_kohort_bolumler(sonuclar, filtre, istatistik),
        yapay_zeka=False,
        uyari=_fallback_uyari(),
    )


def _fmt(deger) -> str:
    if deger in (None, "", "—"):
        return "—"
    try:
        sayi = float(deger)
        if sayi == int(sayi):
            return str(int(sayi))
        return f"{sayi:.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(deger)


def ktt_sinav_grup_analizi(ktt: KttSinav, sonuclar, ozet: dict) -> KttAnalizSonuc:
    kayitlar = _sonuc_listesi(sonuclar)
    if not kayitlar:
        return KttAnalizSonuc(
            baslik=f"{ktt.ad} · Değerlendirme",
            tur="sinav_grup",
            bolumler=[
                KttAnalizBolum(
                    baslik="Not",
                    icerik="Bu KTT için henüz sonuç girilmediğinden akademik değerlendirme üretilememiştir.",
                )
            ],
        )

    istatistik = _genis_istatistik(kayitlar)
    istatistik.update(
        {
            "ozet_kart": ozet,
            "sinif_kirilimi": _sinif_kirilimi(kayitlar),
        }
    )

    payload = {
        "sinav": {
            "ad": ktt.ad,
            "ders": ktt.ders.ad if ktt.ders_id else "—",
            "sinif": ktt.sinif_goster,
            "tarih": ktt.sinav_tarihi.isoformat(),
            "soru_sayisi": ktt.soru_sayisi,
            "aciklama": (ktt.aciklama or "").strip(),
        },
        "istatistik": istatistik,
        "ogrenci_sonuclari": _ogrenci_satirlari(kayitlar, limit=50),
    }

    llm = ktt_analiz_llm_uret(payload, tur="sinav_grup")
    if llm:
        return KttAnalizSonuc(
            baslik=f"{ktt.ad} · Akademik Değerlendirme",
            tur="sinav_grup",
            bolumler=_llm_bolumleri(llm),
            yapay_zeka=True,
        )

    return _fallback_sinav_grup(ktt, istatistik, kayitlar)


def ktt_rapor_analizi(
    sonuclar,
    istatistik: dict,
    filtre: dict,
    filtre_etiketleri: dict,
    *,
    talebe: Talebe | None = None,
) -> KttAnalizSonuc:
    kayitlar = _sonuc_listesi(sonuclar)
    if not kayitlar:
        return KttAnalizSonuc(
            baslik="KTT Değerlendirmesi",
            tur="rapor_grup",
            bolumler=[
                KttAnalizBolum(
                    baslik="Not",
                    icerik="Seçilen filtrelerde sonuç kaydı bulunmadığından değerlendirme yapılamamıştır.",
                )
            ],
        )

    genis = _genis_istatistik(kayitlar)
    genis.update(
        {
            "filtre_ozet": istatistik,
            "sinif_kirilimi": _sinif_kirilimi(kayitlar),
            "ders_kirilimi": _ders_kirilimi(kayitlar),
        }
    )

    bireysel = talebe is not None or bool(filtre.get("talebe"))
    if bireysel and kayitlar:
        hedef = talebe or kayitlar[0].talebe
        payload = {
            "ogrenci": {
                "ad_soyad": hedef.ad_soyad,
                "sinif": str(hedef.sinif_sube or "—"),
                "talebe_no": hedef.talebe_no or "",
            },
            "filtre": filtre_etiketleri,
            "istatistik": genis,
            "ktt_gecmisi": _sinav_kirilimi(kayitlar),
            "detay_kayitlar": _ogrenci_satirlari(kayitlar, limit=30),
        }
        llm = ktt_analiz_llm_uret(payload, tur="rapor_bireysel")
        if llm:
            return KttAnalizSonuc(
                baslik=f"{hedef.ad_soyad} · Bireysel Akademik Değerlendirme",
                tur="rapor_bireysel",
                bolumler=_llm_bolumleri(llm),
                yapay_zeka=True,
            )
        return _fallback_rapor_bireysel(hedef, kayitlar)

    payload = {
        "filtre": filtre_etiketleri,
        "istatistik": genis,
        "ders_kirilimi": _ders_kirilimi(kayitlar),
        "sinif_kirilimi": _sinif_kirilimi(kayitlar),
        "ornek_kayitlar": _ogrenci_satirlari(kayitlar, limit=40),
    }
    llm = ktt_analiz_llm_uret(payload, tur="rapor_grup")
    if llm:
        return KttAnalizSonuc(
            baslik="KTT Kohort · Akademik Değerlendirme",
            tur="rapor_grup",
            bolumler=_llm_bolumleri(llm),
            yapay_zeka=True,
        )

    return _fallback_rapor_grup(kayitlar, filtre_etiketleri, istatistik)


def ktt_analiz_durumu() -> dict[str, Any]:
    from django.conf import settings

    aktif = ktt_analiz_llm_aktif_mi()
    if aktif:
        return {"aktif": True, "etiket": "Yapay Zeka", "uyari": ""}
    if not getattr(settings, "OPENAI_API_KEY", "").strip():
        return {"aktif": False, "etiket": "Otomatik Analiz", "uyari": ""}
    return {"aktif": False, "etiket": "Otomatik Analiz", "uyari": ""}
