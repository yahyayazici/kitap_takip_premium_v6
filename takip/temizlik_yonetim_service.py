"""Kat bazlı temizlik görev paneli — veri ve yardımcılar."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q
from django.utils.timezone import localdate

from takip.models import (
    PersonelProfili,
    Talebe,
    TemizlikAlani,
    TemizlikGorevlisi,
    TemizlikGunlukKontrol,
    TemizlikKati,
    TemizlikKatSorumlusu,
    TemizlikListesi,
    TemizlikMahalSorumlusu,
)

DEFAULT_KATLAR: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Giriş Kat",
        (
            ("HOL — LOBİ", "Giriş holü ve lobi"),
            ("TOPLANTI ODASI", "Toplantı salonu"),
            ("WC", "Giriş kat lavabo"),
            ("MUTFAK", "Mutfak ve servis"),
        ),
    ),
    (
        "1. KAT",
        (
            ("KORİDOR", "1. kat koridor"),
            ("WC", "1. kat lavabo"),
            ("ETÜT SALONU", "Etüt alanı"),
        ),
    ),
    (
        "2. KAT",
        (
            ("KORİDOR", "2. kat koridor"),
            ("WC", "2. kat lavabo"),
            ("YATAKHANE", "Yatakhanesi"),
        ),
    ),
)


def personel_secenekleri() -> list[dict]:
    rows = []
    for profil in PersonelProfili.objects.filter(aktif=True).select_related("user").order_by("ad_soyad"):
        rows.append(
            {
                "id": profil.user_id,
                "ad": profil.ad_soyad,
            }
        )
    return rows


def personel_ad(user: User) -> str:
    profil = getattr(user, "personel_profili", None)
    if profil:
        return profil.ad_soyad
    return user.get_full_name() or user.username


def talebe_secenekleri(liste: TemizlikListesi) -> list[Talebe]:
    from takip.temizlik_service import talebe_havuzunu_al

    return talebe_havuzunu_al(liste)


def katlari_hazirla(liste: TemizlikListesi) -> None:
    if liste.katlar.exists():
        return

    sira = 0
    for kat_ad, mahaller in DEFAULT_KATLAR:
        sira += 1
        kat = TemizlikKati.objects.create(liste=liste, ad=kat_ad, sira=sira, aktif=True)
        alan_sira = 0
        for mahal_ad, aciklama in mahaller:
            alan_sira += 1
            alan, _ = TemizlikAlani.objects.get_or_create(
                kat=kat,
                ad=mahal_ad,
                defaults={"aciklama": aciklama, "sira": alan_sira, "aktif": True},
            )
            if alan.kat_id != kat.pk:
                alan.kat = kat
                alan.aciklama = aciklama or alan.aciklama
                alan.sira = alan_sira
                alan.aktif = True
                alan.save(update_fields=["kat", "aciklama", "sira", "aktif"])
            liste.alanlar.add(alan)


def gorev_paneli(liste: TemizlikListesi, *, kat_id: int | None = None) -> dict:
    katlari_hazirla(liste)

    kat_qs = (
        liste.katlar.filter(aktif=True)
        .prefetch_related(
            Prefetch(
                "sorumlular",
                queryset=TemizlikKatSorumlusu.objects.select_related(
                    "personel", "personel__personel_profili"
                ),
            ),
            Prefetch(
                "alanlar",
                queryset=TemizlikAlani.objects.filter(aktif=True)
                .prefetch_related(
                    Prefetch(
                        "gorevliler",
                        queryset=TemizlikGorevlisi.objects.filter(liste=liste).select_related(
                            "talebe", "talebe__sinif_sube"
                        ),
                    ),
                    Prefetch(
                        "mahal_sorumlulari",
                        queryset=TemizlikMahalSorumlusu.objects.select_related(
                            "personel", "personel__personel_profili"
                        ),
                    ),
                )
                .order_by("sira", "ad"),
            ),
        )
        .order_by("sira", "ad")
    )
    katlar = list(kat_qs)
    secili = None
    if kat_id:
        secili = next((k for k in katlar if k.pk == kat_id), None)
    if not secili and katlar:
        secili = katlar[0]

    mahaller = []
    if secili:
        for alan in secili.alanlar.all():
            gorevliler = [
                {
                    "id": g.pk,
                    "ad_soyad": g.talebe.ad_soyad,
                    "sinif": str(g.talebe.sinif_sube) if g.talebe.sinif_sube_id else g.talebe.sinif or "",
                }
                for g in alan.gorevliler.all()
            ]
            sorumlular = [
                {
                    "id": s.pk,
                    "personel_id": s.personel_id,
                    "ad": personel_ad(s.personel),
                }
                for s in alan.mahal_sorumlulari.all()
            ]
            mahaller.append(
                {
                    "alan": alan,
                    "gorevliler": gorevliler,
                    "sorumlular": sorumlular,
                }
            )

    sorumlular = []
    if secili:
        for kayit in secili.sorumlular.all():
            sorumlular.append(
                {
                    "id": kayit.pk,
                    "personel_id": kayit.personel_id,
                    "ad": personel_ad(kayit.personel),
                }
            )

    return {
        "liste": liste,
        "katlar": katlar,
        "secili_kat": secili,
        "mahaller": mahaller,
        "sorumlular": sorumlular,
        "personeller": personel_secenekleri(),
        "talebeler": talebe_secenekleri(liste),
    }


def kat_ekle(liste: TemizlikListesi, ad: str) -> TemizlikKati | None:
    ad = (ad or "").strip()
    if not ad:
        return None
    max_sira = liste.katlar.aggregate(m=Max("sira"))["m"] or 0
    return TemizlikKati.objects.create(liste=liste, ad=ad, sira=max_sira + 1, aktif=True)


def sorumlu_ekle(kat: TemizlikKati, personel_id: int) -> bool:
    if not User.objects.filter(pk=personel_id).exists():
        return False
    TemizlikKatSorumlusu.objects.get_or_create(kat=kat, personel_id=personel_id)
    return True


def sorumlu_sil(kat: TemizlikKati, personel_id: int) -> None:
    TemizlikKatSorumlusu.objects.filter(kat=kat, personel_id=personel_id).delete()


def mahal_ekle(kat: TemizlikKati, ad: str, aciklama: str = "") -> TemizlikAlani | None:
    ad = (ad or "").strip()
    if not ad:
        return None
    max_sira = kat.alanlar.aggregate(m=Max("sira"))["m"] or 0
    alan = TemizlikAlani.objects.create(
        kat=kat,
        ad=ad,
        aciklama=(aciklama or "").strip(),
        sira=max_sira + 1,
        aktif=True,
    )
    kat.liste.alanlar.add(alan)
    return alan


def mahal_sil(alan: TemizlikAlani, liste: TemizlikListesi) -> None:
    liste.alanlar.remove(alan)
    alan.delete()


def mahal_sorumlu_ekle(alan: TemizlikAlani, personel_id: int) -> bool:
    if not User.objects.filter(pk=personel_id).exists():
        return False
    TemizlikMahalSorumlusu.objects.get_or_create(alan=alan, personel_id=personel_id)
    return True


def mahal_sorumlu_sil(alan: TemizlikAlani, personel_id: int) -> None:
    TemizlikMahalSorumlusu.objects.filter(alan=alan, personel_id=personel_id).delete()


def gorevli_ekle(liste: TemizlikListesi, alan: TemizlikAlani, talebe_id: int):
    """Görevli ekler; başarıda TemizlikGorevlisi, aksi halde None."""
    if not Talebe.objects.filter(pk=talebe_id).exists():
        return None
    obj, _ = TemizlikGorevlisi.objects.get_or_create(
        liste=liste, alan=alan, talebe_id=talebe_id
    )
    return obj


def gorevli_sil(gorevli_id: int, liste: TemizlikListesi) -> int | None:
    """Siler; silinen kaydın talebe_id'sini döner (yoksa None)."""
    kayit = TemizlikGorevlisi.objects.filter(pk=gorevli_id, liste=liste).first()
    if not kayit:
        return None
    talebe_id = kayit.talebe_id
    kayit.delete()
    return talebe_id


