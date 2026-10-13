"""Birden çok denemeyi kapsayan raporlar: ortalama listesi, kazanım yüzdesi,
sınıf konu analizi ve gelişim raporu. Hepsi Sonuc / TestSonuc ve
A sırasına çevrilmiş cevaplar (Sonuc.cevaplar_a) üzerinden hesaplanır."""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from okuma.models import Deneme, Ogrenci, Soru, Sonuc
from okuma.services.puanlama import harita_kur

# Gelişim raporu eşikleri (net cinsinden / oran)
YUKSELIS_ESIGI = 3.0
DUSUS_ESIGI = -3.0
RISK_DUSUS_ESIGI = -5.0
RISK_DUSUK_BASARI_ORANI = 0.70
RISK_KATILIM_ORANI = 0.75


def ders_anahtari(test) -> str:
    return test.lgs_ders or test.ders


def secili_denemeler(idler) -> list[Deneme]:
    return list(Deneme.objects.filter(pk__in=[i for i in idler if str(i).isdigit()]).order_by("tarih", "pk"))


def ders_listesi(denemeler: list[Deneme]) -> list[tuple[str, str]]:
    """Denemelerdeki dersler, optik sırasıyla: [(anahtar, ad), ...]."""
    gorulen: dict[str, str] = {}
    for d in denemeler:
        for t in d.testler.order_by("sira"):
            gorulen.setdefault(ders_anahtari(t), t.ders)
    return list(gorulen.items())


def sonuc_listesi(denemeler: list[Deneme], sube: str | None = None) -> list[Sonuc]:
    qs = Sonuc.objects.filter(deneme__in=denemeler).select_related("ogrenci", "deneme").prefetch_related(
        "test_sonuclari__test"
    )
    if sube:
        qs = qs.filter(sube=sube)
    return list(qs)


def _ort(degerler) -> float | None:
    degerler = [v for v in degerler if v is not None]
    return statistics.fmean(degerler) if degerler else None


def _sira_ver(satirlar, anahtar) -> None:
    """Eşit değerler aynı sırayı alır (1, 2, 2, 4)."""
    onceki, sira = object(), 0
    for i, s in enumerate(satirlar, start=1):
        deger = anahtar(s)
        if deger != onceki:
            sira, onceki = i, deger
        s.sira = sira


# ── Ortalama listesi ────────────────────────────────────────────────────────


@dataclass
class OrtalamaSatiri:
    ogrenci: Ogrenci
    sube: str
    deneme_sayisi: int
    dersler: dict[str, tuple[float, float, float]]
    dogru: float
    yanlis: float
    net: float
    puan: float | None
    sira: int = 0


def ortalama_listesi(denemeler, sube=None):
    """Öğrenci başına seçili denemelerdeki ders ve toplam ortalamaları; puana göre sıralı."""
    ogrenciye_gore: dict[int, list[Sonuc]] = defaultdict(list)
    for s in sonuc_listesi(denemeler, sube):
        ogrenciye_gore[s.ogrenci_id].append(s)

    satirlar = []
    for liste in ogrenciye_gore.values():
        toplam = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
        for s in liste:
            for ts in s.test_sonuclari.all():
                a = toplam[ders_anahtari(ts.test)]
                a[0] += ts.dogru
                a[1] += ts.yanlis
                a[2] += float(ts.net)
                a[3] += 1
        son = max(liste, key=lambda s: (s.deneme.tarih, s.deneme_id))
        satirlar.append(
            OrtalamaSatiri(
                ogrenci=son.ogrenci,
                sube=son.sube,
                deneme_sayisi=len(liste),
                dersler={k: (a[0] / a[3], a[1] / a[3], a[2] / a[3]) for k, a in toplam.items()},
                dogru=_ort(s.dogru for s in liste),
                yanlis=_ort(s.yanlis for s in liste),
                net=_ort(float(s.net) for s in liste),
                puan=_ort(float(s.puan) if s.puan is not None else None for s in liste),
            )
        )
    satirlar.sort(key=lambda r: (r.puan if r.puan is not None else -1, r.net), reverse=True)
    _sira_ver(satirlar, lambda r: (r.puan, r.net))

    ortalama = None
    if satirlar:
        anahtarlar = {k for r in satirlar for k in r.dersler}
        ortalama = {
            "dersler": {
                k: tuple(_ort(r.dersler[k][i] for r in satirlar if k in r.dersler) for i in range(3)) for k in anahtarlar
            },
            "dogru": _ort(r.dogru for r in satirlar),
            "yanlis": _ort(r.yanlis for r in satirlar),
            "net": _ort(r.net for r in satirlar),
            "puan": _ort(r.puan for r in satirlar),
        }
    return satirlar, ortalama


# ── Kazanım bazlı sayımlar ─────────────────────────────────────────────────


@dataclass
class KazanimSayim:
    kazanim: object
    ders: str  # ders anahtarı
    ders_adi: str
    soru_sayisi: int = 0
    # öğrenci id → [doğru, yanlış, boş]
    ogrenciler: dict[int, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0, 0]))


