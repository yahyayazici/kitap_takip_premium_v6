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
    """Pasif et — model save()/full_clean atlanır (eski kayıtlarda 500 önlenir)."""
    Talebe.objects.filter(pk=talebe.pk).update(
        aktif=False,
        durum=Talebe.Durum.AYRILDI,
        talebe_no=None,
    )

    from takip.talebe_panel_models import TalebeHesap

    hesap = (
        TalebeHesap.objects.filter(talebe_id=talebe.pk)
        .select_related("user")
        .first()
    )
    if hesap:
        if hesap.aktif:
            TalebeHesap.objects.filter(pk=hesap.pk).update(aktif=False)
        if hesap.user_id:
            User.objects.filter(pk=hesap.user_id).update(is_active=False)


def personel_pasif_et(personel: PersonelProfili) -> None:
    PersonelProfili.objects.filter(pk=personel.pk).update(aktif=False)

    if personel.user_id:
        User.objects.filter(pk=personel.user_id).update(is_active=False)

    if personel.etut_hocasi_id:
        etut_hocasi_pasif_et(personel.etut_hocasi, personel_pasif=False)


def etut_hocasi_pasif_et(hoca: EtutHocasi, *, personel_pasif: bool = True) -> None:
    EtutHocasi.objects.filter(pk=hoca.pk).update(aktif=False)

    if hoca.user_id:
        User.objects.filter(pk=hoca.user_id).update(is_active=False)

    if personel_pasif:
        personel = getattr(hoca, "personel_kaydi", None)
        if personel and personel.aktif:
            PersonelProfili.objects.filter(pk=personel.pk).update(aktif=False)
            if personel.user_id:
                User.objects.filter(pk=personel.user_id).update(is_active=False)

    try:
        profil = hoca.odeme_profili
    except OgretmenOdemeProfili.DoesNotExist:
        profil = None
    if profil and profil.aktif:
        OgretmenOdemeProfili.objects.filter(pk=profil.pk).update(aktif=False)


def ogretmen_pasif_et(hoca: EtutHocasi) -> None:
    etut_hocasi_pasif_et(hoca)


def talebe_kalici_sil(talebe: Talebe) -> None:
    if talebe.aktif:
        raise ValueError("Aktif talebe kalıcı silinemez; önce pasif edin.")
    from django.db.models.deletion import ProtectedError

    from takip.talebe_panel_models import TalebeHesap

    hesap = TalebeHesap.objects.filter(talebe_id=talebe.pk).select_related("user").first()
    if hesap and hesap.user_id:
        User.objects.filter(pk=hesap.user_id).delete()
    elif hesap:
        TalebeHesap.objects.filter(pk=hesap.pk).delete()

    try:
        talebe.delete()
    except ProtectedError as exc:
        raise ValueError(
            "Bu talebenin bağlı disiplin veya yemek kaydı var; "
            "kalıcı silinemez."
        ) from exc


def _personel_kalici_sil_on_hazirlik(personel: PersonelProfili) -> None:
    """PROTECT ve etüt CASCADE engellerini kaldırır."""
    personel.veli_randevulari.all().delete()
    personel.disiplin_kurul_katilimlari.all().delete()
    if personel.etut_hocasi_id:
        PersonelProfili.objects.filter(pk=personel.pk).update(etut_hocasi_id=None)
        personel.etut_hocasi_id = None


def personel_kalici_sil(personel: PersonelProfili) -> None:
    if personel.aktif:
        raise ValueError("Aktif personel kalıcı silinemez; önce pasif edin.")
    from django.db.models.deletion import ProtectedError

    user_id = personel.user_id
    etut_id = personel.etut_hocasi_id
    _personel_kalici_sil_on_hazirlik(personel)

    try:
        personel.delete()
    except ProtectedError as exc:
        raise ValueError(
            "Personel profili başka kayıtlara bağlı olduğu için silinemedi."
        ) from exc

    if not user_id:
        return

    etut_var = etut_id and EtutHocasi.objects.filter(pk=etut_id).exists()
    talebe_bagli = etut_var and Talebe.objects.filter(etut_hocasi_id=etut_id).exists()
    if talebe_bagli:
        User.objects.filter(pk=user_id).update(is_active=False)
        return

    try:
        User.objects.filter(pk=user_id).delete()
    except ProtectedError as exc:
        raise ValueError(
            "Personel profili silindi ancak kullanıcı hesabı başka kayıtlara "
            "bağlı olduğu için kaldırılamadı."
        ) from exc


def ogretmen_kalici_sil(hoca: EtutHocasi) -> None:
    if hoca.aktif:
        raise ValueError("Aktif öğretmen kalıcı silinemez; önce pasif edin.")
    if getattr(hoca, "personel_kaydi", None):
        raise ValueError("Personel kaydına bağlı öğretmen buradan kalıcı silinemez.")
    user_id = hoca.user_id
    try:
        profil = hoca.odeme_profili
    except OgretmenOdemeProfili.DoesNotExist:
        profil = None
    if profil:
        profil.delete()
    hoca.delete()
    if user_id:
        User.objects.filter(pk=user_id).delete()
