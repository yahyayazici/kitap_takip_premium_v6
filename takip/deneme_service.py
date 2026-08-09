"""Deneme sorguları ve yardımcılar."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Count, QuerySet

from takip.models import DenemeSinavi, DenemeSonucu, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can

BRANS_ETIKETLERI = {
    "turkce": "Türkçe",
    "matematik": "Matematik",
    "fen": "Fen Bilimleri",
    "sosyal": "Sosyal Bilgiler",
    "din": "Din Kültürü",
    "ingilizce": "İngilizce",
}

# Deneme detay ekranı ve günlük soru takip eşlemesi (Din hariç 5 ders)
DENEME_DETAY_BRANSLAR: tuple[str, ...] = (
    "turkce",
    "matematik",
    "fen",
    "sosyal",
    "ingilizce",
)

DENEME_BRANS_DERS_MAP: dict[str, str] = {
    kod: BRANS_ETIKETLERI[kod]
    for kod in DENEME_DETAY_BRANSLAR
}


def deneme_detay_satirlari(sonuclar) -> list[dict]:
    """Sıralama tablosu + ders ders D/Y/B için şablon satırları."""
    rows: list[dict] = []
    for sira, sonuc in enumerate(sonuclar, start=1):
        brans_map = {b.brans: b for b in sonuc.brans_satirlari.all()}
        branslar = []
        for kod in DENEME_DETAY_BRANSLAR:
            b = brans_map.get(kod)
            branslar.append(
                {
                    "kod": kod,
                    "etiket": BRANS_ETIKETLERI[kod],
                    "dogru": int(b.dogru or 0) if b else 0,
                    "yanlis": int(b.yanlis or 0) if b else 0,
                    "bos": int(b.bos or 0) if b else 0,
                    "net": b.net if b else 0,
                }
            )
        rows.append({"sira": sira, "sonuc": sonuc, "branslar": branslar})
    return rows


def deneme_yukleyebilir(user: User) -> bool:
    from takip.permissions.registry import LEGACY_IDARE_ROLLER
    from takip.permissions.service import kullanici_birincil_rol_slug

    if user.is_superuser:
        return True
    if kullanici_birincil_rol_slug(user) not in LEGACY_IDARE_ROLLER:
        return False
    return can(user, "deneme", "create")


def yetkili_denemeler(user: User) -> QuerySet[DenemeSinavi]:
    if not can(user, "deneme", "view"):
        return DenemeSinavi.objects.none()

    qs = DenemeSinavi.objects.annotate(
        sonuc_sayisi=Count("sonuclar")
    ).order_by("-sinav_tarihi", "-id")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(
        durum=DenemeSinavi.Durum.AKTIF,
        sonuclar__talebe_id__in=talebe_ids,
    ).distinct()


def yetkili_deneme_sonuclari(user: User) -> QuerySet[DenemeSonucu]:
    if not can(user, "deneme", "view"):
        return DenemeSonucu.objects.none()

    qs = DenemeSonucu.objects.select_related(
        "deneme", "talebe", "talebe__sinif_sube"
    ).prefetch_related("brans_satirlari")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def deneme_sonuclari(user: User, deneme: DenemeSinavi) -> QuerySet[DenemeSonucu]:
    qs = yetkili_deneme_sonuclari(user).filter(deneme=deneme)
    return qs.order_by("-toplam_net", "talebe__ad_soyad")


def deneme_sonuc_ozeti(sonuclar) -> dict:
    kayitlar = list(sonuclar)
    if not kayitlar:
        return {
            "ogrenci_sayisi": 0,
            "ortalama_net": "—",
            "ortalama_puan": "—",
            "en_yuksek_puan": "—",
        }

    toplam_net = sum(float(s.toplam_net or 0) for s in kayitlar)
    toplam_puan = sum(float(s.puan or 0) for s in kayitlar)
    en_yuksek = max(float(s.puan or 0) for s in kayitlar)
    adet = len(kayitlar)
    return {
        "ogrenci_sayisi": adet,
        "ortalama_net": round(toplam_net / adet, 2),
        "ortalama_puan": round(toplam_puan / adet, 2),
        "en_yuksek_puan": round(en_yuksek, 2),
    }


def talebe_deneme_sonuclari(talebe: Talebe) -> QuerySet[DenemeSonucu]:
    return (
        DenemeSonucu.objects.filter(talebe=talebe, deneme__durum=DenemeSinavi.Durum.AKTIF)
        .select_related("deneme")
        .prefetch_related("brans_satirlari")
        .order_by("-deneme__sinav_tarihi", "-id")
    )


DENEME_SINAV_SABITLERI: dict[str, dict] = {
    "8": {"baslik": "LGS", "soru": 85, "taban": 100, "tavan": 500},
    "7": {"baslik": "Deneme", "soru": 90, "taban": 0, "tavan": 500},
    "6": {"baslik": "Deneme", "soru": 90, "taban": 0, "tavan": 500},
}


def _talebe_sinif_seviyesi(talebe: Talebe) -> str:
    if getattr(talebe, "sinif_sube_id", None):
        ss = talebe.sinif_sube
        if ss:
            return str(ss.sinif).strip()
    return str(talebe.sinif or "8").strip()


def deneme_puan_yuzdesi(puan: float, taban: float, tavan: float) -> int:
    if tavan <= taban:
        return 0
    yuzde = (float(puan) - taban) / (tavan - taban) * 100
    return max(0, min(100, round(yuzde)))


def talebe_deneme_performans_ozeti(
    talebe: Talebe,
    *,
    gecmis_limit: int | None = None,
) -> dict | None:
    """Öğrenci deneme özeti — LGS tarzı kart + sınav geçmişi."""
    sonuclar = list(talebe_deneme_sonuclari(talebe))
    if not sonuclar:
        return None

    sinif = _talebe_sinif_seviyesi(talebe)
    sabit = DENEME_SINAV_SABITLERI.get(sinif, DENEME_SINAV_SABITLERI["8"])
    taban = float(sabit["taban"])
    tavan = float(sabit["tavan"])

    puanlar = [float(s.puan or 0) for s in sonuclar]
    netler = [float(s.toplam_net or 0) for s in sonuclar]
    ort_puan = round(sum(puanlar) / len(puanlar), 2)
    ort_net = round(sum(netler) / len(netler), 2)

    gecmis = []
    for sonuc in sonuclar[: gecmis_limit or len(sonuclar)]:
        puan = float(sonuc.puan or 0)
        gecmis.append(
            {
                "deneme_id": sonuc.deneme_id,
                "ad": sonuc.deneme.ad,
                "tarih": sonuc.deneme.sinav_tarihi,
                "puan": puan,
                "net": float(sonuc.toplam_net or 0),
                "yuzde": deneme_puan_yuzdesi(puan, taban, tavan),
            }
        )

    grafik_kaynak = list(reversed(sonuclar[:10]))
    max_net = max(float(s.toplam_net or 0) for s in grafik_kaynak) or 1
    grafik = [
        {
            "etiket": s.deneme.sinav_tarihi.strftime("%d.%m"),
            "baslik": s.deneme.ad,
            "net": float(s.toplam_net or 0),
            "puan": float(s.puan or 0),
            "net_yuzde": round(float(s.toplam_net or 0) * 100 / max_net, 1),
        }
        for s in grafik_kaynak
    ]

    return {
        "baslik": sabit["baslik"],
        "soru": sabit["soru"],
        "taban": int(sabit["taban"]),
        "tavan": int(sabit["tavan"]),
        "ortalama_puan": ort_puan,
        "ortalama_net": ort_net,
        "en_yuksek_puan": round(max(puanlar), 2),
        "en_dusuk_puan": round(min(puanlar), 2),
        "genel_yuzde": deneme_puan_yuzdesi(ort_puan, taban, tavan),
        "toplam_sinav": len(sonuclar),
        "gecmis": gecmis,
        "grafik": grafik,
    }
