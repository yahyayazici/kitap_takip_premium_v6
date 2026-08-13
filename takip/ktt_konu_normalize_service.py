"""KTT konu adı normalizasyonu ve standart konu eşleştirmesi."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import F

from takip.konu_destek_models import KonuKatalogu
from takip.konu_destek_service import ders_adindan_brans, konu_getir_veya_olustur
from takip.ktt_akilli_models import KonuAlias, KonuEslestirmeInceleme, KttEslestirmeEsik
from takip.models import KttSinav

YAYGIN_KISALTMALAR = {
    "a": "anlam",
    "anl": "anlam",
    "paragraf": "paragrafta anlam",
    "par": "paragrafta anlam",
    "yazim": "yazim kurallari",
    "noktalama": "noktalama isaretleri",
    "anlatim boz": "anlatim bozuklugu",
    "problem": "problemler",
    "problemler": "problemler",
    "rasyonel": "rasyonel sayilar",
    "tam sayi": "tam sayilar",
    "cebirsel": "cebirsel ifadeler",
    "basinc": "basinc",
    "basinç": "basinc",
}

DEFAULT_ESIK = {
    "yuksek_guven": 88,
    "orta_guven": 72,
}


@dataclass(frozen=True)
class KonuEslestirmeSonuc:
    konu: KonuKatalogu | None
    ham_metin: str
    guven: int
    kaynak: str  # alias, tam, fuzzy, yeni, bekliyor
    inceleme_id: int | None = None


def esikler() -> dict:
    kayit = KttEslestirmeEsik.objects.first()
    if not kayit:
        return dict(DEFAULT_ESIK)
    return {
        "yuksek_guven": kayit.yuksek_guven,
        "orta_guven": kayit.orta_guven,
        "kapanma_gelisim_puan": kayit.kapanma_gelisim_puan,
        "zayif_ktt_puan": kayit.zayif_ktt_puan,
    }


def _turkce_ascii(metin: str) -> str:
    tablo = str.maketrans(
        "çğıöşüÇĞİÖŞÜ",
        "cgiosucgiosu",
    )
    return metin.translate(tablo)


def normalize_konu_metni(metin: str) -> str:
    if not metin:
        return ""
    metin = unicodedata.normalize("NFKC", metin.strip())
    metin = _turkce_ascii(metin.casefold())
    metin = re.sub(r"[^\w\s]", " ", metin, flags=re.UNICODE)
    metin = re.sub(r"\s+", " ", metin).strip()
    parcalar = metin.split()
    genisletilmis: list[str] = []
    for parca in parcalar:
        if parca.endswith(".") and len(parca) <= 3:
            parca = parca.rstrip(".")
        genisletilmis.append(YAYGIN_KISALTMALAR.get(parca, parca))
    return " ".join(genisletilmis).strip()


def _benzerlik(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _katalog_adaylari(sinif: str, brans: str) -> list[KonuKatalogu]:
    return list(
        KonuKatalogu.objects.filter(
            sinif_seviyesi=sinif,
            brans=brans,
            aktif=True,
        ).order_by("konu_ad")
    )


def konu_eslestir(
    sinif_seviyesi: str,
    brans: str,
    ham_metin: str,
    *,
    ktt: KttSinav | None = None,
    otomatik_kaydet: bool = True,
    yeni_konu_olustur: bool = True,
) -> KonuEslestirmeSonuc:
    """Sınıf + branş bağlamında standart konu eşleştirmesi."""
    ham = (ham_metin or "").strip()
    norm = normalize_konu_metni(ham)
    if not norm:
        return KonuEslestirmeSonuc(None, ham, 0, "bos")

    esik = esikler()

    alias = (
        KonuAlias.objects.filter(
            sinif_seviyesi=sinif_seviyesi,
            brans=brans,
            ham_normalize=norm,
            onaylandi=True,
        )
        .select_related("konu")
        .first()
    )
    if alias:
        if otomatik_kaydet:
            KonuAlias.objects.filter(pk=alias.pk).update(
                kullanim_sayisi=F("kullanim_sayisi") + 1
            )
        return KonuEslestirmeSonuc(alias.konu, ham, 100, "alias")

    adaylar = _katalog_adaylari(sinif_seviyesi, brans)
    en_iyi: KonuKatalogu | None = None
    en_skor = 0.0
    for aday in adaylar:
        aday_norm = normalize_konu_metni(aday.konu_ad)
        skor = max(
            _benzerlik(norm, aday_norm),
            _benzerlik(norm, aday_norm.replace(" ", "")),
        )
        if norm in aday_norm or aday_norm in norm:
            skor = max(skor, 0.92)
        if skor > en_skor:
            en_skor = skor
            en_iyi = aday

    guven = int(round(en_skor * 100))

    if en_iyi and guven >= esik["yuksek_guven"]:
        if otomatik_kaydet:
            _alias_kaydet(sinif_seviyesi, brans, norm, en_iyi)
        return KonuEslestirmeSonuc(en_iyi, ham, guven, "fuzzy")

    if en_iyi and guven >= esik["orta_guven"]:
        inceleme_id = None
        if otomatik_kaydet:
            inceleme, _ = KonuEslestirmeInceleme.objects.get_or_create(
                sinif_seviyesi=sinif_seviyesi,
                brans=brans,
                ham_normalize=norm,
                defaults={
                    "ham_metin": ham,
                    "onerilen_konu": en_iyi,
                    "guven_yuzde": guven,
                    "ktt": ktt,
                    "durum": KonuEslestirmeInceleme.Durum.BEKLIYOR,
                },
            )
            inceleme_id = inceleme.id
        return KonuEslestirmeSonuc(en_iyi, ham, guven, "bekliyor", inceleme_id)

    if yeni_konu_olustur:
        konu = konu_getir_veya_olustur(sinif_seviyesi, brans, ham.title())
        if otomatik_kaydet and guven >= esik["orta_guven"] and en_iyi:
            _alias_kaydet(sinif_seviyesi, brans, norm, en_iyi)
        return KonuEslestirmeSonuc(konu, ham, guven, "yeni")

    return KonuEslestirmeSonuc(en_iyi, ham, guven, "dusuk")


def _alias_kaydet(sinif: str, brans: str, norm: str, konu: KonuKatalogu) -> None:
    KonuAlias.objects.update_or_create(
        sinif_seviyesi=sinif,
        brans=brans,
        ham_normalize=norm,
        defaults={"konu": konu, "onaylandi": True},
    )


@transaction.atomic
def ktt_konu_eslestir(ktt: KttSinav, *, kullanici=None) -> KonuEslestirmeSonuc:
    """KTT kaydına standart konu bağlar."""
    ders_ad = ktt.ders.ad if ktt.ders_id else ""
    brans = ders_adindan_brans(ders_ad)
    if not brans:
        return KonuEslestirmeSonuc(None, ktt.ad, 0, "brans_yok")

    ham = ktt.ad.strip()
    sinif = str(ktt.sinif_seviyesi or "8").strip()
    sonuc = konu_eslestir(sinif, brans, ham, ktt=ktt)

    ktt.konu_ham_ad = ham
    ktt.konu_katalog = sonuc.konu
    ktt.eslestirme_guven = sonuc.guven
    ktt.save(update_fields=["konu_ham_ad", "konu_katalog", "eslestirme_guven", "guncellenme"])
    return sonuc


def konu_oneri_listesi(
    sinif_seviyesi: str,
    brans: str,
    arama: str,
    limit: int = 10,
) -> list[dict]:
    qs = KonuKatalogu.objects.filter(
        sinif_seviyesi=sinif_seviyesi,
        brans=brans,
        aktif=True,
    )
    arama = (arama or "").strip()
    if arama:
        norm = normalize_konu_metni(arama)
        adaylar = list(qs.order_by("konu_ad")[:80])
        skorlu = []
        for konu in adaylar:
            skor = _benzerlik(norm, normalize_konu_metni(konu.konu_ad))
            if norm in normalize_konu_metni(konu.konu_ad):
                skor = max(skor, 0.95)
            if skor >= 0.45 or arama.casefold() in konu.konu_ad.casefold():
                skorlu.append((skor, konu))
        skorlu.sort(key=lambda x: (-x[0], x[1].konu_ad))
        return [
            {"id": k.id, "ad": k.konu_ad, "guven": int(round(s * 100))}
            for s, k in skorlu[:limit]
        ]
    return [{"id": k.id, "ad": k.konu_ad, "guven": 100} for k in qs.order_by("konu_ad")[:limit]]


def eslestirme_onayla(inceleme_id: int, kullanici=None) -> KonuKatalogu | None:
    inceleme = KonuEslestirmeInceleme.objects.select_related("onerilen_konu").get(
        pk=inceleme_id
    )
    if not inceleme.onerilen_konu_id:
        return None
    inceleme.durum = KonuEslestirmeInceleme.Durum.ONAYLANDI
    inceleme.save(update_fields=["durum", "guncellenme"])
    _alias_kaydet(
        inceleme.sinif_seviyesi,
        inceleme.brans,
        inceleme.ham_normalize,
        inceleme.onerilen_konu,
    )
    if inceleme.ktt_id:
        KttSinav.objects.filter(pk=inceleme.ktt_id).update(
            konu_katalog=inceleme.onerilen_konu,
            eslestirme_guven=inceleme.guven_yuzde,
        )
    return inceleme.onerilen_konu
