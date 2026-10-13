"""Kazanım tablolu cevap anahtarı Excel'ini içe aktarır.

Beklenen başlıklar (sıra önemli değil, büyük/küçük harf duyarsız):
    Test | Ders | A Soru | B Soru [| C Soru | D Soru] | Cevap | Kazanım Kodu | Kazanım-1 … Kazanım-n

Her satır bir sorudur; "Cevap" A kitapçığındaki doğru şıktır. "B Soru", aynı
sorunun B kitapçığındaki sırasıdır. Şıklar kitapçıklar arasında karışmaz.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import openpyxl
from django.db import transaction

from okuma.models import Deneme, Kazanim, KitapcikAnahtari, KitapcikSira, Soru, Test

LGS_KATSAYI = {"turkce": 4, "matematik": 4, "fen": 4, "inkilap": 1, "din": 1, "yabanci_dil": 1}


class AnahtarHatasi(ValueError):
    pass


@dataclass
class AnahtarSoru:
    test: str
    ders: str
    a_no: int
    kitapcik_no: dict[str, int]
    cevap: str
    kazanim_kodu: str
    kazanimlar: list[str]


@dataclass
class AnahtarOzet:
    test_sayisi: int = 0
    soru_sayisi: int = 0
    kazanim_sayisi: int = 0
    kitapciklar: list[str] = field(default_factory=list)
    uyari: str = ""
    eslesmesiz: list[str] = field(default_factory=list)


def _norm(s) -> str:
    s = str(s or "").strip().lower()
    for a, b in zip("ıİçğöşü", "iicgosu"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", s)


# Yayınevlerinin ders kısaltmaları: "Sözel (TÜR)", "Sayısal (MAT)" …
DERS_KISALTMA = {
    "tur": "turkce", "trk": "turkce", "turkce": "turkce",
    "tar": "inkilap", "ink": "inkilap", "inkilap": "inkilap", "sos": "inkilap", "sosyal": "inkilap", "tc": "inkilap",
    "din": "din", "dkab": "din", "dkb": "din",
    "ing": "yabanci_dil", "yd": "yabanci_dil", "ydil": "yabanci_dil", "eng": "yabanci_dil", "alm": "yabanci_dil", "arp": "yabanci_dil",
    "mat": "matematik", "matematik": "matematik",
    "fen": "fen", "fenbilimleri": "fen", "fb": "fen",
}


def lgs_ders_tahmin(ders: str) -> str:
    # Parantez içindeki kısaltma en güvenilir ipucu: "Sözel (TÜR)" → TÜR
    for parca in re.findall(r"\(([^)]*)\)", str(ders or "")):
        if (kod := DERS_KISALTMA.get(_norm(parca))):
            return kod
    d = _norm(ders)
    if d in DERS_KISALTMA:
        return DERS_KISALTMA[d]
    if "turkce" in d:
        return "turkce"
    if d.startswith("mat") or "matematik" in d:
        return "matematik"
    if "fen" in d:
        return "fen"
    if "inkilap" in d or "sosyal" in d or "tarih" in d:
        return "inkilap"
    if "din" in d:
        return "din"
    if "ingilizce" in d or "almanca" in d or "arapca" in d or "yabancidil" in d or d.endswith("dil"):
        return "yabanci_dil"
    return ""


from okuma.services.anahtar_okuyucu import OkumaHatasi, kayitlari_oku, kod_metin_ayir  # noqa: E402,F401


@dataclass
class AnahtarOkuma:
    sorular: list[AnahtarSoru]  # ana kitapçık (A) soruları; eşleştirme varsa kitapcik_no dolu
    bagimsiz: dict[str, dict[str, str]]  # eşleşmesiz kitapçık → {test adı: "CBDA…"}
    uyarilar: list[str]


def _ders_anahtari(ad: str) -> str:
    return lgs_ders_tahmin(ad) or _norm(ad)


def anahtar_oku(veri: bytes) -> AnahtarOkuma:
    """Excel'i (biçimi ne olursa olsun) ana kitapçık soruları + eşleşmesiz kitapçık anahtarlarına çevirir."""
    try:
        kayitlar = kayitlari_oku(veri)
    except OkumaHatasi as exc:
        raise AnahtarHatasi(str(exc))

    harfler = sorted({k.kitapcik for k in kayitlar})
    ana = "A" if "A" in harfler else harfler[0]
    ana_kayitlar = [k for k in kayitlar if k.kitapcik == ana]
    sorular = [
        AnahtarSoru(test=k.test, ders=k.ders, a_no=k.no, kitapcik_no=dict(k.eslesme), cevap=k.cevap,
                    kazanim_kodu=k.kod, kazanimlar=k.metinler)
        for k in ana_kayitlar
    ]
    ana_testler: dict[str, list[AnahtarSoru]] = {}
    for s_ in sorular:
        ana_testler.setdefault(s_.test, []).append(s_)
    ana_sirasi = list(ana_testler)

    bagimsiz: dict[str, dict[str, str]] = {}
    uyarilar: list[str] = []
    for harf in harfler:
        if harf == ana:
            continue
        diger: dict[str, list] = {}
        for k in kayitlar:
            if k.kitapcik == harf:
                diger.setdefault(k.test, []).append(k)
        for sira, (test_adi, liste) in enumerate(diger.items()):
            hedef = next((t for t in ana_sirasi if _ders_anahtari(t) == _ders_anahtari(test_adi)), None)
            if hedef is None:
                hedef = test_adi if test_adi in ana_testler else (ana_sirasi[sira] if sira < len(ana_sirasi) else None)
            if hedef is None:
                raise AnahtarHatasi(f"{harf} kitapçığındaki “{test_adi}” A kitapçığında bulunamadı.")
            a_liste = ana_testler[hedef]
            eslesmeli = all(harf in s_.kitapcik_no for s_ in a_liste)
            if eslesmeli:
                # Eşleştirme var: B anahtarı yalnız sağlama için kullanılır.
                b_cevap = {k.no: k.cevap for k in liste}
                uymayan = [s_.a_no for s_ in a_liste if b_cevap.get(s_.kitapcik_no[harf]) not in (None, s_.cevap)]
                if uymayan:
                    uyarilar.append(
                        f"{hedef}: {harf} kitapçığı anahtarı eşleştirmeyle {len(uymayan)} soruda uyuşmuyor "
                        f"(A'da {', '.join(map(str, uymayan[:6]))}…). Şıklar karıştırılmış olabilir; anahtarı kontrol edin."
                    )
                continue
            nolar = sorted(k.no for k in liste)
            if nolar != list(range(1, len(liste) + 1)):
                raise AnahtarHatasi(f"{harf} kitapçığı · {test_adi}: soru numaraları 1–{len(liste)} arasında eksiksiz olmalı.")
            bagimsiz.setdefault(harf, {})[hedef] = "".join(k.cevap for k in sorted(liste, key=lambda x: x.no))
    return AnahtarOkuma(sorular=sorular, bagimsiz=bagimsiz, uyarilar=uyarilar)


