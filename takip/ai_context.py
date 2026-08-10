"""Talebe ve kurum bağlamı — tüm modüllerden veri toplama."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import localdate

from takip.akademik_mudahale_service import talebe_akademik_ozet
from takip.deneme_service import (
    BRANS_ETIKETLERI,
    DENEME_DETAY_BRANSLAR,
    talebe_deneme_sonuclari,
)
from takip.gelisim_service import _devam_ozeti, _deneme_grafik_verisi
from takip.models import (
    GunlukSoruKaydi,
    KttSonucu,
    OkumaKaydi,
    Talebe,
    Zimmet,
)
from takip.permissions.scope import yetkili_talebeler
from takip.rehberlik_models import OgrenciGorusmesi
from takip.soru_takip_service import aylik_ozet, haftalik_ozet
from takip.veli_service import talebe_kpi_ozeti


def _okuma_ozeti(talebe: Talebe) -> dict[str, Any]:
    zimmetler = Zimmet.objects.filter(talebe=talebe, durum="okunuyor").select_related("kitap")
    aktif = [
        {"kitap": z.kitap.ad, "sayfa": z.kitap.toplam_sayfa or 0}
        for z in zimmetler[:3]
    ]
    bugun = localdate()
    hafta_bas = bugun - timedelta(days=bugun.weekday())
    kayitlar = OkumaKaydi.objects.filter(
        zimmet__talebe=talebe,
        tarih__gte=hafta_bas,
        tarih__lte=bugun,
    )
    hafta_sayfa = sum(k.okunan_sayfa for k in kayitlar)
    return {"aktif_kitaplar": aktif, "bu_hafta_sayfa": int(hafta_sayfa)}


def talebe_zengin_baglam(talebe: Talebe, *, veli_modu: bool = False) -> dict[str, Any]:
    """Gelişim zekası ve veli özeti için talebe veri paketi."""
    bugun = localdate()
    denemeler = list(talebe_deneme_sonuclari(talebe)[:5])
    deneme_satirlari = []
    for sonuc in denemeler:
        brans_map = {b.brans: b for b in sonuc.brans_satirlari.all()}
        branslar = {}
        for kod in DENEME_DETAY_BRANSLAR:
            b = brans_map.get(kod)
            if b:
                branslar[BRANS_ETIKETLERI[kod]] = {
                    "dogru": int(b.dogru or 0),
                    "yanlis": int(b.yanlis or 0),
                    "bos": int(b.bos or 0),
                    "net": float(b.net or 0),
                }
        deneme_satirlari.append(
            {
                "ad": sonuc.deneme.ad,
                "tarih": sonuc.deneme.sinav_tarihi.isoformat(),
                "net": float(sonuc.toplam_net or 0),
                "puan": float(sonuc.puan or 0),
                "branslar": branslar,
            }
        )

    ktt_qs = KttSonucu.objects.filter(talebe=talebe).select_related("ktt", "ktt__ders")
    if veli_modu:
        ktt_qs = ktt_qs.filter(ktt__veliye_goster=True, ktt__aktif=True)
    ktt_satirlari = [
        {
            "ad": s.ktt.ad,
            "ders": s.ktt.ders.ad if s.ktt.ders_id else "—",
            "tarih": s.ktt.sinav_tarihi.isoformat(),
            "puan": float(s.puan or 0),
            "net": float(s.net or 0),
        }
        for s in ktt_qs.order_by("-ktt__sinav_tarihi")[:8]
    ]

    ay_soru = aylik_ozet(talebe, bugun)
    hafta_soru = haftalik_ozet(talebe)
    devam = _devam_ozeti(talebe)
    mudahale = talebe_akademik_ozet(talebe)

    gorusmeler = []
    gorusme_qs = OgrenciGorusmesi.objects.filter(talebe=talebe).select_related("tur")
    if veli_modu:
        gorusme_qs = gorusme_qs.filter(veli_goster=True)
    for g in gorusme_qs.order_by("-tarih")[:5]:
        gorusmeler.append(
            {
                "tur": g.tur.ad,
                "tarih": g.tarih.isoformat(),
                "ozet": g.ozet,
                "genel_durum": g.get_genel_durum_display(),
            }
        )

    okuma = _okuma_ozeti(talebe)
    deneme_grafik = _deneme_grafik_verisi(talebe, limit=4)

    return {
        "ogrenci": {
            "ad_soyad": talebe.ad_soyad,
            "sinif": str(talebe.sinif_sube or talebe.sinif or "—"),
            "talebe_no": talebe.talebe_no or "",
            "etut_hocasi": talebe.etut_hocasi.ad_soyad if talebe.etut_hocasi_id else "—",
        },
        "denemeler": deneme_satirlari,
        "deneme_trend": deneme_grafik,
        "ktt": ktt_satirlari,
        "soru_takip": {
            "bu_ay": ay_soru,
            "bu_hafta": hafta_soru,
        },
        "devam": {
            "devamsizlik": devam.get("devamsizlik", 0),
            "etut_katilim_orani": devam.get("etut_katilim_orani", 0),
            "namaz_katilim_orani": devam.get("namaz_katilim_orani", 0),
        },
        "okuma": okuma,
        "mudahale": mudahale,
        "gorusmeler": gorusmeler,
    }


def kurum_baglam(user: User) -> dict[str, Any]:
    """Kurum zekası için özet istatistikler."""
    qs = yetkili_talebeler(user)
    toplam = qs.count()
    sinif_dagilim = list(
        qs.values("sinif_sube__sinif", "sinif_sube__sube")
        .annotate(adet=models.Count("id"))
        .order_by("-adet")[:8]
    )

    aktif_zimmet = Zimmet.objects.filter(talebe__in=qs, durum="okunuyor").count()
    bugun = localdate()
    ay_bas = bugun.replace(day=1)

    soru_toplam = (
        GunlukSoruKaydi.objects.filter(
            talebe__in=qs,
            tarih__gte=ay_bas,
            tarih__lte=bugun,
        ).aggregate(t=models.Sum("toplam_soru"))["t"]
        or 0
    )

    risk_adaylari = _mudahale_adaylari(user, limit=8)

    return {
        "talebe_sayisi": toplam,
        "sinif_dagilim": sinif_dagilim,
        "aktif_zimmet": aktif_zimmet,
        "bu_ay_soru_toplam": int(soru_toplam),
        "risk_adaylari": risk_adaylari,
    }


def talebe_risk_skoru(talebe: Talebe) -> tuple[int, list[str]]:
    """Kural tabanlı risk skoru (0–100) ve nedenler."""
    nedenler: list[str] = []
    skor = 0

    denemeler = list(talebe_deneme_sonuclari(talebe)[:3])
    if len(denemeler) >= 2:
        son = float(denemeler[0].toplam_net or 0)
        onceki = float(denemeler[1].toplam_net or 0)
        if onceki > 0 and son < onceki * 0.85:
            skor += 25
            nedenler.append(f"Deneme neti düşüşte ({onceki:.1f} → {son:.1f})")

    devam = _devam_ozeti(talebe)
    if devam.get("devamsizlik", 0) >= 2:
        skor += 20
        nedenler.append(f"Bu ay {devam['devamsizlik']} devamsızlık")
    if devam.get("etut_katilim_orani", 100) < 70:
        skor += 15
        nedenler.append(f"Etüt katılımı düşük (%{devam['etut_katilim_orani']})")
    if devam.get("namaz_katilim_orani", 100) < 75:
        skor += 10
        nedenler.append(f"Namaz katılımı düşük (%{devam['namaz_katilim_orani']})")

    ay = aylik_ozet(talebe, localdate())
    if ay.get("toplam_soru", 0) < 50:
        skor += 15
        nedenler.append("Bu ay soru hacmi düşük")

    okuma = _okuma_ozeti(talebe)
    if okuma.get("bu_hafta_sayfa", 0) < 20 and okuma.get("aktif_kitaplar"):
        skor += 10
        nedenler.append("Haftalık okuma tempo düşük")

    return min(100, skor), nedenler


def _mudahale_adaylari(user: User, *, limit: int = 10) -> list[dict[str, Any]]:
    qs = yetkili_talebeler(user).select_related("sinif_sube", "etut_hocasi")[:200]
    adaylar = []
    for talebe in qs:
        skor, nedenler = talebe_risk_skoru(talebe)
        if skor >= 40:
            adaylar.append(
                {
                    "talebe_id": talebe.id,
                    "ad_soyad": talebe.ad_soyad,
                    "sinif": str(talebe.sinif_sube or "—"),
                    "skor": skor,
                    "nedenler": nedenler[:3],
                }
            )
    adaylar.sort(key=lambda x: x["skor"], reverse=True)
    return adaylar[:limit]


def _deneme_gap_konulari(deneme, talebe_id: int | None, *, limit: int = 8) -> list[dict[str, Any]]:
    from decimal import Decimal

    from takip.deneme_models import DenemeGapRaporu, DenemeKonuSonucu

    if not talebe_id:
        return []
    qs = (
        DenemeKonuSonucu.objects.filter(
            rapor__deneme=deneme,
            rapor__talebe_id=talebe_id,
            rapor__durum=DenemeGapRaporu.Durum.ISLENDI,
        )
        .order_by("yuzde", "brans")[:limit]
    )
    return [
        {
            "brans": k.get_brans_display(),
            "konu": k.konu_normalize or k.konu_ham,
            "D": k.dogru,
            "Y": k.yanlis,
            "B": k.bos,
            "yuzde": float(k.yuzde or 0),
            "zayif": (k.yuzde or Decimal("0")) < Decimal("70"),
        }
        for k in qs
    ]


def _deneme_ktt_konulari(talebe, *, limit: int = 6) -> list[dict[str, Any]]:
    """Talebenin son KTT kayıtlarından zayıf/güçlü konu özeti."""
    from decimal import Decimal

    from takip.models import KttSonucu

    if not talebe:
        return []
    kayitlar = list(
        KttSonucu.objects.filter(talebe=talebe)
        .select_related("ktt", "ktt__ders")
        .order_by("-ktt__sinav_tarihi", "-id")[:24]
    )
    if not kayitlar:
        return []
    esik = Decimal("70")
    zayif = [s for s in kayitlar if (s.puan or 0) < esik]
    zayif.sort(key=lambda s: float(s.puan or 0))
    guclu = sorted(kayitlar, key=lambda s: float(s.puan or 0), reverse=True)[:3]
    sonuc: list[dict[str, Any]] = []
    for s in zayif[:limit]:
        sonuc.append(
            {
                "ktt": s.ktt.ad,
                "ders": getattr(s.ktt.ders, "ad", "") or "—",
                "puan": float(s.puan or 0),
                "D": s.dogru,
                "Y": s.yanlis,
                "B": s.bos,
                "tip": "zayif",
            }
        )
    for s in guclu:
        if any(x.get("ktt") == s.ktt.ad for x in sonuc):
            continue
        sonuc.append(
            {
                "ktt": s.ktt.ad,
                "ders": getattr(s.ktt.ders, "ad", "") or "—",
                "puan": float(s.puan or 0),
                "D": s.dogru,
                "Y": s.yanlis,
                "B": s.bos,
                "tip": "guclu",
            }
        )
        if len(sonuc) >= limit + 2:
            break
    return sonuc[: limit + 2]


def deneme_baglam(deneme, sonuclar) -> dict[str, Any]:
    from decimal import Decimal

    from takip.deneme_gap_pdf import deneme_zayif_konular
    from takip.deneme_models import DenemeGapRaporu
    from takip.deneme_service import deneme_detay_satirlari

    satirlar = deneme_detay_satirlari(sonuclar)
    ogrenci_verileri = []
    for satir in satirlar[:40]:
        sonuc = satir["sonuc"]
        brans_ozet = {}
        for b in satir["branslar"]:
            brans_ozet[b["etiket"]] = f"D{b['dogru']} Y{b['yanlis']} B{b['bos']}"
        ogrenci_verileri.append(
            {
                "sira": satir["sira"],
                "talebe": sonuc.talebe.ad_soyad,
                "talebe_id": sonuc.talebe_id,
                "sinif": str(sonuc.talebe.sinif_sube or "—"),
                "net": float(sonuc.toplam_net or 0),
                "puan": float(sonuc.puan or 0),
                "branslar": brans_ozet,
                "gap_konular": _deneme_gap_konulari(deneme, sonuc.talebe_id),
                "ktt_konular": _deneme_ktt_konulari(sonuc.talebe),
            }
        )

    sinif_zayif = [
        {
            "talebe": (
                k.rapor.talebe.ad_soyad
                if k.rapor.talebe_id
                else k.rapor.ham_ad
            ),
            "brans": k.get_brans_display(),
            "konu": k.konu_normalize or k.konu_ham,
            "yuzde": float(k.yuzde or 0),
            "D": k.dogru,
            "Y": k.yanlis,
            "B": k.bos,
        }
        for k in deneme_zayif_konular(deneme, esik=Decimal("70"), limit=25)
    ]
    gap_adet = DenemeGapRaporu.objects.filter(
        deneme=deneme,
        durum=DenemeGapRaporu.Durum.ISLENDI,
    ).count()

    return {
        "deneme": {
            "ad": deneme.ad,
            "tarih": deneme.sinav_tarihi.isoformat(),
            "sinif": deneme.sinif_seviyesi,
            "ogrenci_sayisi": len(satirlar),
            "gap_rapor_sayisi": gap_adet,
        },
        "sonuclar": ogrenci_verileri,
        "gap_zayif_konular_sinif": sinif_zayif,
    }


def baglam_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