def kat_sil(kat: TemizlikKati) -> None:
    liste = kat.liste
    for alan in list(kat.alanlar.all()):
        liste.alanlar.remove(alan)
        alan.delete()
    kat.delete()


def _mahal_satir(liste: TemizlikListesi, alan: TemizlikAlani, bugun) -> dict:
    gorevliler = [
        {
            "id": g.pk,
            "talebe_id": g.talebe_id,
            "ad_soyad": g.talebe.ad_soyad,
            "sinif": str(g.talebe.sinif_sube) if g.talebe.sinif_sube_id else g.talebe.sinif or "",
        }
        for g in alan.gorevliler.all()
    ]
    sorumlular = [
        {
            "id": s.pk,
            "personel_id": s.personel_id,
            "ad": personel_ad(s.personel),
        }
        for s in alan.mahal_sorumlulari.all()
    ]
    kontrol = next(
        (k for k in alan.gunluk_kontroller.all() if k.tarih == bugun),
        None,
    )
    return {
        "alan": alan,
        "gorevliler": gorevliler,
        "sorumlular": sorumlular,
        "kontrol": kontrol,
        "bos": len(gorevliler) == 0,
    }


def _kat_ozet(mahaller: list[dict]) -> dict:
    toplam = len(mahaller)
    bos = sum(1 for m in mahaller if m["bos"])
    gorevli = sum(len(m["gorevliler"]) for m in mahaller)
    return {
        "mahal": toplam,
        "gorevli": gorevli,
        "bos_mahal": bos,
        "eksik_atama": bos,
    }


