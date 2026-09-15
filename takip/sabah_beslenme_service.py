"""Sabah Beslenmesi — sipariş, teslim, borç ve özet işlemleri."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone

from takip.models import Talebe
from takip.permissions.scope import yetkili_talebeler
from takip.permissions.service import can, kullanici_birincil_rol_slug
from takip.sabah_beslenme_models import (
    SabahBeslenmeGunlukMenu,
    SabahBeslenmeIslemLog,
    SabahBeslenmeSiparis,
    para,
)
from takip.user_helpers import etut_hocasi_for_user

MODUL = "sabah_beslenmesi"
MAX_ADET = 20

SATIS_ROLLER = frozenset(
    {"idareci", "ic_mesul", "egitim_mesul", "nehari_mesul", "mahal_sorumlusu"}
)
BORC_KAPAT_ROLLER = frozenset({"idareci", "ic_mesul", "egitim_mesul", "muhasebeci"})


class SabahBeslenmeHata(Exception):
    """Kullanıcıya gösterilebilir iş kuralı hatası."""


def _slug(user: User) -> str | None:
    return kullanici_birincil_rol_slug(user)


def modul_erisimi(user: User) -> bool:
    return can(user, MODUL, "view")


def siparis_girebilir(user: User) -> bool:
    return can(user, MODUL, "create") or can(user, MODUL, "edit")


def satis_yapabilir(user: User) -> bool:
    return can(user, MODUL, "satis")


def menu_yonetebilir(user: User) -> bool:
    if user.is_superuser:
        return True
    return can(user, MODUL, "create") and (
        _slug(user) in SATIS_ROLLER or can(user, MODUL, "satis")
    )


def siparis_iptal_edebilir(user: User) -> bool:
    if user.is_superuser:
        return True
    return can(user, MODUL, "delete") or menu_yonetebilir(user)


def borc_kapatabilir(user: User) -> bool:
    if can(user, MODUL, "borc_kapat"):
        return True
    return can(user, "aidat", "edit") and _slug(user) in BORC_KAPAT_ROLLER


def rapor_gorebilir(user: User) -> bool:
    return can(user, MODUL, "export_pdf") or menu_yonetebilir(user) or borc_kapatabilir(user)


def siparis_penceresi_acik(menu: SabahBeslenmeGunlukMenu) -> bool:
    if menu.durum != SabahBeslenmeGunlukMenu.Durum.ACIK:
        return False
    simdi = timezone.localtime()
    if simdi.date() > menu.tarih:
        return False
    if simdi.date() < menu.tarih:
        return True
    return simdi.time() <= menu.siparis_son_saati


def menu_al(tarih: date | None = None) -> SabahBeslenmeGunlukMenu | None:
    return SabahBeslenmeGunlukMenu.objects.filter(tarih=tarih or timezone.localdate()).first()


def _yetkili_qs(user: User):
    return yetkili_talebeler(user, aktif_only=True)


def siparis_talebe_qs(user: User, *, etudum: bool = False):
    """Namaz yoklaması gibi: varsayılan bütün aktif talebeler; Etüdüm isteğe bağlı."""
    qs = Talebe.objects.filter(aktif=True).select_related("etut_hocasi", "sinif_sube")
    if etudum:
        hoca = etut_hocasi_for_user(user)
        if hoca:
            qs = qs.filter(etut_hocasi=hoca)
    return qs.order_by("sinif_sube__sinif", "sinif_sube__sube", "ad_soyad", "id")


def _log(siparis: SabahBeslenmeSiparis, islem: str, user: User | None, detay: str = "") -> None:
    SabahBeslenmeIslemLog.objects.create(
        siparis=siparis,
        islem=islem,
        yapan=user if user and user.is_authenticated else None,
        detay=detay[:240],
    )


def _sinif_etiketi(talebe) -> str:
    if talebe.sinif_sube_id:
        return str(talebe.sinif_sube)
    parca = " / ".join(p for p in (talebe.sinif, talebe.sube) if p)
    return parca or "—"


def siparis_json(siparis: SabahBeslenmeSiparis) -> dict[str, Any]:
    tutar = siparis.tutar
    teslim_saati = ""
    if siparis.teslim_saati:
        teslim_saati = timezone.localtime(siparis.teslim_saati).strftime("%H:%M")
    return {
        "id": siparis.pk,
        "talebe_id": siparis.talebe_id,
        "talebe": siparis.talebe.ad_soyad,
        "etut": siparis.etut_hocasi.ad_soyad if siparis.etut_hocasi_id else "—",
        "etut_id": siparis.etut_hocasi_id or 0,
        "sinif": _sinif_etiketi(siparis.talebe),
        "urun": siparis.menu.urun,
        "adet": siparis.adet,
        "tutar": str(tutar),
        "tutar_etiket": f"{tutar:.2f} ₺",
        "odeme_turu": siparis.odeme_turu,
        "teslim_edildi": siparis.teslim_edildi,
        "teslim_saati": teslim_saati,
        "teslim_eden": (
            siparis.teslim_eden.get_full_name() or siparis.teslim_eden.username
            if siparis.teslim_eden_id
            else ""
        ),
        "borc_acik": siparis.borc_acik,
        "borc_kapatildi": siparis.borc_kapatildi,
        "borc_kaydi_olustu": siparis.borc_kaydi_olustu,
    }


def gun_ozeti(menu: SabahBeslenmeGunlukMenu | None) -> dict[str, Any]:
    bos = {
        "toplam_siparis_adedi": 0,
        "satisi_yapilan": 0,
        "bekleyen": 0,
        "pesin_tahsil": "0.00",
        "borca_yazilan": "0.00",
        "siparis_satir": 0,
    }
    if not menu:
        return bos

    qs = menu.siparisler.filter(adet__gt=0).select_related("menu")
    satirlar = list(qs)
    toplam_adet = sum(s.adet for s in satirlar)
    satilan = [s for s in satirlar if s.teslim_edildi]
    bekleyen = [s for s in satirlar if not s.teslim_edildi]
    pesin = para(
        sum((s.tutar for s in satilan if s.odeme_turu == SabahBeslenmeSiparis.OdemeTuru.PESIN), Decimal("0.00"))
    )
    borc = para(
        sum(
            (s.tutar for s in satilan if s.odeme_turu == SabahBeslenmeSiparis.OdemeTuru.BORC),
            Decimal("0.00"),
        )
    )
    return {
        "toplam_siparis_adedi": toplam_adet,
        "satisi_yapilan": len(satilan),
        "bekleyen": len(bekleyen),
        "pesin_tahsil": f"{pesin:.2f}",
        "borca_yazilan": f"{borc:.2f}",
        "siparis_satir": len(satirlar),
    }


def satis_satirlari(user: User, menu: SabahBeslenmeGunlukMenu) -> list[SabahBeslenmeSiparis]:
    qs = (
        menu.siparisler.filter(adet__gt=0)
        .select_related("talebe", "talebe__sinif_sube", "etut_hocasi", "menu", "teslim_eden")
        .order_by("teslim_edildi", "talebe__ad_soyad", "id")
    )
    if not satis_yapabilir(user) and not menu_yonetebilir(user) and not borc_kapatabilir(user):
        ids = _yetkili_qs(user).values_list("pk", flat=True)
        qs = qs.filter(talebe_id__in=ids)
    return list(qs)


def etut_siparis_gruplari(
    user: User,
    menu: SabahBeslenmeGunlukMenu | None,
    *,
    etudum: bool = False,
) -> list[dict[str, Any]]:
    talebeler = list(siparis_talebe_qs(user, etudum=etudum))
    mevcut = {}
    if menu:
        mevcut = {
            s.talebe_id: s
            for s in menu.siparisler.filter(talebe_id__in=[t.pk for t in talebeler])
        }
    gruplar: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for talebe in talebeler:
        sinif = _sinif_etiketi(talebe)
        if current is None or current["sinif"] != sinif:
            current = {"sinif": sinif, "satirlar": []}
            gruplar.append(current)
        siparis = mevcut.get(talebe.pk)
        current["satirlar"].append(
            {
                "talebe": talebe,
                "sinif": sinif,
                "siparis": siparis,
                "adet": siparis.adet if siparis else None,
            }
        )
    return gruplar


def menu_kaydet(
    user: User,
    *,
    tarih: date,
    urun: str,
    birim_fiyat: Decimal,
    siparis_son_saati: time,
    durum: str,
) -> SabahBeslenmeGunlukMenu:
    if not menu_yonetebilir(user):
        raise SabahBeslenmeHata("Günlük menüyü yalnızca satış sorumlusu veya yönetici tanımlayabilir.")
    urun = (urun or "").strip()
    if not urun:
        raise SabahBeslenmeHata("Beslenme ürünü zorunludur.")
    fiyat = para(birim_fiyat)
    if fiyat < 0:
        raise SabahBeslenmeHata("Birim fiyat negatif olamaz.")
    if durum not in {SabahBeslenmeGunlukMenu.Durum.ACIK, SabahBeslenmeGunlukMenu.Durum.KAPALI}:
        raise SabahBeslenmeHata("Sipariş durumu geçersiz.")

    with transaction.atomic():
        menu = SabahBeslenmeGunlukMenu.objects.filter(tarih=tarih).first()
        if menu:
            menu.urun = urun
            menu.birim_fiyat = fiyat
            menu.siparis_son_saati = siparis_son_saati
            menu.durum = durum
            menu.guncelleyen = user
            menu.save()
        else:
            menu = SabahBeslenmeGunlukMenu.objects.create(
                tarih=tarih,
                urun=urun,
                birim_fiyat=fiyat,
                siparis_son_saati=siparis_son_saati,
                durum=durum,
                olusturan=user,
                guncelleyen=user,
            )
    return menu


def siparis_kaydet(user: User, *, menu: SabahBeslenmeGunlukMenu, talebe_id: int, adet: int) -> SabahBeslenmeSiparis:
    if not siparis_girebilir(user):
        raise SabahBeslenmeHata("Sipariş girme yetkiniz yok.")
    if adet < 0 or adet > MAX_ADET:
        raise SabahBeslenmeHata(f"Adet 0 ile {MAX_ADET} arasında olmalıdır.")

    talebe = (
        Talebe.objects.filter(pk=talebe_id, aktif=True)
        .select_related("etut_hocasi")
        .first()
    )
    if not talebe:
        raise SabahBeslenmeHata("Talebe bulunamadı.")

    hoca = talebe.etut_hocasi
    kaydeden_hoca = etut_hocasi_for_user(user)
    etut = hoca or kaydeden_hoca

    with transaction.atomic():
        siparis = (
            SabahBeslenmeSiparis.objects.select_for_update(of=("self",))
            .filter(menu=menu, talebe=talebe)
            .first()
        )
        if siparis and siparis.teslim_edildi:
            raise SabahBeslenmeHata("Teslim edilmiş sipariş değiştirilemez. Önce satışı geri alın.")
        if siparis:
            siparis.adet = adet
            siparis.kaydeden = user
            siparis.etut_hocasi = etut
            siparis.save(update_fields=["adet", "kaydeden", "etut_hocasi", "guncellenme"])
        else:
            try:
                siparis = SabahBeslenmeSiparis.objects.create(
                    menu=menu,
                    talebe=talebe,
                    etut_hocasi=etut,
                    adet=adet,
                    kaydeden=user,
                )
            except IntegrityError:
                siparis = SabahBeslenmeSiparis.objects.select_for_update(of=("self",)).get(
                    menu=menu, talebe=talebe
                )
                if siparis.teslim_edildi:
                    raise SabahBeslenmeHata("Teslim edilmiş sipariş değiştirilemez.")
                siparis.adet = adet
                siparis.kaydeden = user
                siparis.etut_hocasi = etut
                siparis.save(update_fields=["adet", "kaydeden", "etut_hocasi", "guncellenme"])
        _log(siparis, SabahBeslenmeIslemLog.Islem.SIPARIS, user, detay=f"adet={adet}")
    return siparis


def _borc_uygula(siparis: SabahBeslenmeSiparis) -> None:
    """Teslim edilmiş satırda borç kaydını tek sefer oluştur veya peşine çevir."""
    if not siparis.teslim_edildi:
        siparis.borc_kaydi_olustu = False
        siparis.borc_tutari = Decimal("0.00")
        siparis.borc_kapatildi = False
        siparis.borc_kapatan = None
        siparis.borc_kapatma_saati = None
        return

    if siparis.odeme_turu == SabahBeslenmeSiparis.OdemeTuru.BORC:
        if siparis.borc_kaydi_olustu:
            return
        siparis.borc_kaydi_olustu = True
        siparis.borc_tutari = siparis.tutar
        siparis.borc_kapatildi = False
        siparis.borc_kapatan = None
        siparis.borc_kapatma_saati = None
        return

    if siparis.borc_kapatildi:
        return
    siparis.borc_kaydi_olustu = False
    siparis.borc_tutari = Decimal("0.00")
    siparis.borc_kapatildi = False
    siparis.borc_kapatan = None
    siparis.borc_kapatma_saati = None


def _kilitli_siparis(siparis_id: int) -> SabahBeslenmeSiparis | None:
    """Postgres FOR UPDATE, nullable etüt/teslim join'ini kilitlemez."""
    return (
        SabahBeslenmeSiparis.objects.select_for_update(of=("self",))
        .select_related("menu", "talebe", "etut_hocasi", "teslim_eden")
        .filter(pk=siparis_id)
        .first()
    )


