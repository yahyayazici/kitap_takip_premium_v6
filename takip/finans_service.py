"""Finans yönetim merkezi — sorgular, hesaplamalar, işlemler."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from takip.finans_models import (
    FinansIndirim,
    FinansIslemLog,
    FinansKampanya,
    FinansTahsilat,
    FinansTaksit,
    FinansUcretPolitikasi,
    TalebeFinansDosyasi,
)
from takip.models import SinifSube, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can
from takip.wave0_models import EgitimYili

DEFAULT_UCRETLER = {
    "5": Decimal("92000"),
    "6": Decimal("92000"),
    "7": Decimal("92000"),
    "8": Decimal("112000"),
}

DEFAULT_INDIRIMLER = (
    ("kardes", "Kardeş", FinansIndirim.Tur.YUZDE, Decimal("10")),
    ("pesin", "Peşin", FinansIndirim.Tur.YUZDE, Decimal("5")),
    ("personel", "Personel", FinansIndirim.Tur.YUZDE, Decimal("15")),
    ("basari", "Başarı", FinansIndirim.Tur.YUZDE, Decimal("10")),
    ("burs", "Burs", FinansIndirim.Tur.YUZDE, Decimal("25")),
    ("referans", "Referans", FinansIndirim.Tur.TUTAR, Decimal("2000")),
    ("yonetim", "Yönetim", FinansIndirim.Tur.YUZDE, Decimal("20")),
    ("erken_kayit", "Erken Kayıt", FinansIndirim.Tur.YUZDE, Decimal("8")),
)


def finans_yonetebilir(user: User) -> bool:
    """Politika, indirim ve tam yönetim — etüt hocası hariç."""
    if user.is_superuser or tum_talebe_kapsami_var(user):
        return True
    from takip.permissions.scope import kullanici_rol_slugleri

    return bool(
        kullanici_rol_slugleri(user)
        & {"idareci", "ic_mesul", "egitim_mesul", "sinif_mesul", "muhasebeci"}
    )


def yetkili_finans_dosyalari(user: User) -> QuerySet[TalebeFinansDosyasi]:
    qs = TalebeFinansDosyasi.objects.select_related(
        "talebe",
        "talebe__sinif_sube",
        "talebe__etut_hocasi",
        "egitim_yili",
    )
    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs
    if not can(user, "aidat", "view"):
        return TalebeFinansDosyasi.objects.none()
    talebe_ids = yetkili_talebeler(user, aktif_only=False).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def aktif_egitim_yili() -> EgitimYili | None:
    return EgitimYili.objects.filter(aktif=True).order_by("-baslangic").first()


def finans_seed_verisi() -> None:
    yil = aktif_egitim_yili()
    if not yil:
        return
    for sinif, tutar in DEFAULT_UCRETLER.items():
        FinansUcretPolitikasi.objects.get_or_create(
            egitim_yili=yil,
            sinif_seviyesi=sinif,
            defaults={"tutar": tutar, "aktif": True},
        )
    for sira, (kod, ad, tur, deger) in enumerate(DEFAULT_INDIRIMLER, start=1):
        FinansIndirim.objects.get_or_create(
            kod=kod,
            defaults={
                "ad": ad,
                "tur": tur,
                "deger": deger,
                "aktif": True,
                "sira": sira,
            },
        )


def _log(
    *,
    user: User | None,
    islem: str,
    detay: str = "",
    dosya: TalebeFinansDosyasi | None = None,
    talebe: Talebe | None = None,
) -> None:
    FinansIslemLog.objects.create(
        dosya=dosya,
        talebe=talebe or (dosya.talebe if dosya else None),
        islem=islem,
        detay=detay,
        kullanici=user,
    )


def talebe_sinif_seviyesi(talebe: Talebe) -> str:
    sinif = (talebe.sinif or "").strip()
    if sinif and sinif[0].isdigit():
        return sinif[0]
    return "7"


def ucret_politikasi_getir(yil: EgitimYili, sinif_seviyesi: str) -> Decimal:
    politika = FinansUcretPolitikasi.objects.filter(
        egitim_yili=yil,
        sinif_seviyesi=sinif_seviyesi,
        aktif=True,
    ).first()
    if politika:
        return politika.tutar
    return DEFAULT_UCRETLER.get(sinif_seviyesi, Decimal("92000"))


def _dosya_durum_guncelle(dosya: TalebeFinansDosyasi) -> None:
    bugun = timezone.localdate()
    if dosya.kalan_tutar <= 0 and dosya.net_ucret > 0:
        dosya.durum = TalebeFinansDosyasi.Durum.TAMAMLANDI
    elif dosya.taksitler.filter(vade__lt=bugun, durum__in=[FinansTaksit.Durum.BEKLIYOR, FinansTaksit.Durum.KISMI, FinansTaksit.Durum.GECIKTI]).exists():
        dosya.durum = TalebeFinansDosyasi.Durum.GECIKTI
    elif dosya.odenen_tutar > 0:
        dosya.durum = TalebeFinansDosyasi.Durum.DEVAM
    else:
        dosya.durum = TalebeFinansDosyasi.Durum.BEKLIYOR

    for taksit in dosya.taksitler.all():
        if taksit.odenen_tutar >= taksit.tutar:
            taksit.durum = FinansTaksit.Durum.ODENDI
        elif taksit.odenen_tutar > 0:
            taksit.durum = FinansTaksit.Durum.KISMI
        elif taksit.vade < bugun:
            taksit.durum = FinansTaksit.Durum.GECIKTI
        else:
            taksit.durum = FinansTaksit.Durum.BEKLIYOR
        taksit.save(update_fields=["durum"])


@transaction.atomic
def odeme_plani_olustur(
    dosya: TalebeFinansDosyasi,
    *,
    pesinat: Decimal,
    taksit_sayisi: int,
    ilk_vade: date,
) -> None:
    dosya.taksitler.all().delete()
    dosya.pesinat = pesinat
    dosya.taksit_sayisi = max(taksit_sayisi, 1)
    kalan = max(dosya.net_ucret - pesinat, Decimal("0.00"))
    if kalan <= 0:
        dosya.save(update_fields=["pesinat", "taksit_sayisi", "guncellenme"])
        return

    taksit_tutari = (kalan / dosya.taksit_sayisi).quantize(Decimal("0.01"))
    vade = ilk_vade
    for sira in range(1, dosya.taksit_sayisi + 1):
        tutar = taksit_tutari
        if sira == dosya.taksit_sayisi:
            tutar = kalan - taksit_tutari * (dosya.taksit_sayisi - 1)
        FinansTaksit.objects.create(
            dosya=dosya,
            sira=sira,
            tutar=tutar,
            vade=vade,
        )
        vade = vade + timedelta(days=30)
    dosya.save(update_fields=["pesinat", "taksit_sayisi", "guncellenme"])


@transaction.atomic
def finans_dosya_olustur(
    talebe: Talebe,
    yil: EgitimYili,
    *,
    indirim_tutari: Decimal = Decimal("0.00"),
    pesinat: Decimal = Decimal("0.00"),
    taksit_sayisi: int = 10,
    user: User | None = None,
) -> TalebeFinansDosyasi:
    sinif = talebe_sinif_seviyesi(talebe)
    toplam = ucret_politikasi_getir(yil, sinif)
    indirim_tutari = min(indirim_tutari, toplam)
    net = toplam - indirim_tutari

    dosya, created = TalebeFinansDosyasi.objects.get_or_create(
        talebe=talebe,
        egitim_yili=yil,
        defaults={
            "toplam_ucret": toplam,
            "indirim_tutari": indirim_tutari,
            "net_ucret": net,
            "pesinat": pesinat,
            "taksit_sayisi": taksit_sayisi,
            "olusturan": user,
        },
    )
    if not created:
        dosya.toplam_ucret = toplam
        dosya.indirim_tutari = indirim_tutari
        dosya.net_ucret = net
        dosya.save(update_fields=["toplam_ucret", "indirim_tutari", "net_ucret", "guncellenme"])

    if pesinat > 0 or taksit_sayisi:
        odeme_plani_olustur(
            dosya,
            pesinat=pesinat,
            taksit_sayisi=taksit_sayisi,
            ilk_vade=timezone.localdate().replace(day=10),
        )

    _dosya_durum_guncelle(dosya)
    dosya.save(update_fields=["durum", "guncellenme"])
    _log(user=user, islem="finans_dosya_olustur", detay=f"Net: {net} ₺", dosya=dosya)
    return dosya


@transaction.atomic
def tahsilat_ekle(
    dosya: TalebeFinansDosyasi,
    *,
    tutar: Decimal,
    tarih: date,
    yontem: str,
    tur: str,
    aciklama: str,
    taksit: FinansTaksit | None,
    user: User | None,
) -> FinansTahsilat:
    kayit = FinansTahsilat.objects.create(
        dosya=dosya,
        taksit=taksit,
        tutar=tutar,
        tarih=tarih,
        yontem=yontem,
        tur=tur,
        aciklama=aciklama,
        kaydeden=user,
    )
    if taksit:
        taksit.odenen_tutar = (
            taksit.tahsilatlar.filter(iptal=False).aggregate(t=Sum("tutar"))["t"] or Decimal("0.00")
        )
        taksit.save(update_fields=["odenen_tutar"])

    dosya.odenen_tutar = (
        dosya.tahsilatlar.filter(iptal=False).aggregate(t=Sum("tutar"))["t"] or Decimal("0.00")
    )
    _dosya_durum_guncelle(dosya)
    dosya.save(update_fields=["odenen_tutar", "durum", "guncellenme"])
    _log(
        user=user,
        islem="tahsilat_ekle",
        detay=f"{tutar} ₺ · {yontem}",
        dosya=dosya,
    )
    return kayit


def dashboard_ozet(user: User, yil: EgitimYili | None = None) -> dict[str, Any]:
    finans_seed_verisi()
    qs = yetkili_finans_dosyalari(user)
    if yil:
        qs = qs.filter(egitim_yili=yil)

    toplam_alacak = qs.aggregate(t=Sum("net_ucret"))["t"] or Decimal("0.00")
    tahsil = qs.aggregate(t=Sum("odenen_tutar"))["t"] or Decimal("0.00")
    bekleyen = max(toplam_alacak - tahsil, Decimal("0.00"))

    bugun = timezone.localdate()
    ay_bas = bugun.replace(day=1)
    bu_ay = (
        FinansTahsilat.objects.filter(
            dosya__in=qs,
            iptal=False,
            tarih__gte=ay_bas,
            tarih__lte=bugun,
        ).aggregate(t=Sum("tutar"))["t"]
        or Decimal("0.00")
    )
    bugun_tahsil = (
        FinansTahsilat.objects.filter(
            dosya__in=qs,
            iptal=False,
            tarih=bugun,
        ).aggregate(t=Sum("tutar"))["t"]
        or Decimal("0.00")
    )

    vadesi_gecen = FinansTaksit.objects.filter(
        dosya__in=qs,
        vade__lt=bugun,
        durum__in=[FinansTaksit.Durum.BEKLIYOR, FinansTaksit.Durum.KISMI, FinansTaksit.Durum.GECIKTI],
    ).aggregate(t=Sum("tutar"), kalan=Sum("tutar") - Sum("odenen_tutar"))
    vadesi_gecen_tutar = (
        FinansTaksit.objects.filter(
            dosya__in=qs,
            vade__lt=bugun,
        )
        .annotate(kalan_f=Sum("tutar") - Sum("odenen_tutar"))
    )
    geciken_tutar = Decimal("0.00")
    geciken_sayisi = qs.filter(durum=TalebeFinansDosyasi.Durum.GECIKTI).count()
    for t in FinansTaksit.objects.filter(
        dosya__in=qs,
        vade__lt=bugun,
        durum__in=[FinansTaksit.Durum.BEKLIYOR, FinansTaksit.Durum.KISMI, FinansTaksit.Durum.GECIKTI],
    ):
        geciken_tutar += t.kalan

    yaklasan = FinansTaksit.objects.filter(
        dosya__in=qs,
        vade__gte=bugun,
        vade__lte=bugun + timedelta(days=14),
        durum__in=[FinansTaksit.Durum.BEKLIYOR, FinansTaksit.Durum.KISMI],
    ).count()

    oran = int(round(100 * float(tahsil) / float(toplam_alacak))) if toplam_alacak else 0

    return {
        "toplam_alacak": toplam_alacak,
        "tahsil_edilen": tahsil,
        "bekleyen": bekleyen,
        "vadesi_gecen": geciken_tutar,
        "geciken_sayisi": geciken_sayisi,
        "bu_ay_tahsilat": bu_ay,
        "bugun_tahsilat": bugun_tahsil,
        "tahsilat_orani": oran,
        "yaklasan_taksit": yaklasan,
    }


def dosya_listesi_filtrele(
    qs: QuerySet[TalebeFinansDosyasi],
    *,
    q: str | None = None,
    sinif_sube_id: str | None = None,
    durum: str | None = None,
) -> QuerySet[TalebeFinansDosyasi]:
    if q:
        qs = qs.filter(
            Q(talebe__ad_soyad__icontains=q)
            | Q(talebe__talebe_no__icontains=q)
        )
    if sinif_sube_id:
        qs = qs.filter(talebe__sinif_sube_id=sinif_sube_id)
    if durum:
        qs = qs.filter(durum=durum)
    return qs


def sag_panel_verisi(user: User, qs: QuerySet[TalebeFinansDosyasi]) -> dict[str, Any]:
    bugun = timezone.localdate()
    ozet = dashboard_ozet(user)
    son_tahsilatlar = list(
        FinansTahsilat.objects.filter(dosya__in=qs, iptal=False)
        .select_related("dosya__talebe", "kaydeden")
        .order_by("-tarih", "-id")[:6]
    )
    yaklasan = list(
        FinansTaksit.objects.filter(
            dosya__in=qs,
            vade__gte=bugun,
            durum__in=[FinansTaksit.Durum.BEKLIYOR, FinansTaksit.Durum.KISMI],
        )
        .select_related("dosya__talebe")
        .order_by("vade")[:5]
    )
    geciken = list(
        FinansTaksit.objects.filter(
            dosya__in=qs,
            vade__lt=bugun,
            durum__in=[FinansTaksit.Durum.BEKLIYOR, FinansTaksit.Durum.KISMI, FinansTaksit.Durum.GECIKTI],
        )
        .select_related("dosya__talebe")
        .order_by("vade")[:5]
    )
    return {
        **ozet,
        "son_tahsilatlar": son_tahsilatlar,
        "yaklasan_taksitler": yaklasan,
        "geciken_taksitler": geciken,
    }


def finans_analiz(user: User, qs: QuerySet[TalebeFinansDosyasi]) -> list[dict[str, str]]:
    ozet = dashboard_ozet(user)
    hafta_sonu = timezone.localdate() + timedelta(days=7)
    bu_hafta = (
        FinansTaksit.objects.filter(
            dosya__in=qs,
            vade__lte=hafta_sonu,
            vade__gte=timezone.localdate(),
        ).aggregate(t=Sum("tutar"))["t"]
        or Decimal("0.00")
    )
    return [
        {"etiket": "Tahsilat oranı", "deger": f"%{ozet['tahsilat_orani']}"},
        {"etiket": "Vadesi geçen öğrenci", "deger": str(ozet["geciken_sayisi"])},
        {
            "etiket": "Bu hafta tahsil edilmesi gereken",
            "deger": f"{bu_hafta:,.0f} ₺".replace(",", "."),
        },
    ]


def aylik_tahsilat_grafik(user: User, qs: QuerySet[TalebeFinansDosyasi], *, ay_sayisi: int = 6) -> list[dict]:
    bugun = timezone.localdate()
    grafik = []
    for i in range(ay_sayisi - 1, -1, -1):
        ref = bugun.replace(day=1)
        for _ in range(i):
            ref = (ref - timedelta(days=1)).replace(day=1)
        if ref.month == 12:
            bitis = ref.replace(day=31)
        else:
            bitis = ref.replace(month=ref.month + 1, day=1) - timedelta(days=1)
        tutar = (
            FinansTahsilat.objects.filter(
                dosya__in=qs,
                iptal=False,
                tarih__gte=ref,
                tarih__lte=bitis,
            ).aggregate(t=Sum("tutar"))["t"]
            or Decimal("0.00")
        )
        max_t = float(tutar) or 1
        grafik.append(
            {
                "etiket": ref.strftime("%b"),
                "tutar": tutar,
                "yuzde": min(100, round(float(tutar) / max(max_t, 1) * 100)),
            }
        )
    if grafik:
        peak = max(float(g["tutar"]) for g in grafik) or 1
        for g in grafik:
            g["yuzde"] = round(float(g["tutar"]) * 100 / peak, 1)
    return grafik


def yeni_yil_politikasi_kopyala(kaynak: EgitimYili, hedef: EgitimYili) -> int:
    adet = 0
    for p in FinansUcretPolitikasi.objects.filter(egitim_yili=kaynak, aktif=True):
        _, created = FinansUcretPolitikasi.objects.get_or_create(
            egitim_yili=hedef,
            sinif_seviyesi=p.sinif_seviyesi,
            defaults={"tutar": p.tutar, "aktif": True},
        )
        if created:
            adet += 1
    return adet


def sinif_sube_secenekleri() -> QuerySet[SinifSube]:
    return SinifSube.objects.filter(aktif=True).order_by("sinif", "sube")
