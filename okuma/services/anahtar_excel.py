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

from okuma.models import Deneme, Kazanim, KitapcikSira, Soru, Test

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


# ── Sütun tanıma ───────────────────────────────────────────────────────────
# Başlıklar küçük harf, Türkçe karaktersiz ve boşluksuz karşılaştırılır.
KOD_DESENI = re.compile(
    r"^\s*((?:[A-Za-zÇĞİÖŞÜçğıöşü]{1,4}\.){0,3}[A-Za-zÇĞİÖŞÜçğıöşü]{0,3}\d+(?:\.[0-9A-Za-z]+)+)\.?\s*(?:[-–—:]\s*|\s+)(\S.*)$"
)


def kod_metin_ayir(deger: str) -> tuple[str, str]:
    """'8.3.2.1 - Bağlamdan…' → ('8.3.2.1', 'Bağlamdan…'); kod yoksa ('', metin)."""
    deger = str(deger or "").strip()
    m = KOD_DESENI.match(deger)
    if m:
        return m.group(1).rstrip("."), m.group(2).strip()
    return "", deger


def _sutun_turu(h: str) -> tuple[str, str] | None:
    """Başlığın ne olduğunu söyler: ('a',''), ('kitapcik','B'), ('cevap',''), ('test',''), ('testno',''),
    ('ders',''), ('kod',''), ('kodmetin',''), ('metin','')."""
    if not h:
        return None
    if re.fullmatch(r"a(kitapcigi?)?(soru(su)?)?(no|numarasi|sira(si)?)?", h) and h != "a":
        return ("a", "")
    if (m := re.fullmatch(r"([b-e])(kitapcigi?)?(soru(su)?)?(no|numarasi|sira(si)?)?", h)) and len(h) > 1:
        return ("kitapcik", m.group(1).upper())
    if "cevap" in h or h in {"dogru", "dogrusik", "anahtar", "dc", "dogrucvp", "cvp"}:
        return ("cevap", "")
    if "kazanim" in h and "kod" in h and ("metin" in h or "veya" in h or "adi" in h):
        return ("kodmetin", "")
    if h in {"kazanimkodu", "kazanimkod", "kod", "kazanimno", "kazanimnumarasi", "mebkodu"}:
        return ("kod", "")
    if h.startswith("kazanim") or h.startswith("konu") or h in {"altkonu", "ogrenmecikti", "ogrenmeciktisi"}:
        return ("metin", "")
    if h in {"testno", "testnumarasi", "testsirasi", "bolumno"}:
        return ("testno", "")
    if "testadi" in h or "aciklama" in h or h in {"test", "testismi", "bolum", "oturum", "testler"}:
        return ("test", "")
    if h in {"ders", "dersadi", "dersler", "brans", "bransadi", "alan", "derskodu"}:
        return ("ders", "")
    if h in {"soruno", "sorunumarasi", "soru", "sirano", "no"}:
        return ("soruno", "")
    return None


def _basliklari_bul(satirlar) -> tuple[int, dict] | None:
    """Soru no + cevap sütunu olan ilk satırı başlık kabul eder; sütun haritasını döndürür."""
    for i, satir in enumerate(satirlar):
        harita: dict = {"kitapcik": {}, "metin": []}
        for j, h in enumerate(satir or ()):
            tur = _sutun_turu(_norm(h))
            if tur is None:
                continue
            ad, ek = tur
            if ad == "kitapcik":
                harita["kitapcik"].setdefault(ek, j)
            elif ad == "metin":
                harita["metin"].append(j)
            else:
                harita.setdefault(ad, j)
        if "a" not in harita and "soruno" in harita:
            harita["a"] = harita["soruno"]
        if "a" in harita and "cevap" in harita and ({"test", "testno", "ders"} & harita.keys()):
            return i, harita
    return None


def _tamsayi(v) -> int | None:
    if v in (None, ""):
        return None
    try:
        f = float(str(v).replace(",", ".").strip())
    except ValueError:
        return None
    return int(f) if f == int(f) else None


IPTAL = {"X", "IPTAL", "İPTAL", "-", "—"}