def yonetim_merkezi(liste: TemizlikListesi) -> dict:
    katlari_hazirla(liste)
    bugun = localdate()
    hafta_baslangic = bugun - timedelta(days=bugun.weekday())

    kontrol_prefetch = Prefetch(
        "gunluk_kontroller",
        queryset=TemizlikGunlukKontrol.objects.filter(
            liste=liste,
            tarih=bugun,
        ),
    )

    kat_qs = (
        liste.katlar.filter(aktif=True)
        .prefetch_related(
            Prefetch(
                "sorumlular",
                queryset=TemizlikKatSorumlusu.objects.select_related(
                    "personel", "personel__personel_profili"
                ),
            ),
            Prefetch(
                "alanlar",
                queryset=TemizlikAlani.objects.filter(aktif=True)
                .prefetch_related(
                    Prefetch(
                        "gorevliler",
                        queryset=TemizlikGorevlisi.objects.filter(liste=liste).select_related(
                            "talebe", "talebe__sinif_sube"
                        ),
                    ),
                    Prefetch(
                        "mahal_sorumlulari",
                        queryset=TemizlikMahalSorumlusu.objects.select_related(
                            "personel", "personel__personel_profili"
                        ),
                    ),
                    kontrol_prefetch,
                )
                .order_by("sira", "ad"),
            ),
        )
        .order_by("sira", "ad")
    )

    kat_kartlari = []
    toplam_mahal = 0
    toplam_gorevli = 0
    bos_mahal = 0

    for kat in kat_qs:
        mahaller = [_mahal_satir(liste, alan, bugun) for alan in kat.alanlar.all()]
        ozet = _kat_ozet(mahaller)
        toplam_mahal += ozet["mahal"]
        toplam_gorevli += ozet["gorevli"]
        bos_mahal += ozet["bos_mahal"]

        sorumlular = [
            {
                "id": kayit.pk,
                "personel_id": kayit.personel_id,
                "ad": personel_ad(kayit.personel),
            }
            for kayit in kat.sorumlular.all()
        ]
        kat_kartlari.append(
            {
                "kat": kat,
                "sorumlular": sorumlular,
                "mahaller": mahaller,
                "ozet": ozet,
            }
        )

    gorev_sayaclari = Counter(
        TemizlikGorevlisi.objects.filter(liste=liste).values_list(
            "talebe_id", flat=True
        )
    )
    talebe_map = {
        t.pk: t
        for t in Talebe.objects.filter(pk__in=gorev_sayaclari.keys()).only(
            "id", "ad_soyad"
        )
    }
    yuk_analizi = [
        {
            "talebe_id": tid,
            "ad_soyad": talebe_map[tid].ad_soyad,
            "sayi": sayi,
        }
        for tid, sayi in gorev_sayaclari.most_common()
    ]

    dengesiz = False
    if yuk_analizi:
        sayilar = [row["sayi"] for row in yuk_analizi]
        dengesiz = max(sayilar) - min(sayilar) >= 2

    hafta_degisim = TemizlikGorevlisi.objects.filter(
        liste=liste,
        olusturulma__date__gte=hafta_baslangic,
    ).count()

    son_duzenleme = (
        TemizlikGorevlisi.objects.filter(liste=liste)
        .order_by("-guncellenme")
        .first()
    )

    stats = {
        "toplam_kat": len(kat_kartlari),
        "toplam_mahal": toplam_mahal,
        "gorevli_talebe": len(gorev_sayaclari),
        "bos_mahal": bos_mahal,
        "eksik_atama": bos_mahal,
        "hafta_degisim": hafta_degisim,
    }

    sidebar = {
        "bugun_eksik": bos_mahal,
        "bos_mahal": bos_mahal,
        "en_yogun": yuk_analizi[0] if yuk_analizi else None,
        "en_az": yuk_analizi[-1] if yuk_analizi else None,
        "son_duzenleme": son_duzenleme.guncellenme if son_duzenleme else None,
    }

    return {
        "liste": liste,
        "kat_kartlari": kat_kartlari,
        "stats": stats,
        "yuk_analizi": yuk_analizi,
        "dengesiz": dengesiz,
        "sidebar": sidebar,
        "personeller": personel_secenekleri(),
        "talebeler": talebe_secenekleri(liste),
        "bugun": bugun,
        "kontrol_secenekleri": TemizlikGunlukKontrol.Durum.choices,
    }


