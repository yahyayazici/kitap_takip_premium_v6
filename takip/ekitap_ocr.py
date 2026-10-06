"""Taranmış (yazı katmanı olmayan) sayfalar için OCR.

Tesseract sistem programı (Dockerfile: ``tesseract-ocr``) alt süreç olarak
çağrılır; Python bağımlılığı eklenmez. Kurulu değilse OCR atlanır ve sayfa
"taranmış" olarak işaretlenmeye devam eder.

Çıktı, metin katmanlı sayfalarla aynı tespit hattına girer:
- satır başındaki "12." / "12)" sözcükleri → soru numarası adayları,
- "A)" satırları → şık başlangıcı,
- mürekkep bantları (dikey şeritlerde koyu piksel satırları) → içerik kutuları;
  böylece soru alanları şekilleri ve şıkları da kapsar.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)

OCR_GENISLIK = 2400  # OCR için sayfa görseli genişliği (A4'te ~290 dpi)
OCR_ZAMAN_ASIMI = 60
MUREKKEP_ESIGI = 150
SERIT_SAYISI = 24

_NUMARA = re.compile(r"^(\d{1,3})[.)]$|^(\d{1,3})[.)]\S")
_SIK_A = re.compile(r"^A[).]")


@dataclass
class OcrSozcuk:
    metin: str
    guven: float
    x0: float
    y0: float
    x1: float
    y1: float
    satir: tuple  # (psm, blok, paragraf, satır)


def ocr_kullanilabilir() -> bool:
    return shutil.which("tesseract") is not None


def _tesseract(gorsel, psm: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png") as dosya:
        gorsel.save(dosya.name, format="PNG")
        sonuc = subprocess.run(
            ["tesseract", dosya.name, "stdout", "--psm", psm, "-l", "eng", "tsv"],
            capture_output=True,
            timeout=OCR_ZAMAN_ASIMI,
            check=False,
        )
    if sonuc.returncode != 0:
        raise RuntimeError(sonuc.stderr.decode("utf-8", "ignore")[:200])
    return sonuc.stdout.decode("utf-8", "ignore")


def sozcukleri_oku(gorsel, psm: str = "4") -> list[OcrSozcuk]:
    """Sayfa görselindeki sözcükler (koordinatlar 0–1, sol üst orijinli).

    psm 4 (değişken boyutlu tek sütun) satır yapısını korur; psm 11 (seyrek
    metin) şekillerin yanındaki numaraları da kaçırmaz. ``sayfayi_oku`` ikisini
    birleştirir.
    """
    W, H = gorsel.size
    sozcukler: list[OcrSozcuk] = []
    satirlar = _tesseract(gorsel, psm).splitlines()
    for satir in satirlar[1:]:
        p = satir.split("\t")
        if len(p) < 12 or p[0] != "5" or not p[11].strip():
            continue
        try:
            sol, ust, gen, yuk = (int(v) for v in p[6:10])
            guven = float(p[10])
        except ValueError:
            continue
        sozcukler.append(
            OcrSozcuk(
                metin=p[11].strip(),
                guven=max(guven, 0.0) / 100.0,
                x0=sol / W, y0=ust / H, x1=(sol + gen) / W, y1=(ust + yuk) / H,
                satir=(psm, int(p[2]), int(p[3]), int(p[4])),
            )
        )
    return sozcukler


SUTUN_BOSLUGU = 0.025


def satir_parcalari(sozcukler: list[OcrSozcuk]) -> list[list[OcrSozcuk]]:
    """OCR satırlarını büyük yatay boşluklardan böler (iki sütun tek satır okunabilir)."""
    satirlar: dict[tuple, list[OcrSozcuk]] = {}
    for s in sozcukler:
        satirlar.setdefault(s.satir, []).append(s)
    parcalar: list[list[OcrSozcuk]] = []
    for liste in satirlar.values():
        liste.sort(key=lambda w: w.x0)
        parca = [liste[0]]
        for w in liste[1:]:
            if w.x0 - parca[-1].x1 > SUTUN_BOSLUGU:
                parcalar.append(parca)
                parca = []
            parca.append(w)
        parcalar.append(parca)
    return parcalar


def satir_baslari(sozcukler: list[OcrSozcuk]) -> list[OcrSozcuk]:
    return [p[0] for p in satir_parcalari(sozcukler)]


def numara_adaylari(sozcukler: list[OcrSozcuk]) -> list[tuple[int, OcrSozcuk, bool]]:
    """(numara, sözcük, ardından metin geliyor mu) — yalnızca satır başları."""
    sonuc = []
    for parca in satir_parcalari(sozcukler):
        bas = parca[0]
        e = _NUMARA.match(bas.metin)
        if not e:
            continue
        no = int(e.group(1) or e.group(2))
        if 1 <= no <= 200:
            sonuc.append((no, bas, len(parca) > 1))
    return sonuc


def grup_basliklari(sozcukler: list[OcrSozcuk]) -> list[tuple[tuple[float, float, float, float], list[int]]]:
    """"9 ve 10. soruları ..." satırları: (kutu, numaralar)."""
    from takip.ekitap_soru_tespit import _grup_basligi

    sonuc = []
    for parca in satir_parcalari([s for s in sozcukler if s.satir[0] == "4"]):
        numaralar = _grup_basligi(" ".join(w.metin for w in parca))
        if numaralar:
            sonuc.append((
                (min(w.x0 for w in parca), min(w.y0 for w in parca), max(w.x1 for w in parca), max(w.y1 for w in parca)),
                numaralar,
            ))
    return sonuc


def sik_baslari(sozcukler: list[OcrSozcuk]) -> list[OcrSozcuk]:
    return [s for s in satir_baslari(sozcukler) if _SIK_A.match(s.metin)]


def murekkep_kutulari(gorsel) -> list[tuple[float, float, float, float]]:
    """Dikey şeritlerde ardışık mürekkep satırlarının kutuları (0–1).

    Şekiller ve çizimler OCR'da sözcük üretmediği için soru alanının altını
    belirlemede bu kutular kullanılır.
    """
    from PIL import Image, ImageOps

    kucuk = gorsel.convert("L")
    oran = 800 / max(kucuk.width, 1)
    kucuk = kucuk.resize((800, max(int(kucuk.height * oran), 1)))
    murekkep = ImageOps.invert(kucuk).point(lambda v: 255 if v > 255 - MUREKKEP_ESIGI else 0)
    W, H = murekkep.size
    serit = W / SERIT_SAYISI
    kutular = []
    for i in range(SERIT_SAYISI):
        x0, x1 = int(i * serit), int((i + 1) * serit)
        parca = murekkep.crop((x0, 0, x1, H))
        # Satır başına mürekkep var mı: genişliği 1 piksele indirip bak.
        sutun = parca.resize((1, H), Image.Resampling.BOX)
        degerler = list(sutun.getdata())
        y = 0
        while y < H:
            if degerler[y] < 2:
                y += 1
                continue
            bas = y
            while y < H and degerler[y] >= 2:
                y += 1
            bant = parca.crop((0, bas, x1 - x0, y)).getbbox()
            if bant:
                kutular.append(((x0 + bant[0]) / W, bas / H, (x0 + bant[2]) / W, y / H))
    return _seritleri_birlestir(kutular)


def _seritleri_birlestir(kutular, bosluk: float = 0.012):
    """Aynı satırdaki bitişik şerit kutularını birleştirir.

    Sözcük arası boşluk küçük, sütun oluğu büyüktür: tam genişlikteki bir satır
    tek kutu olur (sayfa o yükseklikte tek sütun sayılır), iki sütunun aynı
    yükseklikteki satırları ayrı kalır.
    """
    sonuc: list[list[float]] = []
    for k in sorted(kutular, key=lambda k: (k[0], k[1])):
        for s in sonuc:
            dikey = min(s[3], k[3]) - max(s[1], k[1])
            if dikey > 0.5 * min(s[3] - s[1], k[3] - k[1]) and 0 <= k[0] - s[2] <= bosluk:
                s[0], s[1], s[2], s[3] = min(s[0], k[0]), min(s[1], k[1]), max(s[2], k[2]), max(s[3], k[3])
                break
        else:
            sonuc.append(list(k))
    return [tuple(s) for s in sonuc]


@dataclass
class OcrSayfasi:
    numaralar: list[tuple[int, OcrSozcuk, bool]]
    sik_baslari: list[OcrSozcuk]
    murekkep: list[tuple[float, float, float, float]]
    karakter: int
    grup_basliklari: list = None


def _tekillestir(ogeler, kutu):
    sonuc = []
    for oge in ogeler:
        k = kutu(oge)
        if any(abs(k.x0 - kutu(d).x0) < 0.01 and abs(k.y0 - kutu(d).y0) < 0.008 for d in sonuc):
            continue
        sonuc.append(oge)
    return sonuc


def sayfayi_oku(gorsel) -> OcrSayfasi:
    """Taranmış sayfa görselini OCR ile okur (psm 4 + psm 11 birleşimi)."""
    if gorsel.width != OCR_GENISLIK:
        gorsel = gorsel.resize((OCR_GENISLIK, max(int(gorsel.height * OCR_GENISLIK / gorsel.width), 1)))
    gri = gorsel.convert("L")
    sozcukler = sozcukleri_oku(gri, "4") + sozcukleri_oku(gri, "11")
    numaralar = _tekillestir(
        sorted(numara_adaylari(sozcukler), key=lambda n: (-n[2], -n[1].guven)), lambda n: n[1]
    )
    siklar = _tekillestir(sik_baslari(sozcukler), lambda s: s)
    return OcrSayfasi(
        numaralar=numaralar,
        sik_baslari=siklar,
        murekkep=murekkep_kutulari(gri),
        karakter=sum(len(s.metin) for s in sozcukler) // 2,
        grup_basliklari=grup_basliklari(sozcukler),
    )