def excel_oku(veri: bytes) -> list[AnahtarSoru]:
    """Yayınevinden bağımsız cevap anahtarı okuyucu.

    Bütün sayfalarda, başlığın yerini ve sütun adlarını kendisi bulur:
    A/B/C/D soru no, doğru cevap, test adı/no, ders, kazanım kodu ve metni
    (ayrı ya da "8.3.2.1 - metin" biçiminde tek hücrede).
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(veri), data_only=True, read_only=True)
    except Exception as exc:
        raise AnahtarHatasi(f"Dosya Excel olarak açılamadı: {exc}")

    for ws in wb.worksheets:
        satirlar = list(ws.iter_rows(values_only=True))
        bulunan = _basliklari_bul(satirlar)
        if bulunan:
            break
    else:
        raise AnahtarHatasi(
            "Cevap anahtarı tablosu bulunamadı. Başlık satırında en az şu sütunlar olmalı: "
            "soru numarası (\"A Soru No\" ya da \"Soru No\"), doğru cevap (\"Cevap\" / \"Doğru Cevap\") "
            "ve ders ya da test adı."
        )
    baslik_idx, h = bulunan

    def hucre(satir, ad):
        j = h.get(ad)
        return satir[j] if j is not None and j < len(satir) else None

    sorular: list[AnahtarSoru] = []
    for satir_no, satir in enumerate(satirlar[baslik_idx + 1 :], start=baslik_idx + 2):
        if not satir or all(v in (None, "") for v in satir):
            continue
        a_no = _tamsayi(hucre(satir, "a"))
        if a_no is None:
            continue  # ara başlık, toplam satırı vb.
        cevap = str(hucre(satir, "cevap") or "").strip().upper().replace("İ", "I")
        if not cevap:
            continue
        if cevap in IPTAL or cevap == "IPTAL":
            cevap = "X"
        if cevap not in {"A", "B", "C", "D", "E", "X"}:
            raise AnahtarHatasi(f"{satir_no}. satır: geçersiz cevap {cevap!r}. İptal soru için X yazın.")

        test_adi = str(hucre(satir, "test") or "").strip()
        test_no = _tamsayi(hucre(satir, "testno"))
        ders = str(hucre(satir, "ders") or "").strip() or test_adi
        test = test_adi or ders or (f"{test_no}. Test" if test_no else "")
        if not test:
            raise AnahtarHatasi(f"{satir_no}. satır: ders / test adı boş.")
        ders = ders or test

        kitapcik_no = {}
        for k, j in h["kitapcik"].items():
            if j < len(satir) and (no := _tamsayi(satir[j])) is not None:
                kitapcik_no[k] = no

        kod = str(hucre(satir, "kod") or "").strip()
        metinler = []
        if h.get("kodmetin") is not None:
            k2, m2 = kod_metin_ayir(hucre(satir, "kodmetin"))
            kod = kod or k2
            if m2:
                metinler.append(m2)
        for j in h["metin"]:
            if j < len(satir) and satir[j] not in (None, ""):
                k2, m2 = kod_metin_ayir(satir[j])
                kod = kod or k2
                metinler.append(m2 or str(satir[j]).strip())
        if kod and not metinler:
            metinler.append(kod)

        sorular.append(
            AnahtarSoru(
                test=test, ders=ders, a_no=a_no, kitapcik_no=kitapcik_no, cevap=cevap,
                kazanim_kodu=kod[:40], kazanimlar=metinler,
            )
        )
    if not sorular:
        raise AnahtarHatasi("Başlık bulundu ama altında soru satırı yok.")
    return sorular


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
    testler = _dogrula(excel_oku(veri))
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

    deneme.kitapciklar = ",".join(sorted(kitapciklar))
    deneme.hesaplanma = None
    deneme.save(update_fields=["kitapciklar", "hesaplanma"])
    ozet.kazanim_sayisi = len(kazanim_idler)
    ozet.kitapciklar = sorted(kitapciklar)
    ozet.uyari = _sinif_uyarisi(deneme, [s for _, liste in eslesme for s in liste])
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
def anahtar_elle(test: Test, a_cevaplar: str, b_sirasi: str = "") -> None:
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

    test.sorular.filter(no__gt=test.soru_sayisi).delete()
    for no, cevap in enumerate(cevaplar, start=1):
        soru, _ = Soru.objects.update_or_create(
            test=test, no=no, defaults={"dogru": "" if cevap == "X" else cevap, "iptal": cevap == "X"}
        )
        if b:
            KitapcikSira.objects.update_or_create(soru=soru, kitapcik="B", defaults={"no": b[no - 1]})
        elif b_sirasi is not None and not b_sirasi.strip():
            KitapcikSira.objects.filter(soru=soru, kitapcik="B").delete()

    deneme = test.deneme
    var_b = KitapcikSira.objects.filter(soru__test__deneme=deneme, kitapcik="B").exists()
    deneme.kitapciklar = "A,B" if var_b else "A"
    deneme.save(update_fields=["kitapciklar"])
