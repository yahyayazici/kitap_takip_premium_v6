"""Dershane programı — iş kuralları ve panel verisi."""

from __future__ import annotations

import csv
from datetime import date, datetime, time
from io import StringIO
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from takip.dershane_program_models import (
    DershaneDersAtamasi,
    DershaneEtutGrubu,
    DershaneGrupDersOgretmen,
    DershaneProgramGun,
    DershaneProgramSablon,
    DershaneProgramSurum,
    DershaneProgrami,
    DershaneSaatBloku,
)
from takip.models import Ders, EtutHocasi, PersonelProfili, SinifSube
from takip.ogretmen_odeme_models import OgretmenOdemeDersKaydi
from takip.permissions.service import can

GUN_ADLARI: tuple[str, ...] = (
    "Pazartesi",
    "Salı",
    "Çarşamba",
    "Perşembe",
    "Cuma",
    "Cumartesi",
    "Pazar",
)

GUN_KISA: tuple[str, ...] = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")

ADIMLAR: tuple[dict[str, str], ...] = (
    {"no": "1", "baslik": "Gün Seç", "aciklama": "Program hazırlanacak günü seç."},
    {
        "no": "2",
        "baslik": "Saat Bloklarını Oluştur",
        "aciklama": "O güne ait ders, namaz, yemek, mola vb. saatleri belirle.",
    },
    {
        "no": "3",
        "baslik": "Ders Ataması Yap",
        "aciklama": "Her ders saatine sınıf/etüt, ders ve öğretmen ata.",
    },
    {
        "no": "4",
        "baslik": "Diğer Günleri Hazırla",
        "aciklama": "Haftanın diğer günlerini aynı sistemle tamamla.",
    },
    {
        "no": "5",
        "baslik": "Görüntüle ve Çıktı Al",
        "aciklama": "Programı farklı görünümlerde incele ve çıktı al.",
    },
)

DERS_RENKLERI: dict[str, str] = {
    "matematik": "#dbeafe",
    "fen": "#dcfce7",
    "fen bilimleri": "#dcfce7",
    "türkçe": "#ccfbf1",
    "turkce": "#ccfbf1",
    "sosyal": "#ffedd5",
    "sosyal bilgiler": "#ffedd5",
    "ingilizce": "#f3e8ff",
    "din": "#fef9c3",
    "din kültürü": "#fef9c3",
    "rehberlik": "#cffafe",
    "etüt": "#ede9fe",
}

TUR_BADGE: dict[str, str] = {
    DershaneSaatBloku.Tur.DERS: "dp-badge-blue",
    DershaneSaatBloku.Tur.NAMAZ: "dp-badge-green",
    DershaneSaatBloku.Tur.YEMEK: "dp-badge-amber",
    DershaneSaatBloku.Tur.MOLA: "dp-badge-gray",
    DershaneSaatBloku.Tur.ETUT: "dp-badge-violet",
    DershaneSaatBloku.Tur.REHBERLIK: "dp-badge-teal",
}

DURUM_BADGE: dict[str, str] = {
    DershaneProgramGun.Durum.TAMAMLANDI: "dp-status-green",
    DershaneProgramGun.Durum.DUZENLENIYOR: "dp-status-amber",
    DershaneProgramGun.Durum.BOS: "dp-status-gray",
}


def dershane_program_gorebilir(user: User) -> bool:
    return can(user, "dershane_programi", "view")


def dershane_program_duzenleyebilir(user: User) -> bool:
    return can(user, "dershane_programi", "edit") or can(
        user, "dershane_programi", "create"
    )


def yetkili_programlar(user: User) -> QuerySet[DershaneProgrami]:
    if not dershane_program_gorebilir(user):
        return DershaneProgrami.objects.none()
    return DershaneProgrami.objects.filter(aktif=True).order_by(
        "-baslangic_tarihi", "-id"
    )


def aktif_program(user: User, program_id: int | None = None) -> DershaneProgrami | None:
    qs = yetkili_programlar(user)
    if program_id:
        return qs.filter(pk=program_id).first()
    return qs.first()


def _gun_kayitlari_olustur(program: DershaneProgrami) -> None:
    for gun in range(7):
        DershaneProgramGun.objects.get_or_create(
            program=program,
            gun=gun,
            defaults={"durum": DershaneProgramGun.Durum.BOS},
        )