def kazanim_sayimlari(denemeler, sube=None):
    """Kazanım × öğrenci doğru/yanlış/boş sayıları ve öğrenci bilgisi (ad, şube)."""
    sayimlar: dict[int, KazanimSayim] = {}
    ogrenci_bilgi: dict[int, tuple[Ogrenci, str]] = {}
    for d in denemeler:
        harita = harita_kur(d)
        testler = {t.pk: t for t in harita.testler}
        soru_kaz = {
            s.pk: list(s.kazanimlar.all())
            for s in Soru.objects.filter(test__deneme=d).prefetch_related("kazanimlar")
        }
        sonuclar = [s for s in sonuc_listesi([d], sube) if s.a_sirali]
        for sonuc in sonuclar:
            ogrenci_bilgi[sonuc.ogrenci_id] = (sonuc.ogrenci, sonuc.sube)
        for sb in harita.sorular:
            if sb.iptal:
                continue
            test = testler[sb.test_id]
            for k in soru_kaz.get(sb.soru_id, []):
                kayit = sayimlar.setdefault(
                    k.pk, KazanimSayim(kazanim=k, ders=ders_anahtari(test), ders_adi=test.ders)
                )
                kayit.soru_sayisi += 1
                for sonuc in sonuclar:
                    c = sonuc.cevaplar_a[sb.a_index]
                    sayac = kayit.ogrenciler[sonuc.ogrenci_id]
                    if c == " ":
                        sayac[2] += 1
                    elif c in sb.dogrular:
                        sayac[0] += 1
                    else:
                        sayac[1] += 1
    return sayimlar, ogrenci_bilgi


def _ders_sirasi(denemeler):
    return {k: i for i, (k, _) in enumerate(ders_listesi(denemeler))}


def kazanim_yuzde_analizi(denemeler, sube=None, alt=0.0, ust=50.0, ders=None, yanlis_katsayi=3):
    """Doğru yüzdesi [alt, ust] aralığında kalan öğrenciler, konu konu.

    Yüzde = doğru ÷ (doğru + yanlış + boş) × 100.
    """
    sayimlar, bilgi = kazanim_sayimlari(denemeler, sube)
    sira = _ders_sirasi(denemeler)
    gruplar = []
    for kayit in sorted(sayimlar.values(), key=lambda x: (sira.get(x.ders, 99), x.kazanim.kod, x.kazanim.metin)):
        if ders and kayit.ders != ders:
            continue
        ogrenciler = []
        for oid, (d, y, b) in kayit.ogrenciler.items():
            toplam = d + y + b
            yuzde = 100 * d / toplam if toplam else 0
            if alt <= yuzde <= ust:
                ogr, sb = bilgi[oid]
                net = d - (y / yanlis_katsayi if yanlis_katsayi else 0)
                ogrenciler.append({"ogrenci": ogr, "sube": sb, "dogru": d, "yanlis": y, "bos": b, "net": net, "toplam": toplam, "yuzde": yuzde})
        if ogrenciler:
            ogrenciler.sort(key=lambda o: (o["yuzde"], o["ogrenci"].ad_soyad))
            gruplar.append({"kayit": kayit, "ogrenciler": ogrenciler})
    return gruplar


def sinif_konu_analizi(denemeler, sube=None):
    """Kazanım × şube doğru yüzdesi tablosu; son sütun kurum geneli."""
    sayimlar, bilgi = kazanim_sayimlari(denemeler, sube)
    sira = _ders_sirasi(denemeler)
    subeler = sorted({sb for _, sb in bilgi.values()})
    satirlar = []
    for kayit in sorted(sayimlar.values(), key=lambda x: (sira.get(x.ders, 99), x.kazanim.kod, x.kazanim.metin)):
        sube_toplam = defaultdict(lambda: [0, 0])
        for oid, (d, y, b) in kayit.ogrenciler.items():
            sb = bilgi[oid][1]
            sube_toplam[sb][0] += d
            sube_toplam[sb][1] += d + y + b
        genel_d = sum(v[0] for v in sube_toplam.values())
        genel_t = sum(v[1] for v in sube_toplam.values())
        satirlar.append(
            {
                "kayit": kayit,
                "subeler": [(100 * sube_toplam[s][0] / sube_toplam[s][1]) if sube_toplam[s][1] else None for s in subeler],
                "genel": 100 * genel_d / genel_t if genel_t else None,
            }
        )
    return subeler, satirlar


# ── Gelişim raporu ─────────────────────────────────────────────────────────


@dataclass
class GelisimSatiri:
    ogrenci: Ogrenci
    sube: str
    netler: list[float | None]  # deneme sırasıyla; girmediği denemede None
    puanlar: list[float | None]
    ort_net: float = 0
    ort_puan: float | None = None
    katilim: float = 0
    trend: float = 0
    kategori: str = "Kararlı"
    riskler: list[str] = field(default_factory=list)
    sira: int = 0


