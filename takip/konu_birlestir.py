"""Farklı kaynaklardan gelen aynı ders ve konuları birleştirir.

Denemeler farklı yayınevlerinden ve sistemlerden gelir: bir yerde ders
"İnkılap", başka yerde "T.C. İnkılap Tarihi ve Atatürkçülük"; konu bir yerde
"NOKTALAMA İŞARETLERİ", başka yerde "T.8.3.1. Noktalama işaretlerini…".
Raporlar bunları içeriklerine göre tek satırda toplamalıdır.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# ── Ders ───────────────────────────────────────────────────────────────────


def _ascii(metin: str) -> str:
    s = (metin or "").replace("İ", "i").replace("I", "ı").lower()
    for a, b in zip("ıçğöşüâîû", "icgosuaiu"):
        s = s.replace(a, b)
    return s


def ders_kodu(*adlar: str) -> str | None:
    """Ders adı ya da anahtarından tek bir ders kodu. 8. sınıf İnkılap ile Sosyal aynı koddur ('sosyal')."""
    for ad in adlar:
        d = re.sub(r"[^a-z]", "", _ascii(ad))
        if not d:
            continue
        if "turkce" in d or d in {"tur", "trk"}:
            return "turkce"
        if "matematik" in d or d in {"mat"}:
            return "matematik"
        if "fen" in d:
            return "fen"
        if "inkilap" in d or "tarih" in d or "sosyal" in d or d in {"ink", "tar", "sos"}:
            return "sosyal"
        if "din" in d or "dkab" in d:
            return "din"
        if "ingilizce" in d or "yabancidil" in d or d in {"ing", "yd"}:
            return "ingilizce"
    return None


def ders_etiketi(kod: str, seviye: str = "") -> str:
    if kod == "sosyal":
        return "İnkılap Tarihi" if str(seviye).strip() == "8" else "Sosyal Bilgiler"
    return {
        "turkce": "Türkçe",
        "matematik": "Matematik",
        "fen": "Fen Bilimleri",
        "din": "Din Kültürü",
        "ingilizce": "İngilizce",
    }.get(kod, kod)


# ── Konu ───────────────────────────────────────────────────────────────────

# "T.8.3.1.", "M.8.1.1.2.", "8.1.4.", "F.8.1.2.1.", "E8.1.R1.", "MAT.7.1.3" gibi kazanım kodları
_KOD = re.compile(r"^\s*(?:[A-Za-zÇĞİÖŞÜçğıöşü]{1,4}\.){0,3}[A-Za-zÇĞİÖŞÜçğıöşü]{0,3}\d+(?:\.[0-9A-Za-z]+)+\.?\s*[-–—:]?\s*")
_DOLGU = {
    "ve", "ile", "ilgili", "bir", "bu", "da", "de", "icin", "olan", "gore", "eder", "yapar", "kavrar",
    "belirler", "aciklar", "tespit", "soru", "sorulari", "sorular", "the", "and", "of",
}
KOK_UZUNLUGU = 5


def _kokler(konu: str) -> list[str]:
    metin = _KOD.sub("", konu or "")
    metin = re.sub(r"\bM\.?\s*KEMAL", "Mustafa Kemal", metin, flags=re.I)  # "M. Kemal" kısaltması
    kelimeler = re.findall(r"[a-z0-9]+", _ascii(metin))
    return [k[:KOK_UZUNLUGU] for k in kelimeler if k not in _DOLGU and len(k) > 1]


def _kodsuz(konu: str) -> str:
    return _KOD.sub("", konu or "").strip()


def _baslik_puani(konu: str) -> tuple:
    """Grup başlığı: kodsuz, kısa, büyük harfli konu adı önce."""
    kodlu = bool(_KOD.match(konu or ""))
    return (kodlu, len(_kokler(konu)), len(konu))


class KonuBirlestirici:
    """Bir dersin konu adlarını içeriklerine göre gruplar.

    Kısa adlar (en az kök sayılı) grup başı olur; daha uzun bir ad, bir grup
    başının bütün köklerini içeriyorsa ya da ona çok benziyorsa o gruba katılır.
    Uzun ad birden çok başla eşleşirse en çok ortak kökü olan seçilir. Gruplar
    birbirine zincirlenmez.
    """

    def __init__(self, konular):
        tekil = sorted({k for k in konular if k}, key=lambda k: (len(_kokler(k)), len(k)))
        self._grup: dict[str, str] = {}
        baslar: list[tuple[str, set[str], str]] = []  # (baş, kökler, düz metin)
        for konu in tekil:
            kokler = set(_kokler(konu))
            duz = " ".join(_kokler(konu))
            en_iyi, en_iyi_puan = None, 0.0
            for bas, bas_kok, bas_duz in baslar:
                if not bas_kok:
                    continue
                # Tek kelimelik genel ad ("Paragraf") ayrıntılı konuları ("Paragrafta anlam ve yapı") yutmasın.
                kapsar = bas_kok <= kokler and (len(bas_kok) >= 2 or len(kokler) <= 2)
                benzer = SequenceMatcher(None, duz, bas_duz).ratio() if duz and bas_duz else 0
                # Kelimelerin çoğu ortaksa (ör. "çocukluk ve öğrenim hayatı" iki yazımla) aynı konudur.
                ortak = len(bas_kok & kokler) / len(bas_kok | kokler) if min(len(bas_kok), len(kokler)) >= 3 else 0
                esles = kapsar or benzer >= 0.88 or ortak >= 0.6
                puan = len(bas_kok & kokler) + (1 if kapsar else 0) if esles else 0
                if puan > en_iyi_puan:
                    en_iyi, en_iyi_puan = bas, puan
            if en_iyi is None:
                baslar.append((konu, kokler, duz))
                self._grup[konu] = konu
            else:
                self._grup[konu] = en_iyi
        # Görünen başlık: grubun en okunur adı
        uyeler: dict[str, list[str]] = {}
        for konu, bas in self._grup.items():
            uyeler.setdefault(bas, []).append(konu)
        self._baslik = {bas: min(liste, key=_baslik_puani) for bas, liste in uyeler.items()}

    def anahtar(self, konu: str) -> str:
        """Konunun grup anahtarı (karşılaştırma için)."""
        return self._grup.get(konu, konu).casefold()

    def baslik(self, konu: str) -> str:
        """Raporda görünecek konu adı."""
        bas = self._grup.get(konu, konu)
        ad = self._baslik.get(bas, bas)
        return _kodsuz(ad) or ad
