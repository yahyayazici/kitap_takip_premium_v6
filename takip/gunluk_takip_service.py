"""Günlük takip sorguları ve işlemler."""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet

from takip.models import GunlukTakipKaydi, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can


def gunluk_takip_gorebilir(user: User) -> bool:
    return can(user, "gunluk_takip", "view")


def gunluk_takip_duzenleyebilir(user: User) -> bool:
    return can(user, "gunluk_takip", "edit") or can(user, "gunluk_takip", "create")


def yetkili_gunluk_kayitlari(user: User) -> QuerySet[GunlukTakipKaydi]:
    if not gunluk_takip_gorebilir(user):
        return GunlukTakipKaydi.objects.none()

    qs = GunlukTakipKaydi.objects.select_related(
        "talebe",
        "talebe__sinif_sube",
    )

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user, aktif_only=True).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def gunluk_kayitlari_filtrele(
    qs: QuerySet[GunlukTakipKaydi],
    *,
    q: str | None = None,
    tarih: str | None = None,
    devam: str | None = None,
) -> QuerySet[GunlukTakipKaydi]:
    if q:
        qs = qs.filter(
            Q(talebe__ad_soyad__icontains=q)
            | Q(talebe__talebe_no__icontains=q)
            | Q(not_alani__icontains=q)
        )
    if tarih:
        qs = qs.filter(tarih=tarih)
    if devam:
        qs = qs.filter(devam=devam)
    return qs


def gunluk_kayit_kaydet(
    talebe: Talebe,
    tarih: date,
    *,
    devam: str,
    etut_katilim: bool,
    not_alani: str = "",
) -> GunlukTakipKaydi:
    kayit, _ = GunlukTakipKaydi.objects.update_or_create(
        talebe=talebe,
        tarih=tarih,
        defaults={
            "devam": devam,
            "etut_katilim": etut_katilim,
            "not_alani": not_alani,
        },
    )
    return kayit


def etut_yoklama_satirlari(user: User, tarih: date) -> list[dict]:
    """Etüt hocasının talebeleri — varsayılan katıldı, sadece devamsız işaretlenir."""
    talebeler = list(
        yetkili_talebeler(user, aktif_only=True)
        .select_related("sinif_sube", "etut_hocasi")
        .order_by("sinif_sube__sinif", "sinif_sube__sube", "ad_soyad")
    )
    if not talebeler:
        return []

    talebe_ids = [t.pk for t in talebeler]
    mevcut = {
        k.talebe_id: k
        for k in GunlukTakipKaydi.objects.filter(talebe_id__in=talebe_ids, tarih=tarih)
    }

    satirlar = []
    for talebe in talebeler:
        kayit = mevcut.get(talebe.pk)
        devamsiz = bool(kayit and not kayit.etut_katilim)
        satirlar.append(
            {
                "talebe": talebe,
                "kayit": kayit,
                "devamsiz": devamsiz,
                "katildi": not devamsiz,
                "sinif_key": _sinif_key(talebe),
                "sinif_etiket": _sinif_etiket(talebe),
            }
        )
    return satirlar


def _sinif_key(talebe: Talebe) -> str:
    if getattr(talebe, "sinif_sube_id", None) and talebe.sinif_sube:
        return talebe.sinif_sube.etiket
    sinif = (talebe.sinif or "").strip()
    sube = (talebe.sube or "").strip()
    if sinif and sube:
        return f"{sinif}-{sube}"
    return sinif or "diger"


def _sinif_etiket(talebe: Talebe) -> str:
    if getattr(talebe, "sinif_sube_id", None) and talebe.sinif_sube:
        return str(talebe.sinif_sube)
    sinif = (talebe.sinif or "").strip()
    sube = (talebe.sube or "").strip()
    if sinif and sube:
        return f"{sinif}/{sube}"
    return sinif or "—"


def etut_sinif_secenekleri(satirlar: list[dict]) -> list[dict]:
    seen: dict[str, str] = {}
    for s in satirlar:
        key = s.get("sinif_key") or _sinif_key(s["talebe"])
        if key not in seen:
            seen[key] = s.get("sinif_etiket") or _sinif_etiket(s["talebe"])
    return [{"key": k, "label": seen[k]} for k in sorted(seen, key=lambda x: seen[x])]


def etut_yoklama_kaydet(user: User, tarih: date, devamsiz_ids: set[int]) -> int:
    talebeler = yetkili_talebeler(user, aktif_only=True)
    mevcut = {
        k.talebe_id: k
        for k in GunlukTakipKaydi.objects.filter(
            talebe__in=talebeler,
            tarih=tarih,
        )
    }

    sayac = 0
    for talebe in talebeler:
        kayit = mevcut.get(talebe.pk)
        devamsiz = talebe.pk in devamsiz_ids
        if devamsiz:
            devam = GunlukTakipKaydi.DevamDurumu.GELMEDI
        elif kayit and kayit.devam == GunlukTakipKaydi.DevamDurumu.GEC:
            devam = kayit.devam
        else:
            devam = GunlukTakipKaydi.DevamDurumu.GELDI
        gunluk_kayit_kaydet(
            talebe,
            tarih,
            devam=devam,
            etut_katilim=not devamsiz,
            not_alani=kayit.not_alani if kayit else "",
        )
        sayac += 1
    return sayac


def etut_yoklama_ozet(satirlar: list[dict]) -> dict:
    toplam = len(satirlar)
    devamsiz = sum(1 for s in satirlar if s["devamsiz"])
    return {
        "toplam": toplam,
        "katilan": toplam - devamsiz,
        "devamsiz": devamsiz,
    }
