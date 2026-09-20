"""Öğrenci deneme gelişimi — trend, gelişim sıralaması, soru çözüm korelasyonu.

Bu modül mevcut deneme/soru takip verilerinin üstüne kurulur; yeni bir
soru çözüm sistemi veya deneme modeli açmaz. Grup denemeleri ile
bireysel denemeler burada da açıkça ayrı tutulur — bireysel denemeler
gelişim/trend hesaplarına dahil edilmez, öğrencinin kendi ekranında
ayrı bir liste olarak gösterilir.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils.timezone import localdate

from takip.deneme_service import BRANS_ETIKETLERI, DENEME_BRANS_DERS_MAP
from takip.models import DenemeSinavi, DenemeSonucu, Talebe

TREND_ETIKETLERI: dict[str, str] = {
    "yukseliste": "YÜKSELİŞTE",
    "duseste": "DÜŞÜŞTE",
    "dalgali": "DALGALI",
    "stabil": "STABİL",
    "yetersiz": "Yeterli deneme yok",
}

TREND_ACIKLAMALARI: dict[str, str] = {
    "yukseliste": "Son grup denemelerinde düzenli yükseliyor.",
    "duseste": "Son grup denemelerinde düzenli düşüyor.",
    "dalgali": "Denemeler arasında yüksek değişkenlik var.",
    "stabil": "Belirgin bir değişim yok.",
    "yetersiz": "Trend belirlemek için yeterli grup denemesi yok.",
}

_VARSAYILAN_TREND_ESIK: dict[str, float] = {
    "min_deneme": 3,
    "duzenli_esik": 5.0,
    "stabil_esik": 8.0,
    "dalgali_std_esik": 20.0,
}


def _trend_esik() -> dict[str, float]:
    ozel = getattr(settings, "DENEME_TREND_ESIK", {})
    esik = dict(_VARSAYILAN_TREND_ESIK)
    esik.update(ozel or {})
    return esik


def talebe_grup_deneme_gelisimi(talebe: Talebe) -> list[dict]:
    """Kronolojik (eskiden yeniye) grup deneme puan/net serisi."""
    sonuclar = (
        DenemeSonucu.objects.filter(
            talebe=talebe,
            deneme__tur=DenemeSinavi.Tur.GRUP,
            deneme__durum=DenemeSinavi.Durum.AKTIF,
        )
        .select_related("deneme")
        .prefetch_related("brans_satirlari")
        .order_by("deneme__sinav_tarihi", "deneme__id")
    )
    seri = []
    for sonuc in sonuclar:
        seri.append(
            {
                "deneme_id": sonuc.deneme_id,
                "sira_no": sonuc.deneme.sira_no,
                "ad": sonuc.deneme.ad,
                "tarih": sonuc.deneme.sinav_tarihi,
                "puan": float(sonuc.puan or 0),
                "net": float(sonuc.toplam_net or 0),
                "sonuc": sonuc,
            }
        )
    if seri:
        max_puan = max(nokta["puan"] for nokta in seri) or 1
        for nokta in seri:
            nokta["puan_yuzde"] = round(max(nokta["puan"], 0) / max_puan * 100, 1)
    return seri


def talebe_bireysel_denemeleri(talebe: Talebe) -> list[dict]:
    """Bireysel denemeler — grup gelişimine karıştırılmaz, ayrı ve ordinal numaralı."""
    sonuclar = (
        DenemeSonucu.objects.filter(
            talebe=talebe,
            deneme__tur=DenemeSinavi.Tur.BIREYSEL,
            deneme__durum=DenemeSinavi.Durum.AKTIF,
        )
        .select_related("deneme")
        .order_by("deneme__sinav_tarihi", "deneme__id")
    )
    liste = []
    for sira, sonuc in enumerate(sonuclar, start=1):
        liste.append(
            {
                "sira": sira,
                "etiket": f"Bireysel Deneme #{sira}",
                "deneme_id": sonuc.deneme_id,
                "ad": sonuc.deneme.ad,
                "tarih": sonuc.deneme.sinav_tarihi,
                "puan": float(sonuc.puan or 0),
                "net": float(sonuc.toplam_net or 0),
            }
        )
    return liste


def talebe_gelisim_metrikleri(grup_seri: list[dict]) -> dict | None:
    """İlk→son, son2, son3 ve sezon başından bugüne puan değişimi."""
    if len(grup_seri) < 2:
        return None

    ilk, son = grup_seri[0], grup_seri[-1]
    son2 = grup_seri[-2:]
    son3 = grup_seri[-3:]

    return {
        "ilk_puan": ilk["puan"],
        "son_puan": son["puan"],
        "genel_degisim": round(son["puan"] - ilk["puan"], 2),
        "son2_degisim": (
            round(son2[-1]["puan"] - son2[0]["puan"], 2) if len(son2) == 2 else None
        ),
        "son3_degisim": (
            round(son3[-1]["puan"] - son3[0]["puan"], 2) if len(son3) >= 2 else None
        ),
        "sezon_basi_bugun": round(son["puan"] - ilk["puan"], 2),
    }


def talebe_trend_sinifla(grup_seri: list[dict]) -> dict:
    """YÜKSELİŞTE / DÜŞÜŞTE / DALGALI / STABİL sınıflandırması.

    Sadece tek denemeye bakılmaz; son birkaç grup denemesinin ardışık
    puan farkları değerlendirilir. Eşik değerleri
    ``settings.DENEME_TREND_ESIK`` üzerinden değiştirilebilir.
    """
    esik = _trend_esik()
    min_deneme = int(esik["min_deneme"])

    if len(grup_seri) < 2:
        kod = "yetersiz"
        return {"kod": kod, "etiket": TREND_ETIKETLERI[kod], "aciklama": TREND_ACIKLAMALARI[kod]}

    son_n = grup_seri[-min_deneme:] if len(grup_seri) >= min_deneme else grup_seri
    farklar = [son_n[i + 1]["puan"] - son_n[i]["puan"] for i in range(len(son_n) - 1)]

    duzenli_esik = esik["duzenli_esik"]
    if farklar and all(f >= duzenli_esik for f in farklar):
        kod = "yukseliste"
    elif farklar and all(f <= -duzenli_esik for f in farklar):
        kod = "duseste"
    else:
        ortalama = sum(farklar) / len(farklar)
        varyans = sum((f - ortalama) ** 2 for f in farklar) / len(farklar)
        std = varyans**0.5
        if std >= esik["dalgali_std_esik"]:
            kod = "dalgali"
        elif abs(son_n[-1]["puan"] - son_n[0]["puan"]) <= esik["stabil_esik"]:
            kod = "stabil"
        else:
            kod = "dalgali"

    return {"kod": kod, "etiket": TREND_ETIKETLERI[kod], "aciklama": TREND_ACIKLAMALARI[kod]}


def _brans_net_serisi(grup_seri: list[dict], kod: str) -> list[float | None]:
    netler: list[float | None] = []
    for nokta in grup_seri:
        sonuc: DenemeSonucu = nokta["sonuc"]
        brans = next((b for b in sonuc.brans_satirlari.all() if b.brans == kod), None)
        netler.append(float(brans.net) if brans else None)
    return netler


def talebe_brans_net_gelisimi(grup_seri: list[dict]) -> list[dict]:
    """Ders bazında net gelişimi (madde 12): "14.67 → 15.33 → 16.00 → 17.33"."""
    sonuclar = []
    for kod in DENEME_BRANS_DERS_MAP:
        netler = _brans_net_serisi(grup_seri, kod)
        if not any(n is not None for n in netler):
            continue
        sonuclar.append(
            {
                "kod": kod,
                "etiket": BRANS_ETIKETLERI[kod],
                "netler": netler,
            }
        )
    return sonuclar


def _son_30_gun_soru_sayisi(talebe: Talebe, ders_ad: str, gun: int = 30) -> int:
    bugun = localdate()
    baslangic = bugun - timedelta(days=gun)
    from takip.soru_takip_models import GunlukSoruDersSatiri

    toplam = GunlukSoruDersSatiri.objects.filter(
        kayit__talebe=talebe,
        kayit__tarih__gte=baslangic,
        kayit__tarih__lte=bugun,
        ders__ad=ders_ad,
    ).aggregate(t=Sum("toplam_soru"))["t"]
    return int(toplam or 0)


def talebe_calisma_karsilik_analizi(talebe: Talebe, grup_seri: list[dict]) -> list[dict]:
    """Ders bazında soru çözümü ile deneme net gelişimi ilişkisi (madde 16-17).

    Kesin pedagojik hüküm vermez; sadece "çalışma karşılık veriyor" /
    "yüksek çalışmaya rağmen performans düşüyor" gibi veri temelli
    göstergeler üretir. Nihai değerlendirme etüt hocasına bırakılır.
    """
    if len(grup_seri) < 2:
        return []

    sonuclar = []
    for kod, ders_ad in DENEME_BRANS_DERS_MAP.items():
        netler = [n for n in _brans_net_serisi(grup_seri, kod) if n is not None]
        if len(netler) < 2:
            continue
        net_degisim = round(netler[-1] - netler[0], 2)
        soru_sayisi = _son_30_gun_soru_sayisi(talebe, ders_ad)

        if soru_sayisi >= 50 and net_degisim > 0:
            yorum = "Çalışma karşılık veriyor."
            durum = "olumlu"
        elif soru_sayisi >= 50 and net_degisim <= 0:
            yorum = "Yüksek soru çözümüne rağmen deneme performansı gelişmiyor."
            durum = "uyari"
        elif soru_sayisi < 20 and net_degisim > 0:
            yorum = "Düşük soru çözümüne rağmen performans yükseliyor."
            durum = "notr"
        else:
            yorum = "Soru çözümü ve deneme performansı birlikte değerlendirilmeli."
            durum = "notr"

        sonuclar.append(
            {
                "kod": kod,
                "etiket": BRANS_ETIKETLERI[kod],
                "son_30_gun_soru": soru_sayisi,
                "net_degisim": net_degisim,
                "yorum": yorum,
                "durum": durum,
            }
        )
    return sonuclar


def talebe_deneme_gelisim_paketi(talebe: Talebe) -> dict:
    """Bir öğrencinin deneme gelişimi ekranı için ihtiyaç duyduğu her şey."""
    grup_seri = talebe_grup_deneme_gelisimi(talebe)
    return {
        "grup_seri": grup_seri,
        "bireysel_denemeler": talebe_bireysel_denemeleri(talebe),
        "metrikler": talebe_gelisim_metrikleri(grup_seri),
        "trend": talebe_trend_sinifla(grup_seri),
        "brans_gelisimi": talebe_brans_net_gelisimi(grup_seri),
        "calisma_karsilik": talebe_calisma_karsilik_analizi(talebe, grup_seri),
    }