def excel_oku(veri: bytes) -> list[AnahtarSoru]:
    return anahtar_oku(veri).sorular


def _dogrula(sorular: list[AnahtarSoru]) -> dict[str, list[AnahtarSoru]]:
    testler: dict[str, list[AnahtarSoru]] = {}
    for s in sorular:
        testler.setdefault(s.test, []).append(s)
    for ad, liste in testler.items():
        n = len(liste)
        a_nolar = sorted(s.a_no for s in liste)
        if a_nolar != list(range(1, n + 1)):
            raise AnahtarHatasi(f"{ad}: A soru numaraları 1–{n} arasında eksiksiz olmalı.")
        kitapciklar = {k for s in liste for k in s.kitapcik_no}
        for k in kitapciklar:
            nolar = sorted(s.kitapcik_no.get(k, 0) for s in liste)
            if nolar != list(range(1, n + 1)):
                raise AnahtarHatasi(f"{ad}: {k} kitapçığı sıraları 1–{n} arasında eksiksiz ve tekrarsız olmalı.")
    return testler


def _yapiya_esle(mevcut: list[Test], testler: dict[str, list[AnahtarSoru]]) -> list[tuple[Test, list[AnahtarSoru]]]:
    """Excel'deki testleri deneme türünün hazır testlerine ders adına (yoksa sırasına) göre bağlar."""
    if len(testler) != len(mevcut):
        raise AnahtarHatasi(
            f"Excel'de {len(testler)} ders var, bu deneme türünde {len(mevcut)} ders var: "
            + ", ".join(t.ders for t in mevcut)
        )
    bos = list(mevcut)
    eslesme = []
    for ad, liste in testler.items():
        anahtar = lgs_ders_tahmin(liste[0].ders) or lgs_ders_tahmin(ad)
        test = next((t for t in bos if anahtar and t.lgs_ders == anahtar), None) or bos[0]
        bos.remove(test)
        if len(liste) != test.soru_sayisi:
            raise AnahtarHatasi(
                f"{test.ders}: Excel'de {len(liste)} soru var, bu deneme türünde {test.soru_sayisi} soru olmalı."
            )
        eslesme.append((test, liste))
    return sorted(eslesme, key=lambda x: x[0].sira)


