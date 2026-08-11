"""İmam–müezzin premium panel — havuz, dağıtım ve PDF bağlamı."""

from __future__ import annotations

import calendar
from datetime import date

from django.utils.timezone import localdate

from takip.models import ImamMuezzinAtama, ImamMuezzinHavuzKaydi, ImamMuezzinListesi, Talebe

from .imam_muezzin_service import calisma_gunleri, otomatik_dagit, talebe_havuzunu_al

AY_ADLARI = (
    "",
    "OCAK",
    "ŞUBAT",
    "MART",
    "NİSAN",
    "MAYIS",
    "HAZİRAN",
    "TEMMUZ",
    "AĞUSTOS",
    "EYLÜL",
    "EKİM",
    "KASIM",
    "ARALIK",
)

GUN_ADLARI = (
    "Pazartesi",
    "Salı",
    "Çarşamba",
    "Perşembe",
    "Cuma",
    "Cumartesi",
    "Pazar",
)


def gun_adi(tarih: date) -> str:
    return GUN_ADLARI[tarih.weekday()]


def ay_baslik(liste: ImamMuezzinListesi) -> str:
    return f"{AY_ADLARI[liste.baslangic_tarihi.month]} {liste.baslangic_tarihi.year}"


def ay_araligi(yil: int, ay: int) -> tuple[date, date]:
    son_gun = calendar.monthrange(yil, ay)[1]
    return date(yil, ay, 1), date(yil, ay, son_gun)


def havuz_listesi(liste: ImamMuezzinListesi, rol: str) -> list[dict]:
    kayitlar = (
        liste.havuz_kayitlari.filter(rol=rol)
        .select_related("talebe", "talebe__sinif_sube")
        .order_by("sira", "talebe__ad_soyad")
    )
    return [
        {
            "id": k.pk,
            "talebe_id": k.talebe_id,
            "ad_soyad": k.talebe.ad_soyad,
            "sinif": str(k.talebe.sinif_sube) if k.talebe.sinif_sube_id else "",
            "sira": k.sira,
        }
        for k in kayitlar
    ]


