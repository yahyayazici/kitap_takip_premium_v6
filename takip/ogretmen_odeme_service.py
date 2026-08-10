"""Öğretmen ödeme — iş kuralları, hesaplama ve raporlama."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone

from takip.models import EtutHocasi, SinifSube
from takip.ogretmen_odeme_models import (
    OgretmenOdemeDersKaydi,
    OgretmenOdemeDonemi,
    OgretmenOdemeGunKaydi,
    OgretmenOdemeProfili,
)
from takip.permissions.service import can
from takip.wave0_models import Brans

PARA = Decimal("0.01")
SAAT = Decimal("0.01")


def ogretmen_odeme_finans_gorebilir(user: User) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return can(user, "ogretmen_odeme", "view_financial")


def ogretmen_odeme_girebilir(user: User) -> bool:
    return can(user, "ogretmen_odeme", "create") or can(user, "ogretmen_odeme", "edit")


def ogretmen_odeme_silebilir(user: User) -> bool:
    return can(user, "ogretmen_odeme", "delete")


def _yuvarla_saat(deger: Decimal) -> Decimal:
    return deger.quantize(SAAT, rounding=ROUND_HALF_UP)


def _yuvarla_para(deger: Decimal) -> Decimal:
    return deger.quantize(PARA, rounding=ROUND_HALF_UP)


def _tarih_araligi(baslangic: date, bitis: date) -> list[date]:
    if bitis < baslangic:
        return []
    gunler: list[date] = []
    current = baslangic
    while current <= bitis:
        gunler.append(current)
        current += timedelta(days=1)
    return gunler


def ogretmen_profili(etut_hocasi: EtutHocasi) -> OgretmenOdemeProfili:
    profil, _ = OgretmenOdemeProfili.objects.get_or_create(
        etut_hocasi=etut_hocasi,
        defaults={"saatlik_ucret": Decimal("0.00")},
    )
    return profil


def aktif_ogretmenler() -> QuerySet[EtutHocasi]:
    """Branş öğretmenleri — etüt/sınıf mesulü personel kayıtları hariç."""
    return (
        EtutHocasi.objects.filter(aktif=True, personel_kaydi__isnull=True)
        .select_related("odeme_profili", "odeme_profili__brans")
        .order_by("ad_soyad")
    )


def donem_qs() -> QuerySet[OgretmenOdemeDonemi]:
    return OgretmenOdemeDonemi.objects.select_related(
        "etut_hocasi",
        "etut_hocasi__odeme_profili",
        "etut_hocasi__odeme_profili__brans",
        "olusturan",
    )


@transaction.atomic
def donem_olustur(
    *,
    etut_hocasi: EtutHocasi,
    baslangic: date,
    bitis: date,
    user: User,
    notlar: str = "",
) -> OgretmenOdemeDonemi:
    profil = ogretmen_profili(etut_hocasi)
    donem = OgretmenOdemeDonemi.objects.create(
        etut_hocasi=etut_hocasi,
        baslangic=baslangic,
        bitis=bitis,
        saatlik_ucret=profil.saatlik_ucret,
        notlar=notlar.strip(),
        olusturan=user,
        son_duzenleyen=user,
    )
    OgretmenOdemeGunKaydi.objects.bulk_create(
        [
            OgretmenOdemeGunKaydi(donem=donem, tarih=tarih)
            for tarih in _tarih_araligi(baslangic, bitis)
        ]
    )
    return donem


def _parse_ders_satirlari(post_data) -> dict[int, list[dict]]:
    satirlar: dict[int, list[dict]] = defaultdict(list)
    prefix = "ders_"
    for key, value in post_data.items():
        if not key.startswith(prefix):
            continue
        parcalar = key.split("_")
        if len(parcalar) != 4:
            continue
        _, gun_id, idx, alan = parcalar
        if not gun_id.isdigit():
            continue
        gun_key = int(gun_id)
        idx_no = int(idx)
        while len(satirlar[gun_key]) <= idx_no:
            satirlar[gun_key].append({"sinif_sube": "", "brans": "", "saat": ""})
        satirlar[gun_key][idx_no][alan] = value.strip()
    return satirlar


def donem_matris_verisi(donem: OgretmenOdemeDonemi) -> dict:
    """Sınıf × gün matrisi — mockup arayüzü için."""
    siniflar = list(SinifSube.objects.filter(aktif=True).order_by("sinif", "sube"))
    hucre_map: dict[tuple[int, int], Decimal] = {}

    gunler = []
    for gun in donem.gunler.order_by("tarih"):
        for ders in gun.dersler.all():
            hucre_map[(gun.id, ders.sinif_sube_id)] = ders.saat
        wd = gun.tarih.weekday()
        gun_kisalt = ["PZT", "SAL", "ÇAR", "PER", "CUM", "CMT", "PAZ"][wd]
        gunler.append(
            {
                "id": gun.id,
                "tarih": gun.tarih,
                "gun_kisalt": gun_kisalt,
                "tarih_kisa": gun.tarih.strftime("%d.%m"),
                "hafta_sonu": wd in (4, 6),
                "toplam_saat": gun.toplam_saat,
            }
        )

    satirlar = []
    for sinif in siniflar:
        hucreler = []
        for gun in gunler:
            saat = hucre_map.get((gun["id"], sinif.id))
            hucreler.append(
                {
                    "gun_id": gun["id"],
                    "name": f"cell_{gun['id']}_{sinif.id}",
                    "value": "" if saat is None else str(saat).replace(".", ","),
                }
            )
        satirlar.append({"sinif": sinif, "hucreler": hucreler})

    profil = getattr(donem.etut_hocasi, "odeme_profili", None)
    brans_etiket = profil.brans.ad if profil and profil.brans_id else "—"

    return {
        "donem": donem,
        "siniflar": siniflar,
        "gunler": gunler,
        "satirlar": satirlar,
        "gun_toplamlari": [g["toplam_saat"] for g in gunler],
        "toplam_saat": donem.toplam_saat,
        "odenecek_tutar": donem.odenecek_tutar,
        "ogretmen_bas_harf": donem.etut_hocasi.ad_soyad[:2].upper(),
        "brans_etiket": brans_etiket,
        "donem_yil": f"{donem.baslangic.year}-{donem.bitis.year}",
    }


def _parse_matris_hucreleri(post_data) -> dict[tuple[int, int], Decimal]:
    hucreler: dict[tuple[int, int], Decimal] = {}
    prefix = "cell_"
    for key, value in post_data.items():
        if not key.startswith(prefix):
            continue
        parcalar = key.split("_")
        if len(parcalar) != 3:
            continue
        _, gun_id, sinif_id = parcalar
        if not gun_id.isdigit() or not sinif_id.isdigit():
            continue
        saat_raw = (value or "").replace(",", ".").strip()
        if not saat_raw:
            continue
        try:
            saat = _yuvarla_saat(Decimal(saat_raw))
        except Exception:
            continue
        if saat <= 0:
            continue
        hucreler[(int(gun_id), int(sinif_id))] = saat
    return hucreler


def _matris_kaydet(donem: OgretmenOdemeDonemi, post_data, user: User) -> None:
    hucreler = _parse_matris_hucreleri(post_data)
    gunler = {gun.id: gun for gun in donem.gunler.all()}
    profil = ogretmen_profili(donem.etut_hocasi)
    varsayilan_brans = profil.brans if profil.brans_id else None

    OgretmenOdemeDersKaydi.objects.filter(gun__donem=donem).delete()

    gun_toplam: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    yeni_kayitlar: list[OgretmenOdemeDersKaydi] = []

    for (gun_id, sinif_id), saat in hucreler.items():
        gun = gunler.get(gun_id)
        if not gun:
            continue
        yeni_kayitlar.append(
            OgretmenOdemeDersKaydi(
                gun=gun,
                sinif_sube_id=sinif_id,
                brans=varsayilan_brans,
                saat=saat,
            )
        )
        gun_toplam[gun_id] += saat

    if yeni_kayitlar:
        OgretmenOdemeDersKaydi.objects.bulk_create(yeni_kayitlar)

    for gun_id, gun in gunler.items():
        gun.toplam_saat = _yuvarla_saat(gun_toplam.get(gun_id, Decimal("0.00")))
        gun.save(update_fields=["toplam_saat"])


@transaction.atomic
def donem_kaydet(donem: OgretmenOdemeDonemi, post_data, user: User) -> OgretmenOdemeDonemi:
    if any(k.startswith("cell_") for k in post_data):
        _matris_kaydet(donem, post_data, user)
    else:
        satirlar = _parse_ders_satirlari(post_data)
        gunler = {gun.id: gun for gun in donem.gunler.all()}

        OgretmenOdemeDersKaydi.objects.filter(gun__donem=donem).delete()

        yeni_kayitlar: list[OgretmenOdemeDersKaydi] = []
        for gun_id, gun in gunler.items():
            gun_toplam = Decimal("0.00")
            for satir in satirlar.get(gun_id, []):
                sinif_id = satir.get("sinif_sube", "")
                saat_raw = satir.get("saat", "").replace(",", ".")
                if not sinif_id.isdigit() or not saat_raw:
                    continue
                try:
                    saat = _yuvarla_saat(Decimal(saat_raw))
                except Exception:
                    continue
                if saat <= 0:
                    continue
                brans_id = satir.get("brans", "")
                brans = None
                if brans_id.isdigit():
                    brans = Brans.objects.filter(pk=int(brans_id)).first()
                yeni_kayitlar.append(
                    OgretmenOdemeDersKaydi(
                        gun=gun,
                        sinif_sube_id=int(sinif_id),
                        brans=brans,
                        saat=saat,
                    )
                )
                gun_toplam += saat
            gun.toplam_saat = _yuvarla_saat(gun_toplam)
            gun.save(update_fields=["toplam_saat"])

        if yeni_kayitlar:
            OgretmenOdemeDersKaydi.objects.bulk_create(yeni_kayitlar)

    donem.notlar = post_data.get("notlar", donem.notlar or "").strip()

    if ogretmen_odeme_finans_gorebilir(user):
        ucret_raw = post_data.get("saatlik_ucret", "").replace(",", ".")
        if ucret_raw:
            try:
                donem.saatlik_ucret = _yuvarla_para(Decimal(ucret_raw))
            except Exception:
                pass

    donem_hesapla(donem)
    donem.son_duzenleyen = user
    donem.save()
    return donem


def donem_hesapla(donem: OgretmenOdemeDonemi) -> None:
    toplam = (
        donem.gunler.aggregate(toplam=Sum("toplam_saat")).get("toplam")
        or Decimal("0.00")
    )
    donem.toplam_saat = _yuvarla_saat(Decimal(toplam))
    donem.odenecek_tutar = _yuvarla_para(donem.toplam_saat * donem.saatlik_ucret)


def donem_detay_verisi(donem: OgretmenOdemeDonemi) -> dict:
    gunler = []
    for gun in donem.gunler.prefetch_related(
        "dersler__sinif_sube",
        "dersler__brans",
    ).order_by("tarih"):
        dersler = []
        for d in gun.dersler.all():
            dersler.append(
                {
                    "sinif_sube": d.sinif_sube_id,
                    "sinif_label": str(d.sinif_sube),
                    "brans": d.brans_id or "",
                    "brans_label": d.brans.ad if d.brans_id else "—",
                    "saat": str(d.saat).replace(".", ","),
                    "saat_sayi": d.saat,
                }
            )
        if not dersler:
            dersler = [{"sinif_sube": "", "sinif_label": "", "brans": "", "brans_label": "—", "saat": "", "saat_sayi": 0}]
        gunler.append(
            {
                "id": gun.id,
                "tarih": gun.tarih,
                "tarih_goster": gun.tarih.strftime("%d.%m.%Y"),
                "toplam_saat": gun.toplam_saat,
                "dersler": dersler,
                "has_kayit": any(d["saat_sayi"] for d in dersler),
            }
        )
    return {
        "donem": donem,
        "gunler": gunler,
        "toplam_saat": donem.toplam_saat,
        "odenecek_tutar": donem.odenecek_tutar,
    }


def rapor_filtreleri(request_get) -> dict[str, Any]:
    return {
        "baslangic": request_get.get("baslangic", "").strip(),
        "bitis": request_get.get("bitis", "").strip(),
        "ogretmen": request_get.get("ogretmen", "").strip(),
        "brans": request_get.get("brans", "").strip(),
        "sinif": request_get.get("sinif", "").strip(),
        "gruplama": request_get.get("gruplama", "donemlik").strip() or "donemlik",
    }


def _donem_qs_filtrele(filtre: dict[str, Any]) -> QuerySet[OgretmenOdemeDonemi]:
    qs = donem_qs()
    if filtre["baslangic"]:
        qs = qs.filter(bitis__gte=filtre["baslangic"])
    if filtre["bitis"]:
        qs = qs.filter(baslangic__lte=filtre["bitis"])
    if filtre["ogretmen"].isdigit():
        qs = qs.filter(etut_hocasi_id=int(filtre["ogretmen"]))
    if filtre["brans"].isdigit():
        qs = qs.filter(etut_hocasi__odeme_profili__brans_id=int(filtre["brans"]))
    if filtre["sinif"].isdigit():
        qs = qs.filter(gunler__dersler__sinif_sube_id=int(filtre["sinif"])).distinct()
    return qs.order_by("-baslangic", "etut_hocasi__ad_soyad")


def rapor_ozet_satirlari(filtre: dict[str, Any], *, finans: bool) -> list[dict[str, Any]]:
    gruplama = filtre.get("gruplama", "donemlik")
    if gruplama == "donemlik":
        return _rapor_donemlik(filtre, finans=finans)
    return _rapor_ders_bazli(filtre, finans=finans, gruplama=gruplama)


def _rapor_donemlik(filtre: dict, *, finans: bool) -> list[dict]:
    satirlar = []
    for donem in _donem_qs_filtrele(filtre):
        profil = getattr(donem.etut_hocasi, "odeme_profili", None)
        satir = {
            "etiket": str(donem),
            "ogretmen": donem.etut_hocasi.ad_soyad,
            "brans": profil.brans.ad if profil and profil.brans_id else "—",
            "sinif": "—",
            "baslangic": donem.baslangic,
            "bitis": donem.bitis,
            "toplam_saat": donem.toplam_saat,
            "donem_id": donem.id,
        }
        if finans:
            satir["saatlik_ucret"] = donem.saatlik_ucret
            satir["odenecek_tutar"] = donem.odenecek_tutar
        satirlar.append(satir)
    return satirlar


def _rapor_ders_bazli(filtre: dict, *, finans: bool, gruplama: str) -> list[dict]:
    ders_qs = OgretmenOdemeDersKaydi.objects.select_related(
        "gun__donem__etut_hocasi",
        "gun__donem__etut_hocasi__odeme_profili__brans",
        "sinif_sube",
        "brans",
    ).filter(gun__donem__in=_donem_qs_filtrele(filtre))

    if filtre["baslangic"]:
        ders_qs = ders_qs.filter(gun__tarih__gte=filtre["baslangic"])
    if filtre["bitis"]:
        ders_qs = ders_qs.filter(gun__tarih__lte=filtre["bitis"])

    bucket: dict[tuple, dict] = {}

    for ders in ders_qs:
        tarih = ders.gun.tarih
        if gruplama == "gunluk":
            anahtar = (tarih, ders.gun.donem.etut_hocasi_id, ders.sinif_sube_id, ders.brans_id)
            etiket = tarih.strftime("%d.%m.%Y")
        elif gruplama == "haftalik":
            hafta_bas = tarih - timedelta(days=tarih.weekday())
            anahtar = (hafta_bas, ders.gun.donem.etut_hocasi_id, ders.sinif_sube_id, ders.brans_id)
            etiket = f"Hafta · {hafta_bas:%d.%m.%Y}"
        elif gruplama == "aylik":
            ay_bas = tarih.replace(day=1)
            anahtar = (ay_bas, ders.gun.donem.etut_hocasi_id, ders.sinif_sube_id, ders.brans_id)
            etiket = tarih.strftime("%m.%Y")
        else:
            anahtar = (ders.gun.donem_id, ders.sinif_sube_id, ders.brans_id)
            etiket = str(ders.gun.donem)

        if anahtar not in bucket:
            profil = getattr(ders.gun.donem.etut_hocasi, "odeme_profili", None)
            brans_etiket = "—"
            if ders.brans_id:
                brans_etiket = ders.brans.ad
            elif profil and profil.brans_id:
                brans_etiket = profil.brans.ad
            bucket[anahtar] = {
                "etiket": etiket,
                "ogretmen": ders.gun.donem.etut_hocasi.ad_soyad,
                "brans": brans_etiket,
                "sinif": str(ders.sinif_sube),
                "toplam_saat": Decimal("0.00"),
                "saatlik_ucret": ders.gun.donem.saatlik_ucret,
                "donem_id": ders.gun.donem_id,
            }
        bucket[anahtar]["toplam_saat"] += ders.saat

    satirlar = []
    for veri in bucket.values():
        veri["toplam_saat"] = _yuvarla_saat(veri["toplam_saat"])
        if finans:
            veri["odenecek_tutar"] = _yuvarla_para(
                veri["toplam_saat"] * veri["saatlik_ucret"]
            )
        else:
            veri.pop("saatlik_ucret", None)
        satirlar.append(veri)

    satirlar.sort(key=lambda s: (s.get("ogretmen", ""), s.get("etiket", "")))
    return satirlar


def rapor_istatistik(satirlar: list[dict], *, finans: bool) -> dict:
    toplam_saat = sum(
        (s.get("toplam_saat") or Decimal("0") for s in satirlar),
        Decimal("0"),
    )
    stats = {
        "kayit_sayisi": len(satirlar),
        "toplam_saat": _yuvarla_saat(toplam_saat),
    }
    if finans:
        stats["toplam_odeme"] = _yuvarla_para(
            sum(
                (s.get("odenecek_tutar") or Decimal("0") for s in satirlar),
                Decimal("0"),
            )
        )
    return stats


def rapor_excel_yanit(satirlar: list[dict], *, finans: bool) -> BytesIO:
    from takip.excel_rapor import basit_rapor_xlsx

    kolonlar = ["Dönem / Grup", "Ad-Soyad", "Branş", "Sınıf", "Toplam Saat"]
    if finans:
        kolonlar.extend(["Saatlik Ücret", "Ödenecek Tutar"])
    rows = []
    for satir in satirlar:
        row = [
            satir.get("etiket", ""),
            (satir.get("ogretmen") or "").upper(),
            satir.get("brans", "—"),
            satir.get("sinif", "—"),
            float(satir.get("toplam_saat") or 0),
        ]
        if finans:
            row.extend(
                [
                    float(satir.get("saatlik_ucret") or 0),
                    float(satir.get("odenecek_tutar") or 0),
                ]
            )
        rows.append(row)
    ortala = [2, 3, 4]
    vurgu = []
    genislikler = [22, 26, 14, 12, 12]
    if finans:
        ortala.extend([5, 6])
        vurgu = [6]
        genislikler.extend([14, 14])
    icerik = basit_rapor_xlsx(
        baslik="Öğretmen Ödeme Raporu",
        kolon_basliklari=kolonlar,
        satirlar=rows,
        sayfa_adi="Ödeme",
        ortala_kolonlari=ortala,
        vurgu_kolonlari=vurgu,
        genislikler=genislikler,
    )
    return BytesIO(icerik)


def seed_ogretmen_odeme_demo() -> None:
    hoca = EtutHocasi.objects.filter(aktif=True).first()
    sinif = SinifSube.objects.filter(aktif=True).first()
    if not hoca or not sinif:
        return
    profil = ogretmen_profili(hoca)
    if profil.saatlik_ucret <= 0:
        profil.saatlik_ucret = Decimal("350.00")
        brans = Brans.objects.filter(aktif=True).first()
        if brans:
            profil.brans = brans
        profil.save()

    if OgretmenOdemeDonemi.objects.filter(etut_hocasi=hoca).exists():
        return

    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(is_superuser=True).first()
    if not user:
        return

    bitis = timezone.localdate()
    baslangic = bitis - timedelta(days=6)
    donem = donem_olustur(
        etut_hocasi=hoca,
        baslangic=baslangic,
        bitis=bitis,
        user=user,
    )
    gun = donem.gunler.first()
    if gun:
        OgretmenOdemeDersKaydi.objects.create(
            gun=gun,
            sinif_sube=sinif,
            brans=profil.brans,
            saat=Decimal("3.00"),
        )
        gun.toplam_saat = Decimal("3.00")
        gun.save(update_fields=["toplam_saat"])
        donem_hesapla(donem)
        donem.save()
