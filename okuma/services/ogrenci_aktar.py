"""Öğrenci listesini yapıştırılan metinden ya da Excel'den içe aktarır (numaraya göre ekle/güncelle)."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import openpyxl
from django.db import transaction

from okuma.models import Deneme, Ogrenci
from okuma.services.optik import numara_normalize

SINIF_SUBE = re.compile(r"^(\d{1,2})\s*[\.\-/ ]?\s*(?:sınıf|sinif)?\s*[\-/ ]?\s*([A-Za-zÇĞİÖŞÜçğıöşü])?\s*(?:şube(?:si)?)?$", re.I)


@dataclass
class OgrenciSatiri:
    numara: str
    ad_soyad: str = ""
    sinif: str = ""
    sube: str = ""


@dataclass
class AktarimSonucu:
    eklenen: int = 0
    guncellenen: int = 0
    degismeyen: int = 0
    hatalar: list[str] = field(default_factory=list)
    ogrenci_idler: set[int] = field(default_factory=set)


def _bosluk(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def tr_buyuk(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def sinif_sube_ayir(deger: str) -> tuple[str, str]:
    """'7A', '7-A', '7/A', '7. Sınıf A' → ('7', 'A')."""
    deger = _bosluk(deger)
    if not deger:
        return "", ""
    m = SINIF_SUBE.match(deger)
    if m:
        return m.group(1), tr_buyuk(m.group(2) or "")
    if len(deger) == 1 and deger.isalpha():
        return "", tr_buyuk(deger)
    return "", ""


def metni_ayristir(metin: str) -> tuple[list[OgrenciSatiri], list[str]]:
    """Her satır: `numara<TAB>ad soyad<TAB>sınıf<TAB>şube` (; ya da , da olur)
    veya ayraçsız `numara ad soyad [7A]`."""
    satirlar, hatalar = [], []
    for i, ham in enumerate(metin.splitlines(), start=1):
        if not ham.strip():
            continue
        if "\t" in ham or ";" in ham:
            parcalar = [_bosluk(p) for p in re.split(r"[\t;]", ham)]
        elif ham.count(",") >= 1 and not re.match(r"^\s*\d+\s+\S", ham):
            parcalar = [_bosluk(p) for p in ham.split(",")]
        else:
            kelimeler = ham.split()
            parcalar = [kelimeler[0], " ".join(kelimeler[1:])]
            if len(kelimeler) > 2 and sinif_sube_ayir(kelimeler[-1])[0]:
                parcalar = [kelimeler[0], " ".join(kelimeler[1:-1]), kelimeler[-1]]
        numara = re.sub(r"\D", "", parcalar[0])
        if not numara:
            if i == 1 and not any(ch.isdigit() for ch in parcalar[0]):
                continue  # başlık satırı
            hatalar.append(f"{i}. satır: numara okunamadı ({ham.strip()[:40]})")
            continue
        satir = OgrenciSatiri(numara=numara_normalize(numara), ad_soyad=parcalar[1] if len(parcalar) > 1 else "")
        if len(parcalar) > 3 and parcalar[3]:
            satir.sinif, satir.sube = re.sub(r"\D", "", parcalar[2]), tr_buyuk(parcalar[3][:1])
        elif len(parcalar) > 2:
            satir.sinif, satir.sube = sinif_sube_ayir(parcalar[2])
        satirlar.append(satir)
    return satirlar, hatalar


def _norm(s) -> str:
    s = str(s or "").strip().lower()
    for a, b in zip("ıİçğöşü", "iicgosu"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z]", "", s)


def excel_ayristir(veri: bytes) -> tuple[list[OgrenciSatiri], list[str]]:
    wb = openpyxl.load_workbook(io.BytesIO(veri), data_only=True, read_only=True)
    satirlar = list(wb.worksheets[0].iter_rows(values_only=True))
    baslik_idx, kolon = None, {}
    for i, satir in enumerate(satirlar[:20]):
        normlar = [_norm(h) for h in satir]
        for j, h in enumerate(normlar):
            if h in {"numara", "no", "ogrencino", "okulno", "ogrencinumarasi", "okulnumarasi"}:
                kolon.setdefault("numara", j)
            elif h in {"adsoyad", "adisoyadi", "adivesoyadi", "ogrenci", "ogrenciadi", "isim", "adsoyadi"}:
                kolon.setdefault("ad_soyad", j)
            elif h in {"ad", "adi"}:
                kolon.setdefault("ad", j)
            elif h in {"soyad", "soyadi"}:
                kolon.setdefault("soyad", j)
            elif h in {"sinif", "sinifi", "sinifsube", "sinifsubesi"}:
                kolon.setdefault("sinif", j)
            elif h in {"sube", "subesi"}:
                kolon.setdefault("sube", j)
        if "numara" in kolon:
            baslik_idx = i
            break
        kolon = {}
    if baslik_idx is None:
        raise ValueError("Excel'de 'Numara' (veya 'No') başlıklı sütun bulunamadı.")

    sonuc, hatalar = [], []
    for i, satir in enumerate(satirlar[baslik_idx + 1 :], start=baslik_idx + 2):
        def al(ad):
            return _bosluk(satir[kolon[ad]]) if ad in kolon and kolon[ad] < len(satir) else ""

        ham_no = al("numara")
        if ham_no.endswith(".0"):
            ham_no = ham_no[:-2]
        numara = re.sub(r"\D", "", ham_no)
        if not numara:
            if any(v not in (None, "") for v in satir):
                hatalar.append(f"{i}. satır: numara boş")
            continue
        ad = al("ad_soyad") or " ".join(x for x in (al("ad"), al("soyad")) if x)
        sinif, sube = sinif_sube_ayir(al("sinif"))
        if al("sube"):
            sube = tr_buyuk(al("sube")[:1])
        sonuc.append(OgrenciSatiri(numara=numara_normalize(numara), ad_soyad=ad, sinif=sinif, sube=sube))
    return sonuc, hatalar


@transaction.atomic
def ogrencileri_kaydet(satirlar: list[OgrenciSatiri], varsayilan_sinif: str = "") -> AktarimSonucu:
    sonuc = AktarimSonucu()
    gorulen = set()
    for s in satirlar:
        if s.numara in gorulen:
            sonuc.hatalar.append(f"{s.numara} listede birden fazla kez geçiyor; ilki alındı")
            continue
        gorulen.add(s.numara)
        ogr = Ogrenci.objects.filter(numara=s.numara).first()
        yeni = {
            "ad_soyad": s.ad_soyad,
            "sinif_seviyesi": s.sinif or varsayilan_sinif,
            "sube": s.sube,
        }
        if ogr is None:
            ogr = Ogrenci.objects.create(numara=s.numara, **yeni)
            sonuc.eklenen += 1
        else:
            degisen = [k for k, v in yeni.items() if v and getattr(ogr, k) != v]
            for k in degisen:
                setattr(ogr, k, yeni[k])
            if degisen:
                ogr.save(update_fields=degisen)
                sonuc.guncellenen += 1
            else:
                sonuc.degismeyen += 1
                continue
        sonuc.ogrenci_idler.add(ogr.pk)
    return sonuc


def etkilenen_denemeleri_hesapla(ogrenci_idler) -> int:
    """Şube değişince sıralamalar değişir; ilgili denemeleri yeniden hesaplar."""
    from okuma.services.puanlama import deneme_hesapla

    denemeler = Deneme.objects.filter(sonuclar__ogrenci_id__in=ogrenci_idler).distinct()
    adet = 0
    for d in denemeler:
        deneme_hesapla(d)
        adet += 1
    return adet
