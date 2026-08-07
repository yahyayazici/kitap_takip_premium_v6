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
