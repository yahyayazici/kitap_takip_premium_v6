"""Kullanıcı → etüt hocası eşlemesi (döngüsel import önlemek için)."""

from __future__ import annotations

from django.contrib.auth.models import User

from takip.models import EtutHocasi


def etut_hocasi_for_user(user: User):
    if not user.is_authenticated:
        return None

    if hasattr(EtutHocasi, "user_id"):
        hoca = EtutHocasi.objects.filter(user=user).first()
        if hoca:
            return hoca

    return None


def etut_mesul_for_user(user: User):
    """Etüt veya sınıf mesulü — branş öğretmeni EtutHocasi kaydı değil."""
    hoca = etut_hocasi_for_user(user)
    if not hoca or not hoca.aktif:
        return None

    from takip.etut_zimmet_service import etut_mesul_mu

    return hoca if etut_mesul_mu(hoca) else None
