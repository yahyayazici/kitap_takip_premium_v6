"""Kazanım, madde (soru) ve şube analizleri. Hepsi Sonuc.cevaplar_a üzerinden hesaplanır."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from okuma.models import Deneme, Kazanim, Soru, Sonuc
from okuma.services.puanlama import harita_kur

EKSIK_ESIK = 50  # % — altındaki kazanım "eksik" sayılır
UST_ALT_ORAN = 0.27


def _sonuclar(deneme: Deneme, sube: str | None = None):
    qs = deneme.sonuclar.select_related("ogrenci").order_by("sira_kurum")
    if sube:
        qs = qs.filter(sube=sube)
    return list(qs)


def _soru_kazanimlari(deneme: Deneme) -> dict[int, list[Kazanim]]:
    sorular = Soru.objects.filter(test__deneme=deneme).prefetch_related("kazanimlar")
    return {s.pk: list(s.kazanimlar.all()) for s in sorular}


@dataclass
class KazanimSatiri:
    kazanim: Kazanim
    ders: str
    soru_nolari: list[int] = field(default_factory=list)
    dogru: int = 0
    toplam: int = 0
    sube_oranlari: dict[str, float | None] = field(default_factory=dict)

    @property
    def oran(self) -> float | None:
        return round(100 * self.dogru / self.toplam, 1) if self.toplam else None

    @property
    def eksik(self) -> bool:
        return self.oran is not None and self.oran < EKSIK_ESIK


def kazanim_raporu(deneme: Deneme, sonuclar: list[Sonuc] | None = None) -> list[KazanimSatiri]:
    """Kazanım başarı yüzdesi = doğru sayısı / (öğrenci × soru). Yanlış götürmez."""
    harita = harita_kur(deneme)
    sonuclar = sonuclar if sonuclar is not None else _sonuclar(deneme)
    soru_kaz = _soru_kazanimlari(deneme)
    test_ders = {t.pk: t.ders for t in harita.testler}
    soru_no = {}
    for t in harita.testler:
        for s in t.sorular.all():
            soru_no[s.pk] = s.no

    satirlar: dict[int, KazanimSatiri] = {}
    sube_sayim: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for s in harita.sorular:
        if s.iptal:
            continue
        for k in soru_kaz.get(s.soru_id, []):
            satir = satirlar.setdefault(k.pk, KazanimSatiri(kazanim=k, ders=test_ders[s.test_id]))
            satir.soru_nolari.append(soru_no[s.soru_id])
            for sonuc in sonuclar:
                dogru = sonuc.cevaplar_a[s.a_index] in s.dogrular
                satir.dogru += dogru
                satir.toplam += 1
                sube_sayim[k.pk][sonuc.sube][0] += dogru
                sube_sayim[k.pk][sonuc.sube][1] += 1

    for kid, satir in satirlar.items():
        satir.sube_oranlari = {
            sube: round(100 * d / t, 1) if t else None for sube, (d, t) in sorted(sube_sayim[kid].items())
        }
    sira = {t.ders: t.sira for t in harita.testler}
    return sorted(satirlar.values(), key=lambda x: (sira.get(x.ders, 99), min(x.soru_nolari)))


def ogrenci_kazanimlari(sonuc: Sonuc) -> list[KazanimSatiri]:
    return kazanim_raporu(sonuc.deneme, [sonuc])


@dataclass
class MaddeSatiri:
    test: str
    no: int
    dogru_cevap: str
    iptal: bool
    p: float | None = None
    r: float | None = None
    secenekler: dict[str, int] = field(default_factory=dict)
    ust: dict[str, int] = field(default_factory=dict)
    alt: dict[str, int] = field(default_factory=dict)
    uyarilar: list[str] = field(default_factory=list)

    @property
    def zorluk_etiket(self) -> str:
        if self.p is None:
            return "—"
        if self.p >= 0.8:
            return "Çok kolay"
        if self.p >= 0.6:
            return "Kolay"
        if self.p >= 0.4:
            return "Orta"
        if self.p >= 0.2:
            return "Zor"
        return "Çok zor"

    @property
    def ayirt_etiket(self) -> str:
        # Ebel ölçütleri
        if self.r is None:
            return "—"
        if self.r >= 0.40:
            return "Çok iyi"
        if self.r >= 0.30:
            return "İyi"
        if self.r >= 0.20:
            return "Düzeltilmeli"
        return "Zayıf"


SECENEKLER = ["A", "B", "C", "D", "E", " ", "*"]


def madde_analizi(deneme: Deneme) -> tuple[list[MaddeSatiri], dict[str, float | None]]:
    """Klasik test kuramı: güçlük p, alt-üst %27 ayırt edicilik r, çeldirici dağılımı, KR-20."""
    harita = harita_kur(deneme)
    sonuclar = _sonuclar(deneme)
    n = len(sonuclar)
    test_ad = {t.pk: t.ders for t in harita.testler}
    soru_no = {s.pk: s.no for t in harita.testler for s in t.sorular.all()}

    sirali = sorted(sonuclar, key=lambda s: s.net, reverse=True)
    g = max(1, round(n * UST_ALT_ORAN)) if n >= 4 else 0
    ust, alt = sirali[:g], sirali[-g:] if g else []

    satirlar = []
    for s in harita.sorular:
        dogru_cevap = "/".join(sorted(s.dogrular)) or "X"
        m = MaddeSatiri(test=test_ad[s.test_id], no=soru_no[s.soru_id], dogru_cevap=dogru_cevap, iptal=s.iptal)
        m.secenekler = {c: 0 for c in SECENEKLER}
        for sonuc in sonuclar:
            m.secenekler[sonuc.cevaplar_a[s.a_index]] = m.secenekler.get(sonuc.cevaplar_a[s.a_index], 0) + 1
        if n and not s.iptal:
            m.p = round(sum(m.secenekler.get(c, 0) for c in s.dogrular) / n, 2)
        if g and not s.iptal:
            m.ust = {c: sum(x.cevaplar_a[s.a_index] == c for x in ust) for c in SECENEKLER}
            m.alt = {c: sum(x.cevaplar_a[s.a_index] == c for x in alt) for c in SECENEKLER}
            ud = sum(m.ust[c] for c in s.dogrular)
            ad = sum(m.alt[c] for c in s.dogrular)
            m.r = round((ud - ad) / g, 2)
            for c in "ABCDE":
                if c not in s.dogrular and m.ust.get(c, 0) > ud and m.ust.get(c, 0) >= 2:
                    m.uyarilar.append(f"Üst grup en çok {c} şıkkını seçmiş — anahtarı kontrol edin")
            if m.r < 0:
                m.uyarilar.append("Negatif ayırt edicilik")
        satirlar.append(m)

    kr20 = {}
    for t in harita.testler:
        sorular = [s for s in harita.sorular if s.test_id == t.pk and not s.iptal]
        k = len(sorular)
        if n < 2 or k < 2:
            kr20[t.ders] = None
            continue
        puanlar = [sum(x.cevaplar_a[s.a_index] in s.dogrular for s in sorular) for x in sonuclar]
        varyans = statistics.pvariance(puanlar)
        pq = 0.0
        for s in sorular:
            p = sum(x.cevaplar_a[s.a_index] in s.dogrular for x in sonuclar) / n
            pq += p * (1 - p)
        kr20[t.ders] = round(k / (k - 1) * (1 - pq / varyans), 2) if varyans else None
    return satirlar, kr20


def sube_ozeti(deneme: Deneme) -> tuple[list[str], list[dict]]:
    """Şube × test ortalama net tablosu; son satır kurum geneli."""
    harita = harita_kur(deneme)
    sonuclar = deneme.sonuclar.prefetch_related("test_sonuclari")
    gruplar: dict[str, list] = defaultdict(list)
    for s in sonuclar:
        gruplar[s.sube or "—"].append(s)
        gruplar["Kurum"].append(s)
    dersler = [t.ders for t in harita.testler]
    satirlar = []
    for ad in sorted(k for k in gruplar if k != "Kurum") + ["Kurum"]:
        liste = gruplar[ad]
        test_net = defaultdict(list)
        for s in liste:
            for ts in s.test_sonuclari.all():
                test_net[ts.test_id].append(float(ts.net))
        puanlar = [float(s.puan) for s in liste if s.puan is not None]
        satirlar.append(
            {
                "ad": ad,
                "kisi": len(liste),
                "netler": [round(statistics.fmean(test_net[t.pk]), 2) if test_net[t.pk] else None for t in harita.testler],
                "net": round(statistics.fmean(float(s.net) for s in liste), 2),
                "puan": round(statistics.fmean(puanlar), 2) if puanlar else None,
            }
        )
    return dersler, satirlar


def isi_rengi(oran: float | None) -> str:
    """0–100 arası başarı için sınıf adı (şablonda renklendirme)."""
    if oran is None or math.isnan(oran):
        return "bos"
    if oran < 35:
        return "c1"
    if oran < 50:
        return "c2"
    if oran < 65:
        return "c3"
    if oran < 80:
        return "c4"
    return "c5"
