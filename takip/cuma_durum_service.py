"""Cuma durum stüdyo — haftalık metin seçimi ve personel adı."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.utils.timezone import localdate

from takip.cuma_durum_models import CumaDurumMetni
from takip.models import PersonelProfili


def son_cuma(tarih=None):
    """İçinde bulunulan haftanın Cuma günü (Cumartesi/Pazar dahil önceki Cuma)."""
    tarih = tarih or localdate()
    days_since = (tarih.weekday() - 4) % 7
    return tarih - timedelta(days=days_since)


def personel_gorunen_ad(user: User) -> str:
    profil = PersonelProfili.objects.filter(user=user, aktif=True).first()
    if profil and profil.ad_soyad.strip():
        return profil.ad_soyad.strip()
    tam = (user.get_full_name() or "").strip()
    return tam or user.username


def personel_rol_etiketi(user: User) -> str:
    profil = PersonelProfili.objects.filter(user=user, aktif=True).first()
    if profil:
        return profil.get_ana_rol_display()
    return ""


def aktif_metinler():
    return CumaDurumMetni.objects.filter(aktif=True).order_by("sira", "-id")


def haftalik_oneri_metni(tarih=None) -> CumaDurumMetni | None:
    cuma = son_cuma(tarih)
    atanmis = (
        CumaDurumMetni.objects.filter(aktif=True, cuma_tarihi=cuma)
        .order_by("sira", "-id")
        .first()
    )
    if atanmis:
        return atanmis

    genel = list(
        CumaDurumMetni.objects.filter(aktif=True, cuma_tarihi__isnull=True).order_by(
            "sira", "id"
        )
    )
    if not genel:
        return None
    hafta_no = cuma.isocalendar()[1]
    return genel[hafta_no % len(genel)]


def metin_json(metin: CumaDurumMetni) -> dict:
    return {
        "id": metin.id,
        "metin": metin.metin,
        "kaynak": metin.kaynak,
        "sablon": metin.sablon,
    }


def stuyo_baslangic_verisi(user: User, tarih=None) -> dict:
    cuma = son_cuma(tarih)
    oneri = haftalik_oneri_metni(tarih)
    havuz = [metin_json(m) for m in aktif_metinler()]
    return {
        "cuma_tarihi": cuma.strftime("%d.%m.%Y"),
        "personel_ad": personel_gorunen_ad(user),
        "personel_rol": personel_rol_etiketi(user),
        "oneri": metin_json(oneri) if oneri else None,
        "havuz": havuz,
        "sablonlar": [
            {"kod": kod, "etiket": etiket}
            for kod, etiket in CumaDurumMetni.Sablon.choices
        ],
    }
