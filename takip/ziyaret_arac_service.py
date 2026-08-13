"""Ziyaret Araç Planlama — iş mantığı."""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count, Prefetch, Q

from takip.models import EtutHocasi, PersonelProfili, SinifSube, Talebe
from takip.etut_zimmet_service import etut_mesul_mu, etut_mesul_queryset
from takip.ziyaret_arac_models import (
    ZiyaretAracAtama,
    ZiyaretAraci,
    ZiyaretPlani,
    ZiyaretPlaniTalebe,
    ZiyaretProgramAdimi,
)


@dataclass
class KapasiteOzet:
    talebe_sayisi: int
    arac_sayisi: int
    toplam_kapasite: int
    fark: int
    yeterli: bool
    mesaj: str


@dataclass
class PlanlamaOzet:
    talebe_sayisi: int
    atanan: int
    atanmamis: int
    arac_sayisi: int
    toplam_kapasite: int
    kapasite: KapasiteOzet


@dataclass
class PlanKontrol:
    hazir: bool
    uyarilar: list[str] = field(default_factory=list)
    hatalar: list[str] = field(default_factory=list)


def plan_yonetimi_var(user) -> bool:
    from takip.permissions.scope import tum_talebe_kapsami_var
    from takip.permissions.service import can

    if user.is_superuser:
        return True
    if not can(user, "ziyaret_arac", "edit"):
        return False
    return tum_talebe_kapsami_var(user)


def etut_arac_ekleyebilir(plan: ZiyaretPlani) -> bool:
    return plan.durum in {
        ZiyaretPlani.Durum.TASLAK,
        ZiyaretPlani.Durum.ARAC_TOPLANIYOR,
        ZiyaretPlani.Durum.DAGITIM,
    }


def etut_arac_duzenleyebilir(plan: ZiyaretPlani) -> bool:
    return plan.durum in {
        ZiyaretPlani.Durum.ARAC_TOPLANIYOR,
        ZiyaretPlani.Durum.DAGITIM,
    }


def plan_queryset_yonetim():
    return ZiyaretPlani.objects.prefetch_related(
        "program_adimlari",
        Prefetch(
            "araclar",
            queryset=ZiyaretAraci.objects.select_related(
                "ekleyen", "surucu_personel"
            ).prefetch_related(
                Prefetch(
                    "atamalar",
                    queryset=ZiyaretAracAtama.objects.select_related(
                        "talebe", "talebe__sinif_sube", "etut_hocasi"
                    ).order_by("sira", "id"),
                )
            ),
        ),
        Prefetch(
            "plan_talebeleri",
            queryset=ZiyaretPlaniTalebe.objects.filter(aktif=True).select_related(
                "talebe", "talebe__sinif_sube", "sabit_arac"
            ),
        ),
    )


def arac_talebe_sayisi(arac: ZiyaretAraci) -> int:
    return arac.atamalar.filter(tur=ZiyaretAracAtama.Tur.TALEBE).count()


def arac_kalan_kapasite(arac: ZiyaretAraci) -> int:
    return max(0, arac.kapasite - arac_talebe_sayisi(arac))


def kapasite_ozeti(plan: ZiyaretPlani) -> KapasiteOzet:
    talebe_sayisi = plan.plan_talebeleri.filter(aktif=True).count()
    araclar = list(plan.araclar.all())
    arac_sayisi = len(araclar)
    toplam_kapasite = sum(arac.kapasite for arac in araclar)
    fark = toplam_kapasite - talebe_sayisi
    if talebe_sayisi == 0:
        mesaj = "Ziyaret listesine henüz talebe eklenmedi."
        yeterli = True
    elif fark >= 0:
        if fark == 0:
            mesaj = "Araç kapasitesi yeterli."
        else:
            mesaj = f"Araç kapasitesi yeterli — {fark} boş yer."
        yeterli = True
    else:
        mesaj = (
            f"Toplam araç kapasitesi yetersiz. "
            f"{abs(fark)} talebe için ek kapasite gerekiyor."
        )
        yeterli = False
    return KapasiteOzet(
        talebe_sayisi=talebe_sayisi,
        arac_sayisi=arac_sayisi,
        toplam_kapasite=toplam_kapasite,
        fark=fark,
        yeterli=yeterli,
        mesaj=mesaj,
    )


