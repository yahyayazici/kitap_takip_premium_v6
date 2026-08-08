"""İdareci özet paneli — salt okunur kurum nabzı."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.utils.timezone import localdate

from takip.models import (
    DenemeSonucu,
    KttSonucu,
    NamazYoklamaKaydi,
    PersonelProfili,
    SinifSube,
    Talebe,
    YaziliKamp,
    YaziliSinav,
    YaziliSonuc,
)
from takip.dini_ders_takip_models import DiniDersKonuKaydi
from takip.vazife_models import PersonelVazife
from takip.yct_models import YctOlay


def _pct(n: int, d: int) -> int:
    if d <= 0:
        return 0
    return int(round(100 * n / d))


def idareci_ozet() -> dict:
    bugun = localdate()
    son_30 = bugun - timedelta(days=30)

    personeller = (
        PersonelProfili.objects.filter(aktif=True)
        .select_related("user", "etut_hocasi")
        .order_by("ad_soyad")
    )

    siniflar = list(
        SinifSube.objects.filter(aktif=True)
        .annotate(talebe_sayisi=Count("talebeler", distinct=True))
        .order_by("sinif", "sube")
    )

    # Dini ders: sınıf bazlı tamamlanma (konu kaydı / aktif talebe yaklaşık)
    dini_satirlar = []
    for sinif in siniflar:
        talebe_ids = list(
            Talebe.objects.filter(aktif=True, sinif_sube=sinif).values_list("id", flat=True)
        )
        if not talebe_ids:
            dini_satirlar.append(
                {"sinif": sinif, "talebe": 0, "tamamlanan": 0, "yuzde": 0}
            )
            continue
        tamamlanan = (
            DiniDersKonuKaydi.objects.filter(
                talebe_id__in=talebe_ids,
                tamamlandi=True,
            )
            .values("talebe_id")
            .distinct()
            .count()
        )
        # Daha anlamlı: tamamlanan konu / toplam konu oranı sınıf ortalaması
        kayitlar = DiniDersKonuKaydi.objects.filter(talebe_id__in=talebe_ids)
        toplam_k = kayitlar.count()
        tamam_k = kayitlar.filter(tamamlandi=True).count()
        dini_satirlar.append(
            {
                "sinif": sinif,
                "talebe": len(talebe_ids),
                "tamamlanan": tamam_k,
                "toplam": toplam_k,
                "yuzde": _pct(tamam_k, toplam_k) if toplam_k else 0,
            }
        )

    # Namaz: kayıtlar çoğunlukla gelmedi/izin — sınıf bazlı gelmedi sayısı
    namaz_satirlar = []
    for sinif in siniflar:
        talebe_ids = list(
            Talebe.objects.filter(aktif=True, sinif_sube=sinif).values_list("id", flat=True)
        )
        if not talebe_ids:
            namaz_satirlar.append(
                {"sinif": sinif, "toplam": 0, "gelmedi": 0, "izinli": 0, "yuzde": None}
            )
            continue
        qs = NamazYoklamaKaydi.objects.filter(
            talebe_id__in=talebe_ids,
            oturum__tarih__gte=son_30,
            oturum__tarih__lte=bugun,
        )
        gelmedi = qs.filter(durum="G").count()
        izinli = qs.filter(durum="I").count()
        toplam = qs.count()
        # Öğrenci başına ortalama gelmedi (daha okunaklı)
        ogrenci = len(talebe_ids)
        ort_gelmedi = round(gelmedi / ogrenci, 1) if ogrenci else 0
        namaz_satirlar.append(
            {
                "sinif": sinif,
                "toplam": toplam,
                "gelmedi": gelmedi,
                "izinli": izinli,
                "ort_gelmedi": ort_gelmedi,
                "yuzde": None,
            }
        )

    # Sınav nabız
    aktif_yazili = YaziliSinav.objects.filter(
        kamp__aktif=True,
        durum=YaziliSinav.Durum.AKTIF,
    ).select_related("kamp")
    ornek_sayisi = aktif_yazili.filter(tur=YaziliSinav.Tur.ORNEK).count()
    gercek_sayisi = aktif_yazili.filter(tur=YaziliSinav.Tur.GERCEK).count()

    son_yazili = (
        YaziliSonuc.objects.select_related("sinav", "talebe", "talebe__sinif_sube")
        .order_by("-guncellenme")[:8]
    )
    son_ktt = (
        KttSonucu.objects.select_related("ktt", "talebe")
        .order_by("-id")[:6]
    )
    son_deneme = (
        DenemeSonucu.objects.select_related("deneme", "talebe")
        .order_by("-id")[:6]
    )

    vazife_ozet = {
        "acik": PersonelVazife.objects.exclude(
            durum__in=[PersonelVazife.Durum.TAMAMLANDI, PersonelVazife.Durum.IPTAL]
        ).count(),
        "geciken": PersonelVazife.objects.filter(
            bitis__lt=bugun,
        )
        .exclude(durum__in=[PersonelVazife.Durum.TAMAMLANDI, PersonelVazife.Durum.IPTAL])
        .count(),
        "tamamlanan": PersonelVazife.objects.filter(
            durum=PersonelVazife.Durum.TAMAMLANDI,
            tamamlanma_tarihi__date__gte=son_30,
        ).count(),
    }

    ay_basi = bugun.replace(day=1)
    if bugun.month == 12:
        ay_sonu = bugun.replace(year=bugun.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        ay_sonu = bugun.replace(month=bugun.month + 1, day=1) - timedelta(days=1)

    yct_bu_ay = YctOlay.objects.filter(
        baslangic__lte=ay_sonu,
    ).filter(Q(bitis__gte=ay_basi) | Q(bitis__isnull=True, baslangic__gte=ay_basi))

    return {
        "bugun": bugun,
        "personel_sayisi": personeller.count(),
        "personeller": personeller[:12],
        "sinif_sayisi": len(siniflar),
        "talebe_sayisi": Talebe.objects.filter(aktif=True).count(),
        "dini_satirlar": dini_satirlar,
        "namaz_satirlar": namaz_satirlar,
        "yazili_kamp_sayisi": YaziliKamp.objects.filter(aktif=True).count(),
        "ornek_yazili": ornek_sayisi,
        "gercek_yazili": gercek_sayisi,
        "son_yazili": son_yazili,
        "son_ktt": son_ktt,
        "son_deneme": son_deneme,
        "vazife_ozet": vazife_ozet,
        "acik_vazifeler": PersonelVazife.objects.exclude(
            durum__in=[PersonelVazife.Durum.TAMAMLANDI, PersonelVazife.Durum.IPTAL]
        )
        .select_related("atanan", "sinif_sube")
        .order_by("bitis", "-oncelik")[:8],
        "yct_bu_ay": list(yct_bu_ay.order_by("baslangic")[:10]),
        "yct_ay_etiket": bugun.strftime("%B %Y"),
    }


def yct_ay_takvimi(yil: int, ay: int) -> dict:
    from calendar import Calendar, month_name

    cal = Calendar(firstweekday=0)
    ay_basi = localdate().replace(year=yil, month=ay, day=1)
    if ay == 12:
        ay_sonu = ay_basi.replace(year=yil + 1, month=1, day=1) - timedelta(days=1)
    else:
        ay_sonu = ay_basi.replace(month=ay + 1, day=1) - timedelta(days=1)

    olaylar = list(
        YctOlay.objects.filter(baslangic__lte=ay_sonu).filter(
            Q(bitis__gte=ay_basi) | Q(bitis__isnull=True, baslangic__gte=ay_basi)
        )
    )

    by_day: dict = defaultdict(list)
    for olay in olaylar:
        d0 = max(olay.baslangic, ay_basi)
        d1 = min(olay.bitis_efektif, ay_sonu)
        gun = d0
        while gun <= d1:
            by_day[gun.day].append(olay)
            gun += timedelta(days=1)

    weeks = []
    for week in cal.monthdayscalendar(yil, ay):
        row = []
        for day in week:
            row.append(
                {
                    "day": day or None,
                    "olaylar": by_day.get(day, []) if day else [],
                }
            )
        weeks.append(row)

    return {
        "yil": yil,
        "ay": ay,
        "ay_adi": month_name[ay],
        "weeks": weeks,
        "olaylar": olaylar,
    }
