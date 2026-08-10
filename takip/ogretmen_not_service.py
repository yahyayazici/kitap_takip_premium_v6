"""Öğretmen haftalık not + günlük yoklama — sorgu ve kayıt."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import QuerySet
from django.utils.timezone import localdate

from takip.talebe_foto_util import talebe_foto_meta
from takip.models import Ders, EtutHocasi, SinifSube, Talebe
from takip.ogretmen_not_models import (
    OgretmenHaftalikKonu,
    OgretmenSinavNotu,
    OgretmenSinifYoklama,
)
from takip.ogretmen_service import (
    HAFTA_KAPANIS_SAAT,
    _demo_siniflar,
    _hafta_araligi,
    aktif_hafta_baslangic,
    hafta_yazilabilir_mi,
)


def ogretmen_sinif_ogrencileri(hoca: EtutHocasi, sinif: SinifSube) -> list[Talebe]:
    """Sorumlu sınıftaki tüm aktif öğrenciler (etüt hocası atamasından bağımsız)."""
    if not hoca.sorumlu_sinif_subeler.filter(pk=sinif.pk, aktif=True).exists():
        return []
    return list(
        Talebe.objects.filter(
            sinif_sube=sinif,
            durum=Talebe.Durum.AKTIF,
        ).order_by("ad_soyad")
    )


def ogretmen_dersleri(hoca: EtutHocasi | None = None) -> list[Ders]:
    """Aktif dersler — öğretmenin branşı varsa yalnızca o branşın dersleri."""
    qs = Ders.objects.filter(aktif=True).select_related("brans").order_by("sira", "ad")
    if hoca is None:
        return list(qs)
    try:
        profil = hoca.odeme_profili
    except Exception:
        profil = None
    if profil and getattr(profil, "brans_id", None):
        qs = qs.filter(brans_id=profil.brans_id)
    return list(qs)


def _parse_puan(raw: str) -> Decimal | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        puan = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError("geçersiz")
    if puan < 0 or puan > 100:
        raise ValueError("aralık")
    return puan


def ogretmen_not_girisi_verisi(
    hoca: EtutHocasi,
    *,
    sinif_id: int | None = None,
    tarih: date | None = None,
    ders_id: int | None = None,
) -> dict:
    siniflar = _demo_siniflar(hoca)
    hafta_no, baslangic, bitis = _hafta_araligi()
    tarih = tarih or localdate()
    dersler = ogretmen_dersleri(hoca)
    yazilabilir = hafta_yazilabilir_mi()

    secili = None
    if sinif_id:
        secili = next((s for s in siniflar if s.id == sinif_id), None)

    secili_ders = None
    if ders_id:
        secili_ders = next((d for d in dersler if d.id == ders_id), None)
    if not secili_ders and dersler:
        secili_ders = next(
            (d for d in dersler if d.ad == "Sosyal Bilgiler"),
            dersler[0],
        )

    ogrenci_satirlari = []
    yok_ids: set[int] = set()
    islenen_konu = ""

    if secili and secili_ders:
        sinif = SinifSube.objects.filter(pk=secili.id).first()
        if sinif:
            ogrenciler = ogretmen_sinif_ogrencileri(hoca, sinif)
            mevcut_notlar = {
                n.talebe_id: n
                for n in OgretmenSinavNotu.objects.filter(
                    etut_hocasi=hoca,
                    talebe__sinif_sube=sinif,
                    ders=secili_ders,
                    hafta_baslangic=baslangic,
                )
            }
            yok_ids = set(
                OgretmenSinifYoklama.objects.filter(
                    etut_hocasi=hoca,
                    tarih=tarih,
                    yok=True,
                    talebe__sinif_sube=sinif,
                ).values_list("talebe_id", flat=True)
            )
            konu_kaydi = OgretmenHaftalikKonu.objects.filter(
                etut_hocasi=hoca,
                sinif_sube=sinif,
                ders=secili_ders,
                hafta_baslangic=baslangic,
            ).first()
            islenen_konu = konu_kaydi.konu if konu_kaydi else ""

            for ogrenci in ogrenciler:
                not_kaydi = mevcut_notlar.get(ogrenci.id)
                meta = talebe_foto_meta(ogrenci)
                ogrenci_satirlari.append(
                    {
                        "id": ogrenci.id,
                        "ad_soyad": ogrenci.ad_soyad,
                        "foto_url": meta["foto_url"],
                        "bas_harf": meta["bas_harf"],
                        "katilim": not_kaydi.katilim if not_kaydi and not_kaydi.katilim is not None else "",
                        "takip": not_kaydi.takip if not_kaydi and not_kaydi.takip is not None else "",
                        "disiplin": not_kaydi.disiplin if not_kaydi and not_kaydi.disiplin is not None else "",
                        "aciklama": not_kaydi.aciklama if not_kaydi else "",
                        "yok": ogrenci.id in yok_ids,
                    }
                )

    return {
        "hoca": hoca,
        "siniflar": siniflar,
        "secili_sinif": secili,
        "ogrenciler": ogrenci_satirlari,
        "dersler": dersler,
        "secili_ders": secili_ders,
        "islenen_konu": islenen_konu,
        "hafta_no": hafta_no,
        "hafta_baslangic": baslangic,
        "hafta_bitis": bitis,
        "bugun": tarih,
        "hafta_yazilabilir": yazilabilir,
        "hafta_kapanis_saat": HAFTA_KAPANIS_SAAT,
    }


def ogretmen_not_kaydet(
    hoca: EtutHocasi,
    sinif_id: int,
    post_data,
    *,
    tarih: date | None = None,
) -> tuple[list[str], dict | None]:
    tarih = tarih or localdate()
    hatalar: list[str] = []
    hafta_no, hafta_baslangic, _ = _hafta_araligi(tarih)

    if not hafta_yazilabilir_mi():
        return [
            f"Bu hafta kapandı. Not girişi Pazar saat {HAFTA_KAPANIS_SAAT:02d}:00’e kadar açıktır."
        ], None

    sinif = SinifSube.objects.filter(pk=sinif_id).first()
    if not sinif:
        return ["Sınıf bulunamadı."], None

    try:
        ders_id = int(post_data.get("ders_id") or 0)
    except (TypeError, ValueError):
        ders_id = 0
    izinli_ders_ids = {d.id for d in ogretmen_dersleri(hoca)}
    ders = Ders.objects.filter(pk=ders_id, aktif=True).first()
    if not ders or ders.id not in izinli_ders_ids:
        return ["Geçerli bir ders seçin (branşınıza ait ders)."], None

    ogrenciler = ogretmen_sinif_ogrencileri(hoca, sinif)
    if not ogrenciler:
        return ["Bu sınıfta kayıtlı öğrenci yok."], None

    isaretlenen_yok = {
        int(x)
        for x in post_data.getlist("yok_talebe")
        if str(x).isdigit()
    }
    konu = (post_data.get("islenen_konu") or "").strip()

    hazirlanan: list[dict] = []
    for ogrenci in ogrenciler:
        prefix = str(ogrenci.id)
        try:
            katilim = _parse_puan(post_data.get(f"katilim_{prefix}", ""))
            takip = _parse_puan(post_data.get(f"takip_{prefix}", ""))
            disiplin = _parse_puan(post_data.get(f"disiplin_{prefix}", ""))
        except ValueError as exc:
            if str(exc) == "aralık":
                hatalar.append(f"{ogrenci.ad_soyad}: Puan 0–100 arasında olmalı.")
            else:
                hatalar.append(f"{ogrenci.ad_soyad}: Geçerli puan girin.")
            continue

        aciklama = (post_data.get(f"aciklama_{prefix}") or "").strip()
        eksikler = []
        if katilim is None:
            eksikler.append("Katılım")
        if takip is None:
            eksikler.append("Takip")
        if disiplin is None:
            eksikler.append("Disiplin")
        if not aciklama:
            eksikler.append("Değerlendirme notu")
        if eksikler:
            hatalar.append(f"{ogrenci.ad_soyad}: {', '.join(eksikler)} zorunludur.")
            continue

        hazirlanan.append(
            {
                "ogrenci": ogrenci,
                "katilim": katilim,
                "takip": takip,
                "disiplin": disiplin,
                "aciklama": aciklama,
                "yok": ogrenci.id in isaretlenen_yok,
            }
        )

    if hatalar:
        return hatalar, None

    OgretmenHaftalikKonu.objects.update_or_create(
        sinif_sube=sinif,
        etut_hocasi=hoca,
        ders=ders,
        hafta_baslangic=hafta_baslangic,
        defaults={"konu": konu},
    )

    for satir in hazirlanan:
        ogrenci = satir["ogrenci"]
        if satir["yok"]:
            OgretmenSinifYoklama.objects.update_or_create(
                talebe=ogrenci,
                etut_hocasi=hoca,
                tarih=tarih,
                defaults={"yok": True},
            )
        else:
            OgretmenSinifYoklama.objects.filter(
                talebe=ogrenci,
                etut_hocasi=hoca,
                tarih=tarih,
            ).delete()

        OgretmenSinavNotu.objects.update_or_create(
            talebe_id=ogrenci.id,
            etut_hocasi=hoca,
            ders=ders,
            hafta_baslangic=hafta_baslangic,
            defaults={
                "katilim": satir["katilim"],
                "takip": satir["takip"],
                "disiplin": satir["disiplin"],
                "aciklama": satir["aciklama"],
                "veliye_goster": True,
                "tarih": hafta_baslangic,
            },
        )

    return [], {
        "kayitlar": hazirlanan,
        "ders": ders,
        "hafta_baslangic": hafta_baslangic,
        "hafta_no": hafta_no,
    }


def talebe_ogretmen_notlari(talebe: Talebe, limit: int = 20) -> QuerySet[OgretmenSinavNotu]:
    return (
        OgretmenSinavNotu.objects.filter(
            talebe=talebe,
            veliye_goster=True,
        )
        .select_related("ders", "etut_hocasi")
        .order_by("-hafta_baslangic", "-id")[:limit]
    )


def talebe_bugun_yok_mu(talebe: Talebe, tarih: date | None = None) -> bool:
    tarih = tarih or localdate()
    return OgretmenSinifYoklama.objects.filter(
        talebe=talebe,
        tarih=tarih,
        yok=True,
    ).exists()


def _not_qs_base() -> QuerySet[OgretmenSinavNotu]:
    return OgretmenSinavNotu.objects.select_related(
        "talebe",
        "talebe__sinif_sube",
        "ders",
        "etut_hocasi",
    )


def hoca_degerlendirme_qs(
    hoca: EtutHocasi,
    *,
    sinif_id: int | None = None,
    talebe_id: int | None = None,
    hafta_baslangic: date | None = None,
) -> QuerySet[OgretmenSinavNotu]:
    """Yalnızca bu öğretmenin girdiği değerlendirme kayıtları."""
    qs = _not_qs_base().filter(etut_hocasi=hoca)
    if sinif_id:
        qs = qs.filter(talebe__sinif_sube_id=sinif_id)
    if talebe_id:
        qs = qs.filter(talebe_id=talebe_id)
    if hafta_baslangic:
        qs = qs.filter(hafta_baslangic=hafta_baslangic)
    return qs.order_by("-hafta_baslangic", "talebe__ad_soyad", "ders__ad")


def admin_degerlendirme_qs(
    *,
    sinif_id: int | None = None,
    talebe_id: int | None = None,
    hoca_id: int | None = None,
    hafta_baslangic: date | None = None,
) -> QuerySet[OgretmenSinavNotu]:
    qs = _not_qs_base()
    if sinif_id:
        qs = qs.filter(talebe__sinif_sube_id=sinif_id)
    if talebe_id:
        qs = qs.filter(talebe_id=talebe_id)
    if hoca_id:
        qs = qs.filter(etut_hocasi_id=hoca_id)
    if hafta_baslangic:
        qs = qs.filter(hafta_baslangic=hafta_baslangic)
    return qs.order_by("-hafta_baslangic", "talebe__sinif_sube__sinif", "talebe__ad_soyad")


def ogretmen_haftalik_takip_ozeti(hafta_baslangic: date) -> dict:
    """Aktif branş öğretmenlerinin seçilen haftada not girip girmediği özeti."""
    from takip.ogretmen_odeme_service import aktif_ogretmenler

    hocalar = list(
        aktif_ogretmenler().prefetch_related("sorumlu_sinif_subeler")
    )
    giren_ids = set(
        OgretmenSinavNotu.objects.filter(hafta_baslangic=hafta_baslangic)
        .values_list("etut_hocasi_id", flat=True)
        .distinct()
    )
    konu_ids = set(
        OgretmenHaftalikKonu.objects.filter(hafta_baslangic=hafta_baslangic)
        .exclude(konu="")
        .values_list("etut_hocasi_id", flat=True)
        .distinct()
    )
    from django.db.models import Count

    not_sayilari = {
        row["etut_hocasi_id"]: row["adet"]
        for row in (
            OgretmenSinavNotu.objects.filter(hafta_baslangic=hafta_baslangic)
            .values("etut_hocasi_id")
            .annotate(adet=Count("id"))
        )
    }

    satirlar = []
    for hoca in hocalar:
        girdi = hoca.id in giren_ids
        brans = ""
        try:
            profil = hoca.odeme_profili
        except Exception:
            profil = None
        if profil and getattr(profil, "brans_id", None):
            brans = profil.brans.ad
        siniflar = ", ".join(
            str(s) for s in hoca.sorumlu_sinif_subeler.all() if s.aktif
        )
        satirlar.append(
            {
                "hoca": hoca,
                "brans": brans or "—",
                "siniflar": siniflar or "—",
                "girdi": girdi,
                "konu_girdi": hoca.id in konu_ids,
                "not_sayisi": not_sayilari.get(hoca.id, 0),
            }
        )

    giren = sum(1 for s in satirlar if s["girdi"])
    return {
        "hafta_baslangic": hafta_baslangic,
        "satirlar": satirlar,
        "toplam_hoca": len(satirlar),
        "giren": giren,
        "girmeyen": len(satirlar) - giren,
    }


def talebe_karne_verisi(talebe: Talebe, *, sadece_veliye_acik: bool = True) -> dict:
    qs = _not_qs_base().filter(talebe=talebe)
    if sadece_veliye_acik:
        qs = qs.filter(veliye_goster=True)
    notlar = list(qs.order_by("-hafta_baslangic", "ders__ad"))

    def _ort(alan: str) -> Decimal | None:
        degerler = [getattr(n, alan) for n in notlar if getattr(n, alan) is not None]
        if not degerler:
            return None
        return (sum(degerler) / len(degerler)).quantize(Decimal("0.01"))

    ortalama = _ort("puan")
    katilim_ort = _ort("katilim")
    takip_ort = _ort("takip")
    disiplin_ort = _ort("disiplin")
    son_not = notlar[0] if notlar else None

    return {
        "talebe": talebe,
        "notlar": notlar,
        "ortalama": ortalama,
        "katilim_ort": katilim_ort,
        "takip_ort": takip_ort,
        "disiplin_ort": disiplin_ort,
        "kayit_sayisi": len(notlar),
        "son_not": son_not,
    }


def talebe_haftalik_karne_verisi(
    talebe: Talebe,
    hafta_baslangic: date | None = None,
    *,
    sadece_veliye_acik: bool = True,
) -> dict:
    """Tek haftalık eğitim değerlendirme karnesi verisi."""
    baslangic = hafta_baslangic or aktif_hafta_baslangic()
    bitis = baslangic + timedelta(days=6)
    qs = _not_qs_base().filter(talebe=talebe, hafta_baslangic=baslangic)
    if sadece_veliye_acik:
        qs = qs.filter(veliye_goster=True)
    notlar = list(qs.order_by("ders__ad", "etut_hocasi__ad_soyad"))

    konu_map: dict[tuple[int, int], str] = {}
    if talebe.sinif_sube_id:
        for k in OgretmenHaftalikKonu.objects.filter(
            sinif_sube_id=talebe.sinif_sube_id,
            hafta_baslangic=baslangic,
        ):
            konu_map[(k.etut_hocasi_id, k.ders_id)] = (k.konu or "").strip()

    satirlar = []
    for n in notlar:
        satirlar.append(
            {
                "ogretmen": n.etut_hocasi.ad_soyad,
                "ders": n.ders.ad if n.ders_id else "—",
                "konu": konu_map.get((n.etut_hocasi_id, n.ders_id), "") or "—",
                "puan": n.puan,
                "degerlendirme": (n.aciklama or "").strip() or "—",
                "not": n,
            }
        )

    puanlar = [s["puan"] for s in satirlar if s["puan"] is not None]
    ortalama = (
        (sum(puanlar) / len(puanlar)).quantize(Decimal("0.01")) if puanlar else None
    )

    return {
        "talebe": talebe,
        "hafta_baslangic": baslangic,
        "hafta_bitis": bitis,
        "satirlar": satirlar,
        "ortalama": ortalama,
        "kayit_sayisi": len(satirlar),
    }


def etut_haftalik_karne_listesi(
    hoca: EtutHocasi,
    hafta_baslangic: date | None = None,
) -> dict:
    """Etüt hocasının talebeleri için haftalık karne özeti."""
    baslangic = hafta_baslangic or aktif_hafta_baslangic()
    bitis = baslangic + timedelta(days=6)
    talebeler = list(
        Talebe.objects.filter(etut_hocasi=hoca, aktif=True)
        .select_related("sinif_sube")
        .order_by("sinif_sube__sinif", "sinif_sube__sube", "ad_soyad")
    )
    notlar = list(
        _not_qs_base().filter(
            talebe__etut_hocasi=hoca,
            hafta_baslangic=baslangic,
            veliye_goster=True,
        )
    )
    by_talebe: dict[int, list[OgretmenSinavNotu]] = defaultdict(list)
    for n in notlar:
        by_talebe[n.talebe_id].append(n)

    arsiv_haftalar = list(
        OgretmenSinavNotu.objects.filter(
            talebe__etut_hocasi=hoca,
            veliye_goster=True,
        )
        .values_list("hafta_baslangic", flat=True)
        .distinct()
        .order_by("-hafta_baslangic")[:16]
    )

    satirlar = []
    for talebe in talebeler:
        ns = by_talebe.get(talebe.id, [])
        puanlar = [n.puan for n in ns if n.puan is not None]
        ortalama = (
            (sum(puanlar) / len(puanlar)).quantize(Decimal("0.01")) if puanlar else None
        )
        satirlar.append(
            {
                "talebe": talebe,
                "not_sayisi": len(ns),
                "ortalama": ortalama,
                "notlar": ns,
            }
        )

    aktif = aktif_hafta_baslangic()
    return {
        "hoca": hoca,
        "hafta_baslangic": baslangic,
        "hafta_bitis": bitis,
        "aktif_hafta": aktif,
        "arsiv_modu": baslangic != aktif,
        "arsiv_haftalar": arsiv_haftalar,
        "satirlar": satirlar,
        "talebe_sayisi": len(satirlar),
        "not_girilen": sum(1 for s in satirlar if s["not_sayisi"]),
    }


def hoca_degerlendirme_paneli(
    hoca: EtutHocasi,
    *,
    sinif_id: int | None = None,
    talebe_id: int | None = None,
) -> dict:
    from takip.ogretmen_service import _demo_siniflar, _hafta_araligi

    siniflar = _demo_siniflar(hoca)
    hafta_no, baslangic, bitis = _hafta_araligi()
    notlar = list(hoca_degerlendirme_qs(hoca, sinif_id=sinif_id, talebe_id=talebe_id)[:200])

    talebeler = []
    if sinif_id:
        sinif = SinifSube.objects.filter(pk=sinif_id).first()
        if sinif:
            talebeler = ogretmen_sinif_ogrencileri(hoca, sinif)
    else:
        seen = set()
        for n in notlar:
            if n.talebe_id not in seen:
                seen.add(n.talebe_id)
                talebeler.append(n.talebe)

    return {
        "hoca": hoca,
        "siniflar": siniflar,
        "secili_sinif_id": sinif_id,
        "secili_talebe_id": talebe_id,
        "talebeler": talebeler,
        "notlar": notlar,
        "hafta_no": hafta_no,
        "hafta_baslangic": baslangic,
        "hafta_bitis": bitis,
        "bugun": localdate(),
    }