@transaction.atomic
def anahtar_yukle(deneme: Deneme, veri: bytes) -> AnahtarOzet:
    """Cevap anahtarını, kitapçık sıralarını ve kazanımları Excel'den kurar.

    Deneme türü seçilmişse dersler sabittir; Excel bu yapıya oturtulur.
    Tür yoksa testler Excel'e göre baştan oluşturulur.
    """
    okuma = anahtar_oku(veri)
    testler = _dogrula(okuma.sorular)
    deneme.sonuclar.all().delete()
    mevcut = list(deneme.testler.order_by("sira"))
    lgs = deneme.sinav_turu == Deneme.SinavTuru.LGS

    if deneme.tur_id and mevcut:
        eslesme = _yapiya_esle(mevcut, testler)
        Soru.objects.filter(test__deneme=deneme).delete()
    else:
        deneme.testler.all().delete()
        eslesme = []
        for sira, (ad, liste) in enumerate(testler.items(), start=1):
            ders = liste[0].ders
            lgs_ders = lgs_ders_tahmin(ders)
            eslesme.append((
                Test.objects.create(
                    deneme=deneme,
                    ad=ad,
                    ders=ders,
                    oturum=ad.split("(")[0].strip() if "(" in ad else "",
                    sira=sira,
                    soru_sayisi=len(liste),
                    katsayi=LGS_KATSAYI.get(lgs_ders, 1) if lgs else 1,
                    lgs_ders=lgs_ders,
                ),
                liste,
            ))

    ozet = AnahtarOzet()
    kitapciklar = {"A"}
    kazanim_idler = set()
    for test, liste in eslesme:
        for s in sorted(liste, key=lambda x: x.a_no):
            soru = Soru.objects.create(
                test=test,
                no=s.a_no,
                dogru="" if s.cevap == "X" else s.cevap,
                iptal=s.cevap == "X",
            )
            for k, no in s.kitapcik_no.items():
                KitapcikSira.objects.create(soru=soru, kitapcik=k, no=no)
                kitapciklar.add(k)
            for j, metin in enumerate(s.kazanimlar):
                kazanim, _ = Kazanim.objects.get_or_create(
                    ders=test.ders, kod=s.kazanim_kodu if j == 0 else "", metin=metin[:400]
                )
                soru.kazanimlar.add(kazanim)
                kazanim_idler.add(kazanim.pk)
        ozet.test_sayisi += 1
        ozet.soru_sayisi += len(liste)

    # Eşleşmesiz kitapçıklar kendi anahtarlarıyla puanlanır.
    KitapcikAnahtari.objects.filter(test__deneme=deneme).delete()
    excel_testi = {liste[0].test: test for test, liste in eslesme}
    for harf, anahtarlar in okuma.bagimsiz.items():
        for test_adi, cevaplar in anahtarlar.items():
            test = excel_testi[test_adi]
            if len(cevaplar) != test.soru_sayisi:
                raise AnahtarHatasi(f"{harf} kitapçığı · {test.ders}: {test.soru_sayisi} soru olmalı, {len(cevaplar)} var.")
            KitapcikAnahtari.objects.create(test=test, kitapcik=harf, cevaplar=cevaplar)
        kitapciklar.add(harf)
        ozet.eslesmesiz.append(harf)

    deneme.kitapciklar = ",".join(sorted(kitapciklar))
    deneme.hesaplanma = None
    deneme.save(update_fields=["kitapciklar", "hesaplanma"])
    ozet.kazanim_sayisi = len(kazanim_idler)
    ozet.kitapciklar = sorted(kitapciklar)
    uyarilar = [_sinif_uyarisi(deneme, [s for _, liste in eslesme for s in liste]), *okuma.uyarilar]
    if ozet.eslesmesiz:
        uyarilar.append(
            f"{', '.join(ozet.eslesmesiz)} kitapçığı için A ile soru eşleştirmesi yok: bu kitapçığın puan ve netleri "
            "doğru hesaplanır, ama soru ve kazanım analizine yalnız eşleşen kitapçıklar girer. Eşleştirmeyi "
            "“Cevap anahtarı” sayfasından ekleyebilirsiniz."
        )
    ozet.uyari = " ".join(u for u in uyarilar if u)
    return ozet


