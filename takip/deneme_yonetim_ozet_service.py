"""Yönetici — Deneme Özeti (sınıflar arası karşılaştırma).

Etüt hocası ekranındaki (deneme_kontrol_service) aynı hesaplamayı
sınıf bazında tekrar kullanır; kod tekrarlanmaz. Öncelikli bilgiler
(sınıf karşılaştırması, en çok gelişen sınıf) üstte, ders/deneme
bazlı detaylar ayrı bölümlerde — tek bir istatistik çöplüğüne
dönüşmemesi için.
"""

from __future__ import annotations

from django.db.models import Avg, Count

from takip.deneme_kontrol_service import sinif_kontrol_verisi_hesapla
from takip.deneme_service import BRANS_ETIKETLERI
from takip.models import DenemeBransSonucu, DenemeSinavi, DenemeSonucu, SinifSube, Talebe


def yonetici_deneme_ozeti(sinif_seviyesi: str = "") -> dict:
    sube_qs = SinifSube.objects.filter(aktif=True).order_by("sinif", "sube")
    if sinif_seviyesi:
        sube_qs = sube_qs.filter(sinif=sinif_seviyesi)

    sinif_satirlari = []
    for sinif in sube_qs:
        ogrenciler = list(
            Talebe.objects.filter(sinif_sube=sinif, aktif=True).order_by("ad_soyad")
        )
        if not ogrenciler:
            continue
        veri = sinif_kontrol_verisi_hesapla(ogrenciler, sinif)
        if veri["sinif_ortalamasi"] is None:
            continue
        sinif_satirlari.append(
            {
                "sinif": sinif,
                "ortalama": veri["sinif_ortalamasi"],
                "degisim": veri["ortalama_degisim"],
                "yukselen": veri["yukselen"],
                "dusen": veri["dusen"],
                "takip_gereken": veri["takip_gereken"],
                "ogrenci_sayisi": len(ogrenciler),
            }
        )

    sinif_satirlari.sort(key=lambda s: s["sinif"].etiket)

    en_cok_gelisen = None
    gelisenler = [s for s in sinif_satirlari if s["degisim"] is not None]
    if gelisenler:
        en_cok_gelisen = max(gelisenler, key=lambda s: s["degisim"])

    son_deneme = (
        DenemeSinavi.objects.filter(
            tur=DenemeSinavi.Tur.GRUP, durum=DenemeSinavi.Durum.AKTIF
        )
        .order_by("-sinav_tarihi", "-id")
        .first()
    )

    ders_ortalamalari = []
    if son_deneme:
        for row in (
            DenemeBransSonucu.objects.filter(sonuc__deneme=son_deneme)
            .values("brans")
            .annotate(ort_net=Avg("net"))
            .order_by("brans")
        ):
            ders_ortalamalari.append(
                {
                    "kod": row["brans"],
                    "etiket": BRANS_ETIKETLERI.get(row["brans"], row["brans"]),
                    "ortalama_net": round(float(row["ort_net"] or 0), 2),
                }
            )

    kurum_serisi = []
    for deneme in DenemeSinavi.objects.filter(
        tur=DenemeSinavi.Tur.GRUP, durum=DenemeSinavi.Durum.AKTIF
    ).order_by("sinav_tarihi", "id"):
        agg = DenemeSonucu.objects.filter(deneme=deneme).aggregate(
            ort=Avg("puan"), n=Count("id")
        )
        if agg["ort"] is None:
            continue
        kurum_serisi.append(
            {
                "deneme_id": deneme.pk,
                "sira_no": deneme.sira_no,
                "ad": deneme.ad,
                "tarih": deneme.sinav_tarihi,
                "ortalama": round(float(agg["ort"]), 2),
                "ogrenci_sayisi": agg["n"],
            }
        )
    if kurum_serisi:
        max_ort = max(n["ortalama"] for n in kurum_serisi) or 1
        for n in kurum_serisi:
            n["ortalama_yuzde"] = round(n["ortalama"] / max_ort * 100, 1)

    return {
        "sinif_satirlari": sinif_satirlari,
        "en_cok_gelisen": en_cok_gelisen,
        "ders_ortalamalari": ders_ortalamalari,
        "kurum_serisi": kurum_serisi,
        "toplam_yukselen": sum(s["yukselen"] for s in sinif_satirlari),
        "toplam_dusen": sum(s["dusen"] for s in sinif_satirlari),
        "toplam_takip_gereken": sum(s["takip_gereken"] for s in sinif_satirlari),
        "son_deneme": son_deneme,
        "sinif_seviyeleri": list(
            SinifSube.objects.filter(aktif=True)
            .order_by("sinif")
            .values_list("sinif", flat=True)
            .distinct()
        ),
    }
