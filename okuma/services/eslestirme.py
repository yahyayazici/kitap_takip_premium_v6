"""Eşleşmeyen optik satırı için "bu kim olabilir?" önerileri.

Adaylar: denemenin sınıfındaki, bu oturumda henüz okunmamış aktif öğrenciler.
Sıralama: numara benzerliği (rakam yer değiştirmesi, eksik/fazla/yanlış rakam),
optikteki ad soyad benzerliği ve aynı şube.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from okuma.models import Deneme, Ogrenci, OptikSatir


def _uzaklik(a: str, b: str) -> int:
    """Damerau–Levenshtein (bitişik yer değiştirme 1 sayılır)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            maliyet = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + maliyet)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _okunanlar(deneme: Deneme, oturum: str, haric: OptikSatir | None) -> set[int]:
    qs = OptikSatir.objects.filter(yukleme__deneme=deneme, dahil=True, ogrenci__isnull=False)
    if haric is not None:
        qs = qs.exclude(pk=haric.pk)
    return {
        oid for oid, o in qs.values_list("ogrenci_id", "yukleme__oturum") if not o or not oturum or o == oturum
    }


def oneriler(deneme: Deneme, satir: OptikSatir, adet: int = 6, adaylar=None, okunan=None) -> list[tuple[Ogrenci, str]]:
    oturum = satir.yukleme.oturum
    if okunan is None:
        okunan = _okunanlar(deneme, oturum, satir)
    if adaylar is None:
        adaylar = list(Ogrenci.objects.filter(aktif=True, sinif_seviyesi=deneme.sinif_seviyesi))
    numara = satir.numara or ""
    ad = (satir.ad_soyad or "").upper()
    puanli = []
    for o in adaylar:
        if o.pk in okunan:
            continue
        nedenler = []
        puan = 3.0
        if numara and o.numara:
            u = _uzaklik(numara, o.numara)
            puan = u
            if u == 1:
                nedenler.append(f"numara benzer ({numara} ↔ {o.numara})")
        if ad and o.ad_soyad:
            oran = SequenceMatcher(None, ad, o.ad_soyad.upper()).ratio()
            puan -= 2 * oran
            if oran >= 0.6:
                nedenler.append("adı benzer")
        if satir.sube and o.sube and satir.sube.upper() == o.sube.upper():
            puan -= 0.5
        puanli.append((puan, o.ad_soyad or "", o, ", ".join(nedenler) or "henüz okunmadı"))
    puanli.sort(key=lambda x: (x[0], x[1]))
    return [(o, neden) for _, _, o, neden in puanli[:adet]]