def teslim_et(user: User, siparis_id: int) -> SabahBeslenmeSiparis:
    if not satis_yapabilir(user):
        raise SabahBeslenmeHata("Satış işlemi yetkiniz yok.")

    with transaction.atomic():
        siparis = _kilitli_siparis(siparis_id)
        if not siparis:
            raise SabahBeslenmeHata("Sipariş bulunamadı.")
        if siparis.adet <= 0:
            raise SabahBeslenmeHata("Teslim edilmeyen / sıfır adetli sipariş satışa dönüşmez.")
        if siparis.teslim_edildi:
            return siparis

        siparis.teslim_edildi = True
        siparis.teslim_saati = timezone.now()
        siparis.teslim_eden = user
        _borc_uygula(siparis)
        siparis.save()
        _log(
            siparis,
            SabahBeslenmeIslemLog.Islem.TESLIM,
            user,
            detay=f"{siparis.odeme_turu} tutar={siparis.tutar}",
        )
    return siparis


def teslim_geri_al(user: User, siparis_id: int) -> SabahBeslenmeSiparis:
    if not satis_yapabilir(user):
        raise SabahBeslenmeHata("Satış işlemi yetkiniz yok.")

    with transaction.atomic():
        siparis = _kilitli_siparis(siparis_id)
        if not siparis:
            raise SabahBeslenmeHata("Sipariş bulunamadı.")
        if not siparis.teslim_edildi:
            return siparis
        if siparis.borc_kapatildi:
            raise SabahBeslenmeHata("Borç tahsil edilmiş. Teslim geri alınamaz.")

        siparis.teslim_edildi = False
        siparis.teslim_saati = None
        siparis.teslim_eden = None
        siparis.borc_kaydi_olustu = False
        siparis.borc_tutari = Decimal("0.00")
        siparis.borc_kapatildi = False
        siparis.borc_kapatan = None
        siparis.borc_kapatma_saati = None
        siparis.save()
        _log(siparis, SabahBeslenmeIslemLog.Islem.TESLIM_GERI, user)
    return siparis


