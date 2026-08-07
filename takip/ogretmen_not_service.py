"""Öğretmen sınav notu — sorgu ve kayıt."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import QuerySet
from django.utils.timezone import localdate

from takip.models import Ders, EtutHocasi, SinifSube, Talebe
from takip.ogretmen_not_models import OgretmenSinavNotu
from takip.ogretmen_service import _demo_siniflar, _hafta_araligi


def ogretmen_sinif_ogrencileri(hoca: EtutHocasi, sinif: SinifSube) -> list[Talebe]:
    return list(
        Talebe.objects.filter(
            sinif_sube=sinif,
            etut_hocasi=hoca,
            durum=Talebe.Durum.AKTIF,
        ).order_by("ad_soyad")
    )


def ogretmen_dersleri() -> list[Ders]:
    return list(Ders.objects.filter(aktif=True).order_by("sira", "ad"))


def sinif_notlari_for_tarih(
    hoca: EtutHocasi,
    sinif: SinifSube,
    tarih: date,
    ders: Ders | None = None,
) -> dict[int, OgretmenSinavNotu]:
    qs = OgretmenSinavNotu.objects.filter(
        etut_hocasi=hoca,
        talebe__sinif_sube=sinif,
        tarih=tarih,
    ).select_related("talebe", "ders")
    if ders:
        qs = qs.filter(ders=ders)
    return {n.talebe_id: n for n in qs}


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
    dersler = ogretmen_dersleri()

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

    ogrenciler = []
    mevcut_notlar: dict[int, OgretmenSinavNotu] = {}
    if secili:
        sinif = SinifSube.objects.filter(pk=secili.id).first()
        if sinif:
            ogrenciler = ogretmen_sinif_ogrencileri(hoca, sinif)
            if secili_ders:
                mevcut_notlar = sinif_notlari_for_tarih(hoca, sinif, tarih, secili_ders)

    ogrenci_satirlari = []
    for ogrenci in ogrenciler:
        not_kaydi = mevcut_notlar.get(ogrenci.id)
        ogrenci_satirlari.append(
            {
                "id": ogrenci.id,
                "ad_soyad": ogrenci.ad_soyad,
                "tur": not_kaydi.tur if not_kaydi else OgretmenSinavNotu.Tur.YAZILI,
                "puan": not_kaydi.puan if not_kaydi else "",
                "aciklama": not_kaydi.aciklama if not_kaydi else "",
            }
        )

    return {
        "hoca": hoca,
        "siniflar": siniflar,
        "secili_sinif": secili,
        "ogrenciler": ogrenci_satirlari,
        "dersler": dersler,
        "secili_ders": secili_ders,
        "hafta_no": hafta_no,
        "hafta_baslangic": baslangic,
        "hafta_bitis": bitis,
        "bugun": tarih,
    }


def ogretmen_not_kaydet(
    hoca: EtutHocasi,
    sinif_id: int,
    post_data,
    *,
    tarih: date | None = None,
) -> list[str]:
    tarih = tarih or localdate()
    hatalar: list[str] = []

    sinif = SinifSube.objects.filter(pk=sinif_id).first()
    if not sinif:
        return ["Sınıf bulunamadı."]

    try:
        ders_id = int(post_data.get("ders_id") or 0)
    except (TypeError, ValueError):
        ders_id = 0
    ders = Ders.objects.filter(pk=ders_id, aktif=True).first()
    if not ders:
        return ["Geçerli bir ders seçin."]

    ogrenciler = ogretmen_sinif_ogrencileri(hoca, sinif)
    ogrenci_ids = {o.id for o in ogrenciler}

    for ogrenci in ogrenciler:
        prefix = str(ogrenci.id)
        tur = post_data.get(f"tur_{prefix}", OgretmenSinavNotu.Tur.YAZILI)
        if tur not in OgretmenSinavNotu.Tur.values:
            tur = OgretmenSinavNotu.Tur.YAZILI

        puan_raw = (post_data.get(f"puan_{prefix}") or "").strip()
        aciklama = (post_data.get(f"aciklama_{prefix}") or "").strip()

        if not puan_raw and not aciklama:
            OgretmenSinavNotu.objects.filter(
                talebe_id=ogrenci.id,
                etut_hocasi=hoca,
                ders=ders,
                tarih=tarih,
            ).delete()
            continue

        if not puan_raw:
            hatalar.append(f"{ogrenci.ad_soyad}: Puan girin veya satırı boş bırakın.")
            continue

        try:
            puan = Decimal(puan_raw.replace(",", "."))
        except (InvalidOperation, ValueError):
            hatalar.append(f"{ogrenci.ad_soyad}: Geçerli puan girin.")
            continue

        if puan < 0 or puan > 100:
            hatalar.append(f"{ogrenci.ad_soyad}: Puan 0–100 arasında olmalı.")
            continue

        OgretmenSinavNotu.objects.update_or_create(
            talebe_id=ogrenci.id,
            etut_hocasi=hoca,
            ders=ders,
            tarih=tarih,
            defaults={
                "tur": tur,
                "puan": puan,
                "aciklama": aciklama,
                "veliye_goster": True,
            },
        )

    # Güvenlik: yalnızca sınıftaki öğrenciler işlendi
    _ = ogrenci_ids
    return hatalar


def talebe_ogretmen_notlari(talebe: Talebe, limit: int = 20) -> QuerySet[OgretmenSinavNotu]:
    return (
        OgretmenSinavNotu.objects.filter(
            talebe=talebe,
            veliye_goster=True,
        )
        .select_related("ders", "etut_hocasi")
        .order_by("-tarih", "-id")[:limit]
    )