def _sinif_uyarisi(deneme: Deneme, sorular: list[AnahtarSoru]) -> str:
    """Kazanım kodlarındaki sınıf (MAT.7…, F.8…, 8.3.2.1) denemenin sınıfından farklıysa uyarır."""
    sayim: dict[str, int] = {}
    for s in sorular:
        if m := re.search(r"(?:^|[A-Za-z.])([5-8])\.", s.kazanim_kodu or ""):
            sayim[m.group(1)] = sayim.get(m.group(1), 0) + 1
    if not sayim:
        return ""
    en_cok = max(sayim, key=sayim.get)
    if en_cok != str(deneme.sinif_seviyesi) and sayim[en_cok] >= len(sorular) / 2:
        return (
            f"Dikkat: kazanım kodlarının çoğu {en_cok}. sınıfa ait, bu deneme {deneme.sinif_seviyesi}. sınıf. "
            "Doğru dosyayı yüklediğinizden emin olun."
        )
    return ""


def _sira_listesi(metin: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", metin or "")]


@transaction.atomic
def anahtar_elle(test: Test, a_cevaplar: str, b_sirasi: str = "", b_cevaplar: str = "") -> None:
    """Tek bir testin anahtarını elle kurar. Mevcut kazanım bağları korunur.

    a_cevaplar: A kitapçığı cevapları (ör. "ABCD AXCB…"; X = iptal). Boşluk ve rakamlar yok sayılır.
    b_sirasi:   isteğe bağlı; A'daki 1., 2., … sorunun B kitapçığındaki sırası (ör. "13 14 18 19 …").
    """
    cevaplar = re.sub(r"[^A-EX]", "", a_cevaplar.upper().replace("İ", "I"))
    if len(cevaplar) != test.soru_sayisi:
        raise AnahtarHatasi(f"{test.ders}: {test.soru_sayisi} cevap gerekli, {len(cevaplar)} girildi.")
    b = _sira_listesi(b_sirasi)
    if b and sorted(b) != list(range(1, test.soru_sayisi + 1)):
        raise AnahtarHatasi(f"{test.ders}: B sırası 1–{test.soru_sayisi} sayılarını birer kez içermeli.")
    b_anahtar = re.sub(r"[^A-EX]", "", (b_cevaplar or "").upper().replace("İ", "I"))
    if b_anahtar and not b and len(b_anahtar) != test.soru_sayisi:
        raise AnahtarHatasi(f"{test.ders}: B kitapçığı için {test.soru_sayisi} cevap gerekli, {len(b_anahtar)} girildi.")

    test.sorular.filter(no__gt=test.soru_sayisi).delete()
    for no, cevap in enumerate(cevaplar, start=1):
        soru, _ = Soru.objects.update_or_create(
            test=test, no=no, defaults={"dogru": "" if cevap == "X" else cevap, "iptal": cevap == "X"}
        )
        if b:
            KitapcikSira.objects.update_or_create(soru=soru, kitapcik="B", defaults={"no": b[no - 1]})
        elif b_sirasi is not None and not b_sirasi.strip():
            KitapcikSira.objects.filter(soru=soru, kitapcik="B").delete()

    # B için ya sıra (tam eşleştirme) ya da kendi anahtarı (eşleşmesiz) tutulur.
    if b or not b_anahtar:
        KitapcikAnahtari.objects.filter(test=test, kitapcik="B").delete()
    if b_anahtar and not b:
        KitapcikSira.objects.filter(soru__test=test, kitapcik="B").delete()
        KitapcikAnahtari.objects.update_or_create(test=test, kitapcik="B", defaults={"cevaplar": b_anahtar})

    deneme = test.deneme
    var_b = (
        KitapcikSira.objects.filter(soru__test__deneme=deneme, kitapcik="B").exists()
        or KitapcikAnahtari.objects.filter(test__deneme=deneme, kitapcik="B").exists()
    )
    deneme.kitapciklar = "A,B" if var_b else "A"
    deneme.save(update_fields=["kitapciklar"])
