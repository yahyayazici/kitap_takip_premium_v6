"""Yemekçilik — sınıf döngüsü, havuz CRUD, günlük/toplu atama."""

from __future__ import annotations

from calendar import monthcalendar
from datetime import date, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max
from django.utils.timezone import localdate

from takip.models import Talebe
from takip.yemekci_sinif_models import (
    SINIF_ETIKET,
    SINIF_RENKLERI,
    SINIF_SEVIYELERI,
    YemekciAyar,
    YemekciGunAtama,
    YemekciHavuzKaydi,
    YemekciSinifHavuzu,
)

# Eski panel uyumluluğu
def bugunun_listesi():
    return None


def bugunun_atamalari() -> list:
    """Dashboard kartı için bugünkü sınıf görevlileri."""
    return [
        y
        for y in gunun_yemekcileri()
        if y.get("talebe") and not y.get("hafta_sonu")
    ]


def otomatik_dagit(liste=None) -> int:
    """Eski seed/yonetim çağrıları için no-op."""
    havuzlari_kur(seed_talebeler=True)
    return 0


def ayarlari_al() -> YemekciAyar:
    ayar = YemekciAyar.objects.order_by("id").first()
    if ayar:
        return ayar
    return YemekciAyar.objects.create(
        hafta_sonu_cikar=True,
        dongu_baslangic=localdate(),
    )


@transaction.atomic
def havuzlari_kur(seed_talebeler: bool = True) -> list[YemekciSinifHavuzu]:
    """5–8 havuzlarını bir kez oluşturur; isteğe bağlı aktif talebeleri doldurur."""
    havuzlar: list[YemekciSinifHavuzu] = []
    for sinif in SINIF_SEVIYELERI:
        havuz, _ = YemekciSinifHavuzu.objects.get_or_create(
            sinif=sinif,
            defaults={"renk": SINIF_RENKLERI[sinif], "aktif": True},
        )
        if not havuz.renk:
            havuz.renk = SINIF_RENKLERI[sinif]
            havuz.save(update_fields=["renk"])
        havuzlar.append(havuz)

    ayarlari_al()

    if seed_talebeler:
        for havuz in havuzlar:
            if havuz.kayitlar.exists():
                continue
            talebeler = (
                Talebe.objects.filter(aktif=True, sinif_sube__sinif=havuz.sinif)
                .select_related("sinif_sube")
                .order_by("sinif_sube__sube", "ad_soyad", "pk")
            )
            if not talebeler.exists():
                talebeler = Talebe.objects.filter(
                    aktif=True, sinif=havuz.sinif
                ).order_by("sube", "ad_soyad", "pk")
            for sira, talebe in enumerate(talebeler):
                YemekciHavuzKaydi.objects.get_or_create(
                    havuz=havuz,
                    talebe=talebe,
                    defaults={"sira": sira, "aktif": True},
                )
    return havuzlar


def sinif_havuzlari() -> list[YemekciSinifHavuzu]:
    havuzlari_kur(seed_talebeler=True)
    return list(
        YemekciSinifHavuzu.objects.filter(aktif=True, sinif__in=SINIF_SEVIYELERI).order_by(
            "sinif"
        )
    )


def havuz_kayitlari(sinif: str) -> list[YemekciHavuzKaydi]:
    havuz = YemekciSinifHavuzu.objects.filter(sinif=sinif, aktif=True).first()
    if not havuz:
        return []
    return list(
        havuz.kayitlar.filter(aktif=True)
        .select_related("talebe", "talebe__sinif_sube")
        .order_by("sira", "id")
    )


def _is_workday(gun: date, hafta_sonu_cikar: bool) -> bool:
    if not hafta_sonu_cikar:
        return True
    return gun.weekday() < 5  # Pzt–Cum


def workday_index(tarih: date, baslangic: date, hafta_sonu_cikar: bool) -> int:
    """baslangic dahil, tarih gününe kadar (dahil) kaçıncı çalışma günü (0-based)."""
    if tarih < baslangic:
        return 0
    idx = 0
    gun = baslangic
    while gun < tarih:
        if _is_workday(gun, hafta_sonu_cikar):
            idx += 1
        gun += timedelta(days=1)
    if not _is_workday(tarih, hafta_sonu_cikar):
        # hafta sonu: son iş günü indeksini kullan (gösterim için yine hesaplanır)
        return max(0, idx - 1) if idx else 0
    return idx


def aralik_gunleri(
    baslangic: date,
    bitis: date,
    *,
    hafta_sonu_cikar: bool | None = None,
) -> list[date]:
    ayar = ayarlari_al()
    if hafta_sonu_cikar is None:
        hafta_sonu_cikar = ayar.hafta_sonu_cikar
    gunler: list[date] = []
    gun = baslangic
    while gun <= bitis:
        if _is_workday(gun, hafta_sonu_cikar):
            gunler.append(gun)
        gun += timedelta(days=1)
    return gunler


