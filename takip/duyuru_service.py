"""Duyuru görünürlük ve listeleme kuralları."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet
from django.utils.timezone import localdate

from .models import Duyuru
from .panel_permissions import kullanici_rolu


def kullaniciya_gorunur_duyurular(user: User) -> QuerySet[Duyuru]:
    bugun = localdate()

    qs = (
        Duyuru.objects.filter(
            aktif=True,
            baslangic__lte=bugun,
        )
        .filter(
            Q(bitis__isnull=True)
            | Q(bitis__gte=bugun)
        )
    )

    rol = kullanici_rolu(user)

    if rol is None:
        return Duyuru.objects.none()

    # Veli paneli henüz yok; personel veli-only duyuruları görmez.
    qs = qs.exclude(
        hedef_kitle=Duyuru.HedefKitle.VELI,
    )

    return qs.order_by("sira", "-baslangic", "-id")


def veli_duyurulari() -> QuerySet[Duyuru]:
    bugun = localdate()

    return (
        Duyuru.objects.filter(
            aktif=True,
            baslangic__lte=bugun,
            hedef_kitle=Duyuru.HedefKitle.VELI,
        )
        .filter(
            Q(bitis__isnull=True)
            | Q(bitis__gte=bugun)
        )
        .order_by("sira", "-baslangic", "-id")
    )


def video_gomme_adresi(url: str) -> str:
    """YouTube / Vimeo bağlantısını gömme adresine çevirir."""
    url = (url or "").strip()
    if not url:
        return ""

    if "youtube.com/embed/" in url or "player.vimeo.com" in url:
        return url

    if "youtu.be/" in url:
        video_id = url.rstrip("/").split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/embed/{video_id}"

    if "youtube.com/watch" in url:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"

    if "youtube.com/shorts/" in url:
        video_id = url.rstrip("/").split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/embed/{video_id}"

    if "vimeo.com/" in url:
        video_id = url.rstrip("/").split("/")[-1].split("?")[0]
        if video_id.isdigit():
            return f"https://player.vimeo.com/video/{video_id}"

    return url


def duyuru_oto_sahne(duyuru: Duyuru) -> str:
    """Başlık ve içeriğe göre otomatik illüstrasyon sahnesi."""
    metin = f"{duyuru.baslik} {duyuru.ozet}".lower()

    if any(k in metin for k in ("asistan", "dijital asistan", "yapay zeka", "ai asistan", "panel asistan")):
        return "asistan"

    anahtarlar = {
        Duyuru.Kategori.EGITIM: (
            "eğitim",
            "egitim",
            "kitap",
            "sınav",
            "sinav",
            "öğrenci",
            "ogrenci",
            "talebe",
            "platform",
            "ktt",
            "temrin",
            "okuma",
        ),
        Duyuru.Kategori.PROGRAM: (
            "program",
            "etüt",
            "etut",
            "ders",
            "takvim",
            "hafta",
            "plan",
            "yoklama",
            "namaz",
        ),
        Duyuru.Kategori.KURUM: (
            "kurum",
            "duyuru",
            "veli",
            "personel",
            "idare",
            "yönetim",
            "yonetim",
            "toplantı",
            "toplanti",
            "asistan",
            "dijital",
            "yapay zeka",
        ),
    }
    for kategori, kelimeler in anahtarlar.items():
        if any(k in metin for k in kelimeler):
            return kategori
    return duyuru.kategori or Duyuru.Kategori.GENEL
