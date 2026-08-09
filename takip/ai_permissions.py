"""Yapay zeka erişim kontrolü."""

from __future__ import annotations

from django.contrib.auth.models import User

from takip.ai_gateway import ai_platform_aktif_mi
from takip.models import Talebe
from takip.permissions.scope import yetkili_talebeler
from takip.permissions.service import can
from takip.talebe_panel_service import kullanici_talebe_mi, talebe_hesabi_for_user
from takip.veli_service import kullanici_veli_mi, veli_hesabi_for_user, veli_talebeleri


def ai_erisim_var(user: User) -> bool:
    return ai_platform_aktif_mi() and user.is_authenticated


def talebe_ai_erisebilir(user: User, talebe: Talebe) -> bool:
    if not ai_erisim_var(user):
        return False
    if kullanici_talebe_mi(user):
        hesap = talebe_hesabi_for_user(user)
        return bool(hesap and hesap.talebe_id == talebe.id)
    if kullanici_veli_mi(user):
        veli = veli_hesabi_for_user(user)
        if not veli:
            return False
        return veli_talebeleri(veli).filter(pk=talebe.pk).exists()
    return yetkili_talebeler(user).filter(pk=talebe.pk).exists()


def kurum_ai_erisebilir(user: User) -> bool:
    if not ai_erisim_var(user):
        return False
    if kullanici_talebe_mi(user) or kullanici_veli_mi(user):
        return False
    return can(user, "deneme", "view") or can(user, "gelisim_dosyasi", "view") or user.is_superuser


def rehberlik_ai_erisebilir(user: User) -> bool:
    if not ai_erisim_var(user):
        return False
    return can(user, "rehberlik", "view") or can(user, "veli_iletisim", "view") or user.is_superuser