def talebe_ara(liste: TemizlikListesi, q: str, limit: int = 12) -> list[dict]:
    q = (q or "").strip()
    havuz = talebe_secenekleri(liste)
    if q:
        havuz = [
            t
            for t in havuz
            if q.lower() in t.ad_soyad.lower()
            or q.lower() in (t.talebe_no or "").lower()
        ]
    return [
        {
            "id": t.pk,
            "ad_soyad": t.ad_soyad,
            "sinif": str(t.sinif_sube) if t.sinif_sube_id else t.sinif or "",
        }
        for t in havuz[:limit]
    ]


@transaction.atomic
def gorevli_tasi(gorevli_id: int, liste: TemizlikListesi, hedef_alan_id: int) -> bool:
    gorevli = TemizlikGorevlisi.objects.filter(pk=gorevli_id, liste=liste).first()
    if not gorevli:
        return False
    hedef = TemizlikAlani.objects.filter(pk=hedef_alan_id, aktif=True).first()
    if not hedef:
        return False
    if TemizlikGorevlisi.objects.filter(
        liste=liste, alan=hedef, talebe_id=gorevli.talebe_id
    ).exists():
        return False
    gorevli.alan = hedef
    gorevli.save(update_fields=["alan", "guncellenme"])
    return True


def kontrol_guncelle(
    liste: TemizlikListesi,
    alan_id: int,
    durum: str,
    user: User,
    *,
    tarih=None,
) -> TemizlikGunlukKontrol | None:
    if durum not in TemizlikGunlukKontrol.Durum.values:
        return None
    tarih = tarih or localdate()
    kayit, _ = TemizlikGunlukKontrol.objects.update_or_create(
        liste=liste,
        alan_id=alan_id,
        tarih=tarih,
        defaults={"durum": durum, "guncelleyen": user},
    )
    return kayit


