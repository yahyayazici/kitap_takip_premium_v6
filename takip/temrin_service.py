"""KTT sorguları ve yardımcılar."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Avg, Count, Max, QuerySet
from django.utils.timezone import localdate

from takip.models import Ders, EtutHocasi, KttSinav, KttSonucu, SinifSube, Talebe
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user


def _etut_hocasi(user: User) -> EtutHocasi | None:
    return etut_hocasi_for_user(user)


def ktt_tam_yetki(user: User) -> bool:
    return user.is_superuser or can(user, "ktt", "delete")


def yetkili_ktt_sinavlari(user: User) -> QuerySet[KttSinav]:
    from takip.permissions.scope import tum_talebe_kapsami_var

    qs = (
        KttSinav.objects.filter(aktif=True)
        .select_related("ders", "ders__brans", "etut_hocasi", "olusturan")
        .annotate(sonuc_sayisi=Count("sonuclar"))
    )

    if not can(user, "ktt", "view"):
        return KttSinav.objects.none()

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    hoca = _etut_hocasi(user)
    if hoca:
        return qs.filter(etut_hocasi=hoca)

    return KttSinav.objects.none()


def ktt_olusturabilir(user: User) -> bool:
    return can(user, "ktt", "create")


def ktt_duzenleyebilir(user: User, ktt: KttSinav) -> bool:
    if not can(user, "ktt", "edit"):
        return False

    if ktt_tam_yetki(user):
        return True

    hoca = _etut_hocasi(user)
    return hoca is not None and ktt.etut_hocasi_id == hoca.id


def ktt_silebilir(user: User, ktt: KttSinav) -> bool:
    if not can(user, "ktt", "delete"):
        return False
    if ktt_tam_yetki(user):
        return True
    hoca = _etut_hocasi(user)
    return hoca is not None and ktt.etut_hocasi_id == hoca.id


def ktt_sinif_secenekleri(user: User) -> list[SinifSube]:
    from takip.permissions.scope import tum_talebe_kapsami_var

    qs = SinifSube.objects.filter(aktif=True).order_by("sinif", "sube")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return list(qs)

    hoca = _etut_hocasi(user)
    if not hoca:
        return []

    secilen = list(hoca.sorumlu_sinif_subeler.filter(aktif=True).order_by("sinif", "sube"))
    if secilen:
        return secilen

    siniflar = (
        Talebe.objects.filter(etut_hocasi=hoca, aktif=True)
        .exclude(sinif="")
        .values_list("sinif", "sube")
        .distinct()
    )
    seen = set()
    fallback: list[SinifSube] = []
    for sinif, sube in siniflar:
        etiket = f"{sinif}-{sube}"
        if etiket in seen:
            continue
        seen.add(etiket)
        obj, _ = SinifSube.objects.get_or_create(sinif=sinif, sube=sube, defaults={"aktif": True})
        fallback.append(obj)
    return sorted(fallback, key=lambda s: (s.sinif, s.sube))


def hedef_siniflar_kaydet(ktt: KttSinav, secilen: list[str]) -> None:
    temiz = [s.strip() for s in secilen if s and s.strip()]
    ktt.hedef_siniflar = ", ".join(temiz)
    if temiz:
        ktt.sinif_seviyesi = temiz[0].split("-", 1)[0].strip()
    elif not ktt.sinif_seviyesi:
        ktt.sinif_seviyesi = "7"


def seed_ktt_demo() -> None:
    """Örnek KTT sınavları ve sonuçları."""
    hoca = EtutHocasi.objects.filter(ad_soyad__icontains="Yahya").first()
    if not hoca or not hoca.user_id:
        return

    sinif_7a, _ = SinifSube.objects.get_or_create(
        sinif="7", sube="A", defaults={"aktif": True}
    )
    sinif_7b, _ = SinifSube.objects.get_or_create(
        sinif="7", sube="B", defaults={"aktif": True}
    )
    hoca.sorumlu_sinif_subeler.add(sinif_7a, sinif_7b)

    ders_map = {
        ad: Ders.objects.filter(ad=ad, aktif=True).first()
        for ad in (
            "Türkçe",
            "Matematik",
            "Fen Bilimleri",
            "Sosyal Bilgiler",
            "Din Kültürü",
        )
    }

    bugun = localdate()
    ornekler = [
        ("Paragrafın Yapısı", "Türkçe", 20, 0),
        ("Tam Sayı Problemleri", "Matematik", 14, 1),
        ("Rasyonel Sayılar", "Matematik", 17, 2),
        ("Güneş Sistemi", "Fen Bilimleri", 12, 3),
        ("Osmanlı Devlet Teşkilatı", "Sosyal Bilgiler", 16, 4),
        ("Namaz Vakitleri", "Din Kültürü", 15, 5),
        ("Edebî Sanatlar", "Türkçe", 20, 6),
        ("Paragraf", "Türkçe", 52, 7),
    ]

    hedef = "7-A, 7-B"
    talebeler = list(
        Talebe.objects.filter(etut_hocasi=hoca, aktif=True).order_by("ad_soyad")
    )

    for ad, ders_ad, soru, gun_farki in ornekler:
        ders = ders_map.get(ders_ad)
        if not ders:
            continue

        ktt, _ = KttSinav.objects.update_or_create(
            ad=ad,
            etut_hocasi=hoca,
            defaults={
                "ders": ders,
                "sinif_seviyesi": "7",
                "hedef_siniflar": hedef,
                "sinav_tarihi": bugun - timedelta(days=gun_farki),
                "soru_sayisi": soru,
                "veliye_goster": True,
                "aktif": True,
                "olusturan": hoca.user,
            },
        )

        for i, talebe in enumerate(talebeler):
            dogru = max(0, soru - i * 2 - (gun_farki % 3))
            yanlis = min(3, soru - dogru)
            bos = soru - dogru - yanlis
            KttSonucu.objects.update_or_create(
                ktt=ktt,
                talebe=talebe,
                defaults={
                    "dogru": dogru,
                    "yanlis": yanlis,
                    "bos": bos,
                    "kaydeden": hoca.user,
                },
            )


def ktt_sonuc_talebeleri(user: User, ktt: KttSinav) -> QuerySet[Talebe]:
    from takip.permissions.scope import yetkili_talebeler

    talebeler = yetkili_talebeler(user, aktif_only=True)

    if ktt_tam_yetki(user):
        return talebeler.filter(etut_hocasi=ktt.etut_hocasi).order_by("ad_soyad")

    hoca = _etut_hocasi(user)
    if hoca and ktt.etut_hocasi_id == hoca.id:
        return talebeler.order_by("ad_soyad")

    return Talebe.objects.none()


def yetkili_ktt_sonuclari(user: User) -> QuerySet[KttSonucu]:
    if not can(user, "ktt", "view"):
        return KttSonucu.objects.none()

    qs = KttSonucu.objects.filter(ktt__aktif=True).select_related(
        "ktt",
        "ktt__ders",
        "ktt__etut_hocasi",
        "talebe",
        "talebe__sinif_sube",
        "talebe__etut_hocasi",
    )

    if user.is_superuser:
        return qs

    from takip.permissions.scope import tum_talebe_kapsami_var

    if tum_talebe_kapsami_var(user):
        return qs

    hoca = _etut_hocasi(user)
    if hoca:
        return qs.filter(ktt__etut_hocasi=hoca)

    return KttSonucu.objects.none()


def ktt_rapor_filtre_secenekleri(user: User) -> dict:
    sinavlar = yetkili_ktt_sinavlari(user)
    from takip.permissions.scope import yetkili_talebeler

    talebeler = yetkili_talebeler(user, aktif_only=True).order_by("ad_soyad")
    ders_ids = sinavlar.values_list("ders_id", flat=True).distinct()
    dersler = Ders.objects.filter(id__in=ders_ids, aktif=True).order_by("sira", "ad")

    return {
        "sinif_subeler": ktt_sinif_secenekleri(user),
        "dersler": list(dersler),
        "ktt_sinavlari": list(sinavlar.order_by("-sinav_tarihi", "-id")[:100]),
        "talebeler": list(talebeler),
    }


def ktt_rapor_filtrele(
    qs: QuerySet[KttSonucu],
    *,
    sinif_sube_id: str | None = None,
    ders_id: str | None = None,
    ktt_id: str | None = None,
    talebe_id: str | None = None,
    baslangic: str | None = None,
    bitis: str | None = None,
) -> QuerySet[KttSonucu]:
    if sinif_sube_id:
        qs = qs.filter(talebe__sinif_sube_id=sinif_sube_id)
    if ders_id:
        qs = qs.filter(ktt__ders_id=ders_id)
    if ktt_id:
        qs = qs.filter(ktt_id=ktt_id)
    if talebe_id:
        qs = qs.filter(talebe_id=talebe_id)
    if baslangic:
        qs = qs.filter(ktt__sinav_tarihi__gte=baslangic)
    if bitis:
        qs = qs.filter(ktt__sinav_tarihi__lte=bitis)
    return qs


def ktt_rapor_istatistik(qs: QuerySet[KttSonucu]) -> dict:
    agg = qs.aggregate(
        toplam=Count("id"),
        ort_puan=Avg("puan"),
        ort_net=Avg("net"),
        max_puan=Max("puan"),
    )
    return {
        "toplam_sonuc": int(agg["toplam"] or 0),
        "ortalama_puan": round(float(agg["ort_puan"] or 0), 1),
        "ortalama_net": round(float(agg["ort_net"] or 0), 1),
        "en_yuksek_puan": round(float(agg["max_puan"] or 0), 1),
    }


def ktt_rapor_filtre_dict(request) -> dict:
    return {
        "sinif_sube": request.GET.get("sinif_sube", ""),
        "ders": request.GET.get("ders", ""),
        "ktt": request.GET.get("ktt", ""),
        "talebe": request.GET.get("talebe", ""),
        "baslangic": request.GET.get("baslangic", ""),
        "bitis": request.GET.get("bitis", ""),
    }
