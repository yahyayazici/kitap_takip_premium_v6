"""Haftalık etüt planı — saat yönetimi (admin) ve faaliyet planlama (hoca)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils.timezone import localdate, make_aware, now

from takip.dershane_program_models import DershaneDersAtamasi, DershaneSaatBloku
from takip.dershane_program_service import GUN_ADLARI, aktif_program
from takip.models import (
    EtutFaaliyetHavuzu,
    EtutGrupSaatBloku,
    EtutHaftaPlani,
    EtutHocasi,
    EtutPlanFaaliyet,
)
from takip.permissions.scope import tum_talebe_kapsami_var
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user

DURUM_IKONLARI = {
    EtutPlanFaaliyet.UygulamaDurumu.BEKLIYOR: "⏺",
    EtutPlanFaaliyet.UygulamaDurumu.DEVAM: "⏳",
    EtutPlanFaaliyet.UygulamaDurumu.TAMAMLANDI: "✅",
    EtutPlanFaaliyet.UygulamaDurumu.YAPILAMADI: "❌",
}

GUN_ETIKETLERI: tuple[str, ...] = GUN_ADLARI

VARSAYILAN_ETUT_SAATLERI: tuple[tuple[time, time], ...] = (
    (time(17, 0), time(17, 50)),
    (time(18, 0), time(18, 50)),
    (time(19, 0), time(19, 50)),
    (time(20, 0), time(20, 50)),
    (time(21, 0), time(21, 50)),
)

VARSAYILAN_ETUT_GUNLERI: tuple[int, ...] = (0, 1, 2, 3, 4, 5)

HAFTA_ICI_GUNLER: tuple[int, ...] = (0, 1, 2, 3, 4)

CUMARTESI_SAATLERI: tuple[tuple[time, time], ...] = (
    (time(9, 0), time(9, 50)),
    (time(10, 0), time(10, 50)),
    (time(11, 0), time(11, 50)),
    (time(12, 0), time(12, 50)),
    (time(13, 0), time(13, 50)),
)

PAZAR_SAATLERI: tuple[tuple[time, time], ...] = (
    (time(10, 0), time(10, 50)),
    (time(11, 0), time(11, 50)),
    (time(12, 0), time(12, 50)),
)

STANDART_SAAT_ANAHTARLARI: tuple[str, ...] = (
    "17:00",
    "18:00",
    "19:00",
    "20:00",
    "21:00",
)

HAVUZ_TOHUM: tuple[dict[str, str], ...] = (
    {"baslik": "Matematik", "renk": "#dbeafe", "varsayilan_hedef": "40 soru"},
    {"baslik": "Fen", "renk": "#dcfce7", "varsayilan_hedef": "2 test"},
    {"baslik": "Türkçe", "renk": "#ccfbf1", "varsayilan_hedef": "20 paragraf"},
    {"baslik": "Soru Çözümü", "renk": "#ede9fe", "varsayilan_hedef": "40 soru"},
    {"baslik": "Deneme Analizi", "renk": "#ffedd5", "varsayilan_hedef": "1 deneme"},
    {"baslik": "Konu Tekrarı", "renk": "#fef9c3", "varsayilan_hedef": "2 konu"},
    {"baslik": "Kitap Okuma", "renk": "#fce7f3", "varsayilan_hedef": "20 sayfa"},
    {"baslik": "Paragraf", "renk": "#e0e7ff", "varsayilan_hedef": "15 paragraf"},
    {"baslik": "Problem", "renk": "#cffafe", "varsayilan_hedef": "25 problem"},
    {"baslik": "Etüt", "renk": "#f3e8ff", "varsayilan_hedef": ""},
    {"baslik": "Eksik Tamamlama", "renk": "#fee2e2", "varsayilan_hedef": ""},
    {"baslik": "KTT", "renk": "#d1fae5", "varsayilan_hedef": "1 KTT"},
    {"baslik": "Rehberlik", "renk": "#cffafe", "varsayilan_hedef": ""},
    {"baslik": "Serbest Çalışma", "renk": "#f1f5f9", "varsayilan_hedef": ""},
)


def hafta_araligi(referans: date | None = None) -> tuple[date, date]:
    referans = referans or localdate()
    baslangic = referans - timedelta(days=referans.weekday())
    bitis = baslangic + timedelta(days=6)
    return baslangic, bitis


def saat_yonetebilir(user: User) -> bool:
    return user.is_superuser or tum_talebe_kapsami_var(user)


def yetkili_etut_planlari(user: User) -> QuerySet[EtutHaftaPlani]:
    if not can(user, "etut_plani", "view"):
        return EtutHaftaPlani.objects.none()

    qs = EtutHaftaPlani.objects.select_related(
        "etut_hocasi", "olusturan"
    ).prefetch_related("faaliyetler")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    hoca = etut_hocasi_for_user(user)
    if hoca:
        return qs.filter(etut_hocasi=hoca)
    return EtutHaftaPlani.objects.none()


def plan_duzenleyebilir(user: User, plan: EtutHaftaPlani) -> bool:
    if not can(user, "etut_plani", "edit"):
        return False
    return yetkili_etut_planlari(user).filter(pk=plan.pk).exists()


def plan_olusturabilir(user: User, hoca: EtutHocasi | None = None) -> bool:
    if not can(user, "etut_plani", "create"):
        return False
    if user.is_superuser or tum_talebe_kapsami_var(user):
        return True
    eh = etut_hocasi_for_user(user)
    if not eh:
        return False
    return hoca is None or hoca.pk == eh.pk


def mevcut_hafta_plani(user: User, hoca: EtutHocasi | None = None) -> EtutHaftaPlani | None:
    baslangic, _ = hafta_araligi()
    qs = yetkili_etut_planlari(user).filter(hafta_baslangic=baslangic)
    if hoca:
        qs = qs.filter(etut_hocasi=hoca)
    return qs.exclude(durum=EtutHaftaPlani.Durum.TAMAMLANDI).first()


def plan_olustur(
    user: User,
    hoca: EtutHocasi,
    referans: date | None = None,
) -> EtutHaftaPlani:
    baslangic, bitis = hafta_araligi(referans)
    plan, created = EtutHaftaPlani.objects.get_or_create(
        etut_hocasi=hoca,
        hafta_baslangic=baslangic,
        defaults={
            "hafta_bitis": bitis,
            "durum": EtutHaftaPlani.Durum.AKTIF,
            "olusturan": user,
        },
    )
    if not created and plan.durum == EtutHaftaPlani.Durum.TAMAMLANDI:
        plan.durum = EtutHaftaPlani.Durum.AKTIF
        plan.hafta_bitis = bitis
        plan.save(update_fields=["durum", "hafta_bitis", "guncellenme"])
    return plan


def seed_havuz_kartlari() -> None:
    if EtutFaaliyetHavuzu.objects.filter(ozel=False).exists():
        return
    for sira, kart in enumerate(HAVUZ_TOHUM):
        EtutFaaliyetHavuzu.objects.create(
            baslik=kart["baslik"],
            varsayilan_hedef=kart.get("varsayilan_hedef", ""),
            renk=kart.get("renk", "#eff6ff"),
            sira=sira,
            ozel=False,
        )


def faaliyet_havuzu(user: User, hoca: EtutHocasi | None) -> list[EtutFaaliyetHavuzu]:
    seed_havuz_kartlari()
    qs = EtutFaaliyetHavuzu.objects.filter(aktif=True)
    if hoca:
        qs = qs.filter(Q(ozel=False) | Q(ozel=True, etut_hocasi=hoca))
    else:
        qs = qs.filter(ozel=False)
    return list(qs.order_by("sira", "baslik"))


def hocanin_saat_bloklari(hoca: EtutHocasi) -> QuerySet[EtutGrupSaatBloku]:
    return EtutGrupSaatBloku.objects.filter(
        etut_hocasi=hoca,
        aktif=True,
        durum=EtutGrupSaatBloku.Durum.AKTIF,
    ).order_by("gun", "sira", "baslangic_saati")


def hocanin_tum_saat_bloklari(hoca: EtutHocasi) -> QuerySet[EtutGrupSaatBloku]:
    return EtutGrupSaatBloku.objects.filter(
        etut_hocasi=hoca,
    ).order_by("gun", "sira", "baslangic_saati")


def kurum_saat_kaynak_hoca() -> EtutHocasi | None:
    """Kurum geneli saat şablonunun tutulduğu referans grup."""
    from takip.models import EtutHocasi

    return EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad", "pk").first()


@transaction.atomic
def kurum_saatlerini_tum_gruplara_yay(kaynak: EtutHocasi | None = None) -> int:
    """Merkez şablonu tüm aktif etüt gruplarına kopyalar."""
    from takip.models import EtutHocasi

    kaynak = kaynak or kurum_saat_kaynak_hoca()
    if not kaynak:
        return 0
    hedefler = EtutHocasi.objects.filter(aktif=True).exclude(pk=kaynak.pk)
    for hedef in hedefler:
        gruptan_gruba_saat_kopyala(kaynak, hedef)
    return hedefler.count()


def kurum_saat_islem_sonrasi(kaynak: EtutHocasi | None = None) -> int:
    """Admin saat değişikliğinden sonra otomatik senkron."""
    return kurum_saatlerini_tum_gruplara_yay(kaynak)


@transaction.atomic
def saat_bloklari_otomatik_olustur(
    hoca: EtutHocasi,
    *,
    gunler: tuple[int, ...] | None = None,
    saatler: tuple[tuple[time, time], ...] | None = None,
    temizle: bool = False,
) -> int:
    gunler = gunler or VARSAYILAN_ETUT_GUNLERI
    saatler = saatler or VARSAYILAN_ETUT_SAATLERI
    if temizle:
        EtutGrupSaatBloku.objects.filter(etut_hocasi=hoca).delete()

    olusturulan = 0
    for gun in gunler:
        for sira, (bas, bit) in enumerate(saatler):
            _, created = EtutGrupSaatBloku.objects.get_or_create(
                etut_hocasi=hoca,
                gun=gun,
                baslangic_saati=bas,
                defaults={
                    "bitis_saati": bit,
                    "sira": sira,
                    "aktif": True,
                    "durum": EtutGrupSaatBloku.Durum.AKTIF,
                },
            )
            if created:
                olusturulan += 1
    return olusturulan


def _saat_satirlari(bloklar: list[EtutGrupSaatBloku]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for blok in bloklar:
        key = blok.baslangic_saati.strftime("%H:%M")
        if key not in seen:
            seen[key] = {
                "anahtar": key,
                "baslangic": blok.baslangic_saati.strftime("%H:%M"),
                "bitis": blok.bitis_saati.strftime("%H:%M"),
                "goster": blok.saat_goster,
            }
    return sorted(seen.values(), key=lambda x: x["baslangic"])


def plan_grid_verisi(plan: EtutHaftaPlani, hoca: EtutHocasi) -> dict[str, Any]:
    bloklar = list(hocanin_saat_bloklari(hoca))
    faaliyetler = {
        f.saat_bloku_id: f
        for f in plan.faaliyetler.select_related("havuz", "saat_bloku").filter(
            saat_bloku__isnull=False
        )
    }
    satirlar_raw = _saat_satirlari(bloklar)
    gun_hucre_map: dict[int, dict[str, dict[str, Any]]] = {}
    for gun, label in EtutPlanFaaliyet.Gun.choices:
        gun_bloklari = [b for b in bloklar if b.gun == gun]
        if not gun_bloklari:
            continue
        gun_hucre_map[gun] = {}
        for satir in satirlar_raw:
            blok = next(
                (
                    b
                    for b in gun_bloklari
                    if b.baslangic_saati.strftime("%H:%M") == satir["baslangic"]
                ),
                None,
            )
            faaliyet = faaliyetler.get(blok.pk) if blok else None
            gun_hucre_map[gun][satir["baslangic"]] = {
                "blok": blok,
                "blok_id": blok.pk if blok else None,
                "faaliyet": faaliyet,
                "bos": faaliyet is None,
                "saat": satir["goster"],
            }

    gunler = []
    for gun, label in EtutPlanFaaliyet.Gun.choices:
        if gun not in gun_hucre_map:
            continue
        gunler.append({"gun": gun, "label": label})

    satirlar = []
    for satir in satirlar_raw:
        hucreler = []
        for gun_item in gunler:
            hucreler.append(gun_hucre_map[gun_item["gun"]][satir["baslangic"]])
        satirlar.append({"saat": satir, "hucreler": hucreler})

    return {
        "satirlar": satirlar,
        "gunler": gunler,
        "toplam_saat": len(bloklar),
    }


def _faaliyet_turu_baslik(baslik: str) -> str:
    lower = baslik.lower()
    mapping = {
        "ktt": EtutPlanFaaliyet.FaaliyetTuru.KTT,
        "deneme": EtutPlanFaaliyet.FaaliyetTuru.DENEME_ANALIZ,
        "kitap": EtutPlanFaaliyet.FaaliyetTuru.KITAP_OKUMA,
        "konu": EtutPlanFaaliyet.FaaliyetTuru.KONU_TEKRAR,
        "soru": EtutPlanFaaliyet.FaaliyetTuru.SORU_COZUM,
        "paragraf": EtutPlanFaaliyet.FaaliyetTuru.SORU_COZUM,
        "rehberlik": EtutPlanFaaliyet.FaaliyetTuru.AKADEMIK,
    }
    for anahtar, tur in mapping.items():
        if anahtar in lower:
            return tur
    return EtutPlanFaaliyet.FaaliyetTuru.ETUT


@transaction.atomic
def faaliyet_ata(
    plan: EtutHaftaPlani,
    *,
    saat_bloku_id: int,
    havuz_id: int | None = None,
    baslik: str = "",
    aciklama: str = "",
    hedef: str = "",
    renk: str = "",
) -> EtutPlanFaaliyet:
    blok = EtutGrupSaatBloku.objects.get(
        pk=saat_bloku_id, etut_hocasi=plan.etut_hocasi, aktif=True
    )
    havuz = None
    if havuz_id:
        havuz = EtutFaaliyetHavuzu.objects.filter(pk=havuz_id, aktif=True).first()

    if havuz:
        baslik = baslik or havuz.baslik
        aciklama = aciklama or havuz.aciklama
        hedef = hedef or havuz.varsayilan_hedef
        renk = renk or havuz.renk

    if not baslik.strip():
        raise ValueError("Faaliyet başlığı gerekli.")

    faaliyet, _ = EtutPlanFaaliyet.objects.update_or_create(
        plan=plan,
        saat_bloku=blok,
        defaults={
            "gun": blok.gun,
            "sira": blok.sira,
            "havuz": havuz,
            "baslik": baslik.strip(),
            "aciklama": aciklama.strip(),
            "hedef": hedef.strip(),
            "renk": renk or "#eff6ff",
            "faaliyet_turu": _faaliyet_turu_baslik(baslik),
            "uygulama_durumu": EtutPlanFaaliyet.UygulamaDurumu.BEKLIYOR,
        },
    )
    return faaliyet


def faaliyet_sil(plan: EtutHaftaPlani, faaliyet_id: int) -> bool:
    deleted, _ = plan.faaliyetler.filter(pk=faaliyet_id).delete()
    return deleted > 0


def faaliyet_durum_guncelle(
    plan: EtutHaftaPlani,
    faaliyet_id: int,
    durum: str,
    *,
    notu: str = "",
) -> EtutPlanFaaliyet | None:
    if durum not in EtutPlanFaaliyet.UygulamaDurumu.values:
        return None
    faaliyet = plan.faaliyetler.filter(pk=faaliyet_id).first()
    if not faaliyet:
        return None
    faaliyet.uygulama_durumu = durum
    if notu:
        faaliyet.tamamlanma_notu = notu
    faaliyet.save(update_fields=["uygulama_durumu", "tamamlanma_notu", "guncellenme"])
    return faaliyet


def ozel_havuz_karti_olustur(
    user: User,
    hoca: EtutHocasi,
    *,
    baslik: str,
    aciklama: str = "",
    hedef: str = "",
    renk: str = "#eff6ff",
) -> EtutFaaliyetHavuzu:
    return EtutFaaliyetHavuzu.objects.create(
        baslik=baslik.strip(),
        aciklama=aciklama.strip(),
        varsayilan_hedef=hedef.strip(),
        renk=renk or "#eff6ff",
        ozel=True,
        etut_hocasi=hoca,
        olusturan=user,
        sira=900 + EtutFaaliyetHavuzu.objects.filter(ozel=True, etut_hocasi=hoca).count(),
    )


@transaction.atomic
def gecen_haftayi_kopyala(plan: EtutHaftaPlani) -> int:
    onceki_baslangic = plan.hafta_baslangic - timedelta(days=7)
    onceki = (
        EtutHaftaPlani.objects.filter(
            etut_hocasi=plan.etut_hocasi,
            hafta_baslangic=onceki_baslangic,
        )
        .prefetch_related("faaliyetler")
        .first()
    )
    if not onceki:
        return 0

    plan.faaliyetler.all().delete()
    kopya = 0
    for faaliyet in onceki.faaliyetler.filter(saat_bloku__isnull=False):
        if not faaliyet.saat_bloku or not faaliyet.saat_bloku.aktif:
            continue
        EtutPlanFaaliyet.objects.create(
            plan=plan,
            saat_bloku=faaliyet.saat_bloku,
            havuz=faaliyet.havuz,
            gun=faaliyet.gun,
            sira=faaliyet.sira,
            faaliyet_turu=faaliyet.faaliyet_turu,
            baslik=faaliyet.baslik,
            aciklama=faaliyet.aciklama,
            hedef=faaliyet.hedef,
            renk=faaliyet.renk,
        )
        kopya += 1
    return kopya


def faaliyetler_gun_gruplu(plan: EtutHaftaPlani) -> list[dict]:
    faaliyetler = list(
        plan.faaliyetler.select_related("saat_bloku").order_by("gun", "sira", "id")
    )
    gruplar = []
    for gun, label in EtutPlanFaaliyet.Gun.choices:
        gun_faaliyetleri = [f for f in faaliyetler if f.gun == gun]
        if gun_faaliyetleri:
            gruplar.append({"gun": gun, "label": label, "faaliyetler": gun_faaliyetleri})
    return gruplar


def plan_ozet(plan: EtutHaftaPlani, hoca: EtutHocasi | None = None) -> dict:
    faaliyetler = plan.faaliyetler.all()
    toplam_saat = hocanin_saat_bloklari(hoca or plan.etut_hocasi).count() if hoca or plan.etut_hocasi else 0
    planlanan = faaliyetler.filter(saat_bloku__isnull=False).count()
    return {
        "toplam": faaliyetler.count(),
        "planlanan": planlanan,
        "bos_saat": max(toplam_saat - planlanan, 0),
        "toplam_saat": toplam_saat,
        "tamamlandi": faaliyetler.filter(
            uygulama_durumu=EtutPlanFaaliyet.UygulamaDurumu.TAMAMLANDI
        ).count(),
        "devam": faaliyetler.filter(
            uygulama_durumu=EtutPlanFaaliyet.UygulamaDurumu.DEVAM
        ).count(),
        "yapilamadi": faaliyetler.filter(
            uygulama_durumu=EtutPlanFaaliyet.UygulamaDurumu.YAPILAMADI
        ).count(),
        "bekliyor": faaliyetler.filter(
            uygulama_durumu=EtutPlanFaaliyet.UygulamaDurumu.BEKLIYOR
        ).count(),
    }


def dershane_hafta_onizleme(user: User, hoca: EtutHocasi) -> list[dict[str, Any]]:
    program = aktif_program(user)
    if not program:
        return []

    grup = program.etut_gruplari.filter(etut_hocasi=hoca).first()
    if not grup:
        return []

    gunler = []
    for gun, label in EtutPlanFaaliyet.Gun.choices:
        atamalar = (
            DershaneDersAtamasi.objects.filter(
                program=program,
                etut_grubu=grup,
                saat_bloku__gun=gun,
                saat_bloku__tur__in=[
                    DershaneSaatBloku.Tur.DERS,
                    DershaneSaatBloku.Tur.ETUT,
                    DershaneSaatBloku.Tur.REHBERLIK,
                ],
            )
            .select_related("ders", "saat_bloku")
            .order_by("saat_bloku__sira", "saat_bloku__baslangic_saati")
        )
        dersler = []
        for atama in atamalar:
            ad = atama.ders.ad if atama.ders else atama.saat_bloku.aciklama
            if ad and ad not in dersler:
                dersler.append(ad)
        if dersler:
            gunler.append({"gun": gun, "label": label, "dersler": dersler})
    return gunler


def _slot_datetime(plan: EtutHaftaPlani, faaliyet: EtutPlanFaaliyet) -> datetime | None:
    if not faaliyet.saat_bloku:
        return None
    gun_tarihi = plan.hafta_baslangic + timedelta(days=faaliyet.gun)
    dt = datetime.combine(gun_tarihi, faaliyet.saat_bloku.bitis_saati)
    return make_aware(dt)


def faaliyet_durum_tonu(plan: EtutHaftaPlani, faaliyet: EtutPlanFaaliyet) -> str:
    if faaliyet.uygulama_durumu == EtutPlanFaaliyet.UygulamaDurumu.TAMAMLANDI:
        return "tamam"
    bitis = _slot_datetime(plan, faaliyet)
    if bitis and bitis < now():
        return "gecikti"
    return "normal"


def dashboard_etut_plani(user: User) -> dict[str, Any] | None:
    hoca = etut_hocasi_for_user(user)
    if not hoca and not tum_talebe_kapsami_var(user):
        return None
    if tum_talebe_kapsami_var(user) and not hoca:
        hoca = EtutHocasi.objects.filter(aktif=True).first()
    if not hoca:
        return None

    plan = mevcut_hafta_plani(user, hoca)
    if not plan:
        return {
            "plan": None,
            "hoca": hoca,
            "gunler": [],
            "ozet": {"planlanan": 0, "tamamlandi": 0, "bekliyor": 0, "bos_saat": 0},
            "url": "etut_plan_panel",
        }

    gunler = []
    for grup in faaliyetler_gun_gruplu(plan):
        satirlar = []
        for faaliyet in grup["faaliyetler"]:
            saat = ""
            if faaliyet.saat_bloku:
                saat = faaliyet.saat_bloku.baslangic_saati.strftime("%H:%M")
            satirlar.append(
                {
                    "saat": saat,
                    "baslik": faaliyet.baslik,
                    "ton": faaliyet_durum_tonu(plan, faaliyet),
                }
            )
        gunler.append({"label": grup["label"], "satirlar": satirlar})

    ozet = plan_ozet(plan, hoca)
    return {
        "plan": plan,
        "hoca": hoca,
        "gunler": gunler,
        "ozet": ozet,
        "url": "etut_plan_panel",
    }


def builder_baglami(
    user: User,
    *,
    hoca: EtutHocasi,
    plan: EtutHaftaPlani | None = None,
) -> dict[str, Any]:
    seed_havuz_kartlari()
    if not plan:
        plan = mevcut_hafta_plani(user, hoca)
    if not plan and plan_olusturabilir(user, hoca):
        plan = plan_olustur(user, hoca)

    grid = plan_grid_verisi(plan, hoca) if plan else {"satirlar": [], "gunler": [], "toplam_saat": 0}
    baslangic, bitis = hafta_araligi()

    return {
        "plan": plan,
        "hoca": hoca,
        "grid": grid,
        "havuz": faaliyet_havuzu(user, hoca),
        "dershane_onizleme": dershane_hafta_onizleme(user, hoca),
        "ozet": plan_ozet(plan, hoca) if plan else None,
        "hafta_baslangic": baslangic,
        "hafta_bitis": bitis,
        "duzenleyebilir": bool(plan and plan_duzenleyebilir(user, plan)),
        "saat_yonetebilir": saat_yonetebilir(user),
        "gun_etiketleri": GUN_ETIKETLERI,
    }


def admin_yonetim_baglami(user: User, hoca: EtutHocasi | None = None) -> dict[str, Any]:
    from takip.models import EtutHocasi

    hocalar = list(EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad"))
    kaynak = kurum_saat_kaynak_hoca()
    hafta_grid = admin_hafta_grid_verisi(kaynak) if kaynak else None

    return {
        "hocalar": hocalar,
        "hoca": kaynak,
        "grup_sayisi": len(hocalar),
        "hafta_grid": hafta_grid,
        "standart_saatler": STANDART_SAAT_ANAHTARLARI,
        "toplam_blok": hafta_grid["stats"]["toplam"] if hafta_grid else 0,
        "havuz": list(
            EtutFaaliyetHavuzu.objects.filter(ozel=False, aktif=True).order_by("sira")
        ),
    }


def admin_hafta_grid_verisi(hoca: EtutHocasi) -> dict[str, Any]:
    bloklar = list(hocanin_tum_saat_bloklari(hoca))
    time_map: dict[str, dict[str, Any]] = {}
    for blok in bloklar:
        key = blok.baslangic_saati.strftime("%H:%M")
        if key not in time_map:
            time_map[key] = {
                "anahtar": key,
                "baslangic": key,
                "bitis": blok.bitis_saati.strftime("%H:%M"),
                "goster": blok.saat_goster,
            }

    gunler = [
        {"gun": gun, "label": label}
        for gun, label in EtutPlanFaaliyet.Gun.choices
    ]
    satirlar = []
    for key in sorted(time_map.keys()):
        hucreler = []
        for gun_item in gunler:
            gun = gun_item["gun"]
            blok = next(
                (
                    b
                    for b in bloklar
                    if b.gun == gun
                    and b.baslangic_saati.strftime("%H:%M") == key
                ),
                None,
            )
            hucreler.append(
                {
                    "gun": gun,
                    "blok": blok,
                    "bos": blok is None,
                    "durum": blok.durum if blok else "",
                }
            )
        satirlar.append({"saat": time_map[key], "hucreler": hucreler})

    stats = {
        "toplam": len(bloklar),
        "aktif": sum(
            1 for b in bloklar if b.durum == EtutGrupSaatBloku.Durum.AKTIF
        ),
        "pasif": sum(
            1 for b in bloklar if b.durum == EtutGrupSaatBloku.Durum.PASIF
        ),
        "izinli": sum(
            1 for b in bloklar if b.durum == EtutGrupSaatBloku.Durum.IZINLI
        ),
        "planlanan": 0,
    }
    return {"satirlar": satirlar, "gunler": gunler, "stats": stats}


def grup_atama_matrisi() -> list[dict[str, Any]]:
    hocalar = EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad")
    rows = []
    for hoca in hocalar:
        aktif_saatler = {
            b.baslangic_saati.strftime("%H:%M")
            for b in hocanin_saat_bloklari(hoca)
        }
        rows.append(
            {
                "hoca": hoca,
                "saat_list": [
                    {"key": saat, "aktif": saat in aktif_saatler}
                    for saat in STANDART_SAAT_ANAHTARLARI
                ],
            }
        )
    return rows


@transaction.atomic
def gunu_tum_haftaya_kopyala(
    hoca: EtutHocasi,
    kaynak_gun: int = 0,
) -> int:
    kaynak = list(
        hocanin_tum_saat_bloklari(hoca).filter(gun=kaynak_gun).order_by("sira")
    )
    if not kaynak:
        return 0

    olusturulan = 0
    for gun, _ in EtutPlanFaaliyet.Gun.choices:
        if gun == kaynak_gun:
            continue
        EtutGrupSaatBloku.objects.filter(etut_hocasi=hoca, gun=gun).delete()
        for sira, blok in enumerate(kaynak):
            EtutGrupSaatBloku.objects.create(
                etut_hocasi=hoca,
                gun=gun,
                baslangic_saati=blok.baslangic_saati,
                bitis_saati=blok.bitis_saati,
                sira=sira,
                durum=blok.durum,
                aktif=True,
            )
            olusturulan += 1
    return olusturulan


@transaction.atomic
def sablon_grup_uygula(hoca: EtutHocasi, tip: str) -> int:
    if tip == "hafta_ici":
        gunler = HAFTA_ICI_GUNLER
        saatler = VARSAYILAN_ETUT_SAATLERI
    elif tip == "cumartesi":
        gunler = (5,)
        saatler = CUMARTESI_SAATLERI
    elif tip == "pazar":
        gunler = (6,)
        saatler = PAZAR_SAATLERI
    else:
        return 0

    for gun in gunler:
        EtutGrupSaatBloku.objects.filter(etut_hocasi=hoca, gun=gun).delete()

    return saat_bloklari_otomatik_olustur(
        hoca,
        gunler=gunler,
        saatler=saatler,
        temizle=False,
    )


@transaction.atomic
def saat_satir_ekle(
    hoca: EtutHocasi,
    *,
    baslangic: time,
    bitis: time,
    gunler: tuple[int, ...] | None = None,
) -> int:
    gunler = gunler or tuple(g for g, _ in EtutPlanFaaliyet.Gun.choices)
    olusturulan = 0
    for gun in gunler:
        sira = EtutGrupSaatBloku.objects.filter(etut_hocasi=hoca, gun=gun).count()
        _, created = EtutGrupSaatBloku.objects.get_or_create(
            etut_hocasi=hoca,
            gun=gun,
            baslangic_saati=baslangic,
            defaults={
                "bitis_saati": bitis,
                "sira": sira,
                "durum": EtutGrupSaatBloku.Durum.AKTIF,
                "aktif": True,
            },
        )
        if created:
            olusturulan += 1
    return olusturulan


def saat_bloku_durum_guncelle(
    hoca: EtutHocasi,
    blok_id: int,
    durum: str,
) -> EtutGrupSaatBloku | None:
    if durum not in EtutGrupSaatBloku.Durum.values:
        return None
    blok = EtutGrupSaatBloku.objects.filter(pk=blok_id, etut_hocasi=hoca).first()
    if not blok:
        return None
    blok.durum = durum
    blok.aktif = durum == EtutGrupSaatBloku.Durum.AKTIF
    blok.save(update_fields=["durum", "aktif", "guncellenme"])
    return blok


@transaction.atomic
def gruptan_gruba_saat_kopyala(
    kaynak: EtutHocasi,
    hedef: EtutHocasi,
) -> int:
    EtutGrupSaatBloku.objects.filter(etut_hocasi=hedef).delete()
    kopya = 0
    for blok in hocanin_tum_saat_bloklari(kaynak):
        EtutGrupSaatBloku.objects.create(
            etut_hocasi=hedef,
            gun=blok.gun,
            baslangic_saati=blok.baslangic_saati,
            bitis_saati=blok.bitis_saati,
            sira=blok.sira,
            durum=blok.durum,
            aktif=blok.aktif,
        )
        kopya += 1
    return kopya


@transaction.atomic
def grup_standart_saat_toggle(
    hoca: EtutHocasi,
    saat_key: str,
    *,
    aktif: bool,
    gunler: tuple[int, ...] | None = None,
) -> int:
    try:
        bas = datetime.strptime(saat_key, "%H:%M").time()
    except ValueError:
        return 0
    bit = (datetime.combine(date.today(), bas) + timedelta(minutes=50)).time()
    gunler = gunler or HAFTA_ICI_GUNLER

    if not aktif:
        deleted, _ = EtutGrupSaatBloku.objects.filter(
            etut_hocasi=hoca,
            gun__in=gunler,
            baslangic_saati=bas,
        ).delete()
        return deleted

    olusturulan = 0
    for gun in gunler:
        _, created = EtutGrupSaatBloku.objects.get_or_create(
            etut_hocasi=hoca,
            gun=gun,
            baslangic_saati=bas,
            defaults={
                "bitis_saati": bit,
                "sira": EtutGrupSaatBloku.objects.filter(
                    etut_hocasi=hoca, gun=gun
                ).count(),
                "durum": EtutGrupSaatBloku.Durum.AKTIF,
                "aktif": True,
            },
        )
        if created:
            olusturulan += 1
    return olusturulan


@transaction.atomic
def saat_bloku_kaydet(
    hoca: EtutHocasi,
    *,
    blok_id: int | None,
    gun: int,
    baslangic: time,
    bitis: time,
    sira: int | None = None,
) -> EtutGrupSaatBloku:
    if sira is None:
        sira = (
            EtutGrupSaatBloku.objects.filter(etut_hocasi=hoca, gun=gun).count()
        )
    if blok_id:
        blok = EtutGrupSaatBloku.objects.get(pk=blok_id, etut_hocasi=hoca)
        blok.gun = gun
        blok.baslangic_saati = baslangic
        blok.bitis_saati = bitis
        blok.sira = sira
        blok.aktif = True
        blok.save()
        return blok
    return EtutGrupSaatBloku.objects.create(
        etut_hocasi=hoca,
        gun=gun,
        baslangic_saati=baslangic,
        bitis_saati=bitis,
        sira=sira,
        durum=EtutGrupSaatBloku.Durum.AKTIF,
    )


def saat_bloku_sil(hoca: EtutHocasi, blok_id: int) -> bool:
    deleted, _ = EtutGrupSaatBloku.objects.filter(
        pk=blok_id, etut_hocasi=hoca
    ).delete()
    return deleted > 0


def saat_bloklari_sirala(hoca: EtutHocasi, gun: int, blok_ids: list[int]) -> None:
    for sira, blok_id in enumerate(blok_ids):
        EtutGrupSaatBloku.objects.filter(
            pk=blok_id, etut_hocasi=hoca, gun=gun
        ).update(sira=sira)


def cakisma_kontrol(hoca: EtutHocasi) -> list[str]:
    uyarilar: list[str] = []
    bloklar = list(hocanin_saat_bloklari(hoca))
    for gun in {b.gun for b in bloklar}:
        gun_bloklari = sorted(
            [b for b in bloklar if b.gun == gun],
            key=lambda b: b.baslangic_saati,
        )
        for i, blok in enumerate(gun_bloklari[:-1]):
            sonraki = gun_bloklari[i + 1]
            if blok.bitis_saati > sonraki.baslangic_saati:
                uyarilar.append(
                    f"{blok.get_gun_display()}: {blok.saat_goster} ile "
                    f"{sonraki.saat_goster} çakışıyor."
                )
    return uyarilar
