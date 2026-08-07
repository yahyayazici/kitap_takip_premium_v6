"""Kurum geneli öğrenci listesi PDF içe aktarma."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

from takip.models import EtutHocasi, SinifSube, Talebe

SINIF_HOCA = {
    ("5", "A"): "Recep Bebek",
    ("5", "B"): "Recep Bebek",
    ("6", "A"): "Yusuf Şahin",
    ("6", "B"): "Yusuf Şahin",
    ("7", "A"): "Yahya Yazıcı",
    ("7", "B"): "Yahya Yazıcı",
    ("8", "A"): "Yahya Yazıcı",
    ("8", "B"): "Yahya Yazıcı",
}

SINIF_SIRA = [
    ("5", "A"),
    ("5", "B"),
    ("6", "A"),
    ("6", "B"),
    ("7", "A"),
    ("7", "B"),
    ("8", "A"),
    ("8", "B"),
]


@dataclass
class PdfOgrenci:
    sinif: str
    sube: str
    ad_soyad: str


@dataclass
class PdfImportSonuc:
    eklenen: int = 0
    guncellenen: int = 0
    silinen: int = 0
    numaralandirilan: int = 0
    hatalar: list[str] = field(default_factory=list)


def _pdf_metni(dosya_yolu: str | Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(dosya_yolu))
    parcalar: list[str] = []
    for sayfa in reader.pages:
        metin = sayfa.extract_text() or ""
        parcalar.append(metin)
    return "\n".join(parcalar)


def _baslik_hali(ad: str) -> str:
    ad = " ".join(ad.split())
    return " ".join(kelime.capitalize() for kelime in ad.split(" "))


def _normalize(ad: str) -> str:
    return " ".join(ad.split()).casefold()


def pdf_ogrencileri_coz(dosya_yolu: str | Path) -> list[PdfOgrenci]:
    metin = _pdf_metni(dosya_yolu)
    ogrenciler: list[PdfOgrenci] = []
    aktif_sinif: str | None = None
    aktif_sube: str | None = None

    sinif_re = re.compile(r"(\d+)\s*-\s*([A-Z])\s+SINIFI", re.IGNORECASE)
    ogrenci_re = re.compile(r"^(\d{1,2})\s+([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s.'-]+)$")

    for ham_satir in metin.splitlines():
        satir = " ".join(ham_satir.split())
        if not satir:
            continue

        sinif_eslesme = sinif_re.search(satir)
        if sinif_eslesme:
            aktif_sinif = sinif_eslesme.group(1)
            aktif_sube = sinif_eslesme.group(2).upper()
            continue

        if not aktif_sinif or not aktif_sube:
            continue

        if satir.upper().startswith("SIRA") or "ÖĞRENCİ ADI" in satir.upper():
            continue

        ogrenci_eslesme = ogrenci_re.match(satir)
        if not ogrenci_eslesme:
            continue

        ad = _baslik_hali(ogrenci_eslesme.group(2))
        ogrenciler.append(
            PdfOgrenci(sinif=aktif_sinif, sube=aktif_sube, ad_soyad=ad)
        )

    return ogrenciler


def _hoca_sinif_atamalarini_guncelle() -> None:
    hocalar = {
        hoca.ad_soyad.strip().casefold(): hoca
        for hoca in EtutHocasi.objects.filter(aktif=True)
    }
    siniflar = {
        (grup.sinif.strip(), grup.sube.strip().upper()): grup
        for grup in SinifSube.objects.filter(aktif=True)
    }

    for (sinif, sube), hoca_adi in SINIF_HOCA.items():
        grup = siniflar.get((sinif, sube))
        hoca = hocalar.get(hoca_adi.casefold())
        if not grup or not hoca:
            continue
        hoca.sorumlu_sinif_subeler.add(grup)


def _korunan_kayitlari_temizle(talebe: Talebe) -> None:
    from takip.models import (
        DisiplinKurulu,
        ImamMuezzinAtama,
        TemizlikAtama,
        YemekciAtama,
    )

    TemizlikAtama.objects.filter(talebe=talebe).delete()
    YemekciAtama.objects.filter(talebe=talebe).delete()
    YemekciAtama.objects.filter(yardimci=talebe).delete()
    ImamMuezzinAtama.objects.filter(imam=talebe).delete()
    ImamMuezzinAtama.objects.filter(muezzin=talebe).delete()
    DisiplinKurulu.objects.filter(talebe=talebe).delete()


@transaction.atomic
def kurum_ogrenci_pdf_ice_aktar(
    dosya_yolu: str | Path,
    *,
    listede_olmayanlari_sil: bool = True,
) -> PdfImportSonuc:
    sonuc = PdfImportSonuc()
    ogrenciler = pdf_ogrencileri_coz(dosya_yolu)

    if not ogrenciler:
        sonuc.hatalar.append("PDF içinden öğrenci okunamadı.")
        return sonuc

    _hoca_sinif_atamalarini_guncelle()

    sinif_haritasi = {
        (grup.sinif.strip(), grup.sube.strip().upper()): grup
        for grup in SinifSube.objects.filter(aktif=True)
    }
    hoca_haritasi = {
        hoca.ad_soyad.strip().casefold(): hoca
        for hoca in EtutHocasi.objects.filter(aktif=True)
    }

    pdf_anahtarlari: set[tuple[str, str, str]] = set()
    sirali_kayitlar: list[tuple[PdfOgrenci, SinifSube, EtutHocasi]] = []

    for ogrenci in ogrenciler:
        grup = sinif_haritasi.get((ogrenci.sinif, ogrenci.sube))
        if not grup:
            sonuc.hatalar.append(
                f"{ogrenci.sinif}/{ogrenci.sube} sınıfı sistemde yok: {ogrenci.ad_soyad}"
            )
            continue

        hoca_adi = SINIF_HOCA.get((ogrenci.sinif, ogrenci.sube))
        hoca = hoca_haritasi.get((hoca_adi or "").casefold())
        if not hoca:
            sonuc.hatalar.append(
                f"{ogrenci.sinif}/{ogrenci.sube} için etüt hocası bulunamadı: {hoca_adi}"
            )
            continue

        if not hoca.sorumlu_sinif_subeler.filter(pk=grup.pk).exists():
            hoca.sorumlu_sinif_subeler.add(grup)

        anahtar = (_normalize(ogrenci.ad_soyad), ogrenci.sinif, ogrenci.sube)
        pdf_anahtarlari.add(anahtar)
        sirali_kayitlar.append((ogrenci, grup, hoca))

    if listede_olmayanlari_sil:
        for talebe in Talebe.objects.select_related("sinif_sube"):
            sinif = talebe.sinif_sube.sinif if talebe.sinif_sube_id else talebe.sinif
            sube = (
                talebe.sinif_sube.sube.upper()
                if talebe.sinif_sube_id
                else talebe.sube.upper()
            )
            anahtar = (_normalize(talebe.ad_soyad), sinif.strip(), sube.strip())
            if anahtar not in pdf_anahtarlari:
                _korunan_kayitlari_temizle(talebe)
                talebe.delete()
                sonuc.silinen += 1

    mevcut_listeler: dict[tuple[str, str, str], list[Talebe]] = defaultdict(list)
    for talebe in Talebe.objects.select_related("sinif_sube"):
        sinif = talebe.sinif_sube.sinif if talebe.sinif_sube_id else talebe.sinif
        sube = (
            talebe.sinif_sube.sube.upper()
            if talebe.sinif_sube_id
            else talebe.sube.upper()
        )
        mevcut_listeler[
            (_normalize(talebe.ad_soyad), sinif.strip(), sube.strip())
        ].append(talebe)

    gecici_on_ek = "tmp-"
    for talebe in Talebe.objects.all():
        if talebe.talebe_no:
            yeni = f"{gecici_on_ek}{talebe.pk}"
            talebe.talebe_no = yeni
            talebe.save(update_fields=["talebe_no"])

    islenen: list[Talebe] = []
    for ogrenci, grup, hoca in sirali_kayitlar:
        anahtar = (_normalize(ogrenci.ad_soyad), ogrenci.sinif, ogrenci.sube)
        bekleyen = mevcut_listeler.get(anahtar) or []
        talebe = bekleyen.pop(0) if bekleyen else None

        if talebe:
            talebe.ad_soyad = ogrenci.ad_soyad
            talebe.sinif_sube = grup
            talebe.etut_hocasi = hoca
            talebe.dini_ders_hocasi = hoca
            talebe.aktif = True
            talebe.durum = Talebe.Durum.AKTIF
            talebe.save()
            sonuc.guncellenen += 1
        else:
            talebe = Talebe(
                ad_soyad=ogrenci.ad_soyad,
                sinif_sube=grup,
                etut_hocasi=hoca,
                dini_ders_hocasi=hoca,
                aktif=True,
                durum=Talebe.Durum.AKTIF,
                talebe_no=f"{gecici_on_ek}yeni-{len(islenen)+1}",
            )
            talebe.save()
            sonuc.eklenen += 1

        islenen.append(talebe)

    for kalan in mevcut_listeler.values():
        for talebe in kalan:
            _korunan_kayitlari_temizle(talebe)
            talebe.delete()
            sonuc.silinen += 1

    for index, talebe in enumerate(islenen, start=1):
        yeni_no = str(index)
        talebe.talebe_no = yeni_no
        talebe.save(update_fields=["talebe_no"])
        sonuc.numaralandirilan += 1

    return sonuc
