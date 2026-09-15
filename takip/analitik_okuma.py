"""Analitik Okuma dersi — kimlik, alan sabitleri ve gösterim yardımcıları."""

from __future__ import annotations

import unicodedata
from decimal import Decimal

from django.db import models

ANALITIK_OKUMA_KOD = "analitik_okuma"
GELMEDI_NOTU = "Derse katılmadı."


class AnalitikAlan(models.TextChoices):
    GORSEL = "gorsel_grafik", "Görsel ve Grafik Çözümleme"
    SOZEL = "sozel_mantik", "Sözel Mantık ve Muhakeme"
    CIKARIM = "cikarma_anlama", "Çıkarım Yapma ve Derin Anlama"
    AKICI = "akici_okuma", "Akıcı ve Sesli Okuma"
    STRATEJIK = "stratejik_soru", "Stratejik Soru Çözme Yaklaşımı"


class AnalitikKayitDurumu(models.TextChoices):
    TASLAK = "taslak", "Taslak"
    TAMAMLANDI = "tamamlandi", "Tamamlandı"


def normalize_ders_ad(ad: str) -> str:
    text = unicodedata.normalize("NFKC", ad or "").casefold()
    text = text.replace("ı", "i").replace("i̇", "i")
    return " ".join(text.split())


def ders_analitik_okuma_mi(ders) -> bool:
    """Ders kodu öncelikli; yoksa güvenilir ad eşlemesi."""
    if ders is None:
        return False
    kod = (getattr(ders, "kod", None) or "").strip().lower()
    if kod == ANALITIK_OKUMA_KOD:
        return True
    return normalize_ders_ad(getattr(ders, "ad", "")) == "analitik okuma"


def bir_ondalik(deger: Decimal | None) -> str | None:
    """Gösterim: bir ondalık, Türkçe virgül. Ham değer değiştirilmez."""
    if deger is None:
        return None
    yuvarlak = Decimal(deger).quantize(Decimal("0.1"))
    return f"{yuvarlak:.1f}".replace(".", ",")


def yildiz_metni(puan: int | None, azami: int = 10) -> str:
    if puan is None:
        return "☆" * azami
    n = max(0, min(azami, int(puan)))
    return ("★" * n) + ("☆" * (azami - n))
