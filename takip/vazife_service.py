"""Personel vazife yardımcıları — aktif bildirimler ve özet."""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q, QuerySet
from django.utils.timezone import localdate

from takip.models import PersonelProfili
from takip.vazife_models import PersonelVazife

_ACIK_DURUMLAR = (
    PersonelVazife.Durum.ATANDI,
    PersonelVazife.Durum.ONAYLANDI,
    PersonelVazife.Durum.DEVAM,
)


def profil_for_user(user: AbstractBaseUser | None) -> PersonelProfili | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return PersonelProfili.objects.filter(user=user, aktif=True).first()


def acik_vazifeler_qs(profil: PersonelProfili) -> QuerySet[PersonelVazife]:
    return PersonelVazife.objects.filter(
        atanan=profil,
        durum__in=_ACIK_DURUMLAR,
    ).select_related("sinif_sube", "atayan")


def bildirim_aktif_qs(
    profil: PersonelProfili,
    *,
    bugun: date | None = None,
) -> QuerySet[PersonelVazife]:
    """
    Son tarihe (bitiş) kadar personelde görünen açık vazifeler.
    Bitiş yoksa başlangıçtan itibaren açık kalsın.
    """
    bugun = bugun or localdate()
    return (
        acik_vazifeler_qs(profil)
        .filter(baslangic__lte=bugun)
        .filter(Q(bitis__isnull=True) | Q(bitis__gte=bugun))
        .order_by("bitis", "oncelik", "-olusturulma")
    )


def vazife_badge_sayisi(user: AbstractBaseUser, *, bugun: date | None = None) -> int:
    profil = profil_for_user(user)
    if not profil:
        return 0
    return bildirim_aktif_qs(profil, bugun=bugun).count()


def vazife_bildirim_kartlari(
    user: AbstractBaseUser,
    *,
    bugun: date | None = None,
    limit: int = 8,
) -> list[dict]:
    """Dashboard / panel için bildirim kartları."""
    profil = profil_for_user(user)
    if not profil:
        return []
    bugun = bugun or localdate()
    kartlar: list[dict] = []
    for v in bildirim_aktif_qs(profil, bugun=bugun)[:limit]:
        kalan = None
        gecikti = False
        if v.bitis:
            kalan = (v.bitis - bugun).days
            gecikti = kalan < 0
        kartlar.append(
            {
                "id": v.pk,
                "baslik": v.baslik,
                "aciklama": (v.aciklama or "").strip(),
                "bitis": v.bitis,
                "baslangic": v.baslangic,
                "oncelik": v.oncelik,
                "oncelik_etiket": v.get_oncelik_display(),
                "durum": v.durum,
                "durum_etiket": v.get_durum_display(),
                "kalan_gun": kalan,
                "gecikti": gecikti,
                "sinif": str(v.sinif_sube) if v.sinif_sube_id else "",
            }
        )
    return kartlar


def ornek_vazifeler_olustur(profil: PersonelProfili, *, atayan=None) -> list[PersonelVazife]:
    """Boş panelde görünüm için örnek kayıtlar (yalnızca profilde yoksa)."""
    if PersonelVazife.objects.filter(atanan=profil).exists():
        return []

    bugun = localdate()
    ornekler = [
        {
            "baslik": "Haftalık sınıf kontrolü",
            "aciklama": "9-A ve 9-B dersliklerini kontrol et; eksik malzeme listesini ilet.",
            "baslangic": bugun,
            "bitis": bugun + timedelta(days=3),
            "oncelik": PersonelVazife.Oncelik.YUKSEK,
            "durum": PersonelVazife.Durum.ATANDI,
        },
        {
            "baslik": "Etüt PDF linklerini kontrol et",
            "aciklama": "Bu haftanın etüt planı PDF bağlantılarının açıldığını doğrula.",
            "baslangic": bugun - timedelta(days=1),
            "bitis": bugun + timedelta(days=5),
            "oncelik": PersonelVazife.Oncelik.NORMAL,
            "durum": PersonelVazife.Durum.DEVAM,
        },
        {
            "baslik": "Namaz yoklama özeti",
            "aciklama": "Sabah namazı yoklama özetini idareye ilet.",
            "baslangic": bugun,
            "bitis": bugun + timedelta(days=1),
            "oncelik": PersonelVazife.Oncelik.ACIL,
            "durum": PersonelVazife.Durum.ONAYLANDI,
        },
        {
            "baslik": "Temizlik kat turu",
            "aciklama": "2. kat ortak alanların temizlik durumunu kontrol et.",
            "baslangic": bugun - timedelta(days=2),
            "bitis": bugun - timedelta(days=1),
            "oncelik": PersonelVazife.Oncelik.NORMAL,
            "durum": PersonelVazife.Durum.TAMAMLANDI,
        },
        {
            "baslik": "Veli görüşme notları arşivi",
            "aciklama": "Geçen haftanın rehberlik notlarını klasöre aktar.",
            "baslangic": bugun,
            "bitis": bugun + timedelta(days=7),
            "oncelik": PersonelVazife.Oncelik.DUSUK,
            "durum": PersonelVazife.Durum.ATANDI,
        },
    ]
    olusan: list[PersonelVazife] = []
    for raw in ornekler:
        olusan.append(
            PersonelVazife.objects.create(
                atanan=profil,
                atayan=atayan,
                **raw,
            )
        )
    return olusan
