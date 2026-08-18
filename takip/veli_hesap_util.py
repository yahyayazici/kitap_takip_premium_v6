"""Veli panel hesabı oluşturma — talebe TC ile giriş."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.contrib.auth.models import User

from takip.models import Talebe
from takip.tc_util import tc_dogrula
from takip.wave0_models import VeliHesap, VeliKisi, VeliTalebeBaglantisi

# Karışıklık yaratabilecek karakterler (0/O, 1/I/l) çıkarıldı — okunabilirlik için.
_GECICI_SIFRE_ALFABE = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
_GECICI_SIFRE_UZUNLUK = 12


def gecici_sifre_uret(uzunluk: int = _GECICI_SIFRE_UZUNLUK) -> str:
    """Yeni veli hesapları için kriptografik olarak güvenli geçici şifre üretir.

    ``secrets`` modülü (CSPRNG) kullanır; tahmin edilebilir bir üretici
    (TC son 4 hane gibi) DEĞİLDİR. Üretilen şifre yalnızca hesap
    oluşturma anında çağırana döndürülür — hiçbir yerde saklanmaz/loglanmaz.
    """
    return "".join(secrets.choice(_GECICI_SIFRE_ALFABE) for _ in range(uzunluk))


@dataclass
class VeliHesapSonucu:
    """``veli_panel_ensure`` çağrısının sonucu."""

    basarili: bool
    olusturuldu: bool = False
    gecici_sifre: str | None = None

    def __bool__(self) -> bool:  # geriye dönük uyumluluk: `if sonuc:` kullanımı
        return self.basarili


def veli_panel_ensure(
    talebe: Talebe,
    tc: str,
    veli_ad: str,
    veli_telefon: str = "",
) -> VeliHesapSonucu:
    """Veli panel hesabını talebenin TC'siyle açar/bağlar.

    ÖNEMLİ (güvenlik): Bu fonksiyon idempotenttir. Hesap zaten varsa
    şifreye KESİNLİKLE dokunulmaz — aksi halde her tekrar çağrıda
    (örn. Excel içe aktarma) veli şifresi sessizce sıfırlanırdı.
    Yalnızca YENİ hesap oluşturulduğunda güvenli bir geçici şifre atanır.
    """
    tc = tc_dogrula(tc)
    username = tc

    mevcut_user = (
        User.objects.filter(username__iexact=username)
        .exclude(veli_hesabi__talebe_baglantilari__talebe=talebe)
        .first()
    )
    if mevcut_user:
        return VeliHesapSonucu(basarili=False)

    user = User.objects.filter(username__iexact=username).first()
    olusturuldu = False
    gecici_sifre: str | None = None

    if user:
        # Mevcut hesap: şifre hash'i korunur, sadece görünen ad güncellenir.
        if veli_ad and user.first_name != veli_ad[:150]:
            user.first_name = veli_ad[:150]
            user.save(update_fields=["first_name"])
    else:
        gecici_sifre = gecici_sifre_uret()
        user = User(username=username[:150], first_name=(veli_ad or "")[:150])
        user.set_password(gecici_sifre)
        user.save()
        olusturuldu = True

    veli_hesap, veli_hesap_yeni = VeliHesap.objects.get_or_create(
        user=user,
        defaults={
            "ad_soyad": veli_ad or talebe.ad_soyad,
            "telefon": veli_telefon,
            "aktif": True,
        },
    )
    if not veli_hesap_yeni:
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
    return VeliHesapSonucu(
        basarili=True,
        olusturuldu=olusturuldu,
        gecici_sifre=gecici_sifre,
    )