def _talebe_karti(talebe: Talebe | None) -> dict[str, Any] | None:
    if not talebe:
        return None
    sinif_label = ""
    if getattr(talebe, "sinif_sube_id", None) and talebe.sinif_sube_id:
        ss = talebe.sinif_sube
        sinif_label = f"{ss.sinif}-{ss.sube}"
    else:
        sinif_label = f"{talebe.sinif or ''}-{talebe.sube or ''}".strip("-")
    return {
        "id": talebe.pk,
        "ad": talebe.ad_soyad,
        "sinif_label": sinif_label or "—",
    }


def gorevli_hesapla(tarih: date, sinif: str) -> dict[str, Any]:
    """Bir sınıf için o günün görevlisi (manuel override öncelikli)."""
    ayar = ayarlari_al()
    override = (
        YemekciGunAtama.objects.filter(tarih=tarih, sinif=sinif)
        .select_related("talebe", "talebe__sinif_sube")
        .first()
    )
    if override and override.manuel:
        return {
            "sinif": sinif,
            "etiket": SINIF_ETIKET.get(sinif, sinif),
            "renk": SINIF_RENKLERI.get(sinif, "#64748b"),
            "talebe": _talebe_karti(override.talebe),
            "manuel": True,
            "atama_id": override.pk,
            "hafta_sonu": not _is_workday(tarih, ayar.hafta_sonu_cikar),
        }

    kayitlar = havuz_kayitlari(sinif)
    talebe = None
    if kayitlar and _is_workday(tarih, ayar.hafta_sonu_cikar):
        idx = workday_index(tarih, ayar.dongu_baslangic, ayar.hafta_sonu_cikar)
        kayit = kayitlar[idx % len(kayitlar)]
        talebe = kayit.talebe
    elif override:
        talebe = override.talebe

    return {
        "sinif": sinif,
        "etiket": SINIF_ETIKET.get(sinif, sinif),
        "renk": SINIF_RENKLERI.get(sinif, "#64748b"),
        "talebe": _talebe_karti(talebe),
        "manuel": bool(override and override.manuel),
        "atama_id": override.pk if override else None,
        "hafta_sonu": not _is_workday(tarih, ayar.hafta_sonu_cikar),
    }


def gunun_yemekcileri(tarih: date | None = None) -> list[dict[str, Any]]:
    tarih = tarih or localdate()
    havuzlari_kur(seed_talebeler=True)
    return [gorevli_hesapla(tarih, s) for s in SINIF_SEVIYELERI]


def aralik_uret(
    baslangic: date,
    bitis: date,
    *,
    hafta_sonu_cikar: bool | None = None,
    kaydet: bool = False,
    user: User | None = None,
) -> list[dict[str, Any]]:
    """Tarih aralığı için satır listesi; kaydet=True ise YemekciGunAtama yazar."""
    gunler = aralik_gunleri(baslangic, bitis, hafta_sonu_cikar=hafta_sonu_cikar)
    satirlar: list[dict[str, Any]] = []
    for gun in gunler:
        hucreler = {}
        for sinif in SINIF_SEVIYELERI:
            kart = gorevli_hesapla(gun, sinif)
            hucreler[sinif] = kart
            if kaydet and kart.get("talebe"):
                YemekciGunAtama.objects.update_or_create(
                    tarih=gun,
                    sinif=sinif,
                    defaults={
                        "talebe_id": kart["talebe"]["id"],
                        "manuel": False,
                        "olusturan": user,
                    },
                )
        satirlar.append({"tarih": gun, "hucreler": hucreler})
    return satirlar


@transaction.atomic
def kayit_ekle(sinif: str, talebe_id: int) -> YemekciHavuzKaydi:
    havuzlari_kur(seed_talebeler=False)
    havuz = YemekciSinifHavuzu.objects.get(sinif=sinif)
    talebe = Talebe.objects.get(pk=talebe_id, aktif=True)
    mevcut = YemekciHavuzKaydi.objects.filter(havuz=havuz, talebe=talebe).first()
    if mevcut:
        if not mevcut.aktif:
            mevcut.aktif = True
            mevcut.save(update_fields=["aktif"])
        return mevcut
    max_sira = (
        YemekciHavuzKaydi.objects.filter(havuz=havuz).aggregate(m=Max("sira")).get("m")
        or -1
    )
    return YemekciHavuzKaydi.objects.create(
        havuz=havuz, talebe=talebe, sira=max_sira + 1, aktif=True
    )