def ornek_havuz_yukle(liste: ImamMuezzinListesi) -> tuple[int, int]:
    """Tüm öğrenci havuzunu imam/müezzin listelerine böler."""
    havuz_temizle(liste)
    tum = talebe_havuzunu_al(liste)
    if not tum:
        return 0, 0

    orta = max(1, len(tum) // 2)
    imam_say = 0
    muezzin_say = 0
    for i, talebe in enumerate(tum[:orta]):
        ImamMuezzinHavuzKaydi.objects.create(
            liste=liste,
            talebe=talebe,
            rol=ImamMuezzinHavuzKaydi.Rol.IMAM,
            sira=i + 1,
        )
        imam_say += 1
    for i, talebe in enumerate(tum[orta:] or tum):
        ImamMuezzinHavuzKaydi.objects.create(
            liste=liste,
            talebe=talebe,
            rol=ImamMuezzinHavuzKaydi.Rol.MUEZZIN,
            sira=i + 1,
        )
        muezzin_say += 1
    return imam_say, muezzin_say


def havuzlari_hazirla(liste: ImamMuezzinListesi) -> None:
    if liste.havuz_kayitlari.exists():
        return

    tum = talebe_havuzunu_al(liste)
    if not tum:
        return

    orta = max(1, len(tum) // 2)
    for i, talebe in enumerate(tum[:orta]):
        ImamMuezzinHavuzKaydi.objects.create(
            liste=liste,
            talebe=talebe,
            rol=ImamMuezzinHavuzKaydi.Rol.IMAM,
            sira=i + 1,
        )
    for i, talebe in enumerate(tum[orta:] or tum):
        ImamMuezzinHavuzKaydi.objects.create(
            liste=liste,
            talebe=talebe,
            rol=ImamMuezzinHavuzKaydi.Rol.MUEZZIN,
            sira=i + 1,
        )


def havuz_ekle(liste: ImamMuezzinListesi, rol: str, talebe_id: int) -> bool:
    if not Talebe.objects.filter(pk=talebe_id, aktif=True).exists():
        return False
    son_sira = (
        liste.havuz_kayitlari.filter(rol=rol).order_by("-sira").values_list("sira", flat=True).first()
        or 0
    )
    ImamMuezzinHavuzKaydi.objects.get_or_create(
        liste=liste,
        rol=rol,
        talebe_id=talebe_id,
        defaults={"sira": son_sira + 1},
    )
    return True


def _parse_id_list(values) -> list[int]:
    ids: list[int] = []
    for x in values or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    return sorted(set(ids))


def havuz_toplu_ekle(liste: ImamMuezzinListesi, rol: str, talebe_ids: list[int]) -> int:
    """Aynı role birden fazla talebe ekler; zaten olanları atlar."""
    if rol not in {ImamMuezzinHavuzKaydi.Rol.IMAM, ImamMuezzinHavuzKaydi.Rol.MUEZZIN}:
        return 0
    ids = _parse_id_list(talebe_ids)
    if not ids:
        return 0
    aktif_ids = set(
        Talebe.objects.filter(pk__in=ids, aktif=True).values_list("pk", flat=True)
    )
    mevcut = set(
        liste.havuz_kayitlari.filter(rol=rol, talebe_id__in=aktif_ids).values_list(
            "talebe_id", flat=True
        )
    )
    son_sira = (
        liste.havuz_kayitlari.filter(rol=rol).order_by("-sira").values_list("sira", flat=True).first()
        or 0
    )
    eklenecek = [tid for tid in ids if tid in aktif_ids and tid not in mevcut]
    kayitlar = [
        ImamMuezzinHavuzKaydi(
            liste=liste,
            rol=rol,
            talebe_id=tid,
            sira=son_sira + i,
        )
        for i, tid in enumerate(eklenecek, start=1)
    ]
    if kayitlar:
        ImamMuezzinHavuzKaydi.objects.bulk_create(kayitlar)
    return len(kayitlar)


def havuz_sil(kayit_id: int, liste: ImamMuezzinListesi) -> None:
    liste.havuz_kayitlari.filter(pk=kayit_id).delete()


def havuz_toplu_sil(liste: ImamMuezzinListesi, kayit_ids: list[int]) -> int:
    ids = _parse_id_list(kayit_ids)
    if not ids:
        return 0
    silinen, _ = liste.havuz_kayitlari.filter(pk__in=ids).delete()
    return silinen


def havuz_yeniden_dagit(liste: ImamMuezzinListesi) -> int:
    """Havuz değişince günlük atamaları ve PDF önizlemesini günceller."""
    if not liste.atamalar.exists():
        return 0
    return otomatik_dagit(liste)


def havuz_temizle(liste: ImamMuezzinListesi, rol: str | None = None) -> None:
    qs = liste.havuz_kayitlari.all()
    if rol:
        qs = qs.filter(rol=rol)
    qs.delete()


def atamalari_temizle(liste: ImamMuezzinListesi) -> None:
    liste.atamalar.all().delete()


def gecen_ayi_kopyala(liste: ImamMuezzinListesi) -> bool:
    onceki = (
        ImamMuezzinListesi.objects.filter(bitis_tarihi__lt=liste.baslangic_tarihi)
        .order_by("-bitis_tarihi")
        .first()
    )
    if not onceki or not onceki.havuz_kayitlari.exists():
        return False

    havuz_temizle(liste)
    for kayit in onceki.havuz_kayitlari.select_related("talebe"):
        ImamMuezzinHavuzKaydi.objects.create(
            liste=liste,
            talebe=kayit.talebe,
            rol=kayit.rol,
            sira=kayit.sira,
        )
    return True


def liste_olustur(liste: ImamMuezzinListesi, *, ornek_yenile: bool = False) -> int:
    if ornek_yenile or not liste.havuz_kayitlari.exists():
        ornek_havuz_yukle(liste)
    else:
        havuzlari_hazirla(liste)
    return otomatik_dagit(liste)


def atama_satirlari(liste: ImamMuezzinListesi) -> list[dict]:
    return [
        {
            "tarih": a.tarih,
            "tarih_goster": a.tarih.strftime("%d.%m.%Y"),
            "gun": gun_adi(a.tarih),
            "imam": a.imam.ad_soyad if a.imam_id else "—",
            "muezzin": a.muezzin.ad_soyad if a.muezzin_id else "—",
        }
        for a in liste.atamalar.select_related("imam", "muezzin").order_by("tarih")
    ]


def gorev_paneli(liste: ImamMuezzinListesi, *, yil: int | None = None, ay: int | None = None) -> dict:
    bugun = localdate()
    yil = yil or liste.baslangic_tarihi.year
    ay = ay or liste.baslangic_tarihi.month
    baslangic, bitis = ay_araligi(yil, ay)

    mevcut_talebeler = {t.pk for t in talebe_havuzunu_al(liste)}
    secilebilir = Talebe.objects.filter(pk__in=mevcut_talebeler, aktif=True).order_by("ad_soyad")

    havuzlari_hazirla(liste)
    imam_havuzu = havuz_listesi(liste, ImamMuezzinHavuzKaydi.Rol.IMAM)
    muezzin_havuzu = havuz_listesi(liste, ImamMuezzinHavuzKaydi.Rol.MUEZZIN)
    imam_ids = {k["talebe_id"] for k in imam_havuzu}
    muezzin_ids = {k["talebe_id"] for k in muezzin_havuzu}

    return {
        "liste": liste,
        "yil": yil,
        "ay": ay,
        "baslangic": baslangic,
        "bitis": bitis,
        "ay_baslik": f"{AY_ADLARI[ay]} {yil}",
        "imam_havuzu": imam_havuzu,
        "muezzin_havuzu": muezzin_havuzu,
        "talebeler": secilebilir,
        "imam_eklenebilir": secilebilir.exclude(pk__in=imam_ids),
        "muezzin_eklenebilir": secilebilir.exclude(pk__in=muezzin_ids),
        "atamalar": atama_satirlari(liste),
        "gun_sayisi": len(calisma_gunleri(liste)),
    }


from config.branding import panel_branding_context


def pdf_baglami(liste: ImamMuezzinListesi) -> dict:
    return {
        "liste": liste,
        "atamalar": liste.atamalar.select_related("imam", "muezzin").order_by("tarih"),
        "atama_satirlari": atama_satirlari(liste),
        **panel_branding_context(),
        "ay_baslik": ay_baslik(liste),
        "gun_adi": gun_adi,
    }
