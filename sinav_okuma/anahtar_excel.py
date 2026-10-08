"""Cevap anahtarı ve kazanım Excel'i.

Beklenen tablo, optik okutma dosyasındaki gibidir. Başlık satırında
Ders, A Soru, B Soru, Cevap ve kazanım sütunları durur. Her satır bir
sorudur. B Soru, aynı sorunun B kitapçıktaki yeridir. Cevap o sorunun
doğru şıkkıdır. Dersler dosyadaki sırayla optik şeride dizilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import zipfile
from io import BytesIO

from sinav_okuma.okuma import GECERLI_SIK, DERS_ETIKETLERI, OptikHata, _katla, ders_kodu


@dataclass
class AnahtarSoru:
    ders_key: str
    ders_ad: str
    test_ad: str
    a_no: int
    b_no: int | None
    cevap: str
    kazanim_kodu: str
    kazanimlar: list[str] = field(default_factory=list)

    @property
    def konu(self) -> str:
        parcalar = []
        if self.kazanim_kodu:
            parcalar.append(self.kazanim_kodu)
        parcalar.extend(metin for metin in self.kazanimlar if metin)
        return " · ".join(parcalar)


@dataclass
class AnahtarBelgesi:
    ad: str
    sinif: str
    sorular: list[AnahtarSoru]

    @property
    def soru_sayisi(self) -> int:
        return len(self.sorular)

    @property
    def dagilim(self) -> list[tuple[str, int]]:
        dagilim: list[tuple[str, int]] = []
        for soru in self._sirala("A"):
            if dagilim and dagilim[-1][0] == soru.ders_key:
                kod, adet = dagilim[-1]
                dagilim[-1] = (kod, adet + 1)
            else:
                dagilim.append((soru.ders_key, 1))
        return dagilim

    @property
    def b_var(self) -> bool:
        return any(soru.b_no for soru in self.sorular)

    def anahtar(self, kitap: str) -> str:
        if kitap == "B" and not self.b_var:
            return ""
        return "".join(soru.cevap for soru in self._sirala(kitap))

    def kazanimlar(self, kitap: str) -> list[str]:
        if kitap == "B" and not self.b_var:
            return []
        return [soru.konu for soru in self._sirala(kitap)]

    def _sirala(self, kitap: str) -> list[AnahtarSoru]:
        alan = "a_no" if kitap != "B" else "b_no"
        bloklar: list[list[AnahtarSoru]] = []
        for soru in self.sorular:
            if not bloklar or bloklar[-1][0].ders_key != soru.ders_key:
                bloklar.append([soru])
            else:
                bloklar[-1].append(soru)
        sonuc: list[AnahtarSoru] = []
        for blok in bloklar:
            sonuc.extend(sorted(blok, key=lambda soru: getattr(soru, alan) or 0))
        return sonuc

    def ozet(self) -> list[dict]:
        satirlar = []
        for kod, adet in self.dagilim:
            ad = next(s.ders_ad for s in self.sorular if s.ders_key == kod)
            satirlar.append({"kod": kod, "ad": ad, "adet": adet, "etiket": DERS_ETIKETLERI.get(kod, ad)})
        return satirlar


def belge_from_sinav(sinav) -> AnahtarBelgesi | None:
    kayitlar = list(sinav.anahtar_sorulari.all())
    if not kayitlar:
        return None
    return AnahtarBelgesi(
        ad=sinav.ad,
        sinif=sinav.sinif_etiket,
        sorular=[
            AnahtarSoru(
                ders_key=kayit.ders_key,
                ders_ad=kayit.ders_ad,
                test_ad=kayit.test_ad,
                a_no=kayit.a_no,
                b_no=kayit.b_no,
                cevap=kayit.cevap,
                kazanim_kodu=kayit.kazanim_kodu,
                kazanimlar=[satir for satir in (kayit.kazanim or "").split("\n") if satir],
            )
            for kayit in kayitlar
        ],
    )


def anahtar_excel_oku(ham: bytes) -> AnahtarBelgesi:
    if not ham:
        raise OptikHata("Excel boş.")
    try:
        import openpyxl
        from openpyxl.utils.exceptions import InvalidFileException
    except ImportError as exc:
        raise OptikHata("Excel okuyucu kurulu değil.") from exc
    try:
        kitap = openpyxl.load_workbook(BytesIO(ham), data_only=True, read_only=True)
    except (InvalidFileException, OSError, ValueError, zipfile.BadZipFile) as exc:
        raise OptikHata("Dosya açılmadı. .xlsx yükleyin.") from exc
    try:
        sayfa = kitap.active
        tablo = [tuple(satir) for satir in sayfa.iter_rows(values_only=True)]
    finally:
        kitap.close()
    if not tablo:
        raise OptikHata("Excel boş.")
    baslik_yeri, sutunlar = _baslik_bul(tablo)
    ad, sinif = _kapak(tablo[:baslik_yeri])
    sorular = _satirlari_oku(tablo[baslik_yeri + 1 :], sutunlar)
    _numaralar_tutarli(sorular)
    return AnahtarBelgesi(ad=ad, sinif=sinif, sorular=sorular)


def _baslik_bul(tablo: list[tuple]) -> tuple[int, dict[str, int]]:
    for yer, satir in enumerate(tablo[:40]):
        bakilan = {}
        kazanimlar: list[tuple[int, int]] = []
        for kolon, hucre in enumerate(satir):
            ad = _katla(str(hucre or ""))
            if not ad:
                continue
            if ad in {"asoru", "asoruno", "asorusayisi"}:
                bakilan["a_no"] = kolon
            elif ad in {"bsoru", "bsoruno", "bsorusayisi"}:
                bakilan["b_no"] = kolon
            elif ad in {"cevap", "dogrucevap", "anahtar"}:
                bakilan["cevap"] = kolon
            elif ad in {"ders", "dersadi", "brans"}:
                bakilan["ders"] = kolon
            elif ad == "test":
                bakilan["test"] = kolon
            elif ad in {"kazanimkodu", "kazanimkod"}:
                bakilan["kod"] = kolon
            elif ad.startswith("kazanim"):
                n = 0
                kuyruk = ad.removeprefix("kazanim")
                if kuyruk.isdigit():
                    n = int(kuyruk)
                kazanimlar.append((n or len(kazanimlar) + 1, kolon))
        if "a_no" in bakilan and "cevap" in bakilan and "ders" in bakilan:
            bakilan["kazanimlar"] = [kolon for _, kolon in sorted(kazanimlar)]
            return yer, bakilan
    raise OptikHata(
        "Başlık satırı yok. Tabloda Ders, A Soru ve Cevap sütunları olmalı."
    )


def _sinif_etiketi(metin: str) -> bool:
    kat = _katla(metin)
    if "sinif" not in kat or len(metin) > 20:
        return False
    return kat.replace("sinif", "").isdigit()


def _kapak(satirlar: list[tuple]) -> tuple[str, str]:
    ad = ""
    sinif = ""
    for satir in satirlar:
        for hucre in satir:
            metin = " ".join(str(hucre or "").split())
            if not metin:
                continue
            if _sinif_etiketi(metin) and not sinif:
                sinif = metin
                continue
            if len(metin) > len(ad):
                ad = metin
    return ad[:200], sinif[:80]


def _satirlari_oku(satirlar: list[tuple], sutunlar: dict) -> list[AnahtarSoru]:
    sorular: list[AnahtarSoru] = []
    for ham in satirlar:
        if not any(hucre is not None and str(hucre).strip() for hucre in ham):
            continue
        ders_ham = _hucre(ham, sutunlar.get("ders"))
        if not ders_ham or _katla(ders_ham) in {"ders", "toplam"}:
            continue
        a_no = _sayi(ham, sutunlar["a_no"])
        if a_no is None:
            continue
        cevap = _hucre(ham, sutunlar["cevap"]).upper().replace("İ", "I")
        if cevap not in GECERLI_SIK:
            raise OptikHata(
                f"{ders_ham} {a_no}. sorunun cevabı A, B, C veya D olmalı."
            )
        kazanimlar = []
        for kolon in sutunlar.get("kazanimlar") or []:
            metin = _hucre(ham, kolon)
            if metin:
                kazanimlar.append(metin)
        sorular.append(
            AnahtarSoru(
                ders_key=ders_kodu(ders_ham),
                ders_ad=ders_ham,
                test_ad=_hucre(ham, sutunlar.get("test")),
                a_no=a_no,
                b_no=_sayi(ham, sutunlar.get("b_no")),
                cevap=cevap,
                kazanim_kodu=_hucre(ham, sutunlar.get("kod"))[:40],
                kazanimlar=kazanimlar,
            )
        )
    if not sorular:
        raise OptikHata("Excel'de soru satırı yok.")
    return sorular


def _numaralar_tutarli(sorular: list[AnahtarSoru]) -> None:
    bloklar: list[list[AnahtarSoru]] = []
    for soru in sorular:
        if not bloklar or bloklar[-1][0].ders_key != soru.ders_key:
            bloklar.append([soru])
        else:
            bloklar[-1].append(soru)
    gorulen: set[str] = set()
    for blok in bloklar:
        if blok[0].ders_key in gorulen:
            raise OptikHata(f"{blok[0].ders_ad} tabloda iki ayrı yerde yazılmış.")
        gorulen.add(blok[0].ders_key)
        ad = blok[0].ders_ad
        a_nolar = [s.a_no for s in blok]
        if len(set(a_nolar)) != len(a_nolar) or sorted(a_nolar) != list(range(1, len(blok) + 1)):
            raise OptikHata(f"{ad} A soru numaraları 1'den {len(blok)}'e kadar birer kez yazılmalı.")
        b_nolar = [s.b_no for s in blok]
        if all(n is None for n in b_nolar):
            continue
        if any(n is None for n in b_nolar):
            raise OptikHata(f"{ad} için B soru numarasının ya hepsi ya hiçbiri yazılmalı.")
        if len(set(b_nolar)) != len(b_nolar) or sorted(b_nolar) != list(range(1, len(blok) + 1)):
            raise OptikHata(f"{ad} B soru numaraları 1'den {len(blok)}'e kadar birer kez yazılmalı.")


def _hucre(satir: tuple, kolon: int | None) -> str:
    if kolon is None or kolon >= len(satir) or satir[kolon] is None:
        return ""
    return " ".join(str(satir[kolon]).split())


def _sayi(satir: tuple, kolon: int | None) -> int | None:
    metin = _hucre(satir, kolon).replace(",", ".")
    if not metin:
        return None
    try:
        sayi = int(float(metin))
    except ValueError as exc:
        raise OptikHata(f"«{metin}» soru numarası değil.") from exc
    if sayi < 1:
        raise OptikHata("Soru numarası 1'den başlar.")
    return sayi
