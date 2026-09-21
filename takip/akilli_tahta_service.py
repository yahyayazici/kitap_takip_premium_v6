"""Akıllı Tahta Dosya Merkezi — iş mantığı: yükleme, doğrulama, yetki, hedefleme."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from takip.akilli_tahta_models import (
    AkilliTahtaDosya,
    AkilliTahtaHedef,
    AkilliTahtaHesap,
    AkilliTahtaIslemKaydi,
    SinifSeviyesi,
)
from takip.dosya_guvenlik import dosya_ozeti, icerik_turu_tespit_et, ilk_baytlar
from takip.permissions.service import can

GORSEL_UZANTILAR = {"png", "jpg", "jpeg", "webp"}
VIDEO_UZANTILAR = {"mp4"}
PDF_UZANTILAR = {"pdf"}

_UZANTI_ICERIK = {
    "png": {"png"},
    "jpg": {"jpeg"},
    "jpeg": {"jpeg"},
    "webp": {"webp"},
    "pdf": {"pdf"},
    "mp4": {"mp4"},
}


class AkilliTahtaHatasi(Exception):
    """Kullanıcıya olduğu gibi gösterilebilecek, anlaşılır Türkçe hata."""


def tam_yetkili(user: User) -> bool:
    """İdareci/ic_mesul/egitim_mesul (ya da süper kullanıcı) — her dosyayı yönetir."""
    return can(user, "akilli_tahta", "manage_accounts")


def dosya_duzenlenebilir_mi(user: User, dosya: AkilliTahtaDosya) -> bool:
    return tam_yetkili(user) or dosya.yukleyen_id == user.id


def dosya_turunu_belirle(dosya: UploadedFile) -> tuple[str, str]:
    """(dosya_turu, mime) döndürür; tür/boyut/uzantı-içerik uyumsuzsa hata yükseltir."""
    ad = (dosya.name or "").strip()
    if "." not in ad:
        raise AkilliTahtaHatasi(
            "Dosyanın uzantısı okunamadı. PDF, JPG, JPEG, PNG, WEBP veya MP4 yükleyin."
        )

    uzanti = ad.rsplit(".", 1)[-1].lower()

    if uzanti in GORSEL_UZANTILAR:
        sinir = settings.AKILLI_TAHTA_MAKS_GORSEL_MB * 1024 * 1024
        sinir_adi = f"{settings.AKILLI_TAHTA_MAKS_GORSEL_MB} MB"
    elif uzanti in PDF_UZANTILAR:
        sinir = settings.AKILLI_TAHTA_MAKS_PDF_MB * 1024 * 1024
        sinir_adi = f"{settings.AKILLI_TAHTA_MAKS_PDF_MB} MB"
    elif uzanti in VIDEO_UZANTILAR:
        sinir = settings.AKILLI_TAHTA_MAKS_VIDEO_MB * 1024 * 1024
        sinir_adi = f"{settings.AKILLI_TAHTA_MAKS_VIDEO_MB} MB"
    else:
        raise AkilliTahtaHatasi(
            f"“.{uzanti}” dosyaları desteklenmiyor. "
            "PDF, JPG, JPEG, PNG, WEBP veya MP4 kullanın."
        )

    if dosya.size > sinir:
        raise AkilliTahtaHatasi(
            f"Dosya çok büyük ({dosya.size / 1024 / 1024:.1f} MB). "
            f"Bu tür için üst sınır {sinir_adi}."
        )

    gercek = icerik_turu_tespit_et(ilk_baytlar(dosya))
    if gercek is None or gercek not in _UZANTI_ICERIK[uzanti]:
        raise AkilliTahtaHatasi(
            "Dosyanın içeriği uzantısıyla uyuşmuyor. "
            "Dosya bozulmuş olabilir; lütfen kaynağından yeniden kaydedip deneyin."
        )

    if uzanti == "mp4":
        mime = "video/mp4"
    elif uzanti == "pdf":
        mime = "application/pdf"
    else:
        mime = f"image/{'jpeg' if gercek == 'jpeg' else gercek}"

    return uzanti, mime


@transaction.atomic
def dosya_yukle(
    *,
    kullanici: User,
    dosya: UploadedFile,
    baslik: str,
    icerik_turu: str,
    ders=None,
    aciklama: str = "",
    tum_siniflar: bool,
    hedef_seviyeler: list[str],
    yayin_baslangic,
    yayin_bitis=None,
    ust_sirada: bool = False,
    indirme_izni: bool = True,
    taslak: bool = False,
) -> AkilliTahtaDosya:
    uzanti, mime = dosya_turunu_belirle(dosya)
    ozet = dosya_ozeti(dosya)

    kayit = AkilliTahtaDosya(
        baslik=baslik[:200],
        dosya_turu=uzanti,
        icerik_turu=icerik_turu,
        ders=ders,
        aciklama=aciklama,
        tum_siniflar=tum_siniflar,
        ust_sirada=ust_sirada,
        indirme_izni=indirme_izni,
        yayin_baslangic=yayin_baslangic,
        yayin_bitis=yayin_bitis,
        durum=(
            AkilliTahtaDosya.Durum.TASLAK if taslak else AkilliTahtaDosya.Durum.YAYINDA
        ),
        yukleyen=kullanici,
        dosya_hash=ozet,
        dosya_boyutu=dosya.size,
        mime=mime,
    )
    kayit.dosya.save(f"{ozet[:16]}.{uzanti}", dosya, save=False)
    kayit.save()

    if not tum_siniflar:
        AkilliTahtaHedef.objects.bulk_create(
            [
                AkilliTahtaHedef(dosya=kayit, sinif_seviyesi=seviye)
                for seviye in hedef_seviyeler
            ]
        )

    islem_kaydet(kullanici, "dosya_yukle", dosya=kayit, detay=kayit.baslik)
    return kayit


def islem_kaydet(kullanici, aksiyon: str, *, dosya=None, hesap=None, detay: str = "") -> None:
    AkilliTahtaIslemKaydi.objects.create(
        kullanici=kullanici if (kullanici and kullanici.is_authenticated) else None,
        aksiyon=aksiyon,
        dosya=dosya,
        hesap=hesap,
        detay=detay,
    )


def yayindaki_dosyalar(sinif_seviyesi: str):
    """Bir sınıf seviyesinin akıllı tahtasında görünmesi gereken dosyalar."""
    simdi = timezone.now()
    return (
        AkilliTahtaDosya.objects.filter(durum=AkilliTahtaDosya.Durum.YAYINDA)
        .filter(yayin_baslangic__lte=simdi)
        .filter(Q(yayin_bitis__isnull=True) | Q(yayin_bitis__gt=simdi))
        .filter(Q(tum_siniflar=True) | Q(hedefler__sinif_seviyesi=sinif_seviyesi))
        .select_related("ders", "yukleyen")
        .distinct()
        .order_by("-ust_sirada", "-olusturulma")
    )