def kapasite_olustu_mesaji(ozet: KapasiteOzet) -> str:
    """Araç toplama aşamasında biriken kapasite özeti."""
    if ozet.arac_sayisi == 0:
        return "Henüz araç eklenmedi — kişilik kapasitesi oluşmadı."
    return (
        f"Toplam {ozet.arac_sayisi} araç ile "
        f"{ozet.toplam_kapasite} kişilik kapasite oluştu."
    )


def planlama_ozeti(plan: ZiyaretPlani) -> PlanlamaOzet:
    aktif_kayitlar = plan.plan_talebeleri.filter(aktif=True)
    talebe_sayisi = aktif_kayitlar.count()
    atanan_ids = set(
        ZiyaretAracAtama.objects.filter(
            arac__plan=plan,
            tur=ZiyaretAracAtama.Tur.TALEBE,
            talebe_id__isnull=False,
        ).values_list("talebe_id", flat=True)
    )
    aktif_ids = set(aktif_kayitlar.values_list("talebe_id", flat=True))
    atanan = len(atanan_ids & aktif_ids)
    kapasite = kapasite_ozeti(plan)
    return PlanlamaOzet(
        talebe_sayisi=talebe_sayisi,
        atanan=atanan,
        atanmamis=max(0, talebe_sayisi - atanan),
        arac_sayisi=kapasite.arac_sayisi,
        toplam_kapasite=kapasite.toplam_kapasite,
        kapasite=kapasite,
    )


def atanmamis_talebeler(plan: ZiyaretPlani) -> list[Talebe]:
    atanan_ids = ZiyaretAracAtama.objects.filter(
        arac__plan=plan,
        tur=ZiyaretAracAtama.Tur.TALEBE,
    ).values_list("talebe_id", flat=True)
    return list(
        Talebe.objects.filter(
            ziyaret_plan_kayitlari__plan=plan,
            ziyaret_plan_kayitlari__aktif=True,
        )
        .exclude(id__in=atanan_ids)
        .select_related("sinif_sube")
        .order_by("ad_soyad")
    )


def arac_kart_verisi(plan: ZiyaretPlani) -> list[dict]:
    kartlar = []
    for arac in plan.araclar.all():
        atamalar = list(arac.atamalar.all())
        talebeler = [
            a.talebe
            for a in atamalar
            if a.tur == ZiyaretAracAtama.Tur.TALEBE and a.talebe_id
        ]
        etut_hocalari = [
            a.etut_hocasi
            for a in atamalar
            if a.tur == ZiyaretAracAtama.Tur.ETUT_HOCASI and a.etut_hocasi_id
        ]
        dolu = len(talebeler)
        kartlar.append(
            {
                "arac": arac,
                "talebeler": talebeler,
                "etut_hocalari": etut_hocalari,
                "dolu": dolu,
                "kapasite": arac.kapasite,
                "kalan": max(0, arac.kapasite - dolu),
                "dolu_mu": dolu >= arac.kapasite,
            }
        )
    return kartlar


def talebe_sabit_mi(plan: ZiyaretPlani, talebe_id: int) -> bool:
    kayit = (
        plan.plan_talebeleri.filter(talebe_id=talebe_id, aktif=True)
        .only("sabit", "sabit_arac_id")
        .first()
    )
    return bool(kayit and kayit.sabit)


def _atama_snapshot(plan: ZiyaretPlani) -> list[dict]:
    return list(
        ZiyaretAracAtama.objects.filter(arac__plan=plan).values(
            "arac_id",
            "tur",
            "talebe_id",
            "etut_hocasi_id",
            "sira",
        )
    )