def gelisim_raporu(denemeler, sube=None):
    sonuclar = sonuc_listesi(denemeler, sube)
    sira_no = {d.pk: i for i, d in enumerate(denemeler)}
    n = len(denemeler)

    ogrenciye_gore: dict[int, list[Sonuc]] = defaultdict(list)
    for s in sonuclar:
        ogrenciye_gore[s.ogrenci_id].append(s)

    # Katılım evreni: denemeye giren herkes + o sınıf düzeyindeki (ve şubedeki) aktif öğrenciler.
    seviyeler = {d.sinif_seviyesi for d in denemeler}
    evren = Ogrenci.objects.filter(aktif=True, sinif_seviyesi__in=seviyeler)
    if sube:
        evren = evren.filter(sube=sube)
    girmeyenler = [o for o in evren if o.pk not in ogrenciye_gore]

    satirlar: list[GelisimSatiri] = []
    for liste in ogrenciye_gore.values():
        netler: list[float | None] = [None] * n
        puanlar: list[float | None] = [None] * n
        for s in liste:
            netler[sira_no[s.deneme_id]] = float(s.net)
            puanlar[sira_no[s.deneme_id]] = float(s.puan) if s.puan is not None else None
        son = max(liste, key=lambda s: sira_no[s.deneme_id])
        satirlar.append(GelisimSatiri(ogrenci=son.ogrenci, sube=son.sube, netler=netler, puanlar=puanlar))
    for o in girmeyenler:
        satirlar.append(GelisimSatiri(ogrenci=o, sube=o.sube, netler=[None] * n, puanlar=[None] * n))

    katilan = [r for r in satirlar if any(v is not None for v in r.netler)]
    genel_ort = _ort(float(s.net) for s in sonuclar) or 0

    for r in satirlar:
        mevcut = [v for v in r.netler if v is not None]
        r.katilim = len(mevcut) / n if n else 0
        if not mevcut:
            r.riskler.append("Hiç katılmadı")
            r.kategori = "—"
            continue
        r.ort_net = statistics.fmean(mevcut)
        r.ort_puan = _ort(r.puanlar)
        r.trend = mevcut[-1] - mevcut[-2] if len(mevcut) >= 2 else 0
        if r.trend >= YUKSELIS_ESIGI:
            r.kategori = "Yükselen"
        elif r.trend <= DUSUS_ESIGI:
            r.kategori = "Düşen"
        if r.trend <= RISK_DUSUS_ESIGI:
            r.riskler.append("Sert düşüş")
        if genel_ort and r.ort_net < genel_ort * RISK_DUSUK_BASARI_ORANI:
            r.riskler.append("Düşük başarı")
        if r.katilim < RISK_KATILIM_ORANI:
            r.riskler.append("Devamsızlık")

    katilan.sort(key=lambda r: r.ort_net, reverse=True)
    _sira_ver(katilan, lambda r: round(r.ort_net, 2))

    # Deneme bazlı ortalamalar
    deneme_ozet = []
    for d in denemeler:
        netler = [float(s.net) for s in sonuclar if s.deneme_id == d.pk]
        deneme_ozet.append({"deneme": d, "kisi": len(netler), "ort_net": _ort(netler)})

    # Şube karşılaştırması
    sube_satirlari = []
    for sb in sorted({r.sube for r in satirlar}):
        grup = [r for r in satirlar if r.sube == sb]
        katilan_grup = [r for r in grup if r.katilim]
        ilk = _ort(r.netler[0] for r in grup) if n else None
        son = _ort(r.netler[-1] for r in grup) if n else None
        degisim = 100 * (son - ilk) / ilk if (n >= 2 and ilk and son is not None) else 0
        sube_satirlari.append(
            {
                "sube": sb,
                "ogrenci": len(grup),
                "ort_net": _ort(r.ort_net for r in katilan_grup),
                "katilim": 100 * _ort(r.katilim for r in grup) if grup else 0,
                "degisim": degisim,
            }
        )

    kategoriler = defaultdict(int)
    riskler = defaultdict(int)
    for r in katilan:
        kategoriler[r.kategori] += 1
    for r in satirlar:
        for risk in r.riskler:
            riskler[risk] += 1

    toplam_beklenen = len(satirlar) * n
    return {
        "ozet": {
            "ogrenci": len(satirlar),
            "sinav": n,
            "genel_ort_net": genel_ort,
            "katilim": 100 * len(sonuclar) / toplam_beklenen if toplam_beklenen else 0,
            "riskli": sum(1 for r in satirlar if r.riskler),
        },
        "deneme_ozet": deneme_ozet,
        "subeler": sube_satirlari,
        "ilk_on": katilan[:10],
        "satirlar": katilan + [r for r in satirlar if r not in katilan],
        "kategoriler": dict(kategoriler),
        "riskler": dict(riskler),
        "riskli_ogrenciler": [r for r in satirlar if r.riskler],
    }