def odeme_turu_ayarla(user: User, siparis_id: int, odeme_turu: str) -> SabahBeslenmeSiparis:
    if not satis_yapabilir(user):
        raise SabahBeslenmeHata("Ödeme tercihini satış sorumlusu değiştirebilir.")
    if odeme_turu not in {
        SabahBeslenmeSiparis.OdemeTuru.PESIN,
        SabahBeslenmeSiparis.OdemeTuru.BORC,
    }:
        raise SabahBeslenmeHata("Ödeme türü geçersiz.")

    with transaction.atomic():
        siparis = _kilitli_siparis(siparis_id)
        if not siparis:
            raise SabahBeslenmeHata("Sipariş bulunamadı.")
        if siparis.borc_kapatildi and odeme_turu == SabahBeslenmeSiparis.OdemeTuru.BORC:
            raise SabahBeslenmeHata("Kapatılmış borç yeniden açılamaz.")
        if siparis.borc_kapatildi and odeme_turu == SabahBeslenmeSiparis.OdemeTuru.PESIN:
            return siparis

        siparis.odeme_turu = odeme_turu
        if siparis.teslim_edildi:
            _borc_uygula(siparis)
        siparis.save()
        _log(siparis, SabahBeslenmeIslemLog.Islem.ODEME, user, detay=odeme_turu)
    return siparis