def _sabit_snapshot(plan: ZiyaretPlani) -> list[dict]:
    return list(
        plan.plan_talebeleri.filter(aktif=True).values(
            "talebe_id", "sabit", "sabit_arac_id"
        )
    )


def geri_al_kaydet(plan_id: int, session) -> None:
    plan = ZiyaretPlani.objects.get(pk=plan_id)
    stack = session.setdefault("ziyaret_geri_al", {})
    plan_stack = stack.setdefault(str(plan_id), [])
    plan_stack.append(
        {
            "atamalar": _atama_snapshot(plan),
            "sabitler": _sabit_snapshot(plan),
        }
    )
    if len(plan_stack) > 10:
        plan_stack.pop(0)


def geri_al(plan_id: int, session) -> bool:
    stack = session.get("ziyaret_geri_al", {}).get(str(plan_id), [])
    if not stack:
        return False
    snapshot = stack.pop()
    plan = ZiyaretPlani.objects.get(pk=plan_id)
    with transaction.atomic():
        ZiyaretAracAtama.objects.filter(arac__plan=plan).delete()
        for row in snapshot["atamalar"]:
            ZiyaretAracAtama.objects.create(**row)
        for row in snapshot["sabitler"]:
            ZiyaretPlaniTalebe.objects.filter(
                plan=plan, talebe_id=row["talebe_id"]
            ).update(sabit=row["sabit"], sabit_arac_id=row["sabit_arac_id"])
    return True


@transaction.atomic
def talebe_ata(
    plan: ZiyaretPlani,
    talebe_id: int,
    arac_id: int,
    *,
    override: bool = False,
) -> tuple[bool, str]:
    arac = ZiyaretAraci.objects.select_for_update().get(pk=arac_id, plan=plan)
    if not plan.plan_talebeleri.filter(talebe_id=talebe_id, aktif=True).exists():
        return False, "Talebe ziyaret listesinde değil."

    mevcut = ZiyaretAracAtama.objects.filter(
        arac__plan=plan,
        tur=ZiyaretAracAtama.Tur.TALEBE,
        talebe_id=talebe_id,
    ).first()
    if mevcut and mevcut.arac_id == arac_id:
        return True, "Zaten bu araçta."

    kalan = arac_kalan_kapasite(arac)
    if kalan <= 0 and not (mevcut and mevcut.arac_id != arac_id):
        if not override:
            return False, "Araç kapasitesi dolu."

    if mevcut:
        mevcut.delete()

    if arac_kalan_kapasite(arac) <= 0 and not override:
        return False, "Araç kapasitesi dolu."

    sira = (
        ZiyaretAracAtama.objects.filter(
            arac=arac, tur=ZiyaretAracAtama.Tur.TALEBE
        ).count()
        + 1
    )
    ZiyaretAracAtama.objects.create(
        arac=arac,
        tur=ZiyaretAracAtama.Tur.TALEBE,
        talebe_id=talebe_id,
        sira=sira,
    )
    return True, "Talebe atandı."


@transaction.atomic
def talebe_cikar(plan: ZiyaretPlani, talebe_id: int) -> None:
    ZiyaretAracAtama.objects.filter(
        arac__plan=plan,
        tur=ZiyaretAracAtama.Tur.TALEBE,
        talebe_id=talebe_id,
    ).delete()


@transaction.atomic
def etut_hocasi_ata(plan: ZiyaretPlani, etut_hocasi_id: int, arac_id: int) -> tuple[bool, str]:
    hoca = EtutHocasi.objects.filter(pk=etut_hocasi_id, aktif=True).first()
    if not hoca or not etut_mesul_mu(hoca):
        return False, "Yalnızca etüt veya sınıf mesulü araca atanabilir."

    arac = ZiyaretAraci.objects.get(pk=arac_id, plan=plan)
    baska = ZiyaretAracAtama.objects.filter(
        arac__plan=plan,
        tur=ZiyaretAracAtama.Tur.ETUT_HOCASI,
        etut_hocasi_id=etut_hocasi_id,
    ).exclude(arac=arac).first()
    if baska:
        return False, "Etüt hocası başka bir araca atanmış."

    ZiyaretAracAtama.objects.filter(
        arac=arac,
        tur=ZiyaretAracAtama.Tur.ETUT_HOCASI,
    ).delete()

    ZiyaretAracAtama.objects.create(
        arac=arac,
        tur=ZiyaretAracAtama.Tur.ETUT_HOCASI,
        etut_hocasi_id=etut_hocasi_id,
        sira=0,
    )
    return True, "Etüt hocası atandı."


