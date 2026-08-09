"""Hızlı kayıt — son kayıtlar ve pasif etme."""

from __future__ import annotations

from django.contrib.auth.models import User

from takip.models import EtutHocasi, PersonelProfili, Talebe
from takip.ogretmen_odeme_models import OgretmenOdemeProfili

SON_KAYIT_LIMIT = 20


def son_kayitlar(tur: str):
    if tur == "talebe":
        return list(
            Talebe.objects.filter(aktif=True)
            .select_related("sinif_sube", "etut_hocasi", "dini_ders_hocasi")
            .order_by("-id")[:SON_KAYIT_LIMIT]
        )
    if tur == "personel":
        return list(
            PersonelProfili.objects.filter(aktif=True)
            .select_related("user", "etut_hocasi")
            .order_by("-olusturulma")[:SON_KAYIT_LIMIT]
        )
    if tur == "ogretmen":
        return list(
            EtutHocasi.objects.filter(
                aktif=True,
                odeme_profili__isnull=False,
                personel_kaydi__isnull=True,
            )
            .select_related("odeme_profili", "odeme_profili__brans")
            .order_by("-id")[:SON_KAYIT_LIMIT]
        )
    return []


def talebe_pasif_et(talebe: Talebe) -> None:
    talebe.aktif = False
    talebe.durum = Talebe.Durum.AYRILDI
    talebe.save(update_fields=["aktif", "durum"])


def personel_pasif_et(personel: PersonelProfili) -> None:
    personel.aktif = False
    personel.save(update_fields=["aktif"])

    if personel.user_id:
        User.objects.filter(pk=personel.user_id).update(is_active=False)

    if personel.etut_hocasi_id:
        etut_hocasi_pasif_et(personel.etut_hocasi)


def etut_hocasi_pasif_et(hoca: EtutHocasi) -> None:
    hoca.aktif = False
    hoca.save(update_fields=["aktif"])

    if hoca.user_id:
        User.objects.filter(pk=hoca.user_id).update(is_active=False)

    personel = getattr(hoca, "personel_kaydi", None)
    if personel and personel.aktif:
        personel.aktif = False
        personel.save(update_fields=["aktif"])

    try:
        profil = hoca.odeme_profili
    except OgretmenOdemeProfili.DoesNotExist:
        profil = None
    if profil and profil.aktif:
        profil.aktif = False
        profil.save(update_fields=["aktif"])


def ogretmen_pasif_et(hoca: EtutHocasi) -> None:
    etut_hocasi_pasif_et(hoca)
