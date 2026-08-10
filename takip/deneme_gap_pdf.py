"""Deneme Gap PDF — konu D/Y/B parse ve talebe eşleştirme."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction

from takip.deneme_excel import normalize_ad, talebe_eslestir
from takip.deneme_models import (
    DenemeBransSonucu,
    DenemeGapRaporu,
    DenemeKonuSonucu,
    DenemeSinavi,
    DenemeSonucu,
)

_SAYI_SONU = re.compile(
    r"^(?P<konu>.+?)\s+"
    r"(?P<toplam>\d+)\s+"
    r"(?P<dogru>\d+)\s+"
    r"(?P<yanlis>\d+)\s+"
    r"(?P<bos>\d+)\s+"
    r"(?P<yuzde>\d+(?:[.,]\d+)?)\s*$"
)

_DERS_SINIF = re.compile(
    r"^(?P<ders>.+?)\s+"
    r"(?:\d+\s*\.?\s*(?:SINIF|SNF)|SINIF|SNF)\b\s*"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)

_BRANS_ANAHTARLAR = (
    (("turkce", "türkçe", "turkce"), DenemeBransSonucu.Brans.TURKCE),
    (("matematik", "mat"), DenemeBransSonucu.Brans.MATEMATIK),
    (("fen", "fen bilim"), DenemeBransSonucu.Brans.FEN),
    (
        ("ink", "atatürk", "sosyal", "inkilap", "inkılap", "tc ink"),
        DenemeBransSonucu.Brans.SOSYAL,
    ),
    (("din", "dkab"), DenemeBransSonucu.Brans.DIN),
    (("ingilizce", "english", "ing "), DenemeBransSonucu.Brans.INGILIZCE),
)

_KONU_BASLIK = re.compile(
    r"Ders\s+Ad\s+Konu\s+Toplam\s+Doğru\s+Yanlış\s+Boş\s+Yüzde",
    re.IGNORECASE,
)


@dataclass
class GapKonuSatir:
    brans: str
    konu_ham: str
    konu_normalize: str
    toplam: int
    dogru: int
    yanlis: int
    bos: int
    yuzde: Decimal


@dataclass
class GapParseSonuc:
    ham_ad: str = ""
    sinif_metni: str = ""
    konu_satirlari: list[GapKonuSatir] = field(default_factory=list)
    ham_metin_ozet: str = ""
    hatalar: list[str] = field(default_factory=list)


def _pdf_metni_bytes(icerik: bytes) -> str:
    from pypdf import PdfReader

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(icerik)
        yol = tmp.name
    try:
        reader = PdfReader(yol)
        parcalar = [(p.extract_text() or "") for p in reader.pages]
        return "\n".join(parcalar)
    finally:
        Path(yol).unlink(missing_ok=True)


def _ad_dosyadan(dosya_adi: str) -> str:
    ad = Path(dosya_adi or "").stem
    ad = re.sub(r"(?i)_?gap_?raporu?", "", ad)
    ad = ad.replace("_", " ").replace("-", " ")
    ad = re.sub(r"\s+", " ", ad).strip()
    return ad.title() if ad else ""


def _ad_metinden(metin: str) -> tuple[str, str]:
    """PDF başından ad ve sınıf çeker."""
    satirlar = [s.strip() for s in metin.splitlines() if s.strip()]
    ad_parcalari: list[str] = []
    sinif = ""
    for satir in satirlar[:12]:
        if re.match(r"(?i)^s[ıi]n[ıi]f\s*:", satir):
            sinif = satir.split(":", 1)[-1].strip()
            break
        if re.match(r"(?i)^(ders\s+ad|no\s*:|deneme\s+seti)", satir):
            break
        if re.match(r"(?i)^no\s*:", satir):
            continue
        # Büyük harfli ad satırları
        if re.fullmatch(r"[A-ZÇĞİÖŞÜa-zçğıöşü\s.'-]{2,40}", satir):
            if "SINIF" in satir.upper() or "DENEME" in satir.upper():
                break
            ad_parcalari.append(satir)
            if len(ad_parcalari) >= 3:
                break
    ad = " ".join(ad_parcalari).strip()
    ad = re.sub(r"\s+", " ", ad)
    return ad, sinif


def ders_brans_kodu(ders: str) -> str | None:
    n = normalize_ad(ders or "")
    if not n:
        return None
    for anahtarlar, kod in _BRANS_ANAHTARLAR:
        if any(a in n for a in anahtarlar):
            return kod
    return None


def konu_normalize(konu: str) -> str:
    metin = " ".join((konu or "").split())
    return metin.replace("..", "").strip(" .:;-")


def _decimal(deger: str) -> Decimal:
    try:
        return Decimal(deger.replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError):
        return Decimal("0.00")


def _satirlari_birlestir(metin: str) -> list[str]:
    """Çok satırlı ders adlarını (İNK / FEN) tek satıra indirger."""
    ham = [s.strip() for s in metin.splitlines() if s.strip()]
    birlesik: list[str] = []
    i = 0
    while i < len(ham):
        satir = ham[i]
        # Sayılarla bitmiyorsa sonraki satırı ekle (ders adı kırılmış)
        while i + 1 < len(ham) and not _SAYI_SONU.search(satir):
            sonraki = ham[i + 1]
            # Sonraki satır tek başına sayı bloğu veya konu+sayı olabilir
            if _SAYI_SONU.search(sonraki) or re.match(r"^\d", sonraki):
                satir = f"{satir} {sonraki}"
                i += 1
                break
            # "8.SINIF DNA..." gibi devam
            if re.match(r"^\d+\s*\.?\s*(SINIF|SNF)", sonraki, re.I) or (
                ders_brans_kodu(satir) and not ders_brans_kodu(sonraki[:20])
            ):
                satir = f"{satir} {sonraki}"
                i += 1
                continue
            break
        birlesik.append(satir)
        i += 1
    return birlesik


def _konu_satiri_coz(satir: str) -> GapKonuSatir | None:
    m = _SAYI_SONU.search(satir)
    if not m:
        return None
    on = m.group("konu").strip()
    dm = _DERS_SINIF.match(on)
    if dm:
        ders = dm.group("ders").strip()
        konu = (dm.group("rest") or "").strip()
    else:
        # "TÜRKÇE DEYİMLER..." — sınıf etiketi yok
        parcalar = on.split()
        if len(parcalar) < 2:
            return None
        # İlk 1–4 kelime ders olabilir
        ders, konu = on, ""
        for kes in range(min(4, len(parcalar)), 0, -1):
            aday = " ".join(parcalar[:kes])
            if ders_brans_kodu(aday):
                ders = aday
                konu = " ".join(parcalar[kes:]).strip()
                break
        if not konu:
            return None

    brans = ders_brans_kodu(ders)
    if not brans or not konu:
        return None

    return GapKonuSatir(
        brans=brans,
        konu_ham=konu,
        konu_normalize=konu_normalize(konu),
        toplam=int(m.group("toplam")),
        dogru=int(m.group("dogru")),
        yanlis=int(m.group("yanlis")),
        bos=int(m.group("bos")),
        yuzde=_decimal(m.group("yuzde")),
    )


def gap_pdf_parse(icerik: bytes, dosya_adi: str = "") -> GapParseSonuc:
    sonuc = GapParseSonuc()
    try:
        metin = _pdf_metni_bytes(icerik)
    except Exception as exc:  # noqa: BLE001
        sonuc.hatalar.append(f"PDF okunamadı: {exc}")
        return sonuc

    if not (metin or "").strip():
        sonuc.hatalar.append("PDF metni boş.")
        return sonuc

    sonuc.ham_metin_ozet = metin[:2000]
    ad, sinif = _ad_metinden(metin)
    if not ad:
        ad = _ad_dosyadan(dosya_adi)
    sonuc.ham_ad = ad
    sonuc.sinif_metni = sinif

    # Konu tablosu: başlıktan sonrası (yoksa tüm metin)
    konu_bolum = metin
    bas = _KONU_BASLIK.search(metin)
    if bas:
        konu_bolum = metin[bas.end() :]
    else:
        # İlk sayfadaki ders özetini atla — "Deneme Seti" sonrası veya 2. blok
        ayir = re.search(r"(?i)Deneme\s+Seti", metin)
        if ayir:
            # Konu tablosu genelde 2. sayfada; tüm metinde dene
            pass

    for satir in _satirlari_birlestir(konu_bolum):
        if _KONU_BASLIK.search(satir):
            continue
        if re.match(r"(?i)^(ders\s+ad\s+toplam|deneme\s+seti|\*)", satir):
            continue
        # Ders özet satırı (Net sütunu var, konu yok) — konu adı sayıdan önce kısa
        coz = _konu_satiri_coz(satir)
        if not coz:
            continue
        # Özet satır filtresi: "TÜRKÇE 8.SINIF 100 89..." → konu boş kalırdı zaten
        if coz.konu_normalize.upper() in {"", "SINIF", "SNF"}:
            continue
        # Konu yerine sadece sayısal/özet kalanları ele
        if re.fullmatch(r"[\d.,\s]+", coz.konu_ham):
            continue
        sonuc.konu_satirlari.append(coz)

    if not sonuc.konu_satirlari:
        sonuc.hatalar.append("Konu satırı bulunamadı.")
    if not sonuc.ham_ad:
        sonuc.hatalar.append("Öğrenci adı okunamadı.")

    return sonuc


@transaction.atomic
def gap_raporu_kaydet(
    deneme: DenemeSinavi,
    icerik: bytes,
    dosya_adi: str,
    *,
    yukleyen=None,
    talebe_id: int | None = None,
    eslesme_manuel: str | None = None,
) -> DenemeGapRaporu:
    parse = gap_pdf_parse(icerik, dosya_adi)
    rapor = DenemeGapRaporu(
        deneme=deneme,
        dosya_adi=(dosya_adi or "gap.pdf")[:255],
        ham_ad=(parse.ham_ad or "")[:200],
        sinif_metni=(parse.sinif_metni or "")[:40],
        ham_metin_ozet=parse.ham_metin_ozet,
        yukleyen=yukleyen,
    )

    if parse.hatalar and not parse.konu_satirlari:
        rapor.durum = DenemeGapRaporu.Durum.HATA
        rapor.hata_mesaji = "; ".join(parse.hatalar)[:500]
        rapor.eslesme = DenemeGapRaporu.Eslesme.YOK
        rapor.save()
        return rapor

    talebe = None
    eslesme = DenemeGapRaporu.Eslesme.YOK
    oneriler: list[dict] = []

    if talebe_id:
        from takip.models import Talebe

        talebe = Talebe.objects.filter(pk=talebe_id, aktif=True).first()
        eslesme = eslesme_manuel or DenemeGapRaporu.Eslesme.MANUEL
    elif parse.ham_ad:
        talebe, tip, oneriler = talebe_eslestir(
            parse.ham_ad,
            parse.sinif_metni or deneme.sinif_seviyesi or "",
        )
        if tip == "otomatik":
            eslesme = DenemeGapRaporu.Eslesme.OTOMATIK
        elif tip == "alias":
            eslesme = DenemeGapRaporu.Eslesme.ALIAS
        elif tip == "oneri":
            eslesme = DenemeGapRaporu.Eslesme.ONERI
            if oneriler:
                rapor.oneri_talebe_id = oneriler[0].get("id")
        else:
            eslesme = DenemeGapRaporu.Eslesme.YOK

    rapor.talebe = talebe
    rapor.eslesme = eslesme
    if talebe:
        rapor.durum = DenemeGapRaporu.Durum.ISLENDI
    else:
        rapor.durum = DenemeGapRaporu.Durum.ESLESME_BEKLIYOR
        if parse.hatalar:
            rapor.hata_mesaji = "; ".join(parse.hatalar)[:500]

    rapor.save()

    # Aynı talebe için önceki gap konu satırlarını bu denemede değiştir
    if talebe:
        eski = DenemeGapRaporu.objects.filter(
            deneme=deneme,
            talebe=talebe,
        ).exclude(pk=rapor.pk)
        eski.delete()

    sonuc = None
    if talebe:
        sonuc = DenemeSonucu.objects.filter(deneme=deneme, talebe=talebe).first()

    DenemeKonuSonucu.objects.bulk_create(
        [
            DenemeKonuSonucu(
                rapor=rapor,
                sonuc=sonuc,
                brans=s.brans,
                konu_ham=s.konu_ham[:300],
                konu_normalize=(s.konu_normalize or s.konu_ham)[:300],
                toplam=s.toplam,
                dogru=s.dogru,
                yanlis=s.yanlis,
                bos=s.bos,
                yuzde=s.yuzde,
            )
            for s in parse.konu_satirlari
        ]
    )
    return rapor


@transaction.atomic
def gap_raporu_eslestir(
    rapor: DenemeGapRaporu,
    talebe_id: int,
    *,
    eslesme: str = DenemeGapRaporu.Eslesme.MANUEL,
) -> DenemeGapRaporu:
    from takip.models import Talebe

    talebe = Talebe.objects.filter(pk=talebe_id, aktif=True).first()
    if not talebe:
        raise ValueError("Talebe bulunamadı.")

    DenemeGapRaporu.objects.filter(
        deneme=rapor.deneme,
        talebe=talebe,
    ).exclude(pk=rapor.pk).delete()

    rapor.talebe = talebe
    rapor.eslesme = eslesme
    rapor.durum = DenemeGapRaporu.Durum.ISLENDI
    rapor.hata_mesaji = ""
    rapor.oneri_talebe_id = None
    rapor.save(
        update_fields=[
            "talebe",
            "eslesme",
            "durum",
            "hata_mesaji",
            "oneri_talebe_id",
            "guncellenme",
        ]
    )

    sonuc = DenemeSonucu.objects.filter(
        deneme=rapor.deneme,
        talebe=talebe,
    ).first()
    rapor.konu_satirlari.update(sonuc=sonuc)
    return rapor


def deneme_zayif_konular(
    deneme: DenemeSinavi,
    *,
    esik: Decimal = Decimal("70"),
    limit: int = 40,
) -> list[DenemeKonuSonucu]:
    return list(
        DenemeKonuSonucu.objects.filter(
            rapor__deneme=deneme,
            rapor__durum=DenemeGapRaporu.Durum.ISLENDI,
            yuzde__lt=esik,
        )
        .select_related("rapor__talebe", "sonuc")
        .order_by("yuzde", "brans")[:limit]
    )