@transaction.atomic
def gorevleri_dengele(liste: TemizlikListesi) -> int:
    mahaller = list(
        TemizlikAlani.objects.filter(
            temizlik_listeleri=liste,
            aktif=True,
        ).order_by("sira", "ad")
    )
    talebeler = talebe_secenekleri(liste)
    if not mahaller or not talebeler:
        return 0

    TemizlikGorevlisi.objects.filter(liste=liste).delete()
    olusturulan = 0
    talebe_idx = 0
    for alan in mahaller:
        talebe = talebeler[talebe_idx % len(talebeler)]
        TemizlikGorevlisi.objects.create(
            liste=liste,
            alan=alan,
            talebe=talebe,
        )
        olusturulan += 1
        talebe_idx += 1
    return olusturulan


@transaction.atomic
def otomatik_gorev_rotasyonu(liste: TemizlikListesi) -> int:
    gorevliler = list(
        TemizlikGorevlisi.objects.filter(liste=liste).order_by("alan__sira", "pk")
    )
    if len(gorevliler) < 2:
        return 0

    alan_ids = [g.alan_id for g in gorevliler]
    talebe_ids = [g.talebe_id for g in gorevliler]
    rotated = talebe_ids[1:] + talebe_ids[:1]

    TemizlikGorevlisi.objects.filter(liste=liste).delete()
    for alan_id, talebe_id in zip(alan_ids, rotated):
        TemizlikGorevlisi.objects.create(
            liste=liste,
            alan_id=alan_id,
            talebe_id=talebe_id,
        )
    return len(gorevliler)


def rapor_satirlari(
    liste: TemizlikListesi,
    *,
    kat_id: str = "",
    mahal_id: str = "",
    talebe_id: str = "",
    personel_id: str = "",
    tarih: str = "",
) -> list[dict]:
    """Filtrelenmiş rapor satırları — kat, mahal, talebe, personel, tarih."""
    merkez = yonetim_merkezi(liste)
    satirlar: list[dict] = []

    kat_filtre = int(kat_id) if kat_id.isdigit() else None
    mahal_filtre = int(mahal_id) if mahal_id.isdigit() else None
    talebe_filtre = int(talebe_id) if talebe_id.isdigit() else None
    personel_filtre = int(personel_id) if personel_id.isdigit() else None

    for kart in merkez["kat_kartlari"]:
        if kat_filtre and kart["kat"].pk != kat_filtre:
            continue
        sorumlu_adlar = ", ".join(s["ad"] for s in kart["sorumlular"])
        if personel_filtre and not any(
            s["personel_id"] == personel_filtre for s in kart["sorumlular"]
        ):
            continue

        for row in kart["mahaller"]:
            if mahal_filtre and row["alan"].pk != mahal_filtre:
                continue
            if not row["gorevliler"]:
                if talebe_filtre:
                    continue
                satirlar.append(
                    {
                        "kat": kart["kat"].ad,
                        "mahal": row["alan"].ad,
                        "talebe": "—",
                        "sorumlular": sorumlu_adlar or "—",
                        "durum": row["kontrol"].get_durum_display()
                        if row["kontrol"]
                        else "Bekliyor",
                        "tarih": merkez["bugun"],
                    }
                )
                continue

            for g in row["gorevliler"]:
                if talebe_filtre and g["talebe_id"] != talebe_filtre:
                    continue
                satirlar.append(
                    {
                        "kat": kart["kat"].ad,
                        "mahal": row["alan"].ad,
                        "talebe": g["ad_soyad"],
                        "sorumlular": sorumlu_adlar or "—",
                        "durum": row["kontrol"].get_durum_display()
                        if row["kontrol"]
                        else "Bekliyor",
                        "tarih": merkez["bugun"],
                    }
                )

    if tarih:
        # Günlük kontrol kayıtları için tarih filtresi (gelecek genişletme)
        pass

    return satirlar
