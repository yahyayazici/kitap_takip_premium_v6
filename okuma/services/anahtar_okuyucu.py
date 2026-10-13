"""Yayınevinden bağımsız cevap anahtarı okuyucu.

Her biçimi aynı düz kayıt listesine çevirir:
    Kayit(kitapcik, test, ders, no, cevap, kod, metinler, eslesme={"B": 17, ...})

Desteklenen biçimler:
- Satır başına bir soru (kazanımlı ya da kazanımsız), başlık dosyanın herhangi bir yerinde.
- Kitapçıklar ayrı sayfalarda ("Kitapçık - A", "Kitapçık - B") ya da aynı sayfada yan yana bloklar.
- A satırında "B Soru No" gibi eşleştirme sütunları.
- Başlıksız düzen: "Türkçe | C B D A …" (her şık ayrı hücrede) ya da "Türkçe | CBDA…" (tek hücrede).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import openpyxl

SIKLAR = set("ABCDE")
IPTAL = {"X", "IPTAL", "-", "—"}


class OkumaHatasi(ValueError):
    pass


@dataclass
class Kayit:
    kitapcik: str
    test: str
    ders: str
    no: int
    cevap: str
    kod: str = ""
    metinler: list[str] = field(default_factory=list)
    eslesme: dict[str, int] = field(default_factory=dict)


def norm(s) -> str:
    s = str(s or "").strip().lower()
    for a, b in zip("ıİçğöşü", "iicgosu"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", s)


KOD_DESENI = re.compile(
    r"^\s*((?:[A-Za-zÇĞİÖŞÜçğıöşü]{1,4}\.){0,3}[A-Za-zÇĞİÖŞÜçğıöşü]{0,3}\d+(?:\.[0-9A-Za-z]+)+)\.?\s*(?:[-–—:]\s*|\s+)(\S.*)$"
)


def kod_metin_ayir(deger) -> tuple[str, str]:
    """'8.3.2.1 - Bağlamdan…' → ('8.3.2.1', 'Bağlamdan…'); kod yoksa ('', metin)."""
    deger = str(deger or "").strip()
    m = KOD_DESENI.match(deger)
    if m:
        return m.group(1).rstrip("."), m.group(2).strip()
    return "", deger


def tamsayi(v) -> int | None:
    if v in (None, ""):
        return None
    try:
        f = float(str(v).replace(",", ".").strip())
    except ValueError:
        return None
    return int(f) if f == int(f) else None


def cevap_normalize(v) -> str | None:
    c = str(v or "").strip().upper().replace("İ", "I")
    if c in SIKLAR:
        return c
    if c in IPTAL or c == "IPTAL":
        return "X"
    return None


def _kitapcik_harfi(metin) -> str | None:
    """'Kitapçık - B', 'B Kitapçığı', 'Doğru Cevap B', 'B Grubu' → 'B'."""
    t = str(metin or "")
    for desen in (
        r"kitap[cç][iı]k\w*\s*[-:–]?\s*\(?([A-Ea-e])\)?\b",
        r"\b([A-Ea-e])\s*kitap[cç][iı]",
        r"\b([A-Ea-e])\s*grubu\b",
        r"grup\s*[-:]?\s*([A-Ea-e])\b",
        r"cevap\w*\s*[-:]?\s*([A-Ea-e])\s*$",
    ):
        if m := re.search(desen, t, re.I):
            return m.group(1).upper()
    return None


# ── Başlık tanıma ──────────────────────────────────────────────────────────


def sutun_turu(ham) -> tuple[str, str] | None:
    h = norm(ham)
    if not h:
        return None
    if re.fullmatch(r"a(kitapci(?:k|gi?))?(soru(su)?)?(no|numarasi|sira(si)?)?", h) and h != "a":
        return ("no", "A")
    if m := re.fullmatch(r"kitapci(?:k|gi?|ginin)([a-e])(soru(su)?)?(no|numarasi|sira(si)?)?", h):
        return ("no", m.group(1).upper())
    if (m := re.fullmatch(r"([b-e])(kitapci(?:k|gi?))?(soru(su)?)?(no|numarasi|sira(si)?)?", h)) and len(h) > 1:
        return ("no", m.group(1).upper())
    if "cevap" in h or h in {"dogru", "dogrusik", "anahtar", "dc", "dogrucvp", "cvp", "yanit"}:
        return ("cevap", (_kitapcik_harfi(ham) or ""))
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
    if h in {"ders", "dersadi", "dersler", "brans", "bransadi", "alan", "derskodu", "dersismi"}:
        return ("ders", "")
    if h in {"soruno", "sorunumarasi", "soru", "sirano", "no", "sorusirasi", "sira"}:
        return ("no", "")
    return None


@dataclass
class Blok:
    """Bir başlık satırındaki tek tablo (yan yana tablolarda her biri ayrı blok)."""

    kitapcik: str = ""  # boşsa sayfa adından ya da varsayılan A
    no: int | None = None
    eslesme: dict[str, int] = field(default_factory=dict)
    cevap: int | None = None
    test: int | None = None
    testno: int | None = None
    ders: int | None = None
    kod: int | None = None
    kodmetin: int | None = None
    metin: list[int] = field(default_factory=list)

    @property
    def gecerli(self) -> bool:
        return self.no is not None and self.cevap is not None


def bloklari_bul(satir) -> list[Blok]:
    """Başlık satırını tablolara (bloklara) ayırır.

    Satırda birden çok cevap sütunu varsa yan yana tablolar vardır: bir blok
    cevabını aldıktan sonra gelen soru-no sütunu (sağında başka cevap sütunu
    varsa) yeni bloğu başlatır. Cevaptan önceki "B Soru No" gibi sütunlar
    A satırındaki eşleştirmedir.
    """
    turler = [(j, *t) for j, h in enumerate(satir or ()) if (t := sutun_turu(h))]
    cevap_yerleri = [j for j, ad, _ in turler if ad == "cevap"]
    bloklar: list[Blok] = []
    blok = Blok()
    for j, ad, ek in turler:
        sagda_cevap = any(c > j for c in cevap_yerleri)
        yeni = (
            (ad == "cevap" and blok.cevap is not None)
            or (ad == "no" and blok.no is not None and blok.cevap is not None and sagda_cevap)
            or (ad == "no" and blok.no is not None and not ek)
            or (ad in ("ders", "test") and getattr(blok, ad) is not None and blok.cevap is not None)
        )
        if yeni:
            bloklar.append(blok)
            blok = Blok()
        if ad == "no":
            if blok.no is None:
                blok.no, blok.kitapcik = j, ek
            elif ek and ek != blok.kitapcik:
                blok.eslesme[ek] = j
        elif ad == "cevap":
            blok.cevap = j
            if ek and not blok.kitapcik:
                blok.kitapcik = ek
        elif ad == "metin":
            blok.metin.append(j)
        elif getattr(blok, ad) is None:
            setattr(blok, ad, j)
    bloklar.append(blok)
    gecerli = [b for b in bloklar if b.gecerli]
    # Ders/test sütunu yalnız ilk blokta olabilir (yan yana tablolarda ortak sütun).
    for b in gecerli[1:]:
        if b.ders is None and b.test is None and b.testno is None:
            b.ders, b.test, b.testno = gecerli[0].ders, gecerli[0].test, gecerli[0].testno
    if not any(b.ders is not None or b.test is not None or b.testno is not None for b in gecerli):
        return []
    return gecerli


# ── Okuma ──────────────────────────────────────────────────────────────────


def _hucre(satir, j):
    return satir[j] if j is not None and j < len(satir) else None


def _blok_kayitlari(satirlar, baslik_idx: int, bloklar: list[Blok], sayfa_harfi: str | None) -> list[Kayit]:
    kayitlar = []
    son_test = {}
    for satir_no, satir in enumerate(satirlar[baslik_idx + 1 :], start=baslik_idx + 2):
        if not satir or all(v in (None, "") for v in satir):
            continue
        # Yeni bir başlık satırı geldiyse (aynı sayfada alt alta tablolar) bu blok biter.
        if bloklari_bul(satir):
            break
        for bi, b in enumerate(bloklar):
            no = tamsayi(_hucre(satir, b.no))
            if no is None:
                continue
            ham_cevap = _hucre(satir, b.cevap)
            if ham_cevap in (None, ""):
                continue
            cevap = cevap_normalize(ham_cevap)
            if cevap is None:
                raise OkumaHatasi(f"{satir_no}. satır: geçersiz cevap {ham_cevap!r}. İptal soru için X yazın.")
            test_adi = str(_hucre(satir, b.test) or "").strip()
            test_no = tamsayi(_hucre(satir, b.testno))
            ders = str(_hucre(satir, b.ders) or "").strip()
            test = test_adi or ders or (f"{test_no}. Test" if test_no else "") or son_test.get(bi, "")
            if not test:
                raise OkumaHatasi(f"{satir_no}. satır: ders / test adı boş.")
            son_test[bi] = test
            kod = str(_hucre(satir, b.kod) or "").strip()
            metinler = []
            for j in ([b.kodmetin] if b.kodmetin is not None else []) + b.metin:
                deger = _hucre(satir, j)
                if deger in (None, ""):
                    continue
                k2, m2 = kod_metin_ayir(deger)
                kod = kod or k2
                metinler.append(m2 or str(deger).strip())
            if kod and not metinler:
                metinler.append(kod)
            eslesme = {k: n for k, j in b.eslesme.items() if (n := tamsayi(_hucre(satir, j))) is not None}
            kayitlar.append(
                Kayit(
                    kitapcik=b.kitapcik or sayfa_harfi or "A",
                    test=test,
                    ders=ders or test,
                    no=no,
                    cevap=cevap,
                    kod=kod[:40],
                    metinler=metinler,
                    eslesme=eslesme,
                )
            )
    return kayitlar


def _dizi_kayitlari(satirlar, sayfa_harfi: str | None) -> list[Kayit]:
    """Başlıksız düzen: 'Türkçe | C | B | D …' ya da 'Türkçe | CBDA…'."""
    from okuma.services.anahtar_excel import lgs_ders_tahmin

    kayitlar = []
    harf = sayfa_harfi
    for satir in satirlar:
        hucreler = [v for v in (satir or ()) if v not in (None, "")]
        if not hucreler:
            continue
        if len(hucreler) == 1 and (h := _kitapcik_harfi(hucreler[0])):
            harf = h
            continue
        ders = None
        cevaplar = []
        for v in hucreler:
            metin = str(v).strip()
            if ders is None and lgs_ders_tahmin(metin) and len(metin) > 2:
                ders = metin
                continue
            if ders is None:
                continue
            if (c := cevap_normalize(metin)) is not None:
                cevaplar.append(c)
            elif re.fullmatch(r"[A-EXa-ex\s]{3,}", metin):
                cevaplar += [c.upper() for c in metin if not c.isspace()]
            elif tamsayi(metin) is not None:
                continue  # soru numarası satırı/sütunu
        if ders and len(cevaplar) >= 3:
            kayitlar += [Kayit(kitapcik=harf or "A", test=ders, ders=ders, no=i, cevap=c) for i, c in enumerate(cevaplar, 1)]
    return kayitlar


def kayitlari_oku(veri: bytes) -> list[Kayit]:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(veri), data_only=True, read_only=True)
    except Exception as exc:
        raise OkumaHatasi(f"Dosya Excel olarak açılamadı: {exc}")

    kayitlar: list[Kayit] = []
    for ws in wb.worksheets:
        satirlar = list(ws.iter_rows(values_only=True))
        sayfa_harfi = _kitapcik_harfi(ws.title)
        sayfa_kayitlari = []
        for i, satir in enumerate(satirlar):
            if bloklar := bloklari_bul(satir):
                # Başlığın üstündeki "A Kitapçığı" gibi etiket, sütunu bloğun başladığı yerde ya da
                # solunda olan en yakın etiketse o bloğun kitapçığıdır (yan yana tablolar).
                etiketler = [
                    (j, h)
                    for s_ in satirlar[max(0, i - 3) : i]
                    for j, v in enumerate(s_ or ())
                    if (h := _kitapcik_harfi(v))
                ]
                for b in bloklar:
                    if b.kitapcik:
                        continue
                    bas = min(j for j in (b.no, b.cevap, b.ders, b.test, b.testno) if j is not None)
                    adaylar = [(j, h) for j, h in etiketler if j <= bas] or etiketler
                    if adaylar:
                        b.kitapcik = max(adaylar)[1] if any(j <= bas for j, _ in etiketler) else adaylar[0][1]
                sayfa_kayitlari += _blok_kayitlari(satirlar, i, bloklar, sayfa_harfi)
        if not sayfa_kayitlari:
            sayfa_kayitlari = _dizi_kayitlari(satirlar, sayfa_harfi)
        kayitlar += sayfa_kayitlari
    if not kayitlar:
        raise OkumaHatasi(
            "Cevap anahtarı tablosu bulunamadı. Başlık satırında soru numarası (\"Soru No\", \"A Soru No\", "
            "\"Kitapçık - A\"), doğru cevap (\"Cevap\", \"Doğru Cevap\") ve ders ya da test adı olmalı; "
            "ya da her satırda ders adı ve ardından cevaplar (\"Türkçe | CBDA…\") bulunmalı."
        )
    return kayitlar
