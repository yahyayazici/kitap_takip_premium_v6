"""ÇİSA — seçilen denemelerin talebe raporu.

Kapak netleri kayıtlı branş netinden gelir. Konu dökümü soru karnesindeki
satırlardan toplanır; aynı soru iki kez sayılmaz.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Exists, OuterRef, Q

from takip.deneme_models import (
    DenemeBransSonucu,
    DenemeSinavi,
    DenemeSonucu,
    DenemeSoruSonucu,
)
from takip.deneme_service import DENEME_KARNE_DERSLERI, tr_ondalik
from takip.models import Talebe

_DERS_SIRA = {kod: i for i, (kod, _etiket) in enumerate(DENEME_KARNE_DERSLERI)}
_DERS_AD = {
    "turkce": "Türkçe",
    "türkçe": "Türkçe",
    "matematik": "Matematik",
    "fen": "Fen Bilimleri",
    "fen bilimleri": "Fen Bilimleri",
    "fen bilgisi": "Fen Bilimleri",
    "sosyal": "Sosyal Bilgiler",
    "sosyal bilgiler": "Sosyal Bilgiler",
    "inkilap": "İnkılap",
    "inkılap": "İnkılap",
    "t.c. inkılap tarihi": "İnkılap",
    "din": "Din Kültürü",
    "din kültürü": "Din Kültürü",
    "din kulturu": "Din Kültürü",
    "ingilizce": "İngilizce",
}
_KOD = {
    "türkçe": "turkce",
    "turkce": "turkce",
    "matematik": "matematik",
    "fen": "fen",
    "fen bilimleri": "fen",
    "fen bilgisi": "fen",
    "sosyal": "sosyal",
    "sosyal bilgiler": "sosyal",
    "inkilap": "inkilap",
    "inkılap": "inkilap",
    "t.c. inkılap tarihi": "inkilap",
    "din": "din",
    "din kültürü": "din",
    "din kulturu": "din",
    "ingilizce": "ingilizce",
}


def _ort(degerler: list[Decimal]) -> Decimal | None:
    if not degerler:
        return None
    return (sum(degerler, Decimal("0")) / Decimal(len(degerler))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _yuzde(pay: int, payda: int) -> int | None:
    if payda <= 0:
        return None
    return int(
        (Decimal(pay) * Decimal(100) / Decimal(payda)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _ders_kodu(ders_key: str, ders_ad: str) -> str:
    ham = (ders_key or "").strip().lower()
    if ham in _DERS_SIRA or ham in _DERS_AD:
        return _KOD.get(ham, ham)
    ad = (ders_ad or "").strip().lower()
    return _KOD.get(ad, ham or ad or "diger")


def _ders_baslik(kod: str, ders_ad: str) -> str:
    if ders_ad.strip():
        return ders_ad.strip()
    return _DERS_AD.get(kod, kod)


def cisa_deneme_listesi(talebe: Talebe) -> list[dict]:
    """Talebenin seçilebileceği denemeler. Taslak yok."""
    soru = DenemeSoruSonucu.objects.filter(
        deneme_id=OuterRef("deneme_id"),
        talebe_id=talebe.id,
    )
    kayitlar = (
        DenemeSonucu.objects.filter(
            talebe=talebe,
            deneme__durum=DenemeSinavi.Durum.AKTIF,
        )
        .select_related("deneme")
        .annotate(soru_karnesi=Exists(soru))
        .order_by("-deneme__sinav_tarihi", "-deneme_id")
    )
    return [
        {
            "id": kayit.deneme_id,
            "ad": kayit.deneme.ad,
            "tarih": kayit.deneme.sinav_tarihi,
            "net": tr_ondalik(kayit.toplam_net),
            "soru_karnesi": bool(kayit.soru_karnesi),
        }
        for kayit in kayitlar
    ]


def cisa_sinif_denemeleri(talebe_ids: list[int]) -> list[dict]:
    """Sınıftaki talebelerin ortak deneme listesi. Taslak ve arşiv yok."""
    if not talebe_ids:
        return []
    sayilar = {
        satir["deneme_id"]: satir["talebe_sayisi"]
        for satir in (
            DenemeSonucu.objects.filter(
                talebe_id__in=talebe_ids,
                deneme__durum=DenemeSinavi.Durum.AKTIF,
            )
            .values("deneme_id")
            .annotate(talebe_sayisi=Count("talebe_id", distinct=True))
        )
    }
    if not sayilar:
        return []
    denemeler = DenemeSinavi.objects.filter(pk__in=sayilar).order_by(
        "-sinav_tarihi", "-id"
    )
    return [
        {
            "id": deneme.id,
            "ad": deneme.ad,
            "tarih": deneme.sinav_tarihi,
            "talebe_sayisi": sayilar[deneme.id],
        }
        for deneme in denemeler
    ]


def _sinif_soru(talebe: Talebe) -> Q:
    if talebe.sinif_sube_id:
        return Q(talebe__sinif_sube_id=talebe.sinif_sube_id)
    return Q(talebe_id=talebe.id)


def _sinif_brans(talebe: Talebe) -> Q:
    if talebe.sinif_sube_id:
        return Q(sonuc__talebe__sinif_sube_id=talebe.sinif_sube_id)
    return Q(sonuc__talebe_id=talebe.id)


def cisa_rapor(talebe: Talebe, deneme_ids: list[int]) -> dict | None:
    """Seçilen denemelerden ÇİSA raporu. Seçim dışı deneme girmez."""
    istenen = {int(i) for i in deneme_ids if str(i).isdigit() or isinstance(i, int)}
    if not istenen:
        return None
    sonuclar = list(
        DenemeSonucu.objects.filter(
            talebe=talebe,
            deneme_id__in=istenen,
            deneme__durum=DenemeSinavi.Durum.AKTIF,
        )
        .select_related("deneme", "talebe", "talebe__sinif_sube")
        .prefetch_related("brans_satirlari")
        .order_by("deneme__sinav_tarihi", "deneme_id")
    )
    if not sonuclar:
        return None

    ids = [s.deneme_id for s in sonuclar]
    sinif_netleri: dict[tuple[int, str], list[Decimal]] = {}
    for satir in DenemeBransSonucu.objects.filter(
        _sinif_brans(talebe), sonuc__deneme_id__in=ids
    ).values("sonuc__deneme_id", "brans", "net"):
        anahtar = (satir["sonuc__deneme_id"], satir["brans"])
        sinif_netleri.setdefault(anahtar, [])
        sinif_netleri[anahtar].append(Decimal(satir["net"] or 0))

    ders_toplam: dict[str, dict] = {}
    for kod, etiket in DENEME_KARNE_DERSLERI:
        ders_toplam[kod] = {
            "ad": etiket.title() if etiket.isupper() else etiket,
            "dogru": 0,
            "yanlis": 0,
            "bos": 0,
            "netler": [],
            "sinif_netler": [],
        }
    # Karne etiketleri büyük harf. Raporda okunur başlık.
    _okunur = {
        "turkce": "Türkçe",
        "sosyal": "Sosyal Bilgiler",
        "din": "Din Kültürü",
        "ingilizce": "İngilizce",
        "matematik": "Matematik",
        "fen": "Fen Bilimleri",
    }
    for kod, kova in ders_toplam.items():
        kova["ad"] = _okunur.get(kod, kova["ad"])

    for sonuc in sonuclar:
        for brans in sonuc.brans_satirlari.all():
            kova = ders_toplam.get(brans.brans)
            if kova is None:
                continue
            kova["dogru"] += int(brans.dogru or 0)
            kova["yanlis"] += int(brans.yanlis or 0)
            kova["bos"] += int(brans.bos or 0)
            kova["netler"].append(Decimal(brans.net or 0))
            sinif_liste = sinif_netleri.get((sonuc.deneme_id, brans.brans))
            sinif_ort = _ort(sinif_liste) if sinif_liste else None
            if sinif_ort is not None:
                kova["sinif_netler"].append(sinif_ort)

    dersler = []
    for kod, _etiket in DENEME_KARNE_DERSLERI:
        kova = ders_toplam[kod]
        if not kova["netler"] and kova["dogru"] + kova["yanlis"] + kova["bos"] == 0:
            continue
        net = _ort(kova["netler"])
        sinif_net = _ort(kova["sinif_netler"])
        toplam = kova["dogru"] + kova["yanlis"] + kova["bos"]
        durum = ""
        if net is not None and sinif_net is not None and net != sinif_net:
            durum = "iyi" if net > sinif_net else "geri"
        dersler.append(
            {
                "ad": kova["ad"],
                "net": tr_ondalik(net) if net is not None else "—",
                "sinif_net": tr_ondalik(sinif_net) if sinif_net is not None else "—",
                "durum": durum,
                "dogru": kova["dogru"],
                "yanlis": kova["yanlis"],
                "bos": kova["bos"],
                "dogru_yuzde": _yuzde(kova["dogru"], toplam),
            }
        )

    soru_var_ids = set(
        DenemeSoruSonucu.objects.filter(deneme_id__in=ids, talebe=talebe)
        .values_list("deneme_id", flat=True)
        .distinct()
    )
    denemeler = [
        {
            "ad": s.deneme.ad,
            "tarih": s.deneme.sinav_tarihi,
            "net": tr_ondalik(s.toplam_net),
            "soru_karnesi": s.deneme_id in soru_var_ids,
        }
        for s in sonuclar
    ]

    konular, kayiplar = _konu_dokumu(talebe, ids, _sinif_soru(talebe))
    sube = getattr(talebe, "sinif_sube", None)
    sinif_yazi = str(sube) if sube is not None else (talebe.sinif or "—")
    return {
        "ad_soyad": talebe.ad_soyad,
        "sinif": sinif_yazi,
        "no": (talebe.talebe_no or "").strip(),
        "denemeler": denemeler,
        "baslangic": sonuclar[0].deneme.sinav_tarihi,
        "bitis": sonuclar[-1].deneme.sinav_tarihi,
        "ortalama_net": tr_ondalik(_ort([Decimal(s.toplam_net or 0) for s in sonuclar])),
        "dersler": dersler,
        "kayiplar": kayiplar,
        "konular": konular,
    }


def _konu_dokumu(talebe: Talebe, ids: list[int], sinif: Q):
    kendi: dict[tuple, dict] = {}
    for kayit in DenemeSoruSonucu.objects.filter(deneme_id__in=ids, talebe=talebe).only(
        "ders_key", "ders_ad", "konu_ad", "sonuc"
    ):
        kod = _ders_kodu(kayit.ders_key, kayit.ders_ad)
        konu = (kayit.konu_ad or "").strip() or "Belirtilmemiş"
        anahtar = (kod, konu.casefold())
        kova = kendi.get(anahtar)
        if kova is None:
            kova = {
                "kod": kod,
                "ders": _ders_baslik(kod, kayit.ders_ad),
                "konu": konu,
                "dogru": 0,
                "yanlis": 0,
                "bos": 0,
            }
            kendi[anahtar] = kova
        if kayit.sonuc == DenemeSoruSonucu.Sonuc.DOGRU:
            kova["dogru"] += 1
        elif kayit.sonuc == DenemeSoruSonucu.Sonuc.YANLIS:
            kova["yanlis"] += 1
        else:
            kova["bos"] += 1

    sinif_kova: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for kayit in (
        DenemeSoruSonucu.objects.filter(sinif, deneme_id__in=ids)
        .only("ders_key", "ders_ad", "konu_ad", "sonuc")
    ):
        kod = _ders_kodu(kayit.ders_key, kayit.ders_ad)
        konu = (kayit.konu_ad or "").strip() or "Belirtilmemiş"
        anahtar = (kod, konu.casefold())
        sinif_kova[anahtar][1] += 1
        if kayit.sonuc == DenemeSoruSonucu.Sonuc.DOGRU:
            sinif_kova[anahtar][0] += 1

    satirlar = []
    for kova in kendi.values():
        toplam = kova["dogru"] + kova["yanlis"] + kova["bos"]
        yuzde = _yuzde(kova["dogru"], toplam)
        sinif_cift = sinif_kova.get((kova["kod"], kova["konu"].casefold()))
        sinif_yuzde = _yuzde(sinif_cift[0], sinif_cift[1]) if sinif_cift else None
        satirlar.append(
            {
                **kova,
                "soru": toplam,
                "yuzde": yuzde,
                "sinif_yuzde": sinif_yuzde,
                "net": DenemeBransSonucu.net_hesapla(kova["dogru"], kova["yanlis"]),
            }
        )

    gruplar: dict[str, dict] = {}
    for satir in satirlar:
        grup = gruplar.get(satir["kod"])
        if grup is None:
            grup = {"kod": satir["kod"], "ders": satir["ders"], "satirlar": []}
            gruplar[satir["kod"]] = grup
        grup["satirlar"].append(satir)
    for grup in gruplar.values():
        grup["satirlar"].sort(
            key=lambda s: (
                s["yuzde"] is None,
                s["yuzde"] if s["yuzde"] is not None else 0,
                s["konu"],
            )
        )
    konular = sorted(
        gruplar.values(),
        key=lambda g: (_DERS_SIRA.get(g["kod"], 50), g["ders"]),
    )

    kayiplar = []
    for satir in satirlar:
        kacirilan = satir["yanlis"] + satir["bos"]
        if kacirilan <= 0:
            continue
        kaynak = "yanlıştan" if satir["yanlis"] >= satir["bos"] else "boştan"
        kayiplar.append({**satir, "kaynak": kaynak, "kacirilan": kacirilan})
    kayiplar.sort(key=lambda s: (-s["kacirilan"], s["yuzde"] if s["yuzde"] is not None else 0))
    return konular, kayiplar[:5]