@transaction.atomic
def etut_hocasi_cikar(plan: ZiyaretPlani, etut_hocasi_id: int) -> None:
    ZiyaretAracAtama.objects.filter(
        arac__plan=plan,
        tur=ZiyaretAracAtama.Tur.ETUT_HOCASI,
        etut_hocasi_id=etut_hocasi_id,
    ).delete()


@transaction.atomic
def otomatik_dagit(
    plan: ZiyaretPlani,
    *,
    yeniden: bool = False,
    seed: int | None = None,
) -> tuple[int, int]:
    """Atanmamış talebeleri karışık ve dengeli dağıt. Etüt hocalarına dokunma."""
    rng = random.Random(seed)
    araclar = list(plan.araclar.all().order_by("id"))
    if not araclar:
        return 0, 0

    if yeniden:
        sabit_talebe_ids = set(
            plan.plan_talebeleri.filter(aktif=True, sabit=True).values_list(
                "talebe_id", flat=True
            )
        )
        ZiyaretAracAtama.objects.filter(
            arac__plan=plan,
            tur=ZiyaretAracAtama.Tur.TALEBE,
        ).exclude(talebe_id__in=sabit_talebe_ids).delete()

        for kayit in plan.plan_talebeleri.filter(aktif=True, sabit=True).select_related(
            "sabit_arac"
        ):
            if kayit.sabit_arac_id:
                talebe_ata(plan, kayit.talebe_id, kayit.sabit_arac_id, override=True)

    atanmamis = atanmamis_talebeler(plan)
    if not atanmamis:
        return 0, 0

    rng.shuffle(atanmamis)
    kalan = {arac.id: arac_kalan_kapasite(arac) for arac in araclar}
    atanan = 0

    for talebe in atanmamis:
        uygun = [a for a in araclar if kalan[a.id] > 0]
        if not uygun:
            break
        uygun.sort(key=lambda a: (-kalan[a.id], rng.random()))
        secilen = uygun[0]
        ok, _ = talebe_ata(plan, talebe.id, secilen.id)
        if ok:
            kalan[secilen.id] -= 1
            atanan += 1

    return atanan, len(atanmamis_talebeler(plan))


@transaction.atomic
def talebe_listesine_ekle(plan: ZiyaretPlani, talebe_ids: list[int]) -> int:
    eklenen = 0
    for talebe_id in talebe_ids:
        kayit, created = ZiyaretPlaniTalebe.objects.get_or_create(
            plan=plan,
            talebe_id=talebe_id,
            defaults={"aktif": True},
        )
        if not created and not kayit.aktif:
            kayit.aktif = True
            kayit.save(update_fields=["aktif"])
        eklenen += 1
    return eklenen


@transaction.atomic
def talebe_listeden_cikar(plan: ZiyaretPlani, talebe_id: int) -> None:
    ZiyaretPlaniTalebe.objects.filter(plan=plan, talebe_id=talebe_id).update(aktif=False)
    talebe_cikar(plan, talebe_id)


@transaction.atomic
def talebe_sabitle(
    plan: ZiyaretPlani,
    talebe_id: int,
    *,
    sabit: bool,
    arac_id: int | None = None,
) -> None:
    kayit = ZiyaretPlaniTalebe.objects.get(plan=plan, talebe_id=talebe_id, aktif=True)
    kayit.sabit = sabit
    kayit.sabit_arac_id = arac_id if sabit else None
    kayit.save(update_fields=["sabit", "sabit_arac"])
    if sabit and arac_id:
        talebe_ata(plan, talebe_id, arac_id, override=True)


