"""Veli panel hesabı oluşturma — talebe TC ile giriş."""

from __future__ import annotations

from django.contrib.auth.models import User

from takip.models import Talebe
from takip.tc_util import tc_dogrula, veli_sifre_tc_son4
from takip.wave0_models import VeliHesap, VeliKisi, VeliTalebeBaglantisi


def veli_panel_ensure(
    talebe: Talebe,
    tc: str,
    veli_ad: str,
    veli_telefon: str = "",
) -> bool:
    """Veli panel hesabını talebe TC + son 4 hane şifre ile aç/güncelle."""
    tc = tc_dogrula(tc)
    username = tc
    sifre = veli_sifre_tc_son4(tc)

    mevcut_user = (
        User.objects.filter(username__iexact=username)
        .exclude(veli_hesabi__talebe_baglantilari__talebe=talebe)
        .first()
    )
    if mevcut_user:
        return False

    user = User.objects.filter(username__iexact=username).first()
    if user:
        user.set_password(sifre)
        if veli_ad:
            user.first_name = veli_ad[:150]
        user.save()
    else:
        user = User(username=username[:150], first_name=(veli_ad or "")[:150])
        user.set_password(sifre)
        user.save()

    veli_hesap, olusturuldu = VeliHesap.objects.get_or_create(
        user=user,
        defaults={
            "ad_soyad": veli_ad or talebe.ad_soyad,
            "telefon": veli_telefon,
            "aktif": True,
        },
    )
    if not olusturuldu:
        if veli_ad:
            veli_hesap.ad_soyad = veli_ad
        if veli_telefon:
            veli_hesap.telefon = veli_telefon
        veli_hesap.aktif = True
        veli_hesap.save()

    VeliTalebeBaglantisi.objects.get_or_create(
        veli=veli_hesap,
        talebe=talebe,
        defaults={"yakinlik": VeliKisi.Yakinlik.VELI},
    )
    return True
