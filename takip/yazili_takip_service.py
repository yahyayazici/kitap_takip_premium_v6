"""Yazılı takip sorguları ve yardımcılar."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils.timezone import localdate

from takip.models import Ders, Talebe, YaziliKamp, YaziliSinav, YaziliSonuc
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user


def yazili_duzenleyebilir(user: User) -> bool:
    return can(user, "yazili_takip", "edit") or can(user, "yazili_takip", "create")


def yazili_olusturabilir(user: User) -> bool:
    return can(user, "yazili_takip", "create") or can(user, "yazili_takip", "edit")


def _yetkili_sinif_seviyeleri(user: User) -> set[str]:
    """Etüt hocasının talebelerinin sınıf seviyeleri (kamp.sinif_seviyesi eşlemesi)."""
    qs = yetkili_talebeler(user).select_related("sinif_sube")
    seviyeler: set[str] = set()
    for t in qs.only("sinif", "sinif_sube__sinif"):
        for ham in (t.sinif, getattr(t.sinif_sube, "sinif", None)):
            if ham is None:
                continue
            s = str(ham).strip()
            if s:
                seviyeler.add(s)
    return seviyeler


def yazili_sinif_secenekleri(user: User):
    from takip.ktt_service import ktt_sinif_secenekleri

    return ktt_sinif_secenekleri(user)


def yazili_sinif_secimlerini_dogrula(user: User, secilen: list[str]) -> tuple[list[str], str | None]:
    from takip.ktt_service import ktt_sinif_secimlerini_dogrula

    return ktt_sinif_secimlerini_dogrula(user, secilen)


def yetkili_kamplar(user: User) -> QuerySet[YaziliKamp]:
    if not can(user, "yazili_takip", "view"):
        return YaziliKamp.objects.none()

    qs = YaziliKamp.objects.filter(aktif=True).annotate(
        sinav_sayisi=Count("sinavlar"),
        sonuc_sayisi=Count("sinavlar__sonuclar"),
    ).order_by("-baslangic", "-id")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = list(yetkili_talebeler(user).values_list("id", flat=True))
    seviyeler = _yetkili_sinif_seviyeleri(user)
    kosul = Q(sinavlar__sonuclar__talebe_id__in=talebe_ids)
    if seviyeler:
        kosul |= Q(sinif_seviyesi__in=seviyeler)
    return qs.filter(kosul).distinct()


def yetkili_sinavlar(user: User, kamp: YaziliKamp | None = None) -> QuerySet[YaziliSinav]:
    if not can(user, "yazili_takip", "view"):
        return YaziliSinav.objects.none()

    qs = YaziliSinav.objects.select_related("kamp", "ders").annotate(
        sonuc_sayisi=Count("sonuclar"),
    )

    if kamp:
        qs = qs.filter(kamp=kamp)

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs.order_by("-sinav_tarihi", "-id")

    talebe_ids = list(yetkili_talebeler(user).values_list("id", flat=True))
    seviyeler = _yetkili_sinif_seviyeleri(user)
    kosul = Q(sonuclar__talebe_id__in=talebe_ids)
    if seviyeler:
        kosul |= Q(kamp__sinif_seviyesi__in=seviyeler)
    return (
        qs.filter(durum=YaziliSinav.Durum.AKTIF)
        .filter(kosul)
        .distinct()
        .order_by("-sinav_tarihi", "-id")
    )


def yetkili_yazili_sonuclari(user: User) -> QuerySet[YaziliSonuc]:
    if not can(user, "yazili_takip", "view"):
        return YaziliSonuc.objects.none()

    qs = YaziliSonuc.objects.select_related(
        "sinav",
        "sinav__kamp",
        "talebe",
        "talebe__sinif_sube",
    )

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def sinav_sonuclari(user: User, sinav: YaziliSinav) -> QuerySet[YaziliSonuc]:
    return (
        yetkili_yazili_sonuclari(user)
        .filter(sinav=sinav)
        .order_by("-puan", "talebe__ad_soyad")
    )


def sinav_sonuclari_sirali(user: User, sinav: YaziliSinav) -> list[dict]:
    sonuclar = list(sinav_sonuclari(user, sinav))
    satirlar = []
    for sira, sonuc in enumerate(sonuclar, start=1):
        satirlar.append({"sira": sira, "sonuc": sonuc})
    return satirlar


def _hedef_sinif_etiketleri(sinav: YaziliSinav) -> list[str]:
    ham = (sinav.hedef_siniflar or "").strip()
    if not ham:
        return []
    return [p.strip() for p in ham.split(",") if p.strip()]


def kamp_talebeleri(kamp: YaziliKamp) -> QuerySet[Talebe]:
    qs = Talebe.objects.filter(aktif=True).select_related("sinif_sube")
    if kamp.sinif_seviyesi:
        qs = qs.filter(
            Q(sinif=kamp.sinif_seviyesi) | Q(sinif_sube__sinif=kamp.sinif_seviyesi)
        )
    return qs.order_by("ad_soyad")


def sinav_sonuc_talebeleri(user: User, sinav: YaziliSinav) -> QuerySet[Talebe]:
    etiketler = _hedef_sinif_etiketleri(sinav)
    qs = Talebe.objects.filter(aktif=True).select_related("sinif_sube")

    if etiketler:
        kosul = Q()
        for etiket in etiketler:
            if "-" in etiket:
                sinif, sube = etiket.split("-", 1)
                kosul |= Q(sinif=sinif, sube=sube) | Q(
                    sinif_sube__sinif=sinif, sinif_sube__sube=sube
                )
            else:
                kosul |= Q(sinif=etiket) | Q(sinif_sube__sinif=etiket)
        qs = qs.filter(kosul)
    else:
        qs = kamp_talebeleri(sinav.kamp)

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs.order_by("ad_soyad")

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(id__in=talebe_ids).order_by("ad_soyad")


def sonuc_giris_satirlari(user: User, sinav: YaziliSinav) -> list[dict]:
    talebeler = list(sinav_sonuc_talebeleri(user, sinav))
    mevcut = {
        s.talebe_id: s
        for s in YaziliSonuc.objects.filter(sinav=sinav, talebe__in=talebeler)
    }
    satirlar = []
    for talebe in talebeler:
        sonuc = mevcut.get(talebe.id)
        satirlar.append(
            {
                "talebe": talebe,
                "sonuc": sonuc,
                "puan": sonuc.puan if sonuc else "",
            }
        )
    return satirlar


def sonuclari_toplu_kaydet(
    user: User,
    sinav: YaziliSinav,
    talebeler: list[Talebe],
    post_data,
) -> tuple[int, list[str]]:
    hatalar: list[str] = []
    kaydedilen = 0

    with transaction.atomic():
        for talebe in talebeler:
            ham = (post_data.get(f"puan_{talebe.id}") or "").strip()
            if ham == "":
                YaziliSonuc.objects.filter(sinav=sinav, talebe=talebe).delete()
                continue

            try:
                puan = Decimal(ham.replace(",", "."))
            except (InvalidOperation, TypeError, ValueError):
                hatalar.append(f"{talebe.ad_soyad}: Geçerli puan girin.")
                continue

            if puan < 0 or puan > 100:
                hatalar.append(f"{talebe.ad_soyad}: Puan 0–100 arasında olmalı.")
                continue

            YaziliSonuc.objects.update_or_create(
                sinav=sinav,
                talebe=talebe,
                defaults={
                    "puan": puan,
                    "dogru": 0,
                    "yanlis": 0,
                    "bos": 0,
                    "kaydeden": user,
                },
            )
            kaydedilen += 1

        if hatalar:
            transaction.set_rollback(True)

    return kaydedilen, hatalar


def _kamp_bul_veya_olustur(
    user: User,
    sinif_seviyesi: str,
    *,
    veli_goster: bool = True,
) -> YaziliKamp:
    bugun = localdate()
    mevcut = (
        YaziliKamp.objects.filter(
            aktif=True,
            sinif_seviyesi=sinif_seviyesi,
            baslangic__lte=bugun,
            bitis__gte=bugun,
        )
        .order_by("-baslangic", "-id")
        .first()
    )
    if mevcut:
        return mevcut

    yil = bugun.year
    return YaziliKamp.objects.create(
        ad=f"{sinif_seviyesi}. Sınıf Yazılı · {yil}",
        baslangic=bugun.replace(month=9, day=1) if bugun.month >= 9 else bugun.replace(year=yil - 1, month=9, day=1),
        bitis=bugun.replace(month=6, day=30) if bugun.month < 9 else bugun.replace(year=yil + 1, month=6, day=30),
        sinif_seviyesi=sinif_seviyesi,
        aktif=True,
        veli_goster=veli_goster,
        olusturan=user,
    )


def yazili_sinav_olustur(
    user: User,
    *,
    ders: Ders,
    sinav_tarihi,
    yazili_no: int,
    tur: str,
    sinif_etiketleri: list[str],
    ad: str = "",
    donem: int = 1,
) -> YaziliSinav:
    if not sinif_etiketleri:
        raise ValueError("En az bir sınıf seçin.")

    seviyeler = sorted({e.split("-", 1)[0] for e in sinif_etiketleri if e})
    sinif_seviyesi = seviyeler[0] if seviyeler else "7"
    kamp = _kamp_bul_veya_olustur(user, sinif_seviyesi)

    brans = ders.brans.ad if ders.brans_id else ""
    baslik = (ad or "").strip()
    if not baslik:
        if tur == YaziliSinav.Tur.GERCEK:
            baslik = f"{ders.ad} · {donem}. Dönem {yazili_no}. Yazılı"
        else:
            baslik = f"{ders.ad} {yazili_no}. Yazılı"

    return YaziliSinav.objects.create(
        kamp=kamp,
        ad=baslik,
        sinav_tarihi=sinav_tarihi,
        ders=ders,
        ders_ad=ders.ad,
        brans=brans,
        yazili_no=yazili_no,
        donem=donem if tur == YaziliSinav.Tur.GERCEK else 1,
        tur=tur or YaziliSinav.Tur.ORNEK,
        hedef_siniflar=", ".join(sinif_etiketleri),
        soru_sayisi=0,
        durum=YaziliSinav.Durum.AKTIF,
        olusturan=user,
    )


def talebe_yazili_sonuclari(talebe: Talebe) -> QuerySet[YaziliSonuc]:
    return (
        YaziliSonuc.objects.filter(
            talebe=talebe,
            sinav__durum=YaziliSinav.Durum.AKTIF,
            sinav__kamp__aktif=True,
            sinav__kamp__veli_goster=True,
        )
        .select_related("sinav", "sinav__kamp")
        .order_by("-sinav__sinav_tarihi", "-id")
    )


def kamp_ozet_istatistik(user: User, kamp: YaziliKamp) -> dict:
    sinavlar = list(yetkili_sinavlar(user, kamp))
    toplam_sonuc = sum(s.sonuc_sayisi for s in sinavlar)
    return {
        "sinav_sayisi": len(sinavlar),
        "toplam_sonuc": toplam_sonuc,
    }


def seed_yazili_takip_demo() -> None:
    """Örnek yazılı kamp + sınav sonuçları."""
    from django.utils import timezone

    bugun = timezone.localdate()
    kamp, _ = YaziliKamp.objects.update_or_create(
        ad="Yazılı Kamp Demo",
        defaults={
            "baslangic": bugun - timedelta(days=14),
            "bitis": bugun + timedelta(days=7),
            "sinif_seviyesi": "7",
            "aktif": True,
            "veli_goster": True,
        },
    )
    ders = Ders.objects.filter(aktif=True).order_by("sira", "ad").first()
    sinav, _ = YaziliSinav.objects.update_or_create(
        kamp=kamp,
        ad="Matematik 1. Yazılı (Örnek)",
        defaults={
            "sinav_tarihi": bugun - timedelta(days=3),
            "ders": ders,
            "ders_ad": ders.ad if ders else "Matematik",
            "brans": "",
            "yazili_no": 1,
            "tur": YaziliSinav.Tur.ORNEK,
            "hedef_siniflar": "7-A, 7-B",
            "soru_sayisi": 0,
            "durum": YaziliSinav.Durum.AKTIF,
        },
    )
    for i, talebe in enumerate(Talebe.objects.filter(aktif=True)[:5]):
        YaziliSonuc.objects.update_or_create(
            sinav=sinav,
            talebe=talebe,
            defaults={
                "puan": Decimal(str(70 + i * 5)),
                "dogru": 0,
                "yanlis": 0,
                "bos": 0,
            },
        )

    gercek, _ = YaziliSinav.objects.update_or_create(
        kamp=kamp,
        ad="Matematik 1. Yazılı (Gerçek)",
        defaults={
            "sinav_tarihi": bugun - timedelta(days=1),
            "ders": ders,
            "ders_ad": ders.ad if ders else "Matematik",
            "yazili_no": 1,
            "tur": YaziliSinav.Tur.GERCEK,
            "hedef_siniflar": "7-A, 7-B",
            "soru_sayisi": 0,
            "durum": YaziliSinav.Durum.AKTIF,
        },
    )
    for i, talebe in enumerate(Talebe.objects.filter(aktif=True)[:5]):
        YaziliSonuc.objects.update_or_create(
            sinav=gercek,
            talebe=talebe,
            defaults={
                "puan": Decimal(str(65 + i * 4)),
                "dogru": 0,
                "yanlis": 0,
                "bos": 0,
            },
        )
