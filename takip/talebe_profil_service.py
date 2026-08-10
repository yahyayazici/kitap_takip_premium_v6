"""Talebe kimlik/veli profili eksiklik kontrolü ve etüt düzenleme yetkisi."""

from __future__ import annotations

from django.contrib.auth.models import User

from takip.models import Talebe
from takip.user_helpers import etut_hocasi_for_user
from takip.wave0_models import VeliKisi

# Hızlı kayıtta boş bırakılıp Excel'deki gibi sonradan doldurulacak alanlar.
PROFIL_ALANLARI: tuple[tuple[str, str], ...] = (
    ("kimlik_adi", "Kimlik adı"),
    ("kimlik_soyadi", "Kimlik soyadı"),
    ("cinsiyet", "Cinsiyet"),
    ("dogum_tarihi", "Doğum tarihi"),
    ("baba_adi", "Baba adı"),
    ("anne_adi", "Anne adı"),
    ("dogum_yeri", "Doğum yeri"),
    ("memleket", "Memleket"),
    ("aile_durumu", "Aile durumu"),
    ("ev_adresi", "Ev adresi"),
)


def profil_eksik_alanlar(talebe: Talebe) -> list[str]:
    eksikler: list[str] = []
    for alan, etiket in PROFIL_ALANLARI:
        deger = getattr(talebe, alan, None)
        if deger is None or (isinstance(deger, str) and not deger.strip()):
            eksikler.append(etiket)

    veli_var = VeliKisi.objects.filter(talebe=talebe).exclude(ad_soyad="").exists()
    if not veli_var:
        eksikler.append("Veli bilgisi")

    return eksikler


def profil_eksik_mi(talebe: Talebe) -> bool:
    return bool(profil_eksik_alanlar(talebe))


def etut_profil_duzenleyebilir(user: User, talebe: Talebe) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    from takip.panel_permissions import tum_talebe_erisimi_var

    if tum_talebe_erisimi_var(user):
        return True

    hoca = etut_hocasi_for_user(user)
    return bool(hoca and talebe.etut_hocasi_id == hoca.id)
