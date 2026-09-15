"""Analitik Okuma ortalamaları ve oturum özeti — dinamik hesap."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, QuerySet

from takip.analitik_okuma import (
    ANALITIK_OKUMA_KOD,
    AnalitikAlan,
    AnalitikKayitDurumu,
    bir_ondalik,
)
from takip.models import Ders, Talebe
from takip.ogretmen_not_models import OgretmenHaftalikKonu, OgretmenSinavNotu


def analitik_ders_q() -> Q:
    return Q(ders__kod=ANALITIK_OKUMA_KOD) | Q(ders__ad__iexact="Analitik Okuma")


def analitik_dersler() -> QuerySet[Ders]:
    return Ders.objects.filter(
        Q(kod=ANALITIK_OKUMA_KOD) | Q(ad__iexact="Analitik Okuma")
    )


def _tamamlanan_not_qs(talebe: Talebe) -> QuerySet[OgretmenSinavNotu]:
    return OgretmenSinavNotu.objects.filter(
        analitik_ders_q(),
        talebe=talebe,
        veliye_goster=True,
    )


def kavram_ortalamasi(talebe: Talebe, *, ders: Ders | None = None) -> Decimal | None:
    qs = _tamamlanan_not_qs(talebe).filter(kavram_puani__isnull=False)
    if ders is not None:
        qs = qs.filter(ders=ders)
    degerler = list(qs.values_list("kavram_puani", flat=True))
    if not degerler:
        return None
    return (sum(Decimal(v) for v in degerler) / len(degerler))


def kavram_ortalamasi_etiket(talebe: Talebe, *, ders: Ders | None = None) -> str | None:
    ham = kavram_ortalamasi(talebe, ders=ders)
    gosterim = bir_ondalik(ham)
    return f"{gosterim}/10" if gosterim else None


def analitik_genel_ortalama(talebe: Talebe) -> Decimal | None:
    qs = _tamamlanan_not_qs(talebe).filter(puan__isnull=False)
    degerler = list(qs.values_list("puan", flat=True))
    if not degerler:
        return None
    return (sum(degerler) / len(degerler)).quantize(Decimal("0.01"))


def _konu_map_for_notes(notlar: list[OgretmenSinavNotu]) -> dict[tuple, OgretmenHaftalikKonu]:
    if not notlar:
        return {}
    talebe = notlar[0].talebe
    sinif_id = talebe.sinif_sube_id
    if not sinif_id:
        return {}
    keys = {(n.etut_hocasi_id, n.ders_id, n.hafta_baslangic) for n in notlar}
    konular = OgretmenHaftalikKonu.objects.filter(
        sinif_sube_id=sinif_id,
        durum=AnalitikKayitDurumu.TAMAMLANDI,
    )
    out = {}
    for k in konular:
        anahtar = (k.etut_hocasi_id, k.ders_id, k.hafta_baslangic)
        if anahtar in keys:
            out[anahtar] = k
    return out


def talebe_analitik_alan_ozeti(talebe: Talebe) -> list[dict]:
    notlar = list(
        _tamamlanan_not_qs(talebe)
        .filter(puan__isnull=False)
        .select_related("ders", "talebe")
    )
    konu_map = _konu_map_for_notes(notlar)
    kova: dict[str, list[Decimal]] = {kod: [] for kod, _ in AnalitikAlan.choices}
    for n in notlar:
        konu = konu_map.get((n.etut_hocasi_id, n.ders_id, n.hafta_baslangic))
        if not konu or not konu.analitik_alan:
            continue
        if konu.analitik_alan in kova and n.puan is not None:
            kova[konu.analitik_alan].append(n.puan)

    satirlar = []
    for kod, etiket in AnalitikAlan.choices:
        puanlar = kova[kod]
        ort = None
        if puanlar:
            ort = (sum(puanlar) / len(puanlar)).quantize(Decimal("0.01"))
        satirlar.append(
            {
                "kod": kod,
                "etiket": etiket,
                "ortalama": ort,
                "ortalama_etiket": f"{ort}/100" if ort is not None else None,
                "adet": len(puanlar),
            }
        )
    return satirlar


def kavram_onerileri(*, limit: int = 24) -> list[str]:
    seen: list[str] = []
    qs = (
        OgretmenHaftalikKonu.objects.exclude(haftanin_kavrami="")
        .filter(analitik_ders_q())
        .order_by("-guncellenme")
        .values_list("haftanin_kavrami", flat=True)
    )
    for ad in qs:
        temiz = (ad or "").strip()
        if temiz and temiz not in seen:
            seen.append(temiz)
        if len(seen) >= limit:
            break
    return seen


def analitik_oturum_ozetleri(
    *,
    hafta_baslangic=None,
    tarih_bas=None,
    tarih_bit=None,
    hoca_id: int | None = None,
    sinif_id: int | None = None,
    alan: str = "",
    durum: str = "",
) -> list[dict]:
    qs = OgretmenHaftalikKonu.objects.filter(analitik_ders_q()).select_related(
        "sinif_sube", "etut_hocasi", "ders"
    )
    if hafta_baslangic:
        qs = qs.filter(hafta_baslangic=hafta_baslangic)
    if tarih_bas:
        qs = qs.filter(hafta_baslangic__gte=tarih_bas)
    if tarih_bit:
        qs = qs.filter(hafta_baslangic__lte=tarih_bit)
    if hoca_id:
        qs = qs.filter(etut_hocasi_id=hoca_id)
    if sinif_id:
        qs = qs.filter(sinif_sube_id=sinif_id)
    if alan:
        qs = qs.filter(analitik_alan=alan)
    if durum:
        qs = qs.filter(durum=durum)

    oturumlar = list(qs.order_by("-hafta_baslangic", "sinif_sube__sinif", "etut_hocasi__ad_soyad"))
    if not oturumlar:
        return []

    notlar = list(
        OgretmenSinavNotu.objects.filter(
            analitik_ders_q(),
            etut_hocasi_id__in={o.etut_hocasi_id for o in oturumlar},
            ders_id__in={o.ders_id for o in oturumlar},
            hafta_baslangic__in={o.hafta_baslangic for o in oturumlar},
        ).select_related("talebe")
    )
    by_key: dict[tuple, list[OgretmenSinavNotu]] = defaultdict(list)
    for n in notlar:
        by_key[(n.etut_hocasi_id, n.ders_id, n.hafta_baslangic, n.talebe.sinif_sube_id)].append(n)

    satirlar = []
    for o in oturumlar:
        grup = by_key.get(
            (o.etut_hocasi_id, o.ders_id, o.hafta_baslangic, o.sinif_sube_id),
            [],
        )
        katilan_puan = [n.puan for n in grup if n.puan is not None]
        katilan_kavram = [n.kavram_puani for n in grup if n.kavram_puani is not None]
        gelmeyen = sum(1 for n in grup if n.puan is None and (n.aciklama or "").strip())
        puan_ort = (
            (sum(katilan_puan) / len(katilan_puan)).quantize(Decimal("0.01"))
            if katilan_puan
            else None
        )
        kavram_ort = (
            (sum(Decimal(v) for v in katilan_kavram) / len(katilan_kavram))
            if katilan_kavram
            else None
        )
        satirlar.append(
            {
                "oturum": o,
                "hafta_baslangic": o.hafta_baslangic,
                "ders_tarihi": o.hafta_baslangic,
                "sinif": o.sinif_sube,
                "ogretmen": o.etut_hocasi,
                "alan": o.get_analitik_alan_display() if o.analitik_alan else "—",
                "alan_kod": o.analitik_alan,
                "kavram": o.haftanin_kavrami or "—",
                "durum": o.get_durum_display(),
                "durum_kod": o.durum,
                "degerlendirilen": len(katilan_puan),
                "gelmeyen": gelmeyen,
                "puan_ort": puan_ort,
                "kavram_ort": bir_ondalik(kavram_ort),
                "notlar": grup,
            }
        )
    return satirlar
