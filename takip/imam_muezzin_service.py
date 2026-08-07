"""İmam–müezzin listesi dağıtım ve sorgular."""

from __future__ import annotations

from datetime import date, timedelta

from django.utils.timezone import localdate

from .models import ImamMuezzinAtama, ImamMuezzinHavuzKaydi, ImamMuezzinListesi, Talebe


def _haric_tarih_set(liste: ImamMuezzinListesi) -> set[date]:
    haric = set()

    for deger in liste.haric_tarihler or []:
        if isinstance(deger, str):
            try:
                yil, ay, gun = deger.split("-")
                haric.add(date(int(yil), int(ay), int(gun)))
            except (ValueError, TypeError):
                continue

    return haric


def calisma_gunleri(liste: ImamMuezzinListesi) -> list[date]:
    haric = _haric_tarih_set(liste)
    gunler: list[date] = []
    gun = liste.baslangic_tarihi

    while gun <= liste.bitis_tarihi:
        hafta_gunu = gun.weekday()

        if hafta_gunu == 5 and not liste.cumartesi_dahil:
            gun += timedelta(days=1)
            continue

        if hafta_gunu == 6 and not liste.pazar_dahil:
            gun += timedelta(days=1)
            continue

        if gun not in haric:
            gunler.append(gun)

        gun += timedelta(days=1)

    return gunler


def talebe_havuzunu_al(liste: ImamMuezzinListesi) -> list[Talebe]:
    havuz = list(
        liste.talebe_havuzu.filter(aktif=True).order_by("sinif", "sube", "ad_soyad")
    )

    if havuz:
        return havuz

    return list(
        Talebe.objects.filter(aktif=True).order_by("sinif", "sube", "ad_soyad")
    )


def _rol_havuzu(liste: ImamMuezzinListesi, rol: str) -> list[Talebe]:
    kayitlar = (
        liste.havuz_kayitlari.filter(rol=rol)
        .select_related("talebe")
        .order_by("sira", "talebe__ad_soyad")
    )
    havuz = [k.talebe for k in kayitlar if k.talebe.aktif]
    if havuz:
        return havuz
    return talebe_havuzunu_al(liste)


def otomatik_dagit(liste: ImamMuezzinListesi) -> int:
    imam_havuz = _rol_havuzu(liste, ImamMuezzinHavuzKaydi.Rol.IMAM)
    muezzin_havuz = _rol_havuzu(liste, ImamMuezzinHavuzKaydi.Rol.MUEZZIN)

    if not imam_havuz or not muezzin_havuz:
        havuz = talebe_havuzunu_al(liste)
        if not havuz:
            return 0
        imam_havuz = havuz
        muezzin_havuz = havuz[1:] + havuz[:1] if len(havuz) > 1 else havuz

    gunler = calisma_gunleri(liste)
    liste.atamalar.all().delete()

    imam_indeks = 0
    muezzin_indeks = 0
    olusturulan = 0

    for gun in gunler:
        imam = imam_havuz[imam_indeks % len(imam_havuz)]
        muezzin = muezzin_havuz[muezzin_indeks % len(muezzin_havuz)]

        if imam.pk == muezzin.pk and len(muezzin_havuz) > 1:
            muezzin_indeks += 1
            muezzin = muezzin_havuz[muezzin_indeks % len(muezzin_havuz)]

        ImamMuezzinAtama.objects.create(
            liste=liste,
            tarih=gun,
            imam=imam,
            muezzin=muezzin,
            manuel_duzenlendi=False,
        )
        olusturulan += 1
        imam_indeks += 1
        muezzin_indeks += 1

    return olusturulan


def bugunun_listesi() -> ImamMuezzinListesi | None:
    bugun = localdate()

    return (
        ImamMuezzinListesi.objects.filter(
            aktif=True,
            baslangic_tarihi__lte=bugun,
            bitis_tarihi__gte=bugun,
        )
        .order_by("-baslangic_tarihi", "id")
        .first()
    )


def bugunun_atamasi() -> ImamMuezzinAtama | None:
    liste = bugunun_listesi()

    if not liste:
        return None

    return (
        liste.atamalar.select_related("imam", "muezzin")
        .filter(tarih=localdate())
        .first()
    )


def parse_haric_tarih_metni(metin: str) -> list[str]:
    """Satır satır veya virgülle ayrılmış tarihleri ISO listesine çevirir."""

    sonuc: list[str] = []

    for ham in metin.replace(",", "\n").splitlines():
        parca = ham.strip()

        if not parca:
            continue

        if "." in parca:
            try:
                gun, ay, yil = parca.split(".")
                parca = f"{int(yil):04d}-{int(ay):02d}-{int(gun):02d}"
            except ValueError:
                continue

        sonuc.append(parca)

    return sorted(set(sonuc))