def plan_kontrol(plan: ZiyaretPlani) -> PlanKontrol:
    uyarilar: list[str] = []
    hatalar: list[str] = []
    ozet = planlama_ozeti(plan)

    if ozet.atanmamis:
        uyarilar.append(f"{ozet.atanmamis} talebe henüz araca atanmadı.")

    if not ozet.kapasite.yeterli:
        uyarilar.append(ozet.kapasite.mesaj)

    for arac in plan.araclar.all():
        if not arac.surucu_ad.strip():
            hatalar.append("Araç sahibi eksik bir kayıt var.")
        if arac.kapasite <= 0:
            hatalar.append(f"{arac.surucu_ad}: kapasite girilmemiş.")
        if arac_talebe_sayisi(arac) > arac.kapasite:
            hatalar.append(f"{arac.surucu_ad}: kapasite aşıldı.")

    talebe_atama_sayilari = (
        ZiyaretAracAtama.objects.filter(
            arac__plan=plan,
            tur=ZiyaretAracAtama.Tur.TALEBE,
        )
        .values("talebe_id")
        .annotate(adet=Count("id"))
        .filter(adet__gt=1)
    )
    if talebe_atama_sayilari.exists():
        hatalar.append("Bazı talebeler birden fazla araca atanmış.")

    etut_cift = (
        ZiyaretAracAtama.objects.filter(
            arac__plan=plan,
            tur=ZiyaretAracAtama.Tur.ETUT_HOCASI,
        )
        .values("etut_hocasi_id")
        .annotate(adet=Count("id"))
        .filter(adet__gt=1)
    )
    if etut_cift.exists():
        hatalar.append("Bazı etüt hocaları birden fazla araca atanmış.")

    for atama in ZiyaretAracAtama.objects.filter(
        arac__plan=plan,
        tur=ZiyaretAracAtama.Tur.ETUT_HOCASI,
    ).select_related("etut_hocasi"):
        if atama.etut_hocasi_id and not etut_mesul_mu(atama.etut_hocasi):
            uyarilar.append(
                f"{atama.etut_hocasi.ad_soyad} etüt/sınıf mesulü değil; "
                "araca atanan kişiyi kaldırıp mesul seçin."
            )

    hazir = not hatalar
    return PlanKontrol(hazir=hazir, uyarilar=uyarilar, hatalar=hatalar)


def toplu_talebe_adaylari(
    *,
    sinif_sube_ids: list[int] | None = None,
    etut_hocasi_ids: list[int] | None = None,
    q: str = "",
) -> list[Talebe]:
    qs = Talebe.objects.filter(durum=Talebe.Durum.AKTIF).select_related(
        "sinif_sube", "etut_hocasi"
    )
    if sinif_sube_ids:
        qs = qs.filter(sinif_sube_id__in=sinif_sube_ids)
    if etut_hocasi_ids:
        mesul_ids = list(
            etut_mesul_queryset()
            .filter(pk__in=etut_hocasi_ids)
            .values_list("pk", flat=True)
        )
        qs = qs.filter(etut_hocasi_id__in=mesul_ids) if mesul_ids else qs.none()
    if q.strip():
        qs = qs.filter(
            Q(ad_soyad__icontains=q.strip()) | Q(talebe_no__icontains=q.strip())
        )
    return list(qs.order_by("ad_soyad")[:500])


def personel_surucu_adaylari(q: str = "") -> list[PersonelProfili]:
    qs = PersonelProfili.objects.filter(aktif=True).order_by("ad_soyad")
    if q.strip():
        qs = qs.filter(ad_soyad__icontains=q.strip())
    return list(qs[:30])


def etut_hocalari_listesi() -> list[EtutHocasi]:
    return list(etut_mesul_queryset())


def sinif_sube_listesi() -> list[SinifSube]:
    return list(SinifSube.objects.filter(aktif=True).order_by("sinif", "sube"))
