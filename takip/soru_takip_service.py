"""Günlük soru takip sorguları ve yardımcılar."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import QuerySet, Sum
from django.utils.timezone import localdate

from takip.models import Ders, GunlukSoruDersSatiri, GunlukSoruKaydi, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can

SORU_TAKIP_DERS_ADLARI: tuple[str, ...] = (
    "Türkçe",
    "Paragraf",
    "Matematik",
    "Fen Bilimleri",
    "Sosyal Bilgiler",
    "İngilizce",
    "Din Kültürü",
)


def soru_takip_dersleri() -> list[Ders]:
    dersler = list(
        Ders.objects.filter(ad__in=SORU_TAKIP_DERS_ADLARI, aktif=True).order_by(
            "sira", "ad"
        )
    )
    sira = {ad: i for i, ad in enumerate(SORU_TAKIP_DERS_ADLARI)}
    dersler.sort(key=lambda d: sira.get(d.ad, 99))
    return dersler


def seed_soru_takip_dersleri() -> None:
    brans_map = {
        "Türkçe": "Türkçe",
        "Paragraf": "Türkçe",
        "Matematik": "Matematik",
        "Fen Bilimleri": "Fen",
        "Sosyal Bilgiler": "Sosyal",
        "İngilizce": "Türkçe",
        "Din Kültürü": "Din",
    }
    from takip.models import Brans

    for sira, ad in enumerate(SORU_TAKIP_DERS_ADLARI, start=1):
        brans, _ = Brans.objects.get_or_create(
            ad=brans_map.get(ad, "Türkçe"),
            defaults={"sira": sira, "aktif": True},
        )
        Ders.objects.get_or_create(
            ad=ad,
            defaults={"brans": brans, "sira": sira, "aktif": True},
        )


def yetkili_soru_kayitlari(user: User) -> QuerySet[GunlukSoruKaydi]:
    if not can(user, "soru_takip", "view"):
        return GunlukSoruKaydi.objects.none()

    qs = GunlukSoruKaydi.objects.select_related(
        "talebe", "talebe__sinif_sube", "talebe__etut_hocasi", "kaydeden"
    ).prefetch_related("ders_satirlari__ders")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def kayit_duzenleyebilir(user: User, kayit: GunlukSoruKaydi) -> bool:
    if not can(user, "soru_takip", "edit"):
        return False
    return yetkili_soru_kayitlari(user).filter(pk=kayit.pk).exists()


def kayit_silebilir(user: User, kayit: GunlukSoruKaydi) -> bool:
    if not can(user, "soru_takip", "delete"):
        return False
    return yetkili_soru_kayitlari(user).filter(pk=kayit.pk).exists()


def aylik_ozet(talebe: Talebe, referans: date | None = None) -> dict:
    referans = referans or localdate()
    baslangic = referans.replace(day=1)
    bitis = referans.replace(day=monthrange(referans.year, referans.month)[1])

    kayitlar = GunlukSoruKaydi.objects.filter(
        talebe=talebe,
        tarih__gte=baslangic,
        tarih__lte=bitis,
    )
    satirlar = GunlukSoruDersSatiri.objects.filter(kayit__in=kayitlar)
    agg = satirlar.aggregate(
        toplam_soru=Sum("toplam_soru"),
        dogru=Sum("dogru"),
        net=Sum("net"),
    )
    toplam_soru = int(agg["toplam_soru"] or 0)
    dogru = int(agg["dogru"] or 0)
    net = agg["net"] or Decimal("0")

    basari = Decimal("0.00")
    if toplam_soru > 0:
        basari = (Decimal(dogru) * Decimal("100") / Decimal(toplam_soru)).quantize(
            Decimal("0.01")
        )

    return {
        "toplam_soru": toplam_soru,
        "toplam_net": Decimal(net).quantize(Decimal("0.01")),
        "basari_orani": basari,
        "gun_sayisi": kayitlar.count(),
    }


def haftalik_ozet(talebe: Talebe, referans: date | None = None) -> dict:
    referans = referans or localdate()
    baslangic = referans - timedelta(days=6)

    kayitlar = GunlukSoruKaydi.objects.filter(
        talebe=talebe,
        tarih__gte=baslangic,
        tarih__lte=referans,
    )
    satirlar = GunlukSoruDersSatiri.objects.filter(kayit__in=kayitlar)
    agg = satirlar.aggregate(
        toplam_soru=Sum("toplam_soru"),
        dogru=Sum("dogru"),
        net=Sum("net"),
    )
    toplam_soru = int(agg["toplam_soru"] or 0)
    dogru = int(agg["dogru"] or 0)
    net = agg["net"] or Decimal("0")

    basari = Decimal("0.00")
    if toplam_soru > 0:
        basari = (Decimal(dogru) * Decimal("100") / Decimal(toplam_soru)).quantize(
            Decimal("0.01")
        )

    return {
        "baslangic": baslangic,
        "bitis": referans,
        "toplam_soru": toplam_soru,
        "toplam_net": Decimal(net).quantize(Decimal("0.01")),
        "basari_orani": basari,
        "gun_sayisi": kayitlar.count(),
    }


def yillik_ozet(talebe: Talebe, yil: int | None = None) -> dict:
    yil = yil or localdate().year
    baslangic = date(yil, 1, 1)
    bitis = date(yil, 12, 31)

    kayitlar = GunlukSoruKaydi.objects.filter(
        talebe=talebe,
        tarih__gte=baslangic,
        tarih__lte=bitis,
    )
    satirlar = GunlukSoruDersSatiri.objects.filter(kayit__in=kayitlar)
    agg = satirlar.aggregate(
        toplam_soru=Sum("toplam_soru"),
        dogru=Sum("dogru"),
        net=Sum("net"),
    )
    toplam_soru = int(agg["toplam_soru"] or 0)
    dogru = int(agg["dogru"] or 0)
    net = agg["net"] or Decimal("0")

    basari = Decimal("0.00")
    if toplam_soru > 0:
        basari = (Decimal(dogru) * Decimal("100") / Decimal(toplam_soru)).quantize(
            Decimal("0.01")
        )

    return {
        "yil": yil,
        "baslangic": baslangic,
        "bitis": bitis,
        "toplam_soru": toplam_soru,
        "toplam_net": Decimal(net).quantize(Decimal("0.01")),
        "basari_orani": basari,
        "gun_sayisi": kayitlar.count(),
    }


def _parse_rapor_tarih(deger: str | None) -> date | None:
    if not deger:
        return None
    try:
        return datetime.strptime(deger, "%Y-%m-%d").date()
    except ValueError:
        return None


def rapor_filtre_dict(request) -> dict[str, str]:
    return {
        "talebe": (request.GET.get("talebe") or "").strip(),
        "ders": (request.GET.get("ders") or "").strip(),
        "donem": (request.GET.get("donem") or "aylik").strip(),
        "referans": (request.GET.get("referans") or "").strip(),
        "baslangic": (request.GET.get("baslangic") or "").strip(),
        "bitis": (request.GET.get("bitis") or "").strip(),
    }


DONEM_ETIKETLERI = {
    "gunluk": "Günlük Rapor",
    "haftalik": "Haftalık Rapor",
    "aylik": "Aylık Rapor",
    "yillik": "Yıllık Rapor",
    "ozel": "Özel Dönem Raporu",
}


def rapor_donemi_coz(filtre: dict[str, str]) -> tuple[date, date, str]:
    referans = _parse_rapor_tarih(filtre.get("referans")) or localdate()
    donem = filtre.get("donem") or "aylik"

    if donem == "ozel":
        bas = _parse_rapor_tarih(filtre.get("baslangic"))
        bit = _parse_rapor_tarih(filtre.get("bitis"))
        if bas and bit:
            if bas > bit:
                bas, bit = bit, bas
            return bas, bit, DONEM_ETIKETLERI["ozel"]
        if bas:
            return bas, localdate(), DONEM_ETIKETLERI["ozel"]
        if bit:
            return bit.replace(day=1), bit, DONEM_ETIKETLERI["ozel"]

    if donem == "gunluk":
        return referans, referans, DONEM_ETIKETLERI["gunluk"]
    if donem == "haftalik":
        return referans - timedelta(days=6), referans, DONEM_ETIKETLERI["haftalik"]
    if donem == "yillik":
        return (
            date(referans.year, 1, 1),
            date(referans.year, 12, 31),
            DONEM_ETIKETLERI["yillik"],
        )

    baslangic = referans.replace(day=1)
    bitis = referans.replace(day=monthrange(referans.year, referans.month)[1])
    return baslangic, bitis, DONEM_ETIKETLERI["aylik"]


def rapor_kayitlari(
    user: User,
    filtre: dict[str, str],
) -> tuple[QuerySet[GunlukSoruKaydi], date, date, str]:
    baslangic, bitis, donem_baslik = rapor_donemi_coz(filtre)
    qs = yetkili_soru_kayitlari(user).filter(
        tarih__gte=baslangic,
        tarih__lte=bitis,
    )
    if filtre.get("talebe"):
        qs = qs.filter(talebe_id=filtre["talebe"])
    if filtre.get("ders"):
        qs = qs.filter(ders_satirlari__ders_id=filtre["ders"]).distinct()
    return qs.order_by("-tarih", "talebe__ad_soyad"), baslangic, bitis, donem_baslik


def _rapor_ders_satirlari(
    kayitlar: QuerySet[GunlukSoruKaydi],
    ders_id: str | None = None,
):
    qs = GunlukSoruDersSatiri.objects.filter(kayit__in=kayitlar).select_related(
        "ders"
    )
    if ders_id:
        qs = qs.filter(ders_id=ders_id)
    return qs


def rapor_istatistik(
    kayitlar: QuerySet[GunlukSoruKaydi],
    *,
    ders_id: str | None = None,
) -> dict:
    satirlar = _rapor_ders_satirlari(kayitlar, ders_id)
    agg = satirlar.aggregate(
        toplam_soru=Sum("toplam_soru"),
        dogru=Sum("dogru"),
        yanlis=Sum("yanlis"),
        bos=Sum("bos"),
        net=Sum("net"),
    )
    toplam_soru = int(agg["toplam_soru"] or 0)
    dogru = int(agg["dogru"] or 0)
    yanlis = int(agg["yanlis"] or 0)
    bos = int(agg["bos"] or 0)
    net = agg["net"] or Decimal("0")

    basari = Decimal("0.00")
    if toplam_soru > 0:
        basari = (Decimal(dogru) * Decimal("100") / Decimal(toplam_soru)).quantize(
            Decimal("0.01")
        )

    return {
        "toplam_soru": toplam_soru,
        "dogru": dogru,
        "yanlis": yanlis,
        "bos": bos,
        "toplam_net": Decimal(net).quantize(Decimal("0.01")),
        "basari_orani": basari,
        "kayit_sayisi": kayitlar.count(),
        "talebe_sayisi": kayitlar.values("talebe_id").distinct().count(),
    }


def rapor_ders_ozeti(
    kayitlar: QuerySet[GunlukSoruKaydi],
    *,
    ders_id: str | None = None,
) -> list[dict]:
    satirlar = _rapor_ders_satirlari(kayitlar, ders_id)
    rows = []
    for item in (
        satirlar.values("ders__ad")
        .annotate(
            toplam_soru=Sum("toplam_soru"),
            dogru=Sum("dogru"),
            yanlis=Sum("yanlis"),
            bos=Sum("bos"),
            net=Sum("net"),
        )
        .order_by("ders__ad")
    ):
        toplam = int(item["toplam_soru"] or 0)
        dogru = int(item["dogru"] or 0)
        basari = Decimal("0.00")
        if toplam > 0:
            basari = (Decimal(dogru) * Decimal("100") / Decimal(toplam)).quantize(
                Decimal("0.01")
            )
        rows.append(
            {
                "ders": item["ders__ad"],
                "toplam_soru": toplam,
                "dogru": dogru,
                "yanlis": int(item["yanlis"] or 0),
                "bos": int(item["bos"] or 0),
                "net": Decimal(item["net"] or 0).quantize(Decimal("0.01")),
                "basari_orani": basari,
            }
        )
    return rows


def rapor_talebe_satirlari(
    kayitlar: QuerySet[GunlukSoruKaydi],
    *,
    ders_id: str | None = None,
) -> list[dict]:
    satirlar = _rapor_ders_satirlari(kayitlar, ders_id)
    rows = []
    for item in (
        satirlar.values(
            "kayit__talebe_id",
            "kayit__talebe__ad_soyad",
            "kayit__talebe__sinif",
            "kayit__talebe__sube",
        )
        .annotate(
            toplam_soru=Sum("toplam_soru"),
            dogru=Sum("dogru"),
            net=Sum("net"),
        )
        .order_by("kayit__talebe__ad_soyad")
    ):
        toplam = int(item["toplam_soru"] or 0)
        dogru = int(item["dogru"] or 0)
        basari = Decimal("0.00")
        if toplam > 0:
            basari = (Decimal(dogru) * Decimal("100") / Decimal(toplam)).quantize(
                Decimal("0.01")
            )
        sinif = item["kayit__talebe__sinif"] or ""
        sube = item["kayit__talebe__sube"] or ""
        sinif_goster = f"{sinif}-{sube}" if sinif and sube else sinif or "—"
        rows.append(
            {
                "talebe_id": item["kayit__talebe_id"],
                "ad_soyad": item["kayit__talebe__ad_soyad"],
                "sinif_goster": sinif_goster,
                "toplam_soru": toplam,
                "toplam_net": Decimal(item["net"] or 0).quantize(Decimal("0.01")),
                "basari_orani": basari,
                "gun_sayisi": kayitlar.filter(
                    talebe_id=item["kayit__talebe_id"]
                ).count(),
            }
        )
    return rows


def rapor_filtre_etiketleri(
    filtre: dict[str, str],
    *,
    talebeler,
    dersler,
    baslangic: date,
    bitis: date,
) -> dict[str, str]:
    talebe_etiket = "Tüm talebeler"
    if filtre.get("talebe"):
        for talebe in talebeler:
            if str(talebe.id) == str(filtre["talebe"]):
                talebe_etiket = talebe.ad_soyad
                break

    ders_etiket = "Tüm dersler"
    if filtre.get("ders"):
        for ders in dersler:
            if str(ders.id) == str(filtre["ders"]):
                ders_etiket = ders.ad
                break

    if baslangic == bitis:
        tarih_goster = baslangic.strftime("%d.%m.%Y")
    else:
        tarih_goster = f"{baslangic:%d.%m.%Y} – {bitis:%d.%m.%Y}"

    return {
        "talebe": talebe_etiket,
        "ders": ders_etiket,
        "donem": DONEM_ETIKETLERI.get(filtre.get("donem") or "aylik", "Rapor"),
        "tarih": tarih_goster,
    }


def rapor_pdf_baglami(
    user: User,
    filtre: dict[str, str],
    *,
    limit: int = 300,
) -> dict:
    kayitlar, baslangic, bitis, donem_baslik = rapor_kayitlari(user, filtre)
    talebeler = list(yetkili_talebeler(user).order_by("ad_soyad"))
    dersler = soru_takip_dersleri()
    ders_id = filtre.get("ders") or None

    talebe = None
    if filtre.get("talebe"):
        talebe = next((t for t in talebeler if str(t.id) == str(filtre["talebe"])), None)

    kayit_list = list(kayitlar[:limit])
    istatistik = rapor_istatistik(kayitlar, ders_id=ders_id)
    ders_ozeti = rapor_ders_ozeti(kayitlar, ders_id=ders_id)
    talebe_satirlari = rapor_talebe_satirlari(kayitlar, ders_id=ders_id)

    return {
        "talebe": talebe,
        "kayitlar": kayit_list,
        "istatistik": istatistik,
        "ders_ozeti": ders_ozeti,
        "talebe_satirlari": talebe_satirlari,
        "filtre": rapor_filtre_etiketleri(
            filtre,
            talebeler=talebeler,
            dersler=dersler,
            baslangic=baslangic,
            bitis=bitis,
        ),
        "donem_baslik": donem_baslik,
        "baslangic": baslangic,
        "bitis": bitis,
        "bireysel": talebe is not None,
    }


def gunluk_ozet(kayit: GunlukSoruKaydi | None) -> dict:
    if not kayit:
        return {
            "toplam_soru": 0,
            "toplam_net": Decimal("0.00"),
            "basari_orani": Decimal("0.00"),
        }

    return {
        "toplam_soru": kayit.toplam_soru,
        "toplam_net": kayit.toplam_net,
        "basari_orani": kayit.basari_orani,
    }


def kayit_satirlari_form_verisi(
    kayit: GunlukSoruKaydi | None,
    dersler: list[Ders],
) -> list[dict]:
    mevcut = {}
    if kayit:
        mevcut = {s.ders_id: s for s in kayit.ders_satirlari.all()}

    satirlar = []
    for ders in dersler:
        s = mevcut.get(ders.id)
        satirlar.append(
            {
                "ders": ders,
                "toplam_soru": s.toplam_soru if s else 0,
                "dogru": s.dogru if s else 0,
                "yanlis": s.yanlis if s else 0,
                "bos": s.bos if s else 0,
                "net": s.net if s else Decimal("0.00"),
            }
        )
    return satirlar


def kayit_kaydet(
    user: User,
    talebe: Talebe,
    tarih: date,
    dersler: list[Ders],
    post_data,
    *,
    gunluk_not: str = "",
) -> tuple[GunlukSoruKaydi | None, list[str]]:
    hatalar: list[str] = []

    kayit, _ = GunlukSoruKaydi.objects.get_or_create(
        talebe=talebe,
        tarih=tarih,
        defaults={"kaydeden": user},
    )
    kayit.gunluk_not = gunluk_not
    kayit.kaydeden = user
    kayit.save()

    for ders in dersler:
        prefix = f"ders_{ders.id}"
        try:
            toplam = int(post_data.get(f"{prefix}_toplam", 0) or 0)
            dogru = int(post_data.get(f"{prefix}_dogru", 0) or 0)
            yanlis = int(post_data.get(f"{prefix}_yanlis", 0) or 0)
            bos = int(post_data.get(f"{prefix}_bos", 0) or 0)
        except (TypeError, ValueError):
            hatalar.append(f"{ders.ad}: Geçerli sayılar girin.")
            continue

        if toplam == 0 and dogru == 0 and yanlis == 0 and bos == 0:
            GunlukSoruDersSatiri.objects.filter(kayit=kayit, ders=ders).delete()
            continue

        if dogru + yanlis + bos != toplam:
            hatalar.append(
                f"{ders.ad}: Doğru + yanlış + boş = {toplam} olmalı."
            )
            continue

        try:
            satir, _ = GunlukSoruDersSatiri.objects.update_or_create(
                kayit=kayit,
                ders=ders,
                defaults={
                    "toplam_soru": toplam,
                    "dogru": dogru,
                    "yanlis": yanlis,
                    "bos": bos,
                },
            )
            satir.save()
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for msgs in exc.message_dict.values():
                    hatalar.extend(msgs)
            elif hasattr(exc, "messages"):
                hatalar.extend(exc.messages)
            else:
                hatalar.append(str(exc))

    if hatalar:
        return None, hatalar

    return kayit, []


def ktt_sonucu_soru_takibe_yansit(
    *,
    user: User,
    ktt,
    talebe: Talebe,
    dogru: int = 0,
    yanlis: int = 0,
    bos: int = 0,
    onceki_dogru: int = 0,
    onceki_yanlis: int = 0,
    onceki_bos: int = 0,
    silindi: bool = False,
) -> None:
    """
    KTT sonucunu talebenin günlük soru takibine yansıtır.

    Aynı KTT tekrar kaydedilirse önceki KTT katkısı düşülüp yenisi eklenir
    (çift sayım olmaz). Sınav tarihindeki ilgili ders satırına işlenir.
    """
    ders = getattr(ktt, "ders", None)
    tarih = getattr(ktt, "sinav_tarihi", None)
    if ders is None or tarih is None:
        return

    kayit, _ = GunlukSoruKaydi.objects.get_or_create(
        talebe=talebe,
        tarih=tarih,
        defaults={"kaydeden": user},
    )

    not_ek = f"KTT: {ktt.ad}"
    mevcut_not = (kayit.gunluk_not or "").strip()
    if not_ek not in mevcut_not:
        kayit.gunluk_not = f"{mevcut_not}\n{not_ek}".strip() if mevcut_not else not_ek
    kayit.kaydeden = user
    kayit.save(update_fields=["gunluk_not", "kaydeden", "guncellenme"])

    satir = GunlukSoruDersSatiri.objects.filter(kayit=kayit, ders=ders).first()
    cur_d = int(satir.dogru or 0) if satir else 0
    cur_y = int(satir.yanlis or 0) if satir else 0
    cur_b = int(satir.bos or 0) if satir else 0

    yeni_d = max(0, cur_d - int(onceki_dogru or 0))
    yeni_y = max(0, cur_y - int(onceki_yanlis or 0))
    yeni_b = max(0, cur_b - int(onceki_bos or 0))
    if not silindi:
        yeni_d += int(dogru or 0)
        yeni_y += int(yanlis or 0)
        yeni_b += int(bos or 0)

    yeni_toplam = yeni_d + yeni_y + yeni_b
    if yeni_toplam <= 0:
        if satir:
            satir.delete()
        return

    GunlukSoruDersSatiri.objects.update_or_create(
        kayit=kayit,
        ders=ders,
        defaults={
            "toplam_soru": yeni_toplam,
            "dogru": yeni_d,
            "yanlis": yeni_y,
            "bos": yeni_b,
        },
    )


def deneme_sonucu_soru_takibe_yansit(
    *,
    user: User,
    deneme,
    sonuc,
) -> None:
    """
    Deneme branş sonuçlarını sınav tarihindeki günlük soru takibine ekler.

    KTT ile aynı mantık: aynı günün ilgili ders satırına D/Y/B eklenir.
    """
    from takip.deneme_service import DENEME_BRANS_DERS_MAP, DENEME_DETAY_BRANSLAR

    tarih = getattr(deneme, "sinav_tarihi", None)
    talebe = getattr(sonuc, "talebe", None)
    if tarih is None or talebe is None:
        return

    kayit, _ = GunlukSoruKaydi.objects.get_or_create(
        talebe=talebe,
        tarih=tarih,
        defaults={"kaydeden": user},
    )

    not_ek = f"Deneme: {deneme.ad}"
    mevcut_not = (kayit.gunluk_not or "").strip()
    if not_ek not in mevcut_not:
        kayit.gunluk_not = f"{mevcut_not}\n{not_ek}".strip() if mevcut_not else not_ek
    kayit.kaydeden = user
    kayit.save(update_fields=["gunluk_not", "kaydeden", "guncellenme"])

    brans_map = {b.brans: b for b in sonuc.brans_satirlari.all()}

    for kod in DENEME_DETAY_BRANSLAR:
        brans_satir = brans_map.get(kod)
        if not brans_satir:
            continue

        ders_ad = DENEME_BRANS_DERS_MAP.get(kod)
        if not ders_ad:
            continue

        ders = Ders.objects.filter(ad=ders_ad, aktif=True).first()
        if not ders:
            continue

        dogru = int(brans_satir.dogru or 0)
        yanlis = int(brans_satir.yanlis or 0)
        bos = int(brans_satir.bos or 0)
        toplam = dogru + yanlis + bos
        if toplam <= 0:
            continue

        satir = GunlukSoruDersSatiri.objects.filter(kayit=kayit, ders=ders).first()
        cur_d = int(satir.dogru or 0) if satir else 0
        cur_y = int(satir.yanlis or 0) if satir else 0
        cur_b = int(satir.bos or 0) if satir else 0

        yeni_d = cur_d + dogru
        yeni_y = cur_y + yanlis
        yeni_b = cur_b + bos
        yeni_toplam = yeni_d + yeni_y + yeni_b

        GunlukSoruDersSatiri.objects.update_or_create(
            kayit=kayit,
            ders=ders,
            defaults={
                "toplam_soru": yeni_toplam,
                "dogru": yeni_d,
                "yanlis": yeni_y,
                "bos": yeni_b,
            },
        )
