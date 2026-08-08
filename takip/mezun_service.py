"""Mezun takip merkezi — sorgular, istatistikler, işlemler."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from config.branding import PANEL_SHORT
from takip.mezun_models import (
    MezunBasari,
    MezunEtkinlik,
    MezunEtkinlikKatilim,
    MezunGuncellemeGorevKayit,
    MezunGuncellemeGorevi,
    MezunIletisim,
    MezunProfil,
    MezunYolculukOlay,
)
from takip.models import Donem, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can

GORUSULMEYEN_GUN = 180


def mezun_gorebilir(user: User) -> bool:
    return can(user, "mezun", "view")


def mezun_duzenleyebilir(user: User) -> bool:
    return can(user, "mezun", "edit") or can(user, "mezun", "create")


def mezun_yonetebilir(user: User) -> bool:
    if user.is_superuser or tum_talebe_kapsami_var(user):
        return True
    from takip.permissions.scope import kullanici_rol_slugleri

    return bool(
        kullanici_rol_slugleri(user)
        & {"idareci", "ic_mesul", "egitim_mesul", "sinif_mesul", "muhasebeci"}
    )


def yetkili_mezun_profilleri(user: User) -> QuerySet[MezunProfil]:
    if not mezun_gorebilir(user):
        return MezunProfil.objects.none()

    qs = MezunProfil.objects.select_related(
        "talebe",
        "talebe__sinif_sube",
        "talebe__etut_hocasi",
        "donem",
        "donem__egitim_yili",
    )

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user, aktif_only=False).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def mezunlari_filtrele(
    qs: QuerySet[MezunProfil],
    *,
    q: str | None = None,
    mezuniyet_yili: str | None = None,
    lise: str | None = None,
    universite: str | None = None,
    bolum: str | None = None,
    basari: str | None = None,
    iletisim: str | None = None,
) -> QuerySet[MezunProfil]:
    if q:
        qs = qs.filter(
            Q(talebe__ad_soyad__icontains=q)
            | Q(talebe__talebe_no__icontains=q)
            | Q(yerlestigi_lise__icontains=q)
            | Q(universite__icontains=q)
            | Q(bolum__icontains=q)
            | Q(meslek__icontains=q)
            | Q(calistigi_kurum__icontains=q)
            | Q(sehir__icontains=q)
        )
    if mezuniyet_yili:
        qs = qs.filter(mezuniyet_yili=mezuniyet_yili)
    if lise:
        qs = qs.filter(yerlestigi_lise__icontains=lise)
    if universite:
        qs = qs.filter(universite__icontains=universite)
    if bolum:
        qs = qs.filter(bolum__icontains=bolum)
    if iletisim:
        qs = qs.filter(iletisim_durumu=iletisim)
    if basari:
        qs = qs.filter(basarilar__kategori=basari).distinct()
    return qs


def mezuniyet_yillari(qs: QuerySet[MezunProfil] | None = None) -> list[int]:
    base = qs if qs is not None else MezunProfil.objects.all()
    return list(
        base.exclude(mezuniyet_yili__isnull=True)
        .values_list("mezuniyet_yili", flat=True)
        .distinct()
        .order_by("-mezuniyet_yili")
    )


def mezun_yil_ozetleri(qs: QuerySet[MezunProfil]) -> list[dict[str, Any]]:
    rows = (
        qs.exclude(mezuniyet_yili__isnull=True)
        .values("mezuniyet_yili")
        .annotate(adet=Count("id"))
        .order_by("-mezuniyet_yili")
    )
    return [{"yil": r["mezuniyet_yili"], "adet": r["adet"]} for r in rows]


def dashboard_ozet(qs: QuerySet[MezunProfil]) -> dict[str, Any]:
    bugun_yil = timezone.localdate().year
    toplam = qs.count()
    bu_yil = qs.filter(mezuniyet_yili=bugun_yil).count()
    ilk_1 = qs.filter(lgs_yuzdelik__lte=1).count()
    ilk_5 = qs.filter(lgs_yuzdelik__lte=5).count()
    ilk_10 = qs.filter(lgs_yuzdelik__lte=10).count()
    universite = qs.exclude(universite="").count()
    iletisimde = qs.filter(
        iletisim_durumu__in=[
            MezunProfil.IletisimDurumu.ILETISIMDE,
            MezunProfil.IletisimDurumu.DUZENLI,
        ]
    ).count()
    return {
        "toplam_mezun": toplam,
        "bu_yil_mezun": bu_yil,
        "ilk_1": ilk_1,
        "ilk_5": ilk_5,
        "ilk_10": ilk_10,
        "universite_yerlesen": universite,
        "iletisimde": iletisimde,
    }


def sag_panel_verisi(user: User, qs: QuerySet[MezunProfil]) -> dict[str, Any]:
    bugun = timezone.localdate()
    esik = bugun - timedelta(days=GORUSULMEYEN_GUN)
    ay_bas = bugun.replace(day=1)

    guncellenmesi_gereken = list(
        qs.filter(
            Q(yerlestigi_lise="")
            | Q(universite="")
            | Q(iletisim_telefon="")
            | Q(iletisim_eposta="")
        ).order_by("-guncellenme")[:5]
    )
    gorusulmeyen = list(
        qs.filter(
            Q(son_gorusme_tarihi__lt=esik) | Q(son_gorusme_tarihi__isnull=True)
        ).order_by("son_gorusme_tarihi")[:5]
    )
    bu_ay_basarilar = list(
        MezunBasari.objects.filter(profil__in=qs, tarih__gte=ay_bas)
        .select_related("profil__talebe")
        .order_by("-tarih")[:5]
    )
    bekleyen_gorevler = []
    if mezun_yonetebilir(user):
        bekleyen_gorevler = list(
            MezunGuncellemeGorevi.objects.filter(tamamlandi=False)
            .select_related("sorumlu")
            .order_by("son_tarih")[:5]
        )
    else:
        bekleyen_gorevler = list(
            MezunGuncellemeGorevi.objects.filter(tamamlandi=False, sorumlu=user)
            .order_by("son_tarih")[:5]
        )

    yaklasan_etkinlikler = list(
        MezunEtkinlik.objects.filter(tarih__gte=bugun).order_by("tarih")[:5]
    )

    return {
        "yaklasan_etkinlikler": yaklasan_etkinlikler,
        "guncellenmesi_gereken": guncellenmesi_gereken,
        "gorusulmeyen": gorusulmeyen,
        "bu_ay_basarilar": bu_ay_basarilar,
        "bekleyen_gorevler": bekleyen_gorevler,
    }


def _yolculuk_ekle(
    profil: MezunProfil,
    *,
    yil: int,
    baslik: str,
    tur: str,
    aciklama: str = "",
    tarih: date | None = None,
    otomatik: bool = True,
) -> None:
    if profil.yolculuk_olaylari.filter(baslik=baslik, yil=yil, tur=tur).exists():
        return
    MezunYolculukOlay.objects.create(
        profil=profil,
        yil=yil,
        baslik=baslik,
        aciklama=aciklama,
        tur=tur,
        tarih=tarih,
        otomatik=otomatik,
    )


def mezun_yolculuk_olustur(profil: MezunProfil) -> None:
    yil = profil.mezuniyet_yili or timezone.localdate().year
    _yolculuk_ekle(
        profil,
        yil=yil,
        baslik=f"{PANEL_SHORT}'dan Mezun Oldu",
        tur=MezunYolculukOlay.Tur.MEZUNIYET,
        tarih=profil.mezuniyet_tarihi,
    )
    if profil.lgs_yuzdelik is not None:
        _yolculuk_ekle(
            profil,
            yil=yil,
            baslik=f"LGS %{profil.lgs_yuzdelik}",
            tur=MezunYolculukOlay.Tur.LGS,
            aciklama=f"Puan: {profil.lgs_puani or '—'}",
        )
    elif profil.lgs_puani is not None:
        _yolculuk_ekle(
            profil,
            yil=yil,
            baslik=f"LGS {profil.lgs_puani}",
            tur=MezunYolculukOlay.Tur.LGS,
        )
    if profil.yerlestigi_lise:
        ly = profil.lise_yerlesme_yili or yil
        _yolculuk_ekle(
            profil,
            yil=ly,
            baslik=f"{profil.yerlestigi_lise}'ne Yerleşti",
            tur=MezunYolculukOlay.Tur.LISE,
        )
    if profil.universite:
        uy = profil.universite_yerlesme_yili or yil
        baslik = profil.universite
        if profil.bolum:
            baslik = f"{profil.universite} — {profil.bolum}"
        _yolculuk_ekle(
            profil,
            yil=uy,
            baslik=baslik,
            tur=MezunYolculukOlay.Tur.UNIVERSITE,
        )


@transaction.atomic
def mezun_yap(
    talebe: Talebe,
    *,
    mezuniyet_yili: int | None = None,
    mezuniyet_tarihi: date | None = None,
    donem: Donem | None = None,
    lgs_puani=None,
    lgs_sira: int | None = None,
    lgs_yuzdelik=None,
    yerlestigi_lise: str = "",
    lise_yerlesme_yili: int | None = None,
    universite: str = "",
    bolum: str = "",
    yks_puani=None,
    yks_sira: int | None = None,
    iletisim_telefon: str = "",
    iletisim_eposta: str = "",
    iletisim_adres: str = "",
    notlar: str = "",
) -> MezunProfil:
    talebe.durum = Talebe.Durum.MEZUN
    talebe.aktif = False
    talebe.save(update_fields=["durum", "aktif"])

    yil = mezuniyet_yili or date.today().year
    profil, created = MezunProfil.objects.update_or_create(
        talebe=talebe,
        defaults={
            "mezuniyet_yili": yil,
            "mezuniyet_tarihi": mezuniyet_tarihi or date.today(),
            "donem": donem,
            "lgs_puani": lgs_puani,
            "lgs_sira": lgs_sira,
            "lgs_yuzdelik": lgs_yuzdelik,
            "yerlestigi_lise": yerlestigi_lise,
            "lise_yerlesme_yili": lise_yerlesme_yili or yil,
            "universite": universite,
            "bolum": bolum,
            "yks_puani": yks_puani,
            "yks_sira": yks_sira,
            "iletisim_telefon": iletisim_telefon or talebe.telefon,
            "iletisim_eposta": iletisim_eposta or talebe.eposta,
            "iletisim_adres": iletisim_adres,
            "notlar": notlar,
            "kurum_bagi": MezunProfil.KurumBagi.AKTIF,
            "iletisim_durumu": MezunProfil.IletisimDurumu.ILETISIMDE,
        },
    )
    if created or not profil.yolculuk_olaylari.exists():
        mezun_yolculuk_olustur(profil)
    return profil


@transaction.atomic
def iletisim_kaydi_ekle(
    profil: MezunProfil,
    *,
    tur: str,
    tarih: date,
    aciklama: str,
    user: User | None,
) -> MezunIletisim:
    kayit = MezunIletisim.objects.create(
        profil=profil,
        tur=tur,
        tarih=tarih,
        aciklama=aciklama,
        kaydeden=user,
    )
    profil.son_gorusme_tarihi = tarih
    profil.iletisim_durumu = MezunProfil.IletisimDurumu.ILETISIMDE
    profil.kurum_bagi = MezunProfil.KurumBagi.DUZENLI
    profil.save(update_fields=["son_gorusme_tarihi", "iletisim_durumu", "kurum_bagi", "guncellenme"])

    if tur == MezunIletisim.Tur.BULUSMA:
        _yolculuk_ekle(
            profil,
            yil=tarih.year,
            baslik="Mezun Buluşmasına Katıldı",
            tur=MezunYolculukOlay.Tur.ETKINLIK,
            tarih=tarih,
            otomatik=True,
        )
    return kayit


@transaction.atomic
def basari_ekle(
    profil: MezunProfil,
    *,
    baslik: str,
    kategori: str,
    tarih: date,
    aciklama: str,
    kurum_yarisma: str,
    arsivde_goster: bool,
    user: User | None,
) -> MezunBasari:
    return MezunBasari.objects.create(
        profil=profil,
        baslik=baslik,
        kategori=kategori,
        tarih=tarih,
        aciklama=aciklama,
        kurum_yarisma=kurum_yarisma,
        arsivde_goster=arsivde_goster,
        kaydeden=user,
    )


def akademik_arsiv_ozeti(talebe: Talebe) -> list[dict[str, str]]:
    from takip.models import KttSonucu

    ktt = KttSonucu.objects.filter(talebe=talebe).count()
    deneme = 0
    try:
        from takip.models import DenemeSonucu

        deneme = DenemeSonucu.objects.filter(talebe=talebe).count()
    except Exception:
        pass

    gorusme = 0
    try:
        from takip.rehberlik_models import OgrenciGorusmesi

        gorusme = OgrenciGorusmesi.objects.filter(talebe=talebe).count()
    except Exception:
        pass

    return [
        {"etiket": "KTT Sonuçları", "deger": str(ktt), "ikon": "📋"},
        {"etiket": "Deneme Performansları", "deger": str(deneme), "ikon": "📊"},
        {"etiket": "Rehberlik Görüşmeleri", "deger": str(gorusme), "ikon": "💬"},
        {"etiket": "Gelişim Dosyası", "deger": "Arşiv", "ikon": "📁"},
    ]


def istatistik_merkezi(qs: QuerySet[MezunProfil]) -> dict[str, Any]:
    yil_grafik = mezun_yil_ozetleri(qs)
    lise_dagilim = list(
        qs.exclude(yerlestigi_lise="")
        .values("yerlestigi_lise")
        .annotate(adet=Count("id"))
        .order_by("-adet")[:8]
    )
    uni_dagilim = list(
        qs.exclude(universite="")
        .values("universite")
        .annotate(adet=Count("id"))
        .order_by("-adet")[:8]
    )
    bolum_dagilim = list(
        qs.exclude(bolum="")
        .values("bolum")
        .annotate(adet=Count("id"))
        .order_by("-adet")[:8]
    )
    ozet = dashboard_ozet(qs)
    katilim = MezunEtkinlikKatilim.objects.filter(
        profil__in=qs,
        durum=MezunEtkinlikKatilim.Durum.KATILDI,
    ).count()
    davet = MezunEtkinlikKatilim.objects.filter(profil__in=qs).count()
    katilim_orani = int(round(100 * katilim / davet)) if davet else 0
    return {
        "ozet": ozet,
        "yil_grafik": yil_grafik,
        "lise_dagilim": lise_dagilim,
        "uni_dagilim": uni_dagilim,
        "bolum_dagilim": bolum_dagilim,
        "katilim_orani": katilim_orani,
    }


def gorev_olustur(
    *,
    baslik: str,
    aciklama: str,
    sorumlu: User,
    son_tarih: date,
    talep_edilen_alanlar: list[str],
    mezuniyet_yili: int | None,
    olusturan: User | None,
    qs: QuerySet[MezunProfil],
) -> MezunGuncellemeGorevi:
    gorev = MezunGuncellemeGorevi.objects.create(
        baslik=baslik,
        aciklama=aciklama,
        sorumlu=sorumlu,
        son_tarih=son_tarih,
        talep_edilen_alanlar=talep_edilen_alanlar,
        mezuniyet_yili=mezuniyet_yili,
        olusturan=olusturan,
    )
    hedef = qs
    if mezuniyet_yili:
        hedef = hedef.filter(mezuniyet_yili=mezuniyet_yili)
    for profil in hedef:
        MezunGuncellemeGorevKayit.objects.get_or_create(gorev=gorev, profil=profil)
    return gorev


def kullanici_gorevleri(user: User) -> QuerySet[MezunGuncellemeGorevi]:
    if mezun_yonetebilir(user):
        return MezunGuncellemeGorevi.objects.all()
    return MezunGuncellemeGorevi.objects.filter(sorumlu=user)


ALAN_ETIKETLERI = {
    "iletisim_telefon": "Telefon",
    "iletisim_eposta": "E-posta",
    "yerlestigi_lise": "Lise",
    "universite": "Üniversite",
    "bolum": "Bölüm",
    "meslek": "Meslek",
    "calistigi_kurum": "Çalıştığı Kurum",
}