def _varsayilan_gruplar_olustur(program: DershaneProgrami) -> None:
    if program.etut_gruplari.exists():
        return

    hocalar = list(EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad"))
    etiketler = [
        ("5", "5. Sınıf Etüt-A"),
        ("5", "5. Sınıf Etüt-B"),
        ("6", "6. Sınıf Etüt-A"),
        ("6", "6. Sınıf Etüt-B"),
        ("7", "7. Sınıf Etüt-A"),
        ("7", "7. Sınıf Etüt-B"),
        ("8", "8. Sınıf Etüt-A"),
        ("8", "8. Sınıf Etüt-B"),
    ]
    for sira, (sinif, etiket) in enumerate(etiketler):
        hoca = hocalar[sira % len(hocalar)] if hocalar else None
        DershaneEtutGrubu.objects.create(
            program=program,
            etiket=etiket,
            sinif_seviye=sinif,
            etut_hocasi=hoca,
            sira=sira,
        )


def varsayilan_program_olustur(user: User) -> DershaneProgrami:
    bugun = timezone.localdate()
    yil = bugun.year
    program, created = DershaneProgrami.objects.get_or_create(
        ad=f"{yil}–{yil + 1} Dershane Programı",
        defaults={
            "aciklama": "Haftalık dershane programı",
            "baslangic_tarihi": date(yil, 9, 1),
            "bitis_tarihi": date(yil + 1, 6, 30),
            "aktif": True,
            "olusturan": user,
        },
    )
    _gun_kayitlari_olustur(program)
    _varsayilan_gruplar_olustur(program)
    if created:
        ornek_cumartesi_verisi(program)
        surum_olustur(program, user, etiket="V1 — İlk sürüm")
    return program


def ders_renk(ders_adi: str) -> str:
    anahtar = (ders_adi or "").strip().lower()
    for key, renk in DERS_RENKLERI.items():
        if key in anahtar:
            return renk
    return "#f8fafc"


def program_veri_anlik_goruntu(program: DershaneProgrami) -> dict[str, Any]:
    saat_bloklari = []
    for blok in program.saat_bloklari.order_by("gun", "sira", "id"):
        saat_bloklari.append(
            {
                "id": blok.id,
                "gun": blok.gun,
                "baslangic_saati": blok.baslangic_saati.strftime("%H:%M:%S"),
                "bitis_saati": blok.bitis_saati.strftime("%H:%M:%S"),
                "tur": blok.tur,
                "aciklama": blok.aciklama,
                "sira": blok.sira,
            }
        )

    return {
        "program": {
            "id": program.pk,
            "ad": program.ad,
            "surum_no": program.surum_no,
        },
        "gunler": list(program.gunler.values("gun", "durum").order_by("gun")),
        "gruplar": list(
            program.etut_gruplari.values(
                "id", "etiket", "sinif_seviye", "sira", "etut_hocasi_id"
            ).order_by("sira", "id")
        ),
        "saat_bloklari": saat_bloklari,
        "atamalar": list(
            program.ders_atamalari.values(
                "id",
                "saat_bloku_id",
                "etut_grubu_id",
                "ders_id",
                "ders_adi",
                "ogretmen_id",
                "ogretmen_adi",
            )
        ),
    }


@transaction.atomic
def surum_olustur(
    program: DershaneProgrami,
    user: User,
    *,
    etiket: str | None = None,
) -> DershaneProgramSurum:
    program.surum_no += 1
    program.save(update_fields=["surum_no", "guncellenme"])
    if not etiket:
        etiket = f"V{program.surum_no} — {timezone.localdate():%d.%m.%Y}"
    return DershaneProgramSurum.objects.create(
        program=program,
        surum_no=program.surum_no,
        etiket=etiket,
        veri=program_veri_anlik_goruntu(program),
        olusturan=user,
    )


def _time_parse(deger: Any) -> time:
    if isinstance(deger, time):
        return deger
    if isinstance(deger, str):
        parcalar = deger.split(":")
        return time(int(parcalar[0]), int(parcalar[1]))
    return time(9, 0)


@transaction.atomic
def surum_geri_yukle(program: DershaneProgrami, surum: DershaneProgramSurum) -> None:
    veri = surum.veri or {}
    program.ders_atamalari.all().delete()
    program.saat_bloklari.all().delete()
    program.etut_gruplari.all().delete()
    program.gunler.all().delete()

    for gun in veri.get("gunler", []):
        DershaneProgramGun.objects.create(
            program=program,
            gun=gun["gun"],
            durum=gun.get("durum", DershaneProgramGun.Durum.BOS),
        )

    grup_map: dict[int, int] = {}
    for grup in veri.get("gruplar", []):
        yeni = DershaneEtutGrubu.objects.create(
            program=program,
            etiket=grup["etiket"],
            sinif_seviye=grup["sinif_seviye"],
            etut_hocasi_id=grup.get("etut_hocasi_id"),
            sira=grup.get("sira", 0),
        )
        grup_map[grup["id"]] = yeni.pk

    blok_map: dict[int, int] = {}
    for blok in veri.get("saat_bloklari", []):
        yeni = DershaneSaatBloku.objects.create(
            program=program,
            gun=blok["gun"],
            baslangic_saati=_time_parse(blok["baslangic_saati"]),
            bitis_saati=_time_parse(blok["bitis_saati"]),
            tur=blok.get("tur", DershaneSaatBloku.Tur.DERS),
            aciklama=blok.get("aciklama", ""),
            sira=blok.get("sira", 0),
        )
        blok_map[blok["id"]] = yeni.pk

    for atama in veri.get("atamalar", []):
        DershaneDersAtamasi.objects.create(
            program=program,
            saat_bloku_id=blok_map[atama["saat_bloku_id"]],
            etut_grubu_id=grup_map[atama["etut_grubu_id"]],
            ders_id=atama.get("ders_id"),
            ders_adi=atama.get("ders_adi", ""),
            ogretmen_id=atama.get("ogretmen_id"),
            ogretmen_adi=atama.get("ogretmen_adi", ""),
        )


def gun_durum_guncelle(program: DershaneProgrami, gun: int) -> str:
    blok_sayisi = program.saat_bloklari.filter(gun=gun).count()
    if blok_sayisi == 0:
        durum = DershaneProgramGun.Durum.BOS
    else:
        ders_bloklari = program.saat_bloklari.filter(
            gun=gun,
            tur__in=[
                DershaneSaatBloku.Tur.DERS,
                DershaneSaatBloku.Tur.ETUT,
                DershaneSaatBloku.Tur.REHBERLIK,
            ],
        )
        beklenen = ders_bloklari.count() * program.etut_gruplari.count()
        mevcut = program.ders_atamalari.filter(
            saat_bloku__gun=gun,
        ).filter(Q(ders_id__isnull=False) | ~Q(ders_adi="")).count()
        if beklenen and mevcut >= beklenen:
            durum = DershaneProgramGun.Durum.TAMAMLANDI
        else:
            durum = DershaneProgramGun.Durum.DUZENLENIYOR

    kayit, _ = DershaneProgramGun.objects.get_or_create(
        program=program,
        gun=gun,
        defaults={"durum": durum},
    )
    if kayit.durum != durum:
        kayit.durum = durum
        kayit.save(update_fields=["durum"])
    return durum


def cakisma_analizi(program: DershaneProgrami, gun: int | None = None) -> dict[str, Any]:
    atamalar = program.ders_atamalari.select_related(
        "saat_bloku", "etut_grubu", "ders", "ogretmen"
    )
    if gun is not None:
        atamalar = atamalar.filter(saat_bloku__gun=gun)

    ogretmen_cakisma = 0
    ogretmen_slot: dict[tuple[int, str, time], int] = {}

    for atama in atamalar:
        blok = atama.saat_bloku
        ogretmen = atama.gorunen_ogretmen.strip().lower()
        if not ogretmen or ogretmen == "—":
            continue
        key = (blok.gun, ogretmen, blok.baslangic_saati)
        ogretmen_slot[key] = ogretmen_slot.get(key, 0) + 1

    for sayi in ogretmen_slot.values():
        if sayi > 1:
            ogretmen_cakisma += sayi - 1

    ders_bloklari = program.saat_bloklari.filter(
        tur__in=[
            DershaneSaatBloku.Tur.DERS,
            DershaneSaatBloku.Tur.ETUT,
            DershaneSaatBloku.Tur.REHBERLIK,
        ],
    )
    if gun is not None:
        ders_bloklari = ders_bloklari.filter(gun=gun)

    grup_sayisi = program.etut_gruplari.count()
    beklenen = ders_bloklari.count() * grup_sayisi
    mevcut = program.ders_atamalari.filter(
        saat_bloku__in=ders_bloklari,
    ).filter(Q(ders_id__isnull=False) | ~Q(ders_adi="")).count()
    bos_hucre = max(beklenen - mevcut, 0)

    toplam_dakika = 0
    for blok in program.saat_bloklari.filter(tur=DershaneSaatBloku.Tur.DERS):
        bas = datetime.combine(date.min, blok.baslangic_saati)
        bit = datetime.combine(date.min, blok.bitis_saati)
        toplam_dakika += int((bit - bas).total_seconds() // 60)

    tamamlanan_gun = program.gunler.filter(
        durum=DershaneProgramGun.Durum.TAMAMLANDI
    ).count()

    return {
        "ogretmen_cakisma": ogretmen_cakisma,
        "grup_cakisma": 0,
        "bos_hucre": bos_hucre,
        "planlanan_ders": mevcut,
        "toplam_ders_saati": max(toplam_dakika // 40, 0),
        "tamamlanan_gun": tamamlanan_gun,
        "sorun_var": ogretmen_cakisma > 0 or bos_hucre > 0,
    }


def panel_baglami(
    user: User,
    *,
    program: DershaneProgrami,
    gun: int = 5,
    filtre: dict[str, str] | None = None,
) -> dict[str, Any]:
    filtre = filtre or {}
    _gun_kayitlari_olustur(program)
    _varsayilan_gruplar_olustur(program)
    gun = max(0, min(6, gun))

    gun_kayitlari = {kayit.gun: kayit for kayit in program.gunler.all()}
    gunler = []
    for index, ad in enumerate(GUN_ADLARI):
        kayit = gun_kayitlari.get(index)
        durum = kayit.durum if kayit else DershaneProgramGun.Durum.BOS
        gunler.append(
            {
                "gun": index,
                "ad": ad,
                "kisa": GUN_KISA[index],
                "durum": durum,
                "durum_etiket": dict(DershaneProgramGun.Durum.choices).get(
                    durum, durum
                ),
                "durum_sinif": DURUM_BADGE.get(durum, "dp-status-gray"),
                "secili": index == gun,
            }
        )

    saat_bloklari_qs = program.saat_bloklari.filter(gun=gun).order_by(
        "sira", "baslangic_saati", "id"
    )
    saat_bloklari = [
        {
            "id": blok.pk,
            "saat": blok.saat_goster,
            "baslangic": blok.baslangic_saati.strftime("%H:%M"),
            "bitis": blok.bitis_saati.strftime("%H:%M"),
            "tur": blok.tur,
            "tur_etiket": blok.get_tur_display(),
            "tur_sinif": TUR_BADGE.get(blok.tur, "dp-badge-gray"),
            "aciklama": blok.aciklama,
            "ders_atamasi_gerektirir": blok.ders_atamasi_gerektirir,
        }
        for blok in saat_bloklari_qs
    ]

    gruplar_qs = program.etut_gruplari.order_by("sira", "id")
    if filtre.get("sinif"):
        gruplar_qs = gruplar_qs.filter(sinif_seviye=filtre["sinif"])
    if filtre.get("etut_grubu"):
        gruplar_qs = gruplar_qs.filter(pk=int(filtre["etut_grubu"]))

    gruplar = list(gruplar_qs)
    atama_map: dict[int, dict[int, DershaneDersAtamasi]] = {}
    for atama in program.ders_atamalari.filter(
        saat_bloku__gun=gun
    ).select_related("ders", "ogretmen", "etut_grubu", "saat_bloku"):
        atama_map.setdefault(atama.saat_bloku_id, {})[atama.etut_grubu_id] = atama

    matris: list[dict[str, Any]] = []
    for blok in saat_bloklari_qs:
        satir = {
            "blok_id": blok.pk,
            "saat": blok.saat_goster,
            "tur": blok.tur,
            "tur_etiket": blok.get_tur_display(),
            "tur_sinif": TUR_BADGE.get(blok.tur, "dp-badge-gray"),
            "aciklama": blok.aciklama,
            "birlestirilmis": not blok.ders_atamasi_gerektirir,
            "hucreler": [],
        }
        if not blok.ders_atamasi_gerektirir:
            satir["birlestirilmis_metin"] = blok.aciklama.upper()
            satir["birlestirilmis_sinif"] = TUR_BADGE.get(
                blok.tur, "dp-badge-gray"
            )
            matris.append(satir)
            continue

        for grup in gruplar:
            atama = atama_map.get(blok.pk, {}).get(grup.pk)
            if atama:
                ders_adi = atama.gorunen_ders
                ogretmen = atama.gorunen_ogretmen
                bos = ders_adi in {"", "—"}
            else:
                ders_adi = ""
                ogretmen = ""
                bos = True

            if filtre.get("atanmamis") == "1" and not bos:
                continue
            if filtre.get("ders") and ders_adi.lower() != filtre["ders"].lower():
                continue
            if (
                filtre.get("ogretmen")
                and ogretmen.lower() != filtre["ogretmen"].lower()
            ):
                continue

            satir["hucreler"].append(
                {
                    "grup_id": grup.pk,
                    "grup_etiket": grup.etiket,
                    "atama_id": atama.pk if atama else None,
                    "ders": ders_adi,
                    "ogretmen": ogretmen,
                    "bos": bos,
                    "renk": ders_renk(ders_adi),
                }
            )
        if satir["hucreler"] or not filtre:
            matris.append(satir)

    ozet = cakisma_analizi(program, gun)
    gun_ozeti = []
    for index, ad in enumerate(GUN_ADLARI):
        kayit = gun_kayitlari.get(index)
        durum = kayit.durum if kayit else DershaneProgramGun.Durum.BOS
        if index == gun:
            durum_etiket = "Aktif Gün"
            durum_sinif = "dp-status-blue"
        else:
            durum_etiket = dict(DershaneProgramGun.Durum.choices).get(
                durum, durum
            )
            durum_sinif = DURUM_BADGE.get(durum, "dp-status-gray")
        gun_ozeti.append(
            {
                "gun": index,
                "ad": ad,
                "durum_etiket": durum_etiket,
                "durum_sinif": durum_sinif,
                "secili": index == gun,
            }
        )

    dersler = Ders.objects.filter(aktif=True).order_by("sira", "ad")
    ogretmenler = PersonelProfili.objects.filter(aktif=True).order_by("ad_soyad")
    siniflar = sorted(
        {
            grup.sinif_seviye
            for grup in program.etut_gruplari.all()
            if grup.sinif_seviye
        },
        key=lambda x: int(x) if x.isdigit() else x,
    )
    sinif_gruplari: dict[str, list[DershaneEtutGrubu]] = {}
    for grup in gruplar:
        sinif_gruplari.setdefault(grup.sinif_seviye, []).append(grup)
    sinif_gruplari_list = [
        {
            "sinif": sinif,
            "gruplar": gruplar_sinif,
            "colspan": len(gruplar_sinif),
        }
        for sinif, gruplar_sinif in sorted(
            sinif_gruplari.items(),
            key=lambda item: int(item[0]) if str(item[0]).isdigit() else item[0],
        )
    ]

    ders_paleti = [
        {
            "id": ders.pk,
            "ad": ders.ad,
            "renk": ders_renk(ders.ad),
            "brans": ders.brans.ad if ders.brans_id else "",
        }
        for ders in dersler
    ]

    aktif_adim = 3
    if not saat_bloklari:
        aktif_adim = 2
    if ozet["tamamlanan_gun"] >= 6:
        aktif_adim = 5

    return {
        "program": program,
        "programlar": list(yetkili_programlar(user)),
        "gun": gun,
        "gun_adi": GUN_ADLARI[gun],
        "gunler": gunler,
        "adimlar": [
            {**adim, "aktif": int(adim["no"]) == aktif_adim}
            for adim in ADIMLAR
        ],
        "saat_bloklari": saat_bloklari,
        "gruplar": gruplar,
        "matris": matris,
        "ozet": ozet,
        "gun_ozeti": gun_ozeti,
        "dersler": dersler,
        "ogretmenler": ogretmenler,
        "siniflar": siniflar,
        "sinif_gruplari_list": sinif_gruplari_list,
        "ders_paleti": ders_paleti,
        "etut_gruplari": program.etut_gruplari.order_by("sira", "id"),
        "sablonlar": DershaneProgramSablon.objects.order_by("-olusturulma")[:8],
        "surumler": program.surumler.order_by("-surum_no")[:8],
        "duzenleyebilir": dershane_program_duzenleyebilir(user),
        "filtre": filtre,
        "goruntuleme_kartlari": _goruntuleme_kartlari(),
    }


def _goruntuleme_kartlari() -> list[dict[str, str]]:
    return [
        {
            "key": "genel",
            "baslik": "Genel Program",
            "aciklama": "Tüm sınıf ve etüt gruplarını birlikte göster.",
            "ikon": "grid",
        },
        {
            "key": "sinif",
            "baslik": "Sınıf Bazlı Program",
            "aciklama": "Seçilen sınıfın haftalık programını göster.",
            "ikon": "layers",
        },
        {
            "key": "etut",
            "baslik": "Etüt Grubu Programı",
            "aciklama": "Seçilen etüt grubunun haftalık programını göster.",
            "ikon": "users",
        },
        {
            "key": "ogretmen",
            "baslik": "Öğretmen Programı",
            "aciklama": "Seçilen öğretmenin haftalık ders programını göster.",
            "ikon": "user",
        },
    ]


@transaction.atomic
def saat_bloku_kaydet(
    program: DershaneProgrami,
    *,
    gun: int,
    baslangic: time,
    bitis: time,
    tur: str,
    aciklama: str,
    blok_id: int | None = None,
) -> DershaneSaatBloku:
    if blok_id:
        blok = DershaneSaatBloku.objects.get(pk=blok_id, program=program)
        blok.baslangic_saati = baslangic
        blok.bitis_saati = bitis
        blok.tur = tur
        blok.aciklama = aciklama
        blok.save()
        gun_durum_guncelle(program, gun)
        return blok

    sira = program.saat_bloklari.filter(gun=gun).count() + 1
    blok = DershaneSaatBloku.objects.create(
        program=program,
        gun=gun,
        baslangic_saati=baslangic,
        bitis_saati=bitis,
        tur=tur,
        aciklama=aciklama,
        sira=sira,
    )
    gun_durum_guncelle(program, gun)
    return blok


def saat_bloku_sil(program: DershaneProgrami, blok_id: int) -> None:
    blok = program.saat_bloklari.filter(pk=blok_id).first()
    if not blok:
        return
    gun = blok.gun
    program.saat_bloklari.filter(pk=blok_id).delete()
    gun_durum_guncelle(program, gun)


@transaction.atomic
def saat_bloku_sirala(
    program: DershaneProgrami, gun: int, sira_listesi: list[int]
) -> None:
    for index, blok_id in enumerate(sira_listesi, start=1):
        program.saat_bloklari.filter(pk=blok_id, gun=gun).update(sira=index)


@transaction.atomic
def atama_kaydet(
    program: DershaneProgrami,
    *,
    saat_bloku_id: int,
    etut_grubu_id: int,
    ders_id: int | None = None,
    ders_adi: str = "",
    ogretmen_id: int | None = None,
    ogretmen_adi: str = "",
) -> tuple[DershaneDersAtamasi | None, str | None]:
    blok = program.saat_bloklari.get(pk=saat_bloku_id)
    grup = program.etut_gruplari.get(pk=etut_grubu_id)

    if not blok.ders_atamasi_gerektirir:
        return None, "Bu saat bloğuna ders atanamaz."

    ders_obj = None
    if ders_id:
        ders_obj = Ders.objects.filter(pk=ders_id).first()
        ders_adi = ders_obj.ad if ders_obj else ders_adi

    ogretmen_obj = None
    if ogretmen_id:
        ogretmen_obj = PersonelProfili.objects.filter(pk=ogretmen_id).first()
        ogretmen_adi = ogretmen_obj.ad_soyad if ogretmen_obj else ogretmen_adi

    if ogretmen_adi:
        cakisan = (
            program.ders_atamalari.filter(saat_bloku__gun=blok.gun)
            .exclude(etut_grubu_id=grup.pk)
            .filter(saat_bloku__baslangic_saati=blok.baslangic_saati)
        )
        if ogretmen_id:
            cakisan = cakisan.filter(ogretmen_id=ogretmen_id)
        else:
            cakisan = cakisan.filter(ogretmen_adi__iexact=ogretmen_adi)
        if cakisan.exists():
            return None, "Öğretmen aynı saatte başka grupta atanmış."

    atama, _ = DershaneDersAtamasi.objects.update_or_create(
        program=program,
        saat_bloku=blok,
        etut_grubu=grup,
        defaults={
            "ders": ders_obj,
            "ders_adi": ders_adi,
            "ogretmen": ogretmen_obj,
            "ogretmen_adi": ogretmen_adi,
        },
    )
    if ders_obj and ogretmen_obj:
        _ogretmen_tercih_kaydet(program, grup, ders_obj, ogretmen_obj)
    gun_durum_guncelle(program, blok.gun)
    return atama, None


def _ogretmen_tercih_kaydet(
    program: DershaneProgrami,
    grup: DershaneEtutGrubu,
    ders_obj: Ders | None,
    ogretmen_obj: PersonelProfili | None,
) -> None:
    if not ders_obj or not ogretmen_obj:
        return
    DershaneGrupDersOgretmen.objects.update_or_create(
        program=program,
        etut_grubu=grup,
        ders=ders_obj,
        defaults={"ogretmen": ogretmen_obj},
    )


def _sube_etiketten(grup: DershaneEtutGrubu) -> str:
    etiket = (grup.etiket or "").upper()
    for parca in ("ETÜT-A", "ETUT-A", "ETÜT A", "ETUT A", "-A", " A"):
        if parca in etiket:
            return "A"
    for parca in ("ETÜT-B", "ETUT-B", "ETÜT B", "ETUT B", "-B", " B"):
        if parca in etiket:
            return "B"
    return ""


def ogretmen_coz(
    program: DershaneProgrami,
    grup: DershaneEtutGrubu,
    ders_obj: Ders,
) -> tuple[PersonelProfili | None, str]:
    """Grup + ders için uygun öğretmeni bul (her şubenin kendi matematikçisi vb.)."""
    tercih = (
        DershaneGrupDersOgretmen.objects.filter(
            program=program,
            etut_grubu=grup,
            ders=ders_obj,
        )
        .select_related("ogretmen")
        .first()
    )
    if tercih and tercih.ogretmen_id:
        return tercih.ogretmen, tercih.ogretmen.ad_soyad

    onceki = (
        program.ders_atamalari.filter(etut_grubu=grup, ders=ders_obj)
        .exclude(ogretmen__isnull=True)
        .select_related("ogretmen")
        .first()
    )
    if onceki and onceki.ogretmen_id:
        return onceki.ogretmen, onceki.gorunen_ogretmen

    if ders_obj.brans_id and grup.sinif_seviye:
        sube = _sube_etiketten(grup)
        sinif_qs = SinifSube.objects.filter(sinif=grup.sinif_seviye, aktif=True)
        if sube:
            sinif_qs = sinif_qs.filter(sube=sube)
        for sinif_sube in sinif_qs:
            odeme = (
                OgretmenOdemeDersKaydi.objects.filter(
                    sinif_sube=sinif_sube,
                    brans=ders_obj.brans,
                )
                .select_related("gun__donem__etut_hocasi")
                .first()
            )
            if odeme and odeme.gun.donem.etut_hocasi_id:
                profil = PersonelProfili.objects.filter(
                    etut_hocasi=odeme.gun.donem.etut_hocasi,
                    aktif=True,
                ).first()
                if profil:
                    return profil, profil.ad_soyad

    if ders_obj.brans_id:
        ad_parca = ders_obj.brans.ad.split()[0].lower()
        aday = (
            PersonelProfili.objects.filter(aktif=True, ad_soyad__icontains=ad_parca[:4])
            .order_by("ad_soyad")
            .first()
        )
        if aday:
            return aday, aday.ad_soyad

    return None, ""


@transaction.atomic
def atama_surukle(
    program: DershaneProgrami,
    *,
    saat_bloku_id: int,
    ders_id: int,
    grup_ids: list[int] | None = None,
    sinif_seviye: str | None = None,
    tum_gruplar: bool = False,
) -> list[dict[str, Any]]:
    """Sürükle-bırak ile tek hücre, sınıf veya satır ataması."""
    blok = program.saat_bloklari.get(pk=saat_bloku_id)
    ders_obj = Ders.objects.get(pk=ders_id, aktif=True)

    if not blok.ders_atamasi_gerektirir:
        return [{"ok": False, "hata": "Bu saat bloğuna ders atanamaz."}]

    if sinif_seviye:
        hedef = list(program.etut_gruplari.filter(sinif_seviye=sinif_seviye).order_by("sira", "id"))
    elif tum_gruplar:
        hedef = list(program.etut_gruplari.order_by("sira", "id"))
    elif grup_ids:
        hedef = list(program.etut_gruplari.filter(pk__in=grup_ids).order_by("sira", "id"))
    else:
        return [{"ok": False, "hata": "Hedef grup seçilmedi."}]

    sonuclar: list[dict[str, Any]] = []
    for grup in hedef:
        ogretmen_obj, ogretmen_adi = ogretmen_coz(program, grup, ders_obj)
        atama, hata = atama_kaydet(
            program,
            saat_bloku_id=saat_bloku_id,
            etut_grubu_id=grup.pk,
            ders_id=ders_obj.pk,
            ders_adi=ders_obj.ad,
            ogretmen_id=ogretmen_obj.pk if ogretmen_obj else None,
            ogretmen_adi=ogretmen_adi,
        )
        if atama and ogretmen_obj:
            _ogretmen_tercih_kaydet(program, grup, ders_obj, ogretmen_obj)
        sonuclar.append(
            {
                "ok": hata is None,
                "hata": hata,
                "grup_id": grup.pk,
                "grup_etiket": grup.etiket,
                "blok_id": saat_bloku_id,
                "ders": ders_obj.ad,
                "ogretmen": ogretmen_adi or (atama.gorunen_ogretmen if atama else ""),
                "renk": ders_renk(ders_obj.ad),
            }
        )
    return sonuclar


@transaction.atomic
def gun_kopyala(
    program: DershaneProgrami,
    *,
    kaynak_gun: int,
    hedef_gun: int,
    saat_bloklari: bool = True,
    dersler: bool = True,
    ogretmenler: bool = True,
) -> None:
    if kaynak_gun == hedef_gun:
        return

    blok_map: dict[int, int] = {}
    if saat_bloklari:
        program.saat_bloklari.filter(gun=hedef_gun).delete()
        for blok in program.saat_bloklari.filter(gun=kaynak_gun).order_by(
            "sira", "id"
        ):
            yeni = DershaneSaatBloku.objects.create(
                program=program,
                gun=hedef_gun,
                baslangic_saati=blok.baslangic_saati,
                bitis_saati=blok.bitis_saati,
                tur=blok.tur,
                aciklama=blok.aciklama,
                sira=blok.sira,
            )
            blok_map[blok.pk] = yeni.pk
    else:
        for eski, yeni in zip(
            program.saat_bloklari.filter(gun=kaynak_gun).order_by("sira", "id"),
            program.saat_bloklari.filter(gun=hedef_gun).order_by("sira", "id"),
        ):
            blok_map[eski.pk] = yeni.pk

    if dersler:
        program.ders_atamalari.filter(saat_bloku__gun=hedef_gun).delete()
        for atama in program.ders_atamalari.filter(
            saat_bloku__gun=kaynak_gun
        ).select_related("saat_bloku"):
            hedef_blok_id = blok_map.get(atama.saat_bloku_id)
            if not hedef_blok_id:
                continue
            DershaneDersAtamasi.objects.create(
                program=program,
                saat_bloku_id=hedef_blok_id,
                etut_grubu=atama.etut_grubu,
                ders=atama.ders,
                ders_adi=atama.ders_adi,
                ogretmen=atama.ogretmen if ogretmenler else None,
                ogretmen_adi=atama.ogretmen_adi if ogretmenler else "",
            )

    gun_durum_guncelle(program, hedef_gun)


@transaction.atomic
def sablon_kaydet(
    program: DershaneProgrami,
    user: User,
    *,
    ad: str,
    aciklama: str = "",
) -> DershaneProgramSablon:
    return DershaneProgramSablon.objects.create(
        ad=ad,
        aciklama=aciklama,
        veri=program_veri_anlik_goruntu(program),
        olusturan=user,
    )


@transaction.atomic
def sablon_yukle(program: DershaneProgrami, sablon: DershaneProgramSablon) -> None:
    sahte = DershaneProgramSurum(
        program=program,
        surum_no=0,
        etiket=sablon.ad,
        veri=sablon.veri,
    )
    surum_geri_yukle(program, sahte)


def excel_yanit(program: DershaneProgrami, gun: int | None = None) -> tuple[str, str]:
    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        ["Gün", "Saat", "Tür", "Etüt Grubu", "Ders", "Öğretmen", "Açıklama"]
    )

    bloklar = program.saat_bloklari.order_by("gun", "sira", "baslangic_saati")
    if gun is not None:
        bloklar = bloklar.filter(gun=gun)

    for blok in bloklar:
        if not blok.ders_atamasi_gerektirir:
            writer.writerow(
                [
                    GUN_ADLARI[blok.gun],
                    blok.saat_goster,
                    blok.get_tur_display(),
                    "—",
                    blok.aciklama,
                    "—",
                    blok.aciklama,
                ]
            )
            continue

        atamalar = program.ders_atamalari.filter(saat_bloku=blok).select_related(
            "etut_grubu"
        )
        if not atamalar.exists():
            writer.writerow(
                [
                    GUN_ADLARI[blok.gun],
                    blok.saat_goster,
                    blok.get_tur_display(),
                    "—",
                    "",
                    "",
                    blok.aciklama,
                ]
            )
            continue

        for atama in atamalar:
            writer.writerow(
                [
                    GUN_ADLARI[blok.gun],
                    blok.saat_goster,
                    blok.get_tur_display(),
                    atama.etut_grubu.etiket,
                    atama.gorunen_ders,
                    atama.gorunen_ogretmen,
                    blok.aciklama,
                ]
            )

    dosya = f"dershane_program_{program.pk}.csv"
    return dosya, buffer.getvalue()


def ornek_cumartesi_verisi(program: DershaneProgrami) -> None:
    cumartesi = 5
    ornek_bloklar = [
        (time(8, 30), time(9, 10), DershaneSaatBloku.Tur.DERS, "1. Ders Saati"),
        (time(9, 20), time(10, 0), DershaneSaatBloku.Tur.DERS, "2. Ders Saati"),
        (time(10, 10), time(10, 50), DershaneSaatBloku.Tur.DERS, "3. Ders Saati"),
        (time(11, 0), time(11, 20), DershaneSaatBloku.Tur.NAMAZ, "Öğle Namazı"),
        (time(11, 20), time(12, 0), DershaneSaatBloku.Tur.DERS, "4. Ders Saati"),
        (time(12, 10), time(12, 50), DershaneSaatBloku.Tur.DERS, "5. Ders Saati"),
        (time(12, 50), time(13, 50), DershaneSaatBloku.Tur.YEMEK, "Öğle Yemeği"),
        (time(14, 0), time(14, 40), DershaneSaatBloku.Tur.DERS, "6. Ders Saati"),
        (time(14, 50), time(15, 30), DershaneSaatBloku.Tur.DERS, "7. Ders Saati"),
        (time(15, 40), time(15, 50), DershaneSaatBloku.Tur.NAMAZ, "İkindi Namazı"),
    ]
    bloklar: list[DershaneSaatBloku] = []
    for sira, (bas, bit, tur, aciklama) in enumerate(ornek_bloklar, start=1):
        bloklar.append(
            DershaneSaatBloku.objects.create(
                program=program,
                gun=cumartesi,
                baslangic_saati=bas,
                bitis_saati=bit,
                tur=tur,
                aciklama=aciklama,
                sira=sira,
            )
        )

    dersler = list(Ders.objects.filter(aktif=True).order_by("sira", "ad")[:6])
    ogretmenler = list(
        PersonelProfili.objects.filter(aktif=True).order_by("ad_soyad")[:6]
    )
    ders_adlari = (
        [d.ad for d in dersler]
        if dersler
        else [
            "Matematik",
            "Fen Bilimleri",
            "Türkçe",
            "Sosyal Bilgiler",
            "İngilizce",
            "Din Kültürü",
        ]
    )
    ogretmen_adlari = (
        [o.ad_soyad for o in ogretmenler]
        if ogretmenler
        else [f"Öğretmen {index + 1}" for index in range(len(gruplar))]
    )
    gruplar = list(program.etut_gruplari.order_by("sira", "id"))
    ders_bloklari = [b for b in bloklar if b.ders_atamasi_gerektirir]

    for grup_index, grup in enumerate(gruplar):
        varsayilan_ogretmen = ogretmen_adlari[grup_index % len(ogretmen_adlari)]
        ogretmen_obj = next(
            (o for o in ogretmenler if o.ad_soyad == varsayilan_ogretmen),
            None,
        )
        for blok_index, blok in enumerate(ders_bloklari):
            ders_adi = ders_adlari[(grup_index + blok_index) % len(ders_adlari)]
            ders_obj = next((d for d in dersler if d.ad == ders_adi), None)
            DershaneDersAtamasi.objects.create(
                program=program,
                saat_bloku=blok,
                etut_grubu=grup,
                ders=ders_obj,
                ders_adi=ders_adi,
                ogretmen=ogretmen_obj,
                ogretmen_adi=varsayilan_ogretmen,
            )

    for index in range(5):
        DershaneProgramGun.objects.update_or_create(
            program=program,
            gun=index,
            defaults={"durum": DershaneProgramGun.Durum.TAMAMLANDI},
        )
    gun_durum_guncelle(program, cumartesi)