@transaction.atomic
def kayit_sil(kayit_id: int) -> None:
    kayit = YemekciHavuzKaydi.objects.filter(pk=kayit_id).first()
    if not kayit:
        return
    havuz = kayit.havuz
    kayit.delete()
    for sira, k in enumerate(havuz.kayitlar.filter(aktif=True).order_by("sira", "id")):
        if k.sira != sira:
            k.sira = sira
            k.save(update_fields=["sira"])


@transaction.atomic
def kayitlari_sirala(sinif: str, kayit_ids: list[int]) -> bool:
    havuz = YemekciSinifHavuzu.objects.filter(sinif=sinif).first()
    if not havuz:
        return False
    izinli = set(havuz.kayitlar.filter(aktif=True).values_list("id", flat=True))
    if not set(kayit_ids).issubset(izinli):
        return False
    for sira, kid in enumerate(kayit_ids):
        YemekciHavuzKaydi.objects.filter(pk=kid, havuz=havuz).update(sira=sira)
    return True


def gorevli_degistir(
    tarih: date, sinif: str, talebe_id: int, user: User | None = None
) -> YemekciGunAtama:
    talebe = Talebe.objects.get(pk=talebe_id, aktif=True)
    atama, _ = YemekciGunAtama.objects.update_or_create(
        tarih=tarih,
        sinif=sinif,
        defaults={"talebe": talebe, "manuel": True, "olusturan": user},
    )
    return atama


def gun_atama_sil(tarih: date, sinif: str) -> None:
    YemekciGunAtama.objects.filter(tarih=tarih, sinif=sinif).delete()


def takvim_ay(yil: int, ay: int) -> list[list[dict[str, Any] | None]]:
    """Ay ızgarası: her hücre {gun, yemekciler} veya None."""
    weeks = monthcalendar(yil, ay)
    grid: list[list[dict[str, Any] | None]] = []
    for week in weeks:
        row: list[dict[str, Any] | None] = []
        for day in week:
            if day == 0:
                row.append(None)
            else:
                d = date(yil, ay, day)
                row.append({"tarih": d, "yemekciler": gunun_yemekcileri(d)})
        grid.append(row)
    return grid


def secilebilir_talebeler(sinif: str) -> list[Talebe]:
    qs = Talebe.objects.filter(aktif=True).select_related("sinif_sube")
    filtered = qs.filter(sinif_sube__sinif=sinif).order_by(
        "sinif_sube__sube", "ad_soyad"
    )
    if filtered.exists():
        return list(filtered)
    return list(qs.filter(sinif=sinif).order_by("sube", "ad_soyad"))


def panel_baglami(
    *,
    tarih: date | None = None,
    sekme: str = "bugun",
    ay: int | None = None,
    yil: int | None = None,
) -> dict[str, Any]:
    havuzlari_kur(seed_talebeler=True)
    ayar = ayarlari_al()
    tarih = tarih or localdate()
    bugun = localdate()
    yil = yil or tarih.year
    ay = ay or tarih.month

    havuz_detay = []
    for h in sinif_havuzlari():
        kayitlar = [
            {
                "id": k.id,
                "sira": k.sira,
                "talebe_id": k.talebe_id,
                "ad": k.talebe.ad_soyad,
                "sinif_label": (
                    f"{k.talebe.sinif_sube.sinif}-{k.talebe.sinif_sube.sube}"
                    if k.talebe.sinif_sube_id
                    else f"{k.talebe.sinif}-{k.talebe.sube}"
                ),
            }
            for k in havuz_kayitlari(h.sinif)
        ]
        havuz_detay.append(
            {
                "sinif": h.sinif,
                "etiket": h.etiket,
                "renk": h.renk_kod,
                "kayitlar": kayitlar,
                "secenekler": [
                    {"id": t.pk, "ad": t.ad_soyad}
                    for t in secilebilir_talebeler(h.sinif)
                    if t.pk not in {k["talebe_id"] for k in kayitlar}
                ],
            }
        )

    return {
        "sekme": sekme,
        "tarih": tarih,
        "bugun": bugun,
        "ayar": ayar,
        "yemekciler": gunun_yemekcileri(tarih),
        "havuzlar": havuz_detay,
        "takvim": takvim_ay(yil, ay) if sekme == "takvim" else None,
        "takvim_yil": yil,
        "takvim_ay": ay,
        "sinif_renkleri": SINIF_RENKLERI,
        "sinif_etiket": SINIF_ETIKET,
        "sure_secenekleri": [
            (7, "7 Günlük (1 Hafta)"),
            (15, "15 Günlük (2 Hafta)"),
            (30, "30 Günlük (1 Ay)"),
            (60, "60 Günlük (2 Ay)"),
        ],
    }
