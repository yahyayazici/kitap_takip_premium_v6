"""Veli randevu — slot üretimi, rezervasyon, raporlar."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from takip.models import PersonelProfili, Talebe, VeliHesap
from takip.rehberlik_models import GorusmeTuru, OgrenciGorusmesi
from takip.veli_randevu_models import RandevuMusaitlik, RandevuPersonelAyar, VeliRandevu


AKTIF_DURUMLAR = (VeliRandevu.Durum.PLANLANDI, VeliRandevu.Durum.TAMAMLANDI)


def randevu_personel_ayar_getir(personel: PersonelProfili) -> RandevuPersonelAyar:
    ayar, _ = RandevuPersonelAyar.objects.get_or_create(
        personel=personel,
        defaults={"aktif": False, "sure_dk": 30},
    )
    return ayar


def veli_icin_personeller(talebe: Talebe) -> QuerySet[PersonelProfili]:
    return (
        PersonelProfili.objects.filter(
            aktif=True,
            randevu_ayari__aktif=True,
        )
        .select_related("randevu_ayari", "etut_hocasi")
        .order_by("ad_soyad")
    )


def _slot_dolu(personel: PersonelProfili, tarih: date, baslangic: time) -> bool:
    return VeliRandevu.objects.filter(
        personel=personel,
        tarih=tarih,
        baslangic=baslangic,
        durum__in=AKTIF_DURUMLAR,
    ).exists()


def musait_slotlar(
    personel: PersonelProfili,
    *,
    baslangic: date | None = None,
    gun_sayisi: int = 21,
) -> list[dict[str, Any]]:
    ayar = getattr(personel, "randevu_ayari", None)
    if not ayar or not ayar.aktif:
        return []

    sure = max(ayar.sure_dk, 10)
    bugun = timezone.localdate()
    simdi = timezone.localtime().time()
    bas = baslangic or bugun

    musaitlikler = list(
        RandevuMusaitlik.objects.filter(personel=personel, aktif=True).order_by(
            "hafta_gunu", "baslangic"
        )
    )
    if not musaitlikler:
        return []

    by_gun: dict[int, list[RandevuMusaitlik]] = {}
    for m in musaitlikler:
        by_gun.setdefault(m.hafta_gunu, []).append(m)

    slotlar: list[dict[str, Any]] = []
    for offset in range(gun_sayisi):
        tarih = bas + timedelta(days=offset)
        if tarih < bugun:
            continue
        for musait in by_gun.get(tarih.weekday(), []):
            cursor = datetime.combine(tarih, musait.baslangic)
            bitis_dt = datetime.combine(tarih, musait.bitis)
            adim = timedelta(minutes=sure)
            while cursor + adim <= bitis_dt:
                baslangic_saat = cursor.time()
                bitis_saat = (cursor + adim).time()
                if tarih == bugun and baslangic_saat <= simdi:
                    cursor += adim
                    continue
                if not _slot_dolu(personel, tarih, baslangic_saat):
                    slotlar.append(
                        {
                            "tarih": tarih,
                            "baslangic": baslangic_saat,
                            "bitis": bitis_saat,
                            "etiket": f"{tarih:%d.%m.%Y} · {baslangic_saat:%H:%M}",
                            "value": f"{tarih.isoformat()}|{baslangic_saat.isoformat()}",
                        }
                    )
                cursor += adim
    return slotlar


@transaction.atomic
def randevu_olustur(
    *,
    veli: VeliHesap,
    talebe: Talebe,
    personel: PersonelProfili,
    tarih: date,
    baslangic: time,
    konu: str = "",
) -> VeliRandevu:
    ayar = randevu_personel_ayar_getir(personel)
    if not ayar.aktif:
        raise ValueError("Bu personel randevu kabul etmiyor.")

    bitis_dt = datetime.combine(tarih, baslangic) + timedelta(minutes=ayar.sure_dk)
    if _slot_dolu(personel, tarih, baslangic):
        raise ValueError("Seçilen saat artık müsait değil.")

    musait = RandevuMusaitlik.objects.filter(
        personel=personel,
        hafta_gunu=tarih.weekday(),
        aktif=True,
        baslangic__lte=baslangic,
        bitis__gte=bitis_dt.time(),
    ).exists()
    if not musait:
        raise ValueError("Seçilen saat personelin müsaitlik aralığında değil.")

    return VeliRandevu.objects.create(
        veli=veli,
        talebe=talebe,
        personel=personel,
        tarih=tarih,
        baslangic=baslangic,
        bitis=bitis_dt.time(),
        konu=konu,
    )


def personel_randevulari(user: User) -> QuerySet[VeliRandevu]:
    try:
        personel = user.personel_profili
    except PersonelProfili.DoesNotExist:
        return VeliRandevu.objects.none()

    return (
        VeliRandevu.objects.filter(personel=personel)
        .select_related("talebe", "veli", "veli__user", "gorusme")
        .order_by("tarih", "baslangic")
    )


def veli_randevulari(veli: VeliHesap, talebe: Talebe | None = None) -> QuerySet[VeliRandevu]:
    qs = VeliRandevu.objects.filter(veli=veli).select_related(
        "personel", "talebe", "gorusme"
    )
    if talebe:
        qs = qs.filter(talebe=talebe)
    return qs.order_by("-tarih", "-baslangic")


def _veli_randevu_turu() -> GorusmeTuru:
    tur, _ = GorusmeTuru.objects.get_or_create(
        kod="veli_randevu",
        defaults={
            "ad": "Veli Randevusu",
            "grup": GorusmeTuru.Grup.VELI,
            "alan": GorusmeTuru.Alan.ILETISIM,
            "ikon": "📅",
            "renk": "#2563eb",
            "sira": 5,
            "aktif": True,
        },
    )
    return tur


@transaction.atomic
def randevu_gorusme_kaydet(
    randevu: VeliRandevu,
    *,
    ozet: str,
    detay: str,
    kararlar: str,
    user: User,
) -> OgrenciGorusmesi:
    gorusme = OgrenciGorusmesi.objects.create(
        talebe=randevu.talebe,
        tur=_veli_randevu_turu(),
        kaydeden=user,
        tarih=randevu.tarih,
        saat=randevu.baslangic,
        ozet=ozet,
        detay=detay,
        kararlar=kararlar,
        veli_goster=True,
    )
    randevu.gorusme = gorusme
    randevu.durum = VeliRandevu.Durum.TAMAMLANDI
    randevu.save(update_fields=["gorusme", "durum", "guncellenme"])
    return gorusme


def randevu_raporla(
    qs: QuerySet[VeliRandevu] | None = None,
    *,
    baslangic: date | None = None,
    bitis: date | None = None,
    personel_id: int | None = None,
    talebe_id: int | None = None,
) -> QuerySet[VeliRandevu]:
    base = qs if qs is not None else VeliRandevu.objects.all()
    base = base.select_related("personel", "talebe", "veli", "gorusme")
    if baslangic:
        base = base.filter(tarih__gte=baslangic)
    if bitis:
        base = base.filter(tarih__lte=bitis)
    if personel_id:
        base = base.filter(personel_id=personel_id)
    if talebe_id:
        base = base.filter(talebe_id=talebe_id)
    return base.order_by("-tarih", "-baslangic")


def randevu_ozet(qs: QuerySet[VeliRandevu]) -> dict[str, Any]:
    return {
        "toplam": qs.count(),
        "planlandi": qs.filter(durum=VeliRandevu.Durum.PLANLANDI).count(),
        "tamamlandi": qs.filter(durum=VeliRandevu.Durum.TAMAMLANDI).count(),
        "iptal": qs.filter(
            durum__in=(VeliRandevu.Durum.IPTAL_VELI, VeliRandevu.Durum.IPTAL_PERSONEL)
        ).count(),
    }


def personel_gunluk_randevular(personel: PersonelProfili, tarih: date | None = None) -> list[VeliRandevu]:
    ref = tarih or timezone.localdate()
    return list(
        VeliRandevu.objects.filter(
            personel=personel,
            tarih=ref,
            durum__in=AKTIF_DURUMLAR,
        )
        .select_related("talebe", "veli")
        .order_by("baslangic")
    )


def ogretmen_randevu_listesi(hoca_user: User, *, limit: int = 5) -> list[dict[str, Any]]:
    try:
        personel = hoca_user.personel_profili
    except PersonelProfili.DoesNotExist:
        return []

    bugun = timezone.localdate()
    kayitlar = (
        VeliRandevu.objects.filter(
            personel=personel,
            tarih__gte=bugun,
            durum=VeliRandevu.Durum.PLANLANDI,
        )
        .select_related("talebe", "veli")
        .order_by("tarih", "baslangic")[:limit]
    )
    return [
        {
            "id": r.pk,
            "talebe": r.talebe.ad_soyad,
            "tarih": r.tarih.strftime("%d.%m.%Y"),
            "saat": r.baslangic.strftime("%H:%M"),
            "konu": r.konu or "Veli görüşmesi",
        }
        for r in kayitlar
    ]
