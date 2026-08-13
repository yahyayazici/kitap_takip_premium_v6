"""Dini ders takip sorguları ve yardımcılar."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.utils import timezone

from takip.models import (
    DiniDersKonu,
    DiniDersKonuKaydi,
    DiniDersSeviyesi,
    DiniDersTakipAlani,
    Talebe,
)
from takip.permissions.scope import tum_talebe_kapsami_var
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user

DEFAULT_ALANLAR: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    (
        "Sure Ezberi",
        (
            ("Seviye 1", ("Fatiha", "Fil", "Kureyş")),
            ("Seviye 2", ("Maun", "Kevser", "Kafirun")),
            ("Seviye 3", ("Yasin (1-5)", "Duha", "İnşirah")),
        ),
    ),
    (
        "İlmihal",
        (
            ("Seviye 1", ("Namazın Şartları", "Abdest", "Gusül")),
            ("Seviye 2", ("Hadesten Taharet", "Teyemmüm", "Namazın Rükünleri")),
            ("Seviye 3", ("Oruç", "Zekât", "Hac ve Umre")),
        ),
    ),
    (
        "Tecvid",
        (
            ("Seviye 1", ("Harflerin Mahreçleri", "Medler")),
            ("Seviye 2", ("Tenvin", "İdgam", "İzhar")),
            ("Seviye 3", ("Med-ı Layyin", "Med-ı Arız", "Kalkale")),
        ),
    ),
)


def seed_dini_ders_demo() -> None:
    seviyeler = {
        s.ad: s
        for s in DiniDersSeviyesi.objects.filter(
            ad__in=["Seviye 1", "Seviye 2", "Seviye 3"]
        )
    }
    for sira_alan, (alan_ad, seviye_konular) in enumerate(DEFAULT_ALANLAR, start=1):
        alan, _ = DiniDersTakipAlani.objects.update_or_create(
            ad=alan_ad,
            defaults={"sira": sira_alan, "aktif": True},
        )
        for seviye_ad, konular in seviye_konular:
            seviye = seviyeler.get(seviye_ad)
            if not seviye:
                continue
            for sira_konu, konu_ad in enumerate(konular, start=1):
                DiniDersKonu.objects.get_or_create(
                    alan=alan,
                    seviye=seviye,
                    ad=konu_ad,
                    defaults={"sira": sira_konu, "aktif": True},
                )

    seed_dini_ders_ornek_atamalar()


def seed_dini_ders_ornek_atamalar() -> None:
    """Demo talebelere seviye/hoca atar ve örnek çizelge işaretleri oluşturur."""
    from takip.models import EtutHocasi

    seviyeler = {
        s.ad: s
        for s in DiniDersSeviyesi.objects.filter(aktif=True)
    }
    hoca = EtutHocasi.objects.filter(aktif=True).order_by("id").first()
    if not hoca:
        return

    for seviye in seviyeler.values():
        seviye.hocalar.add(hoca)

    ornek_talebeler = (
        ("Ahmet Yılmaz", "Seviye 1"),
        ("Mehmet Kaya", "Seviye 2"),
        ("Yusuf Akın", "Seviye 3"),
    )
    for ad_soyad, seviye_ad in ornek_talebeler:
        talebe = Talebe.objects.filter(ad_soyad=ad_soyad, durum=Talebe.Durum.AKTIF).first()
        seviye = seviyeler.get(seviye_ad)
        if not talebe or not seviye:
            continue
        talebe.dini_ders_seviyesi = seviye
        talebe.dini_ders_hocasi = hoca
        talebe.save(update_fields=["dini_ders_seviyesi", "dini_ders_hocasi"])

    admin = User.objects.filter(username="admin").first()
    ahmet = Talebe.objects.filter(ad_soyad="Ahmet Yılmaz").first()
    seviye1 = seviyeler.get("Seviye 1")
    if not ahmet or not seviye1 or not admin:
        return

    ornek_konular = {
        ("Sure Ezberi", "Fatiha"),
        ("Sure Ezberi", "Fil"),
        ("İlmihal", "Namazın Şartları"),
        ("İlmihal", "Abdest"),
        ("Tecvid", "Harflerin Mahreçleri"),
    }
    for alan_ad, konu_ad in ornek_konular:
        konu = DiniDersKonu.objects.filter(
            alan__ad=alan_ad,
            seviye=seviye1,
            ad=konu_ad,
            aktif=True,
        ).first()
        if konu:
            DiniDersKonuKaydi.objects.update_or_create(
                talebe=ahmet,
                konu=konu,
                defaults={"tamamlandi": True, "isaretleyen": admin},
            )

    mehmet = Talebe.objects.filter(ad_soyad="Mehmet Kaya").first()
    seviye2 = seviyeler.get("Seviye 2")
    if mehmet and seviye2:
        konu = DiniDersKonu.objects.filter(
            alan__ad="Sure Ezberi",
            seviye=seviye2,
            ad="Maun",
            aktif=True,
        ).first()
        if konu:
            DiniDersKonuKaydi.objects.update_or_create(
                talebe=mehmet,
                konu=konu,
                defaults={"tamamlandi": True, "isaretleyen": admin},
            )


def yetkili_dini_talebeler(user: User) -> QuerySet[Talebe]:
    if not can(user, "dini_ders_takip", "view"):
        return Talebe.objects.none()

    qs = Talebe.objects.filter(durum=Talebe.Durum.AKTIF).select_related(
        "dini_ders_seviyesi", "dini_ders_hocasi", "sinif_sube"
    )

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    hoca = etut_hocasi_for_user(user)
    if not hoca:
        return Talebe.objects.none()

    # Etüt hocası: yalnızca kendisine dini ders olarak atanmış talebeler
    # (seviye sorumluluğu tüm sınıfı açmaz — aynı seviyede birden fazla hoca olabilir)
    return qs.filter(dini_ders_hocasi=hoca)


def duzenleyebilir(user: User) -> bool:
    return can(user, "dini_ders_takip", "edit")


def konular_for(seviye: DiniDersSeviyesi, alan: DiniDersTakipAlani) -> QuerySet[DiniDersKonu]:
    return DiniDersKonu.objects.filter(
        seviye=seviye,
        alan=alan,
        aktif=True,
    ).order_by("sira", "ad")


def matris_kayit_map(
    talebe_ids: list[int],
    konu_ids: list[int],
) -> dict[tuple[int, int], DiniDersKonuKaydi]:
    kayitlar = DiniDersKonuKaydi.objects.filter(
        talebe_id__in=talebe_ids,
        konu_id__in=konu_ids,
    ).select_related("talebe", "konu")
    return {(k.talebe_id, k.konu_id): k for k in kayitlar}


def hucre_durumu(kayit: DiniDersKonuKaydi | None) -> str:
    if not kayit:
        return "bos"
    if kayit.tamamlandi:
        return "tamam"
    return "devam"


def matris_verisi(
    talebeler: QuerySet[Talebe],
    konular: QuerySet[DiniDersKonu],
) -> dict[int, dict[int, bool]]:
    talebe_ids = list(talebeler.values_list("id", flat=True))
    konu_ids = list(konular.values_list("id", flat=True))
    kayit_map = matris_kayit_map(talebe_ids, konu_ids)
    matris: dict[int, dict[int, bool]] = {tid: {} for tid in talebe_ids}
    for (talebe_id, konu_id), kayit in kayit_map.items():
        if kayit.tamamlandi:
            matris.setdefault(talebe_id, {})[konu_id] = True
    return matris


def talebe_matris_satirlari(
    talebeler: QuerySet[Talebe],
    konular: list[DiniDersKonu],
) -> list[dict]:
    talebe_ids = list(talebeler.values_list("id", flat=True))
    konu_ids = [k.id for k in konular]
    kayit_map = matris_kayit_map(talebe_ids, konu_ids)

    satirlar = []
    for sira, talebe in enumerate(talebeler, start=1):
        hucreler = []
        for konu in konular:
            kayit = kayit_map.get((talebe.id, konu.id))
            durum = hucre_durumu(kayit)
            hucreler.append(
                {
                    "talebe_id": talebe.id,
                    "konu_id": konu.id,
                    "konu_ad": konu.ad,
                    "durum": durum,
                    "tamamlandi": durum == "tamam",
                }
            )
        satirlar.append({"sira": sira, "talebe": talebe, "hucreler": hucreler})
    return satirlar


def cizelge_sidebar_ozeti(
    talebeler: QuerySet[Talebe],
    konular: list[DiniDersKonu],
) -> dict:
    talebe_ids = list(talebeler.values_list("id", flat=True))
    konu_ids = [k.id for k in konular]
    kayit_map = matris_kayit_map(talebe_ids, konu_ids)
    toplam_hucre = len(talebe_ids) * len(konu_ids)

    tamamlanan = sum(1 for k in kayit_map.values() if k.tamamlandi)
    devam_eden = sum(1 for k in kayit_map.values() if not k.tamamlandi)
    islenmeyen = max(0, toplam_hucre - len(kayit_map))

    return {
        "toplam_konu": len(konu_ids),
        "tamamlanan": tamamlanan,
        "devam_eden": devam_eden,
        "islenmeyen": islenmeyen,
        "yuzde": round(100 * tamamlanan / toplam_hucre) if toplam_hucre else 0,
    }


def son_islenen_konular(
    talebeler: QuerySet[Talebe],
    konular: list[DiniDersKonu],
    limit: int = 8,
) -> list[DiniDersKonuKaydi]:
    konu_ids = [k.id for k in konular]
    return list(
        DiniDersKonuKaydi.objects.filter(
            talebe__in=talebeler,
            konu_id__in=konu_ids,
        )
        .select_related("talebe", "konu")
        .order_by("-guncellenme")[:limit]
    )


def temizle_sahte_devam_kayitlari(talebe_ids: list[int], konu_ids: list[int]) -> int:
    """Eski checkbox kaydı tüm hücrelere boş kayıt yazıyordu; işaretsiz kabukları sil."""
    if not talebe_ids or not konu_ids:
        return 0
    deleted, _ = DiniDersKonuKaydi.objects.filter(
        talebe_id__in=talebe_ids,
        konu_id__in=konu_ids,
        tamamlandi=False,
        isaretleyen__isnull=True,
    ).delete()
    return deleted


def kayitlari_kaydet(
    user: User,
    talebe_ids: list[int],
    konu_ids: list[int],
    durumlar: dict[tuple[int, int], str] | set[tuple[int, int]],
) -> int:
    """
    Hücre durumu: bos → devam → tamam.
    Geriye dönük: set verilirse eski checkbox (yalnız tamam) gibi işlenir.
    """
    if isinstance(durumlar, set):
        durum_map = {
            (tid, kid): ("tamam" if (tid, kid) in durumlar else "bos")
            for tid in talebe_ids
            for kid in konu_ids
        }
    else:
        durum_map = durumlar

    guncellenen = 0
    mevcut = matris_kayit_map(talebe_ids, konu_ids)

    for talebe_id in talebe_ids:
        for konu_id in konu_ids:
            durum = durum_map.get((talebe_id, konu_id), "bos")
            if durum not in {"bos", "devam", "tamam"}:
                durum = "bos"
            kayit = mevcut.get((talebe_id, konu_id))

            if durum == "bos":
                if kayit:
                    kayit.delete()
                    guncellenen += 1
                continue

            tamamlandi = durum == "tamam"
            if not kayit:
                DiniDersKonuKaydi.objects.create(
                    talebe_id=talebe_id,
                    konu_id=konu_id,
                    tamamlandi=tamamlandi,
                    isaretleyen=user,
                    tamamlanma_tarihi=timezone.localdate() if tamamlandi else None,
                )
                guncellenen += 1
                continue

            update_fields = ["tamamlandi", "isaretleyen", "guncellenme"]
            if tamamlandi and not kayit.tamamlanma_tarihi:
                kayit.tamamlanma_tarihi = timezone.localdate()
                update_fields.append("tamamlanma_tarihi")
            elif not tamamlandi and kayit.tamamlanma_tarihi:
                kayit.tamamlanma_tarihi = None
                update_fields.append("tamamlanma_tarihi")

            if kayit.tamamlandi != tamamlandi or kayit.isaretleyen_id != user.id:
                kayit.tamamlandi = tamamlandi
                kayit.isaretleyen = user
                kayit.save(update_fields=update_fields)
                guncellenen += 1
    return guncellenen


def talebe_ilerleme_ozeti(talebe: Talebe) -> list[dict]:
    if not talebe.dini_ders_seviyesi_id:
        return []

    alanlar = DiniDersTakipAlani.objects.filter(aktif=True).order_by("sira", "ad")
    ozet = []
    for alan in alanlar:
        toplam = DiniDersKonu.objects.filter(
            alan=alan,
            seviye=talebe.dini_ders_seviyesi,
            aktif=True,
        ).count()
        if not toplam:
            continue
        tamamlanan = DiniDersKonuKaydi.objects.filter(
            talebe=talebe,
            konu__alan=alan,
            konu__seviye=talebe.dini_ders_seviyesi,
            tamamlandi=True,
        ).count()
        ozet.append(
            {
                "alan": alan.ad,
                "tamamlanan": tamamlanan,
                "toplam": toplam,
                "yuzde": round(100 * tamamlanan / toplam) if toplam else 0,
            }
        )
    return ozet


def rapor_ozeti(
    talebeler: QuerySet[Talebe],
    seviye: DiniDersSeviyesi | None = None,
    alan: DiniDersTakipAlani | None = None,
) -> dict:
    qs = talebeler
    if seviye:
        qs = qs.filter(dini_ders_seviyesi=seviye)
    konu_qs = DiniDersKonu.objects.filter(aktif=True)
    if seviye:
        konu_qs = konu_qs.filter(seviye=seviye)
    if alan:
        konu_qs = konu_qs.filter(alan=alan)
    toplam_konu = konu_qs.count()
    talebe_sayisi = qs.count()
    tamamlanan = DiniDersKonuKaydi.objects.filter(
        talebe__in=qs,
        konu__in=konu_qs,
        tamamlandi=True,
    ).count()
    beklenen = toplam_konu * talebe_sayisi if talebe_sayisi else 0
    return {
        "talebe_sayisi": talebe_sayisi,
        "konu_sayisi": toplam_konu,
        "tamamlanan": tamamlanan,
        "beklenen": beklenen,
        "yuzde": round(100 * tamamlanan / beklenen) if beklenen else 0,
    }
