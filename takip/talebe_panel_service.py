"""Talebe paneli — konum, dashboard ve giriş izinleri."""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.utils.timezone import localdate

from takip.duyuru_service import veli_duyurulari
from takip.models import Talebe, TalebeEvGunu, TalebeHesap, TalebeKonumKaydi
from takip.soru_takip_service import (
    haftalik_ozet,
    kayit_kaydet,
    kayit_satirlari_form_verisi,
    soru_takip_dersleri,
)
from takip.soru_takip_models import GunlukSoruKaydi


GIRIS_IZINLI_MODLAR = frozenset(
    {TalebeKonumKaydi.Mod.EV, TalebeKonumKaydi.Mod.IZIN}
)

HAFTA_GUNLERI = (
    "Pazartesi",
    "Salı",
    "Çarşamba",
    "Perşembe",
    "Cuma",
    "Cumartesi",
    "Pazar",
)


def talebe_hesabi_for_user(user: User) -> TalebeHesap | None:
    if not user.is_authenticated:
        return None
    try:
        return user.talebe_hesabi
    except TalebeHesap.DoesNotExist:
        return None


def kullanici_talebe_mi(user: User) -> bool:
    if not user.is_authenticated or user.is_superuser:
        return False

    from takip.models import PersonelProfili

    if PersonelProfili.objects.filter(user=user).exists():
        return False

    hesap = talebe_hesabi_for_user(user)
    return bool(hesap and hesap.aktif)


def varsayilan_ev_gunu() -> int:
    """Cuma = 4 (Python weekday)."""
    return 4


def ev_gunleri() -> set[int]:
    aktif = set(
        TalebeEvGunu.objects.filter(aktif=True).values_list("weekday", flat=True)
    )
    if aktif:
        return aktif
    return {varsayilan_ev_gunu()}


def konum_for_date(talebe: Talebe, tarih: date | None = None) -> TalebeKonumKaydi.Mod:
    tarih = tarih or localdate()

    kayit = TalebeKonumKaydi.objects.filter(talebe=talebe, tarih=tarih).first()
    if kayit:
        return TalebeKonumKaydi.Mod(kayit.mod)

    if tarih.weekday() in ev_gunleri():
        return TalebeKonumKaydi.Mod.EV

    return TalebeKonumKaydi.Mod.KURS


def konum_gosterimi(mod: TalebeKonumKaydi.Mod) -> str:
    return dict(TalebeKonumKaydi.Mod.choices).get(mod, mod)


def okuma_soru_girebilir(talebe: Talebe, tarih: date | None = None) -> bool:
    return konum_for_date(talebe, tarih) in GIRIS_IZINLI_MODLAR


def haftalik_konum_ozeti(talebe: Talebe, referans: date | None = None) -> list[dict]:
    referans = referans or localdate()
    baslangic = referans - timedelta(days=referans.weekday())
    gunler = []

    ozel = {
        k.tarih: k
        for k in TalebeKonumKaydi.objects.filter(
            talebe=talebe,
            tarih__gte=baslangic,
            tarih__lte=baslangic + timedelta(days=6),
        )
    }

    for i in range(7):
        gun = baslangic + timedelta(days=i)
        kayit = ozel.get(gun)
        if kayit:
            mod = TalebeKonumKaydi.Mod(kayit.mod)
            aciklama = kayit.aciklama
        else:
            mod = konum_for_date(talebe, gun)
            aciklama = ""

        gunler.append(
            {
                "tarih": gun,
                "gun_adi": HAFTA_GUNLERI[gun.weekday()],
                "mod": mod,
                "mod_etiket": konum_gosterimi(mod),
                "aciklama": aciklama,
                "bugun": gun == referans,
            }
        )

    return gunler


def talebe_dashboard_verisi(hesap: TalebeHesap) -> dict:
    talebe = hesap.talebe
    bugun = localdate()
    konum = konum_for_date(talebe, bugun)

    return {
        "hesap": hesap,
        "talebe": talebe,
        "bugun": bugun,
        "konum": konum,
        "konum_etiket": konum_gosterimi(konum),
        "okuma_soru_acik": okuma_soru_girebilir(talebe, bugun),
        "haftalik_konum": haftalik_konum_ozeti(talebe, bugun),
        "haftalik_soru": haftalik_ozet(talebe, bugun),
        "duyurular": list(veli_duyurulari()[:3]),
    }


def talebe_profil_verisi(hesap: TalebeHesap) -> dict:
    talebe = hesap.talebe
    return {
        "hesap": hesap,
        "talebe": talebe,
        "sinif_goster": _sinif_goster(talebe),
    }


def _sinif_goster(talebe: Talebe) -> str:
    if talebe.sinif_sube_id:
        return str(talebe.sinif_sube)
    parcalar = [p for p in (talebe.sinif, talebe.sube) if p]
    return " ".join(parcalar) or "—"


def talebe_okuma_soru_form_verisi(hesap: TalebeHesap, tarih: date | None = None) -> dict:
    talebe = hesap.talebe
    tarih = tarih or localdate()
    dersler = soru_takip_dersleri()
    kayit = GunlukSoruKaydi.objects.filter(talebe=talebe, tarih=tarih).first()

    return {
        "hesap": hesap,
        "talebe": talebe,
        "tarih": tarih,
        "konum": konum_for_date(talebe, tarih),
        "konum_etiket": konum_gosterimi(konum_for_date(talebe, tarih)),
        "girebilir": okuma_soru_girebilir(talebe, tarih),
        "dersler": dersler,
        "satirlar": kayit_satirlari_form_verisi(kayit, dersler),
        "kayit": kayit,
        "gunluk_not": kayit.gunluk_not if kayit else "",
    }


def talebe_okuma_soru_kaydet(
    user: User,
    hesap: TalebeHesap,
    post_data,
    tarih: date | None = None,
) -> tuple[bool, list[str]]:
    talebe = hesap.talebe
    tarih = tarih or localdate()

    if not okuma_soru_girebilir(talebe, tarih):
        return False, ["Bugün okuma/soru girişi yapılamaz (kurs günü)."]

    gunluk_not = (post_data.get("gunluk_not") or "").strip()
    dersler = soru_takip_dersleri()

    kayit, hatalar = kayit_kaydet(
        user,
        talebe,
        tarih,
        dersler,
        post_data,
        gunluk_not=gunluk_not,
    )
    if hatalar:
        return False, hatalar
    return bool(kayit), []


def seed_talebe_panel_demo() -> None:
    """Demo talebe hesabı — Cuma ev günü."""
    from django.contrib.auth.models import User

    talebe = Talebe.objects.filter(aktif=True).order_by("id").first()
    if not talebe:
        return

    user, _ = User.objects.get_or_create(username="talebe")
    user.set_password("Talebe123!")
    user.save()

    TalebeHesap.objects.update_or_create(
        user=user,
        defaults={"talebe": talebe, "aktif": True},
    )
    TalebeEvGunu.objects.update_or_create(
        weekday=4,
        defaults={"aktif": True},
    )
