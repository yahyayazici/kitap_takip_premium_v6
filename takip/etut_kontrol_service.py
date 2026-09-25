"""Etüt Kontrol — kazanım Excel verisi üzerinden grafik / dikkat / kutular."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg, Count, Q

from takip.deneme_models import DenemeKazanimSonucu, DenemeSinavi, DenemeSonucu
from takip.etut_zimmet_service import etut_mesul_queryset, hoca_talebe_q
from takip.models import EtutHocasi, Talebe
from takip.user_helpers import etut_hocasi_for_user

ZAYIF_ESIK = Decimal("70")


def _avg_or_none(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(float(value), 2)))


def _trend(values: list[float | None]) -> str:
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "→"
    delta = clean[-1] - clean[-2]
    if delta >= 1.5:
        return "↑"
    if delta <= -1.5:
        return "↓"
    return "→"


def kullanici_etut_hocalari(user) -> list[EtutHocasi]:
    """Giriş yapan için görülebilir etüt/mesul listesi."""
    if not user.is_authenticated:
        return []
    if user.is_superuser or user.is_staff:
        return list(etut_mesul_queryset()[:50]) or list(
            EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad")[:50]
        )
    own = etut_hocasi_for_user(user)
    if own:
        return [own]
    return list(etut_mesul_queryset()[:50])


def hoca_talebe_ids(hoca: EtutHocasi) -> list[int]:
    return list(
        Talebe.objects.filter(aktif=True)
        .filter(hoca_talebe_q(hoca))
        .values_list("id", flat=True)
    )


def hoca_seviye_kirilimi(hoca: EtutHocasi) -> dict:
    """Hocanın talebelerini seviye ve şubeye ayırır. Varsayılan en kalabalık seviyedir."""
    talebeler = (
        Talebe.objects.filter(aktif=True)
        .filter(hoca_talebe_q(hoca))
        .select_related("sinif_sube")
    )
    gruplar: dict[tuple[str, str], list[int]] = {}
    for talebe in talebeler:
        sinif = ""
        sube = ""
        if talebe.sinif_sube_id:
            sinif = talebe.sinif_sube.sinif or ""
            sube = talebe.sinif_sube.sube or ""
        sinif = sinif or (talebe.sinif or "")
        sube = sube or (talebe.sube or "")
        gruplar.setdefault((str(sinif), str(sube)), []).append(talebe.id)
    by_seviye: dict[str, list[tuple[str, list[int]]]] = {}
    for (sinif, sube), ids in gruplar.items():
        by_seviye.setdefault(sinif, []).append((sube, ids))
    if not by_seviye:
        return {"seviye": "", "etiket": "Genel", "genel_ids": [], "subeler": []}
    seviye = max(by_seviye, key=lambda s: sum(len(ids) for _, ids in by_seviye[s]))
    subeler = []
    genel_ids: list[int] = []
    for sube, ids in sorted(by_seviye[seviye], key=lambda row: row[0]):
        etiket = f"{seviye}-{sube}".strip("-") if sube else (seviye or "Genel")
        subeler.append({"etiket": etiket, "ids": ids})
        genel_ids.extend(ids)
    etiket = f"{seviye}. sınıf" if seviye else "Genel"
    return {
        "seviye": seviye,
        "etiket": etiket,
        "genel_ids": genel_ids,
        "subeler": subeler,
    }


def hoca_baskin_sinif_etiket(hoca: EtutHocasi) -> str:
    row = (
        Talebe.objects.filter(aktif=True)
        .filter(hoca_talebe_q(hoca))
        .values("sinif_sube__sinif", "sinif_sube__sube")
        .annotate(n=Count("id"))
        .order_by("-n")
        .first()
    )
    if not row:
        return ""
    sinif = row.get("sinif_sube__sinif") or ""
    sube = row.get("sinif_sube__sube") or ""
    return f"{sinif}-{sube}".strip("-")


def _puanli_sonuclar():
    """Puanı boş ya da hiç işaretlenmemiş satır ortalamaya girmez."""
    return DenemeSonucu.objects.exclude(
        puan=0,
        toplam_dogru=0,
        toplam_yanlis=0,
        toplam_bos=0,
        toplam_net=0,
    )


def deneme_ortalama(deneme: DenemeSinavi, talebe_ids: list[int]) -> Decimal | None:
    """Etüt talebelerinin 500 üzerinden puan ortalaması. Katılmayan talebe yok sayılır."""
    if not talebe_ids:
        return None
    agg = _puanli_sonuclar().filter(
        deneme=deneme,
        talebe_id__in=talebe_ids,
    ).aggregate(avg=Avg("puan"))
    return _avg_or_none(agg["avg"])


def sinif_deneme_ortalama(deneme: DenemeSinavi, sinif_etiket: str) -> Decimal | None:
    if not sinif_etiket:
        return None
    parts = sinif_etiket.replace(" ", "").split("-")
    qs = _puanli_sonuclar().filter(
        deneme=deneme,
        talebe__aktif=True,
    )
    if len(parts) >= 2:
        qs = qs.filter(
            talebe__sinif_sube__sinif=parts[0],
            talebe__sinif_sube__sube=parts[1],
        )
    else:
        qs = qs.filter(
            Q(talebe__sinif_sube__sinif=sinif_etiket)
            | Q(talebe__sinif__icontains=sinif_etiket)
        )
    return _avg_or_none(qs.aggregate(avg=Avg("puan"))["avg"])


def etut_gelisim_serisi(hoca: EtutHocasi) -> dict:
    ids = hoca_talebe_ids(hoca)
    sinif_ad = hoca_baskin_sinif_etiket(hoca)
    denemeler = list(
        DenemeSinavi.objects.filter(
            durum=DenemeSinavi.Durum.AKTIF,
            sonuclar__talebe_id__in=ids,
        )
        .distinct()
        .order_by("sinav_tarihi", "id")
    )
    labels, etut, sinif, tarihler = [], [], [], []
    for i, d in enumerate(denemeler, start=1):
        labels.append(f"{i}. Deneme")
        tarihler.append(d.sinav_tarihi.isoformat() if d.sinav_tarihi else "")
        etut.append(
            float(v) if (v := deneme_ortalama(d, ids)) is not None else None
        )
        sinif.append(
            float(v) if (v := sinif_deneme_ortalama(d, sinif_ad)) is not None else None
        )
    return {
        "labels": labels,
        "etut": etut,
        "sinif": sinif,
        "sinif_ad": sinif_ad,
        "tarihler": tarihler,
        "trend": _trend(etut),
    }


def etut_deneme_kutulari(hoca: EtutHocasi) -> list[dict]:
    ids = hoca_talebe_ids(hoca)
    sinif_ad = hoca_baskin_sinif_etiket(hoca)
    denemeler = list(
        DenemeSinavi.objects.filter(
            durum=DenemeSinavi.Durum.AKTIF,
            kazanim_sonuclari__talebe_id__in=ids,
        )
        .distinct()
        .order_by("-sinav_tarihi", "-id")
    )
    ortalamalar = []
    for d in denemeler:
        ortalamalar.append(deneme_ortalama(d, ids))

    kutular = []
    for i, d in enumerate(denemeler):
        etut_ort = ortalamalar[i]
        onceki = ortalamalar[i + 1] if i + 1 < len(ortalamalar) else None
        trend_vals = [
            float(onceki) if onceki is not None else None,
            float(etut_ort) if etut_ort is not None else None,
        ]
        zayif = (
            DenemeKazanimSonucu.objects.filter(
                deneme=d,
                talebe_id__in=ids,
                yuzde__isnull=False,
                yuzde__lt=ZAYIF_ESIK,
            )
            .values("ders_key", "konu_key")
            .distinct()
            .count()
        )
        kutular.append(
            {
                "deneme": d,
                "etut_ortalama": etut_ort,
                "sinif_ortalama": sinif_deneme_ortalama(d, sinif_ad),
                "zayif_konu": zayif,
                "trend": _trend(trend_vals),
            }
        )
    return kutular


def _kazanimli_denemeler(ids: list[int]) -> list[DenemeSinavi]:
    if not ids:
        return []
    return list(
        DenemeSinavi.objects.filter(
            durum=DenemeSinavi.Durum.AKTIF,
            kazanim_sonuclari__talebe_id__in=ids,
        )
        .distinct()
        .order_by("-sinav_tarihi", "-id")
    )


def etut_gorunum_serisi(hoca: EtutHocasi, kirilim: dict, ayrim: bool) -> dict:
    """Seviye geneli tek çizgi; ayrımda şube başına bir çizgi."""
    ids = kirilim.get("genel_ids") or hoca_talebe_ids(hoca)
    denemeler = []
    if ids:
        denemeler = list(
            DenemeSinavi.objects.filter(
                durum=DenemeSinavi.Durum.AKTIF,
                sonuclar__talebe_id__in=ids,
            )
            .distinct()
            .order_by("sinav_tarihi", "id")
        )
    labels, tarihler = [], []
    for i, deneme in enumerate(denemeler, start=1):
        labels.append(f"{i}. Deneme")
        tarihler.append(deneme.sinav_tarihi.isoformat() if deneme.sinav_tarihi else "")

    def _cizgi(id_list: list[int]) -> list[float | None]:
        out = []
        for deneme in denemeler:
            ortalama = deneme_ortalama(deneme, id_list)
            out.append(float(ortalama) if ortalama is not None else None)
        return out

    subeler = kirilim.get("subeler") or []
    if ayrim and len(subeler) > 1:
        seriler = [{"ad": s["etiket"], "degerler": _cizgi(s["ids"])} for s in subeler]
    else:
        seriler = [{"ad": kirilim.get("etiket") or "Genel", "degerler": _cizgi(ids)}]
    return {"labels": labels, "tarihler": tarihler, "seriler": seriler}


def etut_dikkat(hoca: EtutHocasi, talebe_ids: list[int] | None = None, subeler: list[dict] | None = None) -> dict:
    ids = hoca_talebe_ids(hoca) if talebe_ids is None else talebe_ids
    sinif_ad = hoca_baskin_sinif_etiket(hoca)
    kazanimli = _kazanimli_denemeler(ids)
    son = kazanimli[0] if kazanimli else None
    onceki = kazanimli[1] if len(kazanimli) > 1 else None
    zayif_konular = []
    if son:
        rows = (
            DenemeKazanimSonucu.objects.filter(
                deneme=son,
                talebe_id__in=ids,
                yuzde__isnull=False,
            )
            .values("ders_ad", "konu_ad", "ders_key", "konu_key")
            .annotate(ortalama=Avg("yuzde"), katilim=Count("id"))
            .order_by("ortalama")
        )
        for row in rows:
            ort = _avg_or_none(row["ortalama"])
            siniflar = []
            if subeler:
                for sube in subeler:
                    s_ort = _avg_or_none(
                        DenemeKazanimSonucu.objects.filter(
                            deneme=son,
                            talebe_id__in=sube["ids"],
                            ders_key=row["ders_key"],
                            konu_key=row["konu_key"],
                            yuzde__isnull=False,
                        ).aggregate(avg=Avg("yuzde"))["avg"]
                    )
                    siniflar.append({"etiket": sube["etiket"], "ortalama": s_ort})
                zayif_mi = any(
                    s["ortalama"] is not None and s["ortalama"] < ZAYIF_ESIK for s in siniflar
                ) or (ort is not None and ort < ZAYIF_ESIK)
                if not zayif_mi:
                    continue
            else:
                if ort is None or ort >= ZAYIF_ESIK:
                    continue
            sinif_ort = None
            if sinif_ad and not subeler:
                srows = DenemeKazanimSonucu.objects.filter(
                    deneme=son,
                    ders_key=row["ders_key"],
                    konu_key=row["konu_key"],
                    yuzde__isnull=False,
                    talebe__aktif=True,
                )
                parts = sinif_ad.replace(" ", "").split("-")
                if len(parts) >= 2:
                    srows = srows.filter(
                        talebe__sinif_sube__sinif=parts[0],
                        talebe__sinif_sube__sube=parts[1],
                    )
                sinif_ort = _avg_or_none(srows.aggregate(avg=Avg("yuzde"))["avg"])
            zayif_konular.append(
                {
                    "ders": row["ders_ad"],
                    "konu": row["konu_ad"],
                    "ders_key": row["ders_key"],
                    "konu_key": row["konu_key"],
                    "ortalama": ort,
                    "sinif_ortalama": sinif_ort,
                    "siniflar": siniflar,
                    "zayif": True,
                }
            )
            if len(zayif_konular) >= 12:
                break

    dusen = []
    if son is not None and onceki is not None:
        yeni, eski = son, onceki
        for tid in ids:
            y = deneme_ortalama(yeni, [tid])
            e = deneme_ortalama(eski, [tid])
            if y is None or e is None:
                continue
            delta = float(y) - float(e)
            if delta <= -3:
                talebe = Talebe.objects.filter(pk=tid).first()
                if talebe:
                    dusen.append(
                        {
                            "talebe": talebe,
                            "eski": e,
                            "yeni": y,
                            "delta": round(delta, 1),
                        }
                    )
        dusen.sort(key=lambda r: r["delta"])
        dusen = dusen[:10]

    return {
        "deneme": son,
        "onceki_deneme": onceki,
        "zayif_konular": zayif_konular,
        "dusen_talebeler": dusen,
        "ayrim": bool(subeler),
        "sube_adlari": [s["etiket"] for s in (subeler or [])],
    }


def etut_deneme_siralamasi(hoca: EtutHocasi, deneme: DenemeSinavi) -> list[dict]:
    ids = hoca_talebe_ids(hoca)
    rows = (
        DenemeKazanimSonucu.objects.filter(
            deneme=deneme,
            talebe_id__in=ids,
            yuzde__isnull=False,
        )
        .values(
            "talebe_id",
            "talebe__ad_soyad",
            "talebe__sinif_sube__sinif",
            "talebe__sinif_sube__sube",
        )
        .annotate(ortalama=Avg("yuzde"), konu_sayisi=Count("id"))
        .order_by("-ortalama")
    )
    out = []
    for i, row in enumerate(rows, start=1):
        sinif = row.get("talebe__sinif_sube__sinif") or ""
        sube = row.get("talebe__sinif_sube__sube") or ""
        out.append(
            {
                "sira": i,
                "talebe_id": row["talebe_id"],
                "ad_soyad": row["talebe__ad_soyad"],
                "sinif": f"{sinif}-{sube}".strip("-"),
                "ortalama": _avg_or_none(row["ortalama"]),
                "konu_sayisi": row["konu_sayisi"],
            }
        )
    return out


def deneme_alt_baslik(deneme: DenemeSinavi, talebe_ids: list[int]) -> dict:
    """Tek denemenin kazanım ve talebe özeti — mevcut sıralamanın alt başlıkları."""
    if not talebe_ids:
        return {"kazanimlar": [], "talebeler": []}
    kazanimlar = (
        DenemeKazanimSonucu.objects.filter(
            deneme=deneme,
            talebe_id__in=talebe_ids,
            yuzde__isnull=False,
        )
        .values("ders_ad", "konu_ad")
        .annotate(ortalama=Avg("yuzde"), talebe_sayisi=Count("talebe_id", distinct=True))
        .order_by("ders_ad", "konu_ad")
    )
    kazanim_satir = [
        {
            "ders": r["ders_ad"],
            "konu": r["konu_ad"],
            "ortalama": _avg_or_none(r["ortalama"]),
            "talebe_sayisi": r["talebe_sayisi"],
            "zayif": r["ortalama"] is not None and Decimal(str(r["ortalama"])) < ZAYIF_ESIK,
        }
        for r in kazanimlar
    ]
    ham = DenemeKazanimSonucu.objects.filter(
        deneme=deneme, talebe_id__in=talebe_ids
    ).order_by("yuzde", "ders_ad", "konu_ad")
    kazanim_harita: dict[int, list] = {}
    for k in ham:
        kazanim_harita.setdefault(k.talebe_id, []).append(
            {
                "ders": k.ders_ad,
                "konu": k.konu_ad,
                "yuzde": k.yuzde,
                "net_dogru": k.net_dogru,
                "net_toplam": k.net_toplam,
                "zayif": k.yuzde is not None and k.yuzde < ZAYIF_ESIK,
            }
        )
    talebeler = []
    for tid in talebe_ids:
        ort = deneme_ortalama(deneme, [tid])
        satirlar = kazanim_harita.get(tid, [])
        talebe = Talebe.objects.filter(pk=tid).first()
        if talebe is None:
            continue
        talebeler.append(
            {
                "talebe": talebe,
                "puan": ort,
                "zayif_sayisi": sum(1 for s in satirlar if s["zayif"]),
                "kazanimlar": satirlar,
            }
        )
    talebeler.sort(key=lambda r: (r["puan"] is None, -(float(r["puan"] or 0))))
    return {"kazanimlar": kazanim_satir, "talebeler": talebeler}


def etut_konu_ozeti(hoca: EtutHocasi, deneme: DenemeSinavi, talebe_ids: list[int] | None = None, subeler: list[dict] | None = None) -> list[dict]:
    ids = hoca_talebe_ids(hoca) if talebe_ids is None else talebe_ids
    rows = (
        DenemeKazanimSonucu.objects.filter(
            deneme=deneme,
            talebe_id__in=ids,
            yuzde__isnull=False,
        )
        .values("ders_ad", "konu_ad", "ders_key", "konu_key")
        .annotate(ortalama=Avg("yuzde"), talebe_sayisi=Count("talebe_id", distinct=True))
        .order_by("ders_ad", "konu_ad")
    )
    sonuc = []
    for r in rows:
        siniflar = []
        if subeler:
            for sube in subeler:
                siniflar.append(
                    {
                        "etiket": sube["etiket"],
                        "ortalama": _avg_or_none(
                            DenemeKazanimSonucu.objects.filter(
                                deneme=deneme,
                                talebe_id__in=sube["ids"],
                                ders_key=r["ders_key"],
                                konu_key=r["konu_key"],
                                yuzde__isnull=False,
                            ).aggregate(avg=Avg("yuzde"))["avg"]
                        ),
                    }
                )
        sonuc.append(
            {
                "ders": r["ders_ad"],
                "konu": r["konu_ad"],
                "ders_key": r["ders_key"],
                "konu_key": r["konu_key"],
                "ortalama": _avg_or_none(r["ortalama"]),
                "talebe_sayisi": r["talebe_sayisi"],
                "siniflar": siniflar,
                "zayif": r["ortalama"] is not None
                and Decimal(str(r["ortalama"])) < ZAYIF_ESIK,
            }
        )
    return sonuc


def etut_talebe_kutulari(hoca: EtutHocasi) -> list[dict]:
    talebeler = list(
        Talebe.objects.filter(aktif=True)
        .filter(hoca_talebe_q(hoca))
        .select_related("sinif_sube")
        .order_by("ad_soyad")
    )
    denemeler = list(
        DenemeSinavi.objects.filter(durum=DenemeSinavi.Durum.AKTIF).order_by(
            "-sinav_tarihi", "-id"
        )
    )
    kutular = []
    for t in talebeler:
        orts = []
        zayif_son = 0
        for d in denemeler:
            ort = deneme_ortalama(d, [t.id])
            if ort is not None:
                orts.append(ort)
            if not zayif_son and ort is not None:
                zayif_son = DenemeKazanimSonucu.objects.filter(
                    deneme=d,
                    talebe=t,
                    yuzde__lt=ZAYIF_ESIK,
                ).count()
        son = orts[0] if orts else None
        onceki = orts[1] if len(orts) > 1 else None
        kutular.append(
            {
                "talebe": t,
                "son_ortalama": son,
                "trend": _trend(
                    [
                        float(onceki) if onceki is not None else None,
                        float(son) if son is not None else None,
                    ]
                ),
                "zayif_sayisi": zayif_son,
                "deneme_sayisi": len(orts),
                "seri": [float(v) for v in reversed(orts)],
                "fark": (son - onceki) if son is not None and onceki is not None else None,
            }
        )
    return kutular


def talebe_gelisim_serisi(talebe: Talebe) -> dict:
    """Sınıfın girdiği denemeler eksende kalır. Katılmayan deneme boşluktur, 0 değildir."""
    kapsam = DenemeSinavi.objects.filter(durum=DenemeSinavi.Durum.AKTIF)
    if talebe.sinif_sube_id:
        kapsam = kapsam.filter(sonuclar__talebe__sinif_sube=talebe.sinif_sube)
    else:
        kapsam = kapsam.filter(sonuclar__talebe=talebe)
    denemeler = list(kapsam.distinct().order_by("sinav_tarihi", "id"))
    labels, puanlar, tarihler = [], [], []
    for i, d in enumerate(denemeler, start=1):
        labels.append(f"{i}. Deneme")
        tarihler.append(d.sinav_tarihi.isoformat() if d.sinav_tarihi else "")
        v = deneme_ortalama(d, [talebe.id])
        puanlar.append(float(v) if v is not None else None)
    return {
        "labels": labels,
        "puanlar": puanlar,
        "tarihler": tarihler,
        "son_ortalama": (
            Decimal(str(puanlar[-1])) if puanlar and puanlar[-1] is not None else None
        ),
        "trend": _trend(puanlar),
    }


def talebe_deneme_kutulari(talebe: Talebe) -> list[dict]:
    denemeler = list(
        DenemeSinavi.objects.filter(
            durum=DenemeSinavi.Durum.AKTIF,
            kazanim_sonuclari__talebe=talebe,
        )
        .distinct()
        .order_by("-sinav_tarihi", "-id")
    )
    kutular = []
    onceki_ort = None
    # chronological for trend then reverse display
    chrono = list(reversed(denemeler))
    ort_map = {}
    for d in chrono:
        ort_map[d.id] = deneme_ortalama(d, [talebe.id])

    for d in denemeler:
        ort = ort_map.get(d.id)
        # find previous in chrono
        idx = chrono.index(d)
        prev = ort_map.get(chrono[idx - 1].id) if idx > 0 else None
        kazanimlar = list(
            DenemeKazanimSonucu.objects.filter(deneme=d, talebe=talebe).order_by(
                "yuzde", "ders_ad", "konu_ad"
            )
        )
        zayiflar = [
            {
                "ders": k.ders_ad,
                "konu": k.konu_ad,
                "yuzde": k.yuzde,
                "zayif": k.yuzde is not None and k.yuzde < ZAYIF_ESIK,
            }
            for k in kazanimlar
            if k.yuzde is not None and k.yuzde < ZAYIF_ESIK
        ]
        rows = [
            {
                "ders": k.ders_ad,
                "konu": k.konu_ad,
                "yuzde": k.yuzde,
                "net_dogru": k.net_dogru,
                "net_toplam": k.net_toplam,
                "zayif": k.yuzde is not None and k.yuzde < ZAYIF_ESIK,
            }
            for k in sorted(
                kazanimlar,
                key=lambda x: (
                    0 if (x.yuzde is not None and x.yuzde < ZAYIF_ESIK) else 1,
                    float(x.yuzde) if x.yuzde is not None else 999,
                    x.ders_ad,
                    x.konu_ad,
                ),
            )
        ]
        kutular.append(
            {
                "deneme": d,
                "ortalama": ort,
                "trend": _trend(
                    [
                        float(prev) if prev is not None else None,
                        float(ort) if ort is not None else None,
                    ]
                ),
                "fark": (ort - prev) if ort is not None and prev is not None else None,
                "zayif_sayisi": len(zayiflar),
                "zayiflar": zayiflar[:15],
                "kazanimlar": rows,
                "konu_sayisi": len(kazanimlar),
            }
        )
    return kutular
