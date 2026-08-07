"""Disiplin Kurulu — panel verisi, CRUD, filtreleme, PDF ve rapor."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.urls import reverse
from django.utils import timezone

from takip.disiplin_kurul_models import (
    DisiplinKurulAyar,
    DisiplinKurulGundem,
    DisiplinKurulKarar,
    DisiplinKurulKararNot,
    DisiplinKurulKararTakip,
    DisiplinKurulKatilimci,
    DisiplinKurulVarsayilanGundem,
    DisiplinKurulVarsayilanUye,
    DisiplinKurulu,
)
from takip.models import PersonelProfili, Talebe
from takip.permissions.scope import yetkili_talebeler
from takip.permissions.service import can
from takip.talebe_liste_raporu_service import erisilebilir_siniflar, sinif_etiketi_goster

DEFAULT_GUNDEM = (
    "Akademik değerlendirme",
    "Davranış değerlendirmesi",
    "Ders çalışma düzeni",
    "Dini ders gelişimi",
    "Rehberlik süreci",
    "Veli görüşmesi",
    "Alınacak tedbirler",
)

DURUM_SIRASI = [
    DisiplinKurulu.Durum.TASLAK,
    DisiplinKurulu.Durum.ACILDI,
    DisiplinKurulu.Durum.TOPLANTI,
    DisiplinKurulu.Durum.KARARLAR,
    DisiplinKurulu.Durum.UYGULAMA,
    DisiplinKurulu.Durum.KONTROL,
    DisiplinKurulu.Durum.SONUCLANDI,
]

DURUM_STIL = {
    DisiplinKurulu.Durum.TASLAK: {"renk": "#64748b", "bg": "#f1f5f9"},
    DisiplinKurulu.Durum.ACILDI: {"renk": "#2563eb", "bg": "#eff6ff"},
    DisiplinKurulu.Durum.TOPLANTI: {"renk": "#7c3aed", "bg": "#f5f3ff"},
    DisiplinKurulu.Durum.KARARLAR: {"renk": "#9333ea", "bg": "#faf5ff"},
    DisiplinKurulu.Durum.UYGULAMA: {"renk": "#ea580c", "bg": "#fff7ed"},
    DisiplinKurulu.Durum.KONTROL: {"renk": "#d97706", "bg": "#fffbeb"},
    DisiplinKurulu.Durum.SONUCLANDI: {"renk": "#16a34a", "bg": "#f0fdf4"},
}

KATEGORI_STIL = {
    DisiplinKurulKarar.Kategori.AKADEMIK: {"renk": "#2563eb", "bg": "#eff6ff"},
    DisiplinKurulKarar.Kategori.DAVRANIS: {"renk": "#ea580c", "bg": "#fff7ed"},
    DisiplinKurulKarar.Kategori.DINI: {"renk": "#7c3aed", "bg": "#f5f3ff"},
    DisiplinKurulKarar.Kategori.REHBERLIK: {"renk": "#0891b2", "bg": "#ecfeff"},
    DisiplinKurulKarar.Kategori.DISIPLIN: {"renk": "#dc2626", "bg": "#fef2f2"},
    DisiplinKurulKarar.Kategori.YOKLAMA: {"renk": "#ca8a04", "bg": "#fefce8"},
    DisiplinKurulKarar.Kategori.VELI: {"renk": "#059669", "bg": "#ecfdf5"},
}


def kurul_gorebilir(user: User) -> bool:
    return can(user, "disiplin_kurulu", "view")


def kurul_duzenleyebilir(user: User) -> bool:
    return can(user, "disiplin_kurulu", "edit") or can(user, "disiplin_kurulu", "create")


def kurul_tam_yetki(user: User) -> bool:
    return kurul_duzenleyebilir(user)


def _bugun() -> date:
    return timezone.localdate()


def _ay_baslangic() -> date:
    today = _bugun()
    return today.replace(day=1)


def yeni_kurul_no() -> str:
    year = _bugun().year
    prefix = f"DK-{year}-"
    son = (
        DisiplinKurulu.objects.filter(kurul_no__startswith=prefix)
        .order_by("-kurul_no")
        .values_list("kurul_no", flat=True)
        .first()
    )
    sira = 1
    if son:
        try:
            sira = int(son.split("-")[-1]) + 1
        except ValueError:
            sira = DisiplinKurulu.objects.filter(kurul_no__startswith=prefix).count() + 1
    return f"{prefix}{sira:03d}"


def yeni_karar_no(kurul: DisiplinKurulu) -> str:
    mevcut = kurul.kararlar.count()
    return f"{kurul.kurul_no}/K{mevcut + 1:02d}"


def yetkili_kurullar(user: User) -> QuerySet[DisiplinKurulu]:
    talebe_ids = yetkili_talebeler(user).values_list("pk", flat=True)
    qs = (
        DisiplinKurulu.objects.filter(talebe_id__in=talebe_ids, arsivlandi=False)
        .select_related(
            "talebe",
            "talebe__sinif_sube",
            "talebe__etut_hocasi",
            "oturum_baskani",
            "raportor",
        )
        .prefetch_related("kararlar")
    )
    if kurul_tam_yetki(user):
        return qs
    return qs.filter(
        Q(kararlar__sorumlu=user) | Q(olusturan=user) | Q(katilimcilar__personel__user=user)
    ).distinct()


def yetkili_kararlar(user: User) -> QuerySet[DisiplinKurulKarar]:
    kurul_ids = yetkili_kurullar(user).values_list("pk", flat=True)
    qs = DisiplinKurulKarar.objects.filter(
        kurul_id__in=kurul_ids,
        arsivlandi=False,
    ).select_related("kurul", "kurul__talebe", "sorumlu")
    if kurul_tam_yetki(user):
        return qs
    return qs.filter(sorumlu=user)


def _karar_durum_guncelle(karar: DisiplinKurulKarar) -> None:
    if karar.durum == DisiplinKurulKarar.Durum.TAMAMLANDI:
        return
    if karar.gecikti_mi:
        if karar.durum != DisiplinKurulKarar.Durum.GECIKTI:
            karar.durum = DisiplinKurulKarar.Durum.GECIKTI
            karar.save(update_fields=["durum", "guncellenme"])


def kararlari_durum_kontrol_et(user: User | None = None) -> None:
    qs = DisiplinKurulKarar.objects.filter(
        arsivlandi=False,
        kontrol_tarihi__isnull=False,
    ).exclude(durum=DisiplinKurulKarar.Durum.TAMAMLANDI)
    if user:
        qs = qs.filter(kurul__in=yetkili_kurullar(user))
    for karar in qs:
        _karar_durum_guncelle(karar)


def panel_istatistikleri(user: User) -> list[dict[str, Any]]:
    kurullar = yetkili_kurullar(user)
    kararlar = yetkili_kararlar(user)
    kararlari_durum_kontrol_et(user)
    kararlar = yetkili_kararlar(user)

    aktif = kurullar.exclude(
        durum__in=[DisiplinKurulu.Durum.SONUCLANDI, DisiplinKurulu.Durum.TASLAK]
    ).count()
    bekleyen_karar = kararlar.filter(
        durum__in=[DisiplinKurulKarar.Durum.BEKLIYOR, DisiplinKurulKarar.Durum.UYGULANIYOR]
    ).count()
    kontrol_bekleyen = kararlar.filter(durum=DisiplinKurulKarar.Durum.KONTROL).count()
    bu_ay = kurullar.filter(toplanti_tarihi__gte=_ay_baslangic()).count()
    tamamlanan = kurullar.filter(durum=DisiplinKurulu.Durum.SONUCLANDI).count()

    return [
        {"anahtar": "aktif", "etiket": "Aktif Kurullar", "deger": aktif, "ikon": "layers", "trend": "+2"},
        {"anahtar": "bekleyen", "etiket": "Bekleyen Kararlar", "deger": bekleyen_karar, "ikon": "clipboard", "trend": "—"},
        {"anahtar": "kontrol", "etiket": "Kontrol Bekleyen", "deger": kontrol_bekleyen, "ikon": "eye", "trend": "—"},
        {"anahtar": "bu_ay", "etiket": "Bu Ay Yapılan Kurullar", "deger": bu_ay, "ikon": "calendar", "trend": "+1"},
        {"anahtar": "tamamlanan", "etiket": "Tamamlanan Kurullar", "deger": tamamlanan, "ikon": "check", "trend": "—"},
    ]


def kontrol_merkezi(user: User) -> dict[str, Any]:
    kararlar = yetkili_kararlar(user)
    kararlari_durum_kontrol_et(user)
    kararlar = yetkili_kararlar(user)
    bugun = _bugun()
    hafta_son = bugun + timedelta(days=7)

    bugun_kontrol = kararlar.filter(kontrol_tarihi=bugun).exclude(
        durum=DisiplinKurulKarar.Durum.TAMAMLANDI
    )
    geciken = kararlar.filter(durum=DisiplinKurulKarar.Durum.GECIKTI)
    yaklasan = kararlar.filter(
        kontrol_tarihi__gt=bugun,
        kontrol_tarihi__lte=hafta_son,
    ).exclude(durum=DisiplinKurulKarar.Durum.TAMAMLANDI)
    bu_hafta_kurullar = yetkili_kurullar(user).filter(
        toplanti_tarihi__gte=bugun,
        toplanti_tarihi__lte=hafta_son,
    )
    takip_ogrenciler = (
        Talebe.objects.filter(
            pk__in=geciken.values_list("kurul__talebe_id", flat=True).distinct()
        )
        .select_related("sinif_sube", "etut_hocasi")[:8]
    )

    return {
        "bugun_sayisi": bugun_kontrol.count(),
        "geciken_sayisi": geciken.count(),
        "yaklasan_sayisi": yaklasan.count(),
        "bu_hafta_kurul_sayisi": bu_hafta_kurullar.count(),
        "takip_ogrenci_sayisi": takip_ogrenciler.count(),
        "yaklasan_liste": [_karar_ozet(k) for k in yaklasan.order_by("kontrol_tarihi")[:6]],
        "geciken_liste": [_karar_ozet(k) for k in geciken.order_by("kontrol_tarihi")[:6]],
        "bugun_liste": [_karar_ozet(k) for k in bugun_kontrol[:6]],
    }


def _personel_ad(user: User | None) -> str:
    if not user:
        return "—"
    profil = getattr(user, "personel_profili", None)
    if profil:
        return profil.ad_soyad
    return user.get_full_name() or user.username


def _talebe_etiket(talebe: Talebe) -> str:
    if talebe.sinif_sube_id:
        return sinif_etiketi_goster(talebe.sinif_sube)
    return f"{talebe.sinif}/{talebe.sube}".strip("/") or "—"


def _kurul_kart(kurul: DisiplinKurulu) -> dict[str, Any]:
    stil = DURUM_STIL.get(kurul.durum, DURUM_STIL[DisiplinKurulu.Durum.TASLAK])
    return {
        "pk": kurul.pk,
        "kurul_no": kurul.kurul_no,
        "talebe": kurul.talebe.ad_soyad,
        "talebe_pk": kurul.talebe_id,
        "sinif": _talebe_etiket(kurul.talebe),
        "etut": kurul.talebe.etut_hocasi.ad_soyad if kurul.talebe.etut_hocasi_id else "—",
        "kurul_turu": kurul.get_kurul_turu_display(),
        "toplanti_tarihi": kurul.toplanti_tarihi.strftime("%d.%m.%Y") if kurul.toplanti_tarihi else "—",
        "baskan": _personel_ad(kurul.oturum_baskani),
        "karar_sayisi": kurul.karar_sayisi,
        "sonraki_kontrol": (
            kurul.sonraki_kontrol_tarihi.strftime("%d.%m.%Y")
            if kurul.sonraki_kontrol_tarihi
            else "—"
        ),
        "durum": kurul.durum,
        "durum_etiket": kurul.get_durum_display(),
        "durum_renk": stil["renk"],
        "durum_bg": stil["bg"],
        "detay_url": reverse("disiplin_kurul_detay", args=[kurul.pk]),
    }


def _karar_ozet(karar: DisiplinKurulKarar) -> dict[str, Any]:
    stil = KATEGORI_STIL.get(karar.kategori, KATEGORI_STIL[DisiplinKurulKarar.Kategori.DISIPLIN])
    return {
        "pk": karar.pk,
        "karar_no": karar.karar_no,
        "metin_kisa": (karar.metin[:80] + "…") if len(karar.metin) > 80 else karar.metin,
        "kategori": karar.get_kategori_display(),
        "kategori_renk": stil["renk"],
        "kontrol_tarihi": karar.kontrol_tarihi.strftime("%d.%m.%Y") if karar.kontrol_tarihi else "—",
        "durum": karar.durum,
        "durum_etiket": karar.get_durum_display(),
        "gecikti": karar.gecikti_mi,
        "uyari": karar.uyari_gerekli_mi,
        "talebe": karar.kurul.talebe.ad_soyad,
        "kurul_no": karar.kurul.kurul_no,
        "kurul_url": reverse("disiplin_kurul_detay", args=[karar.kurul_id]),
    }


def filtreli_kurullar(user: User, params: dict[str, str]) -> list[dict[str, Any]]:
    qs = yetkili_kurullar(user)
    talebe_q = (params.get("talebe") or "").strip()
    sinif_q = (params.get("sinif") or "").strip()
    etut_q = (params.get("etut") or "").strip()
    tur_q = (params.get("tur") or "").strip()
    durum_q = (params.get("durum") or "").strip()
    ara_q = (params.get("q") or "").strip()

    if talebe_q:
        qs = qs.filter(talebe_id=talebe_q)
    if sinif_q:
        qs = qs.filter(Q(talebe__sinif_sube_id=sinif_q) | Q(talebe__sinif=sinif_q))
    if etut_q:
        qs = qs.filter(talebe__etut_hocasi_id=etut_q)
    if tur_q:
        qs = qs.filter(kurul_turu=tur_q)
    if durum_q:
        qs = qs.filter(durum=durum_q)
    if ara_q:
        qs = qs.filter(
            Q(kurul_no__icontains=ara_q)
            | Q(talebe__ad_soyad__icontains=ara_q)
            | Q(genel_aciklama__icontains=ara_q)
        )

    return [_kurul_kart(k) for k in qs.order_by("-toplanti_tarihi", "-id")[:80]]


def filtre_secenekleri(user: User) -> dict[str, Any]:
    talebeler = yetkili_talebeler(user).order_by("ad_soyad")
    siniflar = erisilebilir_siniflar(talebeler)
    from takip.models import EtutHocasi

    return {
        "talebeler": talebeler,
        "siniflar": siniflar,
        "etut_hocalari": EtutHocasi.objects.order_by("ad_soyad"),
        "kurul_turleri": DisiplinKurulu.KurulTuru.choices,
        "durumlar": [d for d in DisiplinKurulu.Durum.choices if d[0] != DisiplinKurulu.Durum.TASLAK],
    }


def kurul_surec_adimlari(kurul: DisiplinKurulu) -> list[dict[str, Any]]:
    try:
        aktif_idx = DURUM_SIRASI.index(kurul.durum)
    except ValueError:
        aktif_idx = 0
    adimlar = []
    for idx, durum in enumerate(DURUM_SIRASI):
        if durum == DisiplinKurulu.Durum.TASLAK:
            continue
        label = dict(DisiplinKurulu.Durum.choices).get(durum, durum)
        if idx < aktif_idx:
            state = "done"
        elif idx == aktif_idx:
            state = "active"
        else:
            state = "pending"
        adimlar.append({"durum": durum, "etiket": label, "state": state})
    return adimlar


def karar_takip_timeline(karar: DisiplinKurulKarar) -> list[dict[str, Any]]:
    adimlar = list(karar.takip_adimlari.select_related("kullanici").order_by("olusturulma"))
    if not adimlar:
        return [
            {
                "etiket": "Karar oluşturuldu",
                "tarih": karar.olusturulma.strftime("%d.%m.%Y"),
                "state": "done",
            }
        ]
    result = []
    for idx, adim in enumerate(adimlar):
        state = "done" if idx < len(adimlar) - 1 or karar.durum == DisiplinKurulKarar.Durum.TAMAMLANDI else "active"
        result.append(
            {
                "etiket": adim.get_adim_display(),
                "aciklama": adim.aciklama,
                "tarih": adim.olusturulma.strftime("%d.%m.%Y"),
                "state": state,
            }
        )
    return result


def kurul_detay_verisi(user: User, kurul: DisiplinKurulu) -> dict[str, Any]:
    kararlari_durum_kontrol_et(user)
    talebe = kurul.talebe
    katilimcilar = []
    for k in kurul.katilimcilar.select_related("personel").order_by("sira", "id"):
        katilimcilar.append(
            {
                "ad": k.personel.ad_soyad,
                "kurum_gorevi": k.kurum_gorevi or k.personel.rol_etiketi,
                "kurul_gorevi": k.get_kurul_gorevi_display(),
                "bas_harf": k.personel.ad_soyad[:1].upper(),
            }
        )

    gundem = [
        {
            "sira": g.sira,
            "baslik": g.baslik,
            "durum": g.durum,
            "durum_etiket": g.get_durum_display(),
        }
        for g in kurul.gundem_maddeleri.order_by("sira", "id")
    ]

    kararlar_qs = kurul.kararlar.filter(arsivlandi=False).select_related("sorumlu")
    if not kurul_tam_yetki(user):
        kararlar_qs = kararlar_qs.filter(sorumlu=user)

    kararlar = []
    for karar in kararlar_qs:
        stil = KATEGORI_STIL.get(karar.kategori, KATEGORI_STIL[DisiplinKurulKarar.Kategori.DISIPLIN])
        kararlar.append(
            {
                "pk": karar.pk,
                "karar_no": karar.karar_no,
                "metin": karar.metin,
                "kategori": karar.get_kategori_display(),
                "kategori_kod": karar.kategori,
                "kategori_renk": stil["renk"],
                "kategori_bg": stil["bg"],
                "sorumlu": _personel_ad(karar.sorumlu),
                "baslangic": karar.baslangic_tarihi.strftime("%d.%m.%Y") if karar.baslangic_tarihi else "—",
                "kontrol": karar.kontrol_tarihi.strftime("%d.%m.%Y") if karar.kontrol_tarihi else "—",
                "durum": karar.durum,
                "durum_etiket": karar.get_durum_display(),
                "modul": karar.get_iliskili_modul_display(),
                "notlar": karar.notlar,
                "gecikti": karar.gecikti_mi,
                "uyari": karar.uyari_gerekli_mi,
                "timeline": karar_takip_timeline(karar),
            }
        )

    stil = DURUM_STIL.get(kurul.durum, DURUM_STIL[DisiplinKurulu.Durum.TASLAK])
    return {
        "kurul": kurul,
        "talebe": talebe,
        "sinif": _talebe_etiket(talebe),
        "etut": talebe.etut_hocasi.ad_soyad if talebe.etut_hocasi_id else "—",
        "durum_stil": stil,
        "surec": kurul_surec_adimlari(kurul),
        "katilimcilar": katilimcilar,
        "gundem": gundem,
        "kararlar": kararlar,
        "audit": {
            "olusturan": _personel_ad(kurul.olusturan),
            "son_duzenleyen": _personel_ad(kurul.son_duzenleyen),
            "olusturulma": kurul.olusturulma.strftime("%d.%m.%Y %H:%M"),
            "guncellenme": kurul.guncellenme.strftime("%d.%m.%Y %H:%M"),
        },
        "pdf_url": reverse("disiplin_kurul_pdf", args=[kurul.pk]) if kurul.tutanak_pdf else None,
        "profil_url": reverse("talebe_detay", args=[talebe.pk]),
    }


def talebe_kurul_gecmisi(talebe: Talebe) -> list[dict[str, Any]]:
    kurullar = (
        DisiplinKurulu.objects.filter(talebe=talebe, arsivlandi=False)
        .annotate(karar_adet=Count("kararlar"))
        .order_by("-toplanti_tarihi", "-id")
    )
    return [
        {
            "pk": k.pk,
            "kurul_no": k.kurul_no,
            "tur": k.get_kurul_turu_display(),
            "tarih": k.toplanti_tarihi.strftime("%d %B %Y") if k.toplanti_tarihi else "—",
            "karar_sayisi": k.karar_adet,
            "durum": k.get_durum_display(),
            "url": reverse("disiplin_kurul_detay", args=[k.pk]),
        }
        for k in kurullar
    ]


def aktif_personeller() -> QuerySet[PersonelProfili]:
    return PersonelProfili.objects.filter(aktif=True).select_related("user").order_by("ad_soyad")


def kurul_ayarlari() -> DisiplinKurulAyar:
    return DisiplinKurulAyar.aktif()


def seed_kurul_sablonlari() -> None:
    ayar = kurul_ayarlari()
    if not ayar.varsayilan_toplanti_yeri:
        ayar.varsayilan_toplanti_yeri = "Rehberlik Odası"
        ayar.save(update_fields=["varsayilan_toplanti_yeri", "guncellenme"])

    if not DisiplinKurulVarsayilanGundem.objects.exists():
        for idx, baslik in enumerate(DEFAULT_GUNDEM, start=1):
            DisiplinKurulVarsayilanGundem.objects.create(baslik=baslik, sira=idx)

    if DisiplinKurulVarsayilanUye.objects.exists():
        return

    personeller = list(aktif_personeller()[:5])
    gorevler = [
        DisiplinKurulKatilimci.KurulGorevi.BASKAN,
        DisiplinKurulKatilimci.KurulGorevi.RAPORTOR,
        DisiplinKurulKatilimci.KurulGorevi.UYE,
        DisiplinKurulKatilimci.KurulGorevi.UYE,
        DisiplinKurulKatilimci.KurulGorevi.DANISMAN,
    ]
    for idx, personel in enumerate(personeller):
        DisiplinKurulVarsayilanUye.objects.create(
            personel=personel,
            kurul_gorevi=gorevler[idx] if idx < len(gorevler) else DisiplinKurulKatilimci.KurulGorevi.UYE,
            sira=idx,
        )


def varsayilan_gundem_listesi() -> list[str]:
    seed_kurul_sablonlari()
    return list(
        DisiplinKurulVarsayilanGundem.objects.filter(aktif=True)
        .order_by("sira", "id")
        .values_list("baslik", flat=True)
    )


def varsayilan_katilimcilar() -> list[dict[str, Any]]:
    seed_kurul_sablonlari()
    return [
        {
            "personel_id": uye.personel_id,
            "kurul_gorevi": uye.kurul_gorevi,
            "kurum_gorevi": uye.personel.rol_etiketi,
            "ad_soyad": uye.personel.ad_soyad,
            "gorev_etiket": uye.get_kurul_gorevi_display(),
        }
        for uye in DisiplinKurulVarsayilanUye.objects.filter(aktif=True)
        .select_related("personel")
        .order_by("sira", "id")
    ]


def ayarlar_baglami() -> dict[str, Any]:
    seed_kurul_sablonlari()
    ayar = kurul_ayarlari()
    return {
        "ayar": ayar,
        "uyeler": list(
            DisiplinKurulVarsayilanUye.objects.select_related("personel").order_by("sira", "id")
        ),
        "gundem": list(DisiplinKurulVarsayilanGundem.objects.order_by("sira", "id")),
        "personeller": aktif_personeller(),
        "gorevler": DisiplinKurulKatilimci.KurulGorevi.choices,
        "kurul_adi": ayar.kurul_adi,
    }


@transaction.atomic
def ayar_kaydet(*, kurul_adi: str, varsayilan_yer: str) -> DisiplinKurulAyar:
    ayar = kurul_ayarlari()
    ayar.kurul_adi = kurul_adi.strip() or DisiplinKurulu.KURUL_ADI
    ayar.varsayilan_toplanti_yeri = varsayilan_yer.strip()
    ayar.save()
    return ayar


@transaction.atomic
def varsayilan_uye_kaydet(
    *,
    uye_id: int | None,
    personel_id: int,
    kurul_gorevi: str,
    sira: int | None = None,
    aktif: bool = True,
) -> DisiplinKurulVarsayilanUye:
    if sira is None:
        sira = DisiplinKurulVarsayilanUye.objects.count()
    if uye_id:
        uye = DisiplinKurulVarsayilanUye.objects.get(pk=uye_id)
        uye.personel_id = personel_id
        uye.kurul_gorevi = kurul_gorevi
        uye.sira = sira
        uye.aktif = aktif
        uye.save()
        return uye
    return DisiplinKurulVarsayilanUye.objects.create(
        personel_id=personel_id,
        kurul_gorevi=kurul_gorevi,
        sira=sira,
        aktif=aktif,
    )


def varsayilan_uye_sil(uye_id: int) -> None:
    DisiplinKurulVarsayilanUye.objects.filter(pk=uye_id).delete()


@transaction.atomic
def varsayilan_gundem_kaydet(
    *,
    madde_id: int | None,
    baslik: str,
    sira: int | None = None,
    aktif: bool = True,
) -> DisiplinKurulVarsayilanGundem:
    baslik = baslik.strip()
    if not baslik:
        raise ValueError("Gündem maddesi boş olamaz.")
    if sira is None:
        sira = DisiplinKurulVarsayilanGundem.objects.count() + 1
    if madde_id:
        madde = DisiplinKurulVarsayilanGundem.objects.get(pk=madde_id)
        madde.baslik = baslik
        madde.sira = sira
        madde.aktif = aktif
        madde.save()
        return madde
    return DisiplinKurulVarsayilanGundem.objects.create(
        baslik=baslik, sira=sira, aktif=aktif
    )


def varsayilan_gundem_sil(madde_id: int) -> None:
    DisiplinKurulVarsayilanGundem.objects.filter(pk=madde_id).delete()


@transaction.atomic
def kurul_olustur(user: User, data: dict[str, Any], *, taslak: bool = False) -> DisiplinKurulu:
    talebe = Talebe.objects.get(pk=data["talebe_id"])
    if talebe not in yetkili_talebeler(user):
        raise PermissionError("Bu talebe için kurul oluşturamazsınız.")

    ayar = kurul_ayarlari()
    kurul = DisiplinKurulu.objects.create(
        kurul_no=yeni_kurul_no(),
        talebe=talebe,
        kurul_turu=data.get(
            "kurul_turu", DisiplinKurulu.KurulTuru.ISTISARE_DISIPLIN
        ),
        durum=DisiplinKurulu.Durum.TASLAK if taslak else DisiplinKurulu.Durum.ACILDI,
        toplanti_tarihi=data.get("toplanti_tarihi"),
        toplanti_saati=data.get("toplanti_saati"),
        toplanti_yeri=data.get("toplanti_yeri") or ayar.varsayilan_toplanti_yeri,
        genel_aciklama=data.get("genel_aciklama", ""),
        sonraki_kontrol_tarihi=data.get("sonraki_kontrol_tarihi"),
        olusturan=user,
        son_duzenleyen=user,
    )

    gundem_list = data.get("gundem") or varsayilan_gundem_listesi() or list(DEFAULT_GUNDEM)
    for idx, baslik in enumerate(gundem_list, start=1):
        DisiplinKurulGundem.objects.create(kurul=kurul, sira=idx, baslik=str(baslik).strip())

    katilimcilar = data.get("katilimcilar")
    if not katilimcilar:
        katilimcilar = [
            {"personel_id": k["personel_id"], "kurul_gorevi": k["kurul_gorevi"]}
            for k in varsayilan_katilimcilar()
        ]
    for idx, kat in enumerate(katilimcilar):
        personel = PersonelProfili.objects.get(pk=kat["personel_id"])
        DisiplinKurulKatilimci.objects.create(
            kurul=kurul,
            personel=personel,
            kurum_gorevi=kat.get("kurum_gorevi") or personel.rol_etiketi,
            kurul_gorevi=kat.get("kurul_gorevi", DisiplinKurulKatilimci.KurulGorevi.UYE),
            sira=idx,
        )
        if kat.get("kurul_gorevi") == DisiplinKurulKatilimci.KurulGorevi.BASKAN:
            kurul.oturum_baskani = personel.user
        if kat.get("kurul_gorevi") == DisiplinKurulKatilimci.KurulGorevi.RAPORTOR:
            kurul.raportor = personel.user
    kurul.save()
    return kurul


@transaction.atomic
def karar_ekle(user: User, kurul: DisiplinKurulu, data: dict[str, Any]) -> DisiplinKurulKarar:
    karar = DisiplinKurulKarar.objects.create(
        karar_no=yeni_karar_no(kurul),
        kurul=kurul,
        metin=data["metin"],
        kategori=data.get("kategori", DisiplinKurulKarar.Kategori.DISIPLIN),
        sorumlu_id=data.get("sorumlu_id"),
        baslangic_tarihi=data.get("baslangic_tarihi"),
        kontrol_tarihi=data.get("kontrol_tarihi"),
        durum=data.get("durum", DisiplinKurulKarar.Durum.BEKLIYOR),
        iliskili_modul=data.get("iliskili_modul", DisiplinKurulKarar.IliskiliModul.YOK),
        iliskili_kayit_id=data.get("iliskili_kayit_id"),
        notlar=data.get("notlar", ""),
        olusturan=user,
        son_duzenleyen=user,
    )
    DisiplinKurulKararTakip.objects.create(
        karar=karar,
        adim=DisiplinKurulKararTakip.Adim.OLUSTURULDU,
        aciklama="Karar kaydı oluşturuldu.",
        kullanici=user,
    )
    if karar.sorumlu_id:
        DisiplinKurulKararTakip.objects.create(
            karar=karar,
            adim=DisiplinKurulKararTakip.Adim.PERSONEL,
            aciklama=_personel_ad(karar.sorumlu),
            kullanici=user,
        )
    kurul.son_duzenleyen = user
    kurul.save(update_fields=["son_duzenleyen", "guncellenme"])
    return karar


@transaction.atomic
def karar_durum_guncelle(user: User, karar: DisiplinKurulKarar, yeni_durum: str, not_metni: str = "") -> None:
    eski = karar.durum
    karar.durum = yeni_durum
    karar.son_duzenleyen = user
    karar.save()

    if not_metni.strip():
        DisiplinKurulKararNot.objects.create(karar=karar, yazar=user, metin=not_metni.strip())
        DisiplinKurulKararTakip.objects.create(
            karar=karar,
            adim=DisiplinKurulKararTakip.Adim.NOT,
            aciklama=not_metni.strip()[:240],
            kullanici=user,
        )

    if yeni_durum == DisiplinKurulKarar.Durum.KONTROL:
        DisiplinKurulKararTakip.objects.create(
            karar=karar,
            adim=DisiplinKurulKararTakip.Adim.KONTROL,
            aciklama=f"Durum: {eski} → {yeni_durum}",
            kullanici=user,
        )
    if yeni_durum == DisiplinKurulKarar.Durum.TAMAMLANDI:
        DisiplinKurulKararTakip.objects.create(
            karar=karar,
            adim=DisiplinKurulKararTakip.Adim.TAMAMLANDI,
            aciklama="Karar tamamlandı.",
            kullanici=user,
        )


def kurul_durum_ilerlet(user: User, kurul: DisiplinKurulu, yeni_durum: str) -> None:
    kurul.durum = yeni_durum
    kurul.son_duzenleyen = user
    kurul.save(update_fields=["durum", "son_duzenleyen", "guncellenme"])


def rapor_ozet(user: User, params: dict[str, str]) -> dict[str, Any]:
    kurullar = yetkili_kurullar(user)
    kararlar = yetkili_kararlar(user)
    if params.get("tarih_bas"):
        kurullar = kurullar.filter(toplanti_tarihi__gte=params["tarih_bas"])
        kararlar = kararlar.filter(baslangic_tarihi__gte=params["tarih_bas"])
    if params.get("tarih_bit"):
        kurullar = kurullar.filter(toplanti_tarihi__lte=params["tarih_bit"])
        kararlar = kararlar.filter(baslangic_tarihi__lte=params["tarih_bit"])
    kararlari_durum_kontrol_et(user)
    kararlar = yetkili_kararlar(user)
    return {
        "toplam_kurul": kurullar.count(),
        "toplam_karar": kararlar.count(),
        "tamamlanan": kararlar.filter(durum=DisiplinKurulKarar.Durum.TAMAMLANDI).count(),
        "bekleyen": kararlar.exclude(
            durum__in=[DisiplinKurulKarar.Durum.TAMAMLANDI, DisiplinKurulKarar.Durum.GECIKTI]
        ).count(),
        "geciken": kararlar.filter(durum=DisiplinKurulKarar.Durum.GECIKTI).count(),
        "kurullar": [_kurul_kart(k) for k in kurullar.order_by("-toplanti_tarihi")[:100]],
        "kararlar": [_karar_ozet(k) for k in kararlar.order_by("-kontrol_tarihi")[:100]],
    }


def rapor_csv(user: User, params: dict[str, str]) -> bytes:
    ozet = rapor_ozet(user, params)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Kurul No", "Talebe", "Sınıf", "Durum", "Toplantı", "Karar Sayısı"])
    for k in ozet["kurullar"]:
        writer.writerow(
            [k["kurul_no"], k["talebe"], k["sinif"], k["durum_etiket"], k["toplanti_tarihi"], k["karar_sayisi"]]
        )
    return buffer.getvalue().encode("utf-8-sig")


def pdf_baglam(user: User, kurul: DisiplinKurulu) -> dict[str, Any]:
    detay = kurul_detay_verisi(user, kurul)
    from config.branding import PANEL_ORG, PANEL_SHORT

    return {
        **detay,
        "kurum_adi": PANEL_ORG,
        "panel_adi": PANEL_SHORT,
        "bugun": _bugun().strftime("%d.%m.%Y"),
    }


def seed_demo_kurul(user: User) -> DisiplinKurulu | None:
    talebe = yetkili_talebeler(user).select_related("etut_hocasi").first()
    if not talebe:
        return None
    if DisiplinKurulu.objects.filter(kurul_no__startswith=f"DK-{_bugun().year}-").exists():
        return DisiplinKurulu.objects.filter(kurul_no__startswith=f"DK-{_bugun().year}-").first()

    personel = aktif_personeller()[:3]
    katilimcilar = []
    for idx, p in enumerate(personel):
        gorev = DisiplinKurulKatilimci.KurulGorevi.UYE
        if idx == 0:
            gorev = DisiplinKurulKatilimci.KurulGorevi.BASKAN
        elif idx == 1:
            gorev = DisiplinKurulKatilimci.KurulGorevi.RAPORTOR
        katilimcilar.append({"personel_id": p.pk, "kurul_gorevi": gorev})

    kurul = kurul_olustur(
        user,
        {
            "talebe_id": talebe.pk,
            "kurul_turu": DisiplinKurulu.KurulTuru.ISTISARE_DISIPLIN,
            "toplanti_tarihi": _bugun(),
            "toplanti_saati": timezone.localtime().time().replace(second=0, microsecond=0),
            "toplanti_yeri": "Rehberlik Odası",
            "genel_aciklama": "Demo kurul kaydı — öğrenci gelişim değerlendirmesi.",
            "sonraki_kontrol_tarihi": _bugun() + timedelta(days=14),
            "katilimcilar": katilimcilar,
        },
    )
    kurul.durum = DisiplinKurulu.Durum.UYGULAMA
    kurul.save(update_fields=["durum"])

    if personel:
        karar_ekle(
            user,
            kurul,
            {
                "metin": "Haftalık etüt programına ek çalışma saati tanımlanacaktır.",
                "kategori": DisiplinKurulKarar.Kategori.AKADEMIK,
                "sorumlu_id": personel[0].user_id,
                "baslangic_tarihi": _bugun(),
                "kontrol_tarihi": _bugun() + timedelta(days=7),
                "durum": DisiplinKurulKarar.Durum.UYGULANIYOR,
                "iliskili_modul": DisiplinKurulKarar.IliskiliModul.AKADEMIK,
            },
        )
        karar_ekle(
            user,
            kurul,
            {
                "metin": "Veli ile görüşme planlanacak ve sonuç raporlanacaktır.",
                "kategori": DisiplinKurulKarar.Kategori.VELI,
                "sorumlu_id": personel[1].user_id if len(personel) > 1 else personel[0].user_id,
                "baslangic_tarihi": _bugun(),
                "kontrol_tarihi": _bugun() + timedelta(days=3),
                "durum": DisiplinKurulKarar.Durum.KONTROL,
                "iliskili_modul": DisiplinKurulKarar.IliskiliModul.REHBERLIK,
            },
        )
    return kurul
