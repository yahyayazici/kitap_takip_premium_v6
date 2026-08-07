"""Deneme Excel parse, eşleştirme ve aktarım."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from takip.models import (
    DenemeBransSonucu,
    DenemeEslestirmeAlias,
    DenemeSinavi,
    DenemeSonucu,
    Talebe,
)

BRANS_TANIMLARI: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("turkce", "Türkçe", ("türkçe", "turkce")),
    ("matematik", "Matematik", ("matematik", "mat")),
    ("fen", "Fen Bilimleri", ("fen bilimleri", "fen", "fizik")),
    ("sosyal", "Sosyal Bilgiler", ("sosyal bilgiler", "sosyal", "inkılap", "inkilap")),
    ("din", "Din Kültürü", ("din kültürü", "din kulturu", "din")),
    ("ingilizce", "İngilizce", ("ingilizce", "ingilizce", "ing")),
)

BRANS_KODLARI = [k for k, _, _ in BRANS_TANIMLARI]


def normalize_ad(deger: str) -> str:
    if not deger:
        return ""
    metin = deger.strip().lower()
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    metin = re.sub(r"\s+", " ", metin)
    return metin


def _hucre(deger) -> str:
    if deger is None:
        return ""
    return str(deger).strip()


def _ondalik(deger: str) -> Decimal:
    if not deger:
        return Decimal("0.00")
    metin = deger.strip().replace(" ", "")
    metin = metin.replace(",", ".")
    try:
        return Decimal(metin).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def _tam_sayi(deger: str) -> int:
    if not deger:
        return 0
    metin = deger.strip().replace(",", ".")
    try:
        return max(0, int(float(metin)))
    except (ValueError, TypeError):
        return 0


def _excel_satirlari(dosya) -> list[list[str]]:
    from openpyxl import load_workbook

    workbook = load_workbook(dosya, read_only=True, data_only=True)
    sayfa = workbook.active
    satirlar = []
    for satir in sayfa.iter_rows(values_only=True):
        if not satir:
            continue
        degerler = [_hucre(h) for h in satir]
        if any(degerler):
            satirlar.append(degerler)
    workbook.close()
    return satirlar


def _baslik_haritasi(baslik_satir: list[str]) -> dict[str, Any]:
    harita: dict[str, Any] = {"brans": {}}
    for idx, baslik in enumerate(baslik_satir):
        anahtar = normalize_ad(baslik)
        if not anahtar:
            continue
        if anahtar in {"ad soyad", "adsoyad", "isim", "ogrenci", "öğrenci"}:
            harita["ad_soyad"] = idx
            continue
        if anahtar in {"sinif", "sınıf", "class"}:
            harita["sinif"] = idx
            continue
        if anahtar in {"puan", "score"}:
            harita["puan"] = idx
            continue

        for kod, _, anahtarlar in BRANS_TANIMLARI:
            if any(a in anahtar for a in anahtarlar):
                if "dogru" in anahtar or anahtar.endswith(" d"):
                    harita["brans"].setdefault(kod, {})["dogru"] = idx
                elif "yanlis" in anahtar or "yanlış" in baslik.lower():
                    harita["brans"].setdefault(kod, {})["yanlis"] = idx
                elif "bos" in anahtar or "boş" in baslik.lower():
                    harita["brans"].setdefault(kod, {})["bos"] = idx
                elif "net" in anahtar:
                    harita["brans"].setdefault(kod, {})["net"] = idx
                break

        if "toplam" in anahtar or "genel" in anahtar:
            if "dogru" in anahtar:
                harita.setdefault("toplam", {})["dogru"] = idx
            elif "yanlis" in anahtar or "yanlış" in baslik.lower():
                harita.setdefault("toplam", {})["yanlis"] = idx
            elif "bos" in anahtar or "boş" in baslik.lower():
                harita.setdefault("toplam", {})["bos"] = idx
            elif "net" in anahtar:
                harita.setdefault("toplam", {})["net"] = idx

    return harita


@dataclass
class DenemeImportSatir:
    satir_no: int
    excel_ad_soyad: str
    sinif: str
    talebe_id: int | None = None
    eslesme: str = "yok"
    branslar: dict = field(default_factory=dict)
    toplam: dict = field(default_factory=dict)
    puan: str = "0"
    hatalar: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "satir_no": self.satir_no,
            "excel_ad_soyad": self.excel_ad_soyad,
            "sinif": self.sinif,
            "talebe_id": self.talebe_id,
            "eslesme": self.eslesme,
            "branslar": self.branslar,
            "toplam": self.toplam,
            "puan": self.puan,
            "hatalar": self.hatalar,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DenemeImportSatir:
        return cls(**data)


@dataclass
class DenemeImportOnizleme:
    satirlar: list[DenemeImportSatir] = field(default_factory=list)
    hatalar: list[str] = field(default_factory=list)

    @property
    def toplam_ogrenci(self) -> int:
        return len(self.satirlar)

    @property
    def eslesen(self) -> int:
        return sum(1 for s in self.satirlar if s.talebe_id)

    @property
    def eslesmeyen(self) -> int:
        return sum(1 for s in self.satirlar if not s.talebe_id)

    def to_session(self) -> dict:
        return {
            "satirlar": [s.to_dict() for s in self.satirlar],
            "hatalar": self.hatalar,
        }

    @classmethod
    def from_session(cls, data: dict) -> DenemeImportOnizleme:
        return cls(
            satirlar=[DenemeImportSatir.from_dict(s) for s in data.get("satirlar", [])],
            hatalar=data.get("hatalar", []),
        )


def _satir_deger(satir: list[str], index: int | None) -> str:
    if index is None or index >= len(satir):
        return ""
    return satir[index]


def talebe_eslestir(excel_ad: str, sinif: str = "") -> tuple[Talebe | None, str]:
    norm = normalize_ad(excel_ad)
    if not norm:
        return None, "yok"

    alias = DenemeEslestirmeAlias.objects.filter(excel_adi=norm).select_related("talebe").first()
    if alias and alias.talebe.aktif:
        return alias.talebe, "alias"

    adaylar = list(
        Talebe.objects.filter(aktif=True, ad_soyad__iexact=excel_ad.strip())
    )
    if len(adaylar) == 1:
        return adaylar[0], "otomatik"
    if len(adaylar) > 1 and sinif:
        sinif_norm = normalize_ad(sinif)
        filtre = [
            t
            for t in adaylar
            if sinif_norm
            in normalize_ad(str(t.sinif_sube.sinif if t.sinif_sube else t.sinif))
        ]
        if len(filtre) == 1:
            return filtre[0], "otomatik"
    return None, "yok"


def deneme_excel_onizle(dosya) -> DenemeImportOnizleme:
    onizleme = DenemeImportOnizleme()
    try:
        satirlar = _excel_satirlari(dosya)
    except Exception as exc:
        onizleme.hatalar.append(f"Dosya okunamadı: {exc}")
        return onizleme

    if not satirlar:
        onizleme.hatalar.append("Excel dosyası boş.")
        return onizleme

    harita = _baslik_haritasi(satirlar[0])
    if "ad_soyad" not in harita:
        onizleme.hatalar.append("Ad Soyad sütunu bulunamadı.")
        return onizleme

    for satir_no, satir in enumerate(satirlar[1:], start=2):
        ad = _satir_deger(satir, harita.get("ad_soyad"))
        if not ad:
            continue
        sinif = _satir_deger(satir, harita.get("sinif"))
        kayit = DenemeImportSatir(satir_no=satir_no, excel_ad_soyad=ad, sinif=sinif)

        for kod, _, _ in BRANS_TANIMLARI:
            bh = harita.get("brans", {}).get(kod, {})
            dogru = _tam_sayi(_satir_deger(satir, bh.get("dogru")))
            yanlis = _tam_sayi(_satir_deger(satir, bh.get("yanlis")))
            bos = _tam_sayi(_satir_deger(satir, bh.get("bos")))
            net_raw = _satir_deger(satir, bh.get("net"))
            net = _ondalik(net_raw) if net_raw else DenemeBransSonucu.net_hesapla(dogru, yanlis)
            if dogru or yanlis or bos or net:
                kayit.branslar[kod] = {
                    "dogru": dogru,
                    "yanlis": yanlis,
                    "bos": bos,
                    "net": str(net),
                }

        th = harita.get("toplam", {})
        t_dogru = _tam_sayi(_satir_deger(satir, th.get("dogru")))
        t_yanlis = _tam_sayi(_satir_deger(satir, th.get("yanlis")))
        t_bos = _tam_sayi(_satir_deger(satir, th.get("bos")))
        t_net_raw = _satir_deger(satir, th.get("net"))
        if t_dogru or t_yanlis or t_bos or t_net_raw:
            t_net = _ondalik(t_net_raw) if t_net_raw else sum(
                (_ondalik(v.get("net", "0")) for v in kayit.branslar.values()),
                Decimal("0"),
            )
            kayit.toplam = {
                "dogru": t_dogru,
                "yanlis": t_yanlis,
                "bos": t_bos,
                "net": str(t_net.quantize(Decimal("0.01"))),
            }

        kayit.puan = _satir_deger(satir, harita.get("puan")) or "0"

        talebe, eslesme = talebe_eslestir(ad, sinif)
        if talebe:
            kayit.talebe_id = talebe.id
            kayit.eslesme = eslesme

        onizleme.satirlar.append(kayit)

    return onizleme


def session_key(deneme_id: int) -> str:
    return f"deneme_import_{deneme_id}"


@transaction.atomic
def deneme_sonuclari_aktar(
    deneme: DenemeSinavi,
    onizleme: DenemeImportOnizleme,
    user: User,
) -> tuple[int, list[str]]:
    hatalar: list[str] = []
    if deneme.durum == DenemeSinavi.Durum.AKTIF:
        return 0, ["Bu deneme zaten aktarılmış. Sonuçlar arşivlenir, tekrar yüklenemez."]

    eslesmeyen = [s for s in onizleme.satirlar if not s.talebe_id]
    if eslesmeyen:
        return 0, [f"{len(eslesmeyen)} öğrenci eşleşmedi. Manuel eşleştirme gerekli."]

    DenemeSonucu.objects.filter(deneme=deneme).delete()
    kayit_sayisi = 0

    for satir in onizleme.satirlar:
        talebe = Talebe.objects.get(pk=satir.talebe_id)
        toplam = satir.toplam or {}
        t_net = _ondalik(str(toplam.get("net", "0")))
        if not toplam and satir.branslar:
            t_net = sum(
                (_ondalik(v.get("net", "0")) for v in satir.branslar.values()),
                Decimal("0"),
            ).quantize(Decimal("0.01"))
            toplam = {
                "dogru": sum(v.get("dogru", 0) for v in satir.branslar.values()),
                "yanlis": sum(v.get("yanlis", 0) for v in satir.branslar.values()),
                "bos": sum(v.get("bos", 0) for v in satir.branslar.values()),
                "net": str(t_net),
            }

        sonuc = DenemeSonucu.objects.create(
            deneme=deneme,
            talebe=talebe,
            toplam_dogru=int(toplam.get("dogru", 0)),
            toplam_yanlis=int(toplam.get("yanlis", 0)),
            toplam_bos=int(toplam.get("bos", 0)),
            toplam_net=t_net,
            puan=_ondalik(satir.puan),
        )

        for kod, veri in satir.branslar.items():
            DenemeBransSonucu.objects.create(
                sonuc=sonuc,
                brans=kod,
                dogru=int(veri.get("dogru", 0)),
                yanlis=int(veri.get("yanlis", 0)),
                bos=int(veri.get("bos", 0)),
                net=_ondalik(str(veri.get("net", "0"))),
            )

        norm = normalize_ad(satir.excel_ad_soyad)
        DenemeEslestirmeAlias.objects.update_or_create(
            excel_adi=norm,
            defaults={"talebe": talebe},
        )
        kayit_sayisi += 1

    deneme.durum = DenemeSinavi.Durum.AKTIF
    deneme.yukleyen = user
    deneme.yuklenme_zamani = timezone.now()
    deneme.save(
        update_fields=["durum", "yukleyen", "yuklenme_zamani", "guncellenme"]
    )
    return kayit_sayisi, hatalar