def borc_kapat(user: User, siparis_id: int) -> SabahBeslenmeSiparis:
    if not borc_kapatabilir(user):
        raise SabahBeslenmeHata("Borç kapatma yetkiniz yok.")

    with transaction.atomic():
        siparis = _kilitli_siparis(siparis_id)
        if not siparis:
            raise SabahBeslenmeHata("Sipariş bulunamadı.")
        if not siparis.teslim_edildi or not siparis.borc_kaydi_olustu:
            raise SabahBeslenmeHata("Açık borç kaydı yok.")
        if siparis.borc_kapatildi:
            return siparis
        siparis.borc_kapatildi = True
        siparis.borc_kapatan = user
        siparis.borc_kapatma_saati = timezone.now()
        siparis.save(
            update_fields=["borc_kapatildi", "borc_kapatan", "borc_kapatma_saati", "guncellenme"]
        )
        _log(siparis, SabahBeslenmeIslemLog.Islem.BORC_KAPAT, user, detay=str(siparis.borc_tutari))
    return siparis


def acik_borc_qs(user: User | None = None) -> QuerySet[SabahBeslenmeSiparis]:
    qs = (
        SabahBeslenmeSiparis.objects.filter(
            teslim_edildi=True,
            borc_kaydi_olustu=True,
            borc_kapatildi=False,
        )
        .select_related("talebe", "talebe__sinif_sube", "etut_hocasi", "menu", "teslim_eden")
        .order_by("-teslim_saati", "talebe__ad_soyad")
    )
    if user is not None and not (satis_yapabilir(user) or menu_yonetebilir(user) or borc_kapatabilir(user)):
        qs = qs.filter(talebe_id__in=_yetkili_qs(user).values_list("pk", flat=True))
    return qs


def acik_borc_ozet(user: User) -> dict[str, Any]:
    qs = acik_borc_qs(user)
    toplam = qs.aggregate(t=Sum("borc_tutari"))["t"] or Decimal("0.00")
    return {
        "adet": qs.count(),
        "tutar": para(toplam),
        "tutar_etiket": f"{para(toplam):.2f} ₺",
    }


def rapor_satirlari(user: User, bas: date, bitis: date) -> list[SabahBeslenmeSiparis]:
    qs = (
        SabahBeslenmeSiparis.objects.filter(
            menu__tarih__gte=bas,
            menu__tarih__lte=bitis,
            adet__gt=0,
        )
        .select_related("talebe", "talebe__sinif_sube", "etut_hocasi", "menu", "teslim_eden")
        .order_by("-menu__tarih", "talebe__ad_soyad")
    )
    if not (satis_yapabilir(user) or menu_yonetebilir(user) or borc_kapatabilir(user)):
        qs = qs.filter(talebe_id__in=_yetkili_qs(user).values_list("pk", flat=True))
    return list(qs)
