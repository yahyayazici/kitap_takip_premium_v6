"""Namaz yoklama sorguları ve yardımcılar."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Iterable

from django.contrib.auth.models import User
from django.db.models import Count, QuerySet

from takip.filter_utils import qs_filtre_id
from takip.models import EtutHocasi, NamazDurumu, NamazVakti, NamazYoklamaKaydi, NamazYoklamaOturum, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user

VAKIT_SIRASI = [
    NamazVakti.SABAH,
    NamazVakti.OGLE,
    NamazVakti.IKINDI,
    NamazVakti.AKSAM,
    NamazVakti.YATSI,
]


def namaz_tam_yetki(user: User) -> bool:
    return user.is_superuser or tum_talebe_kapsami_var(user)


def namaz_yoklama_gorebilir(user: User) -> bool:
    return can(user, "namaz_yoklama", "view")


def namaz_yoklama_kaydedebilir(user: User) -> bool:
    return can(user, "namaz_yoklama", "edit") or can(user, "namaz_yoklama", "create")


def _sinif_numarasi(talebe: Talebe) -> int:
    sinif = talebe.sinif_sube.sinif if talebe.sinif_sube_id else (talebe.sinif or "")
    rakamlar = re.sub(r"\D", "", str(sinif))
    return int(rakamlar) if rakamlar else 99


def talebe_sinif_etiketi(talebe: Talebe) -> str:
    if talebe.sinif_sube_id:
        return f"{talebe.sinif_sube.sinif}-{talebe.sinif_sube.sube}"
    if talebe.sinif and talebe.sube:
        return f"{talebe.sinif}-{talebe.sube}"
    return talebe.sinif or "—"


def talebeler_sirali(qs: QuerySet[Talebe]) -> list[Talebe]:
    return sorted(
        qs.select_related("sinif_sube", "etut_hocasi"),
        key=lambda t: (_sinif_numarasi(t), talebe_sinif_etiketi(t), t.ad_soyad.casefold()),
    )


def talebeler_gruplu(qs: QuerySet[Talebe]) -> list[dict]:
    gruplar: dict[str, list[Talebe]] = {}
    for talebe in talebeler_sirali(qs):
        etiket = talebe_sinif_etiketi(talebe)
        gruplar.setdefault(etiket, []).append(talebe)
    return [{"sinif": sinif, "talebeler": items} for sinif, items in gruplar.items()]


def panel_talebeleri(
    user: User,
    *,
    etudum: bool = False,
    sinif_sube_id: str | None = None,
    etut_hocasi_id: str | None = None,
) -> QuerySet[Talebe]:
    if not namaz_yoklama_gorebilir(user):
        return Talebe.objects.none()

    qs = Talebe.objects.filter(aktif=True)

    if user.is_superuser or tum_talebe_kapsami_var(user):
        if etudum:
            hoca = etut_hocasi_for_user(user)
            if hoca:
                qs = qs.filter(etut_hocasi=hoca)
        if sinif_sube_id:
            qs = qs.filter(sinif_sube_id=sinif_sube_id)
        if etut_hocasi_id:
            qs = qs.filter(etut_hocasi_id=etut_hocasi_id)
        return qs

    hoca = etut_hocasi_for_user(user)
    if hoca:
        return qs.filter(etut_hocasi=hoca)

    talebe_ids = yetkili_talebeler(user, aktif_only=True).values_list("id", flat=True)
    return qs.filter(id__in=talebe_ids)


def kayit_haritasi(oturum: NamazYoklamaOturum | None) -> dict[int, str]:
    if not oturum:
        return {}
    return dict(oturum.kayitlar.values_list("talebe_id", "durum"))


def gelmedi_ozetleri(
    user: User,
    tarih: date,
    *,
    sadece_etudum: bool | None = None,
) -> list[dict]:
    oturumlar = list(
        NamazYoklamaOturum.objects.filter(tarih=tarih).prefetch_related(
            "kayitlar__talebe__sinif_sube",
            "kayitlar__talebe__etut_hocasi",
        )
    )

    if sadece_etudum is None:
        sadece_etudum = not namaz_tam_yetki(user)

    hoca = etut_hocasi_for_user(user) if sadece_etudum else None
    ozetler = []

    for vakit in VAKIT_SIRASI:
        oturum = next((o for o in oturumlar if o.vakit == vakit), None)
        gelmeyenler = []
        if oturum:
            kayitlar = oturum.kayitlar.filter(durum=NamazDurumu.GELMEDI).select_related(
                "talebe", "talebe__sinif_sube", "talebe__etut_hocasi"
            )
            if hoca:
                kayitlar = kayitlar.filter(talebe__etut_hocasi=hoca)
            gelmeyenler = list(kayitlar.order_by("talebe__ad_soyad"))

        ozetler.append(
            {
                "vakit": vakit,
                "vakit_label": dict(NamazVakti.choices).get(vakit, vakit),
                "oturum": oturum,
                "sayi": len(gelmeyenler),
                "gelmeyenler": gelmeyenler,
            }
        )

    return ozetler


def etut_gelmedi_bildirimleri(user: User, tarih: date | None = None) -> list[dict]:
    hoca = etut_hocasi_for_user(user)
    if not hoca:
        return []

    tarih = tarih or date.today()
    etiketler = {
        NamazVakti.SABAH: "Sabah Namazına Gelmedi",
        NamazVakti.OGLE: "Öğle Namazına Gelmedi",
        NamazVakti.IKINDI: "İkindi Namazına Gelmedi",
        NamazVakti.AKSAM: "Akşam Namazına Gelmedi",
        NamazVakti.YATSI: "Yatsı Namazına Gelmedi",
    }
    bildirimler = []
    for ozet in gelmedi_ozetleri(user, tarih, sadece_etudum=True):
        if not ozet["gelmeyenler"]:
            continue
        bildirimler.append(
            {
                "vakit": ozet["vakit"],
                "baslik": dict(NamazVakti.choices).get(ozet["vakit"], ozet["vakit"]),
                "etiket": etiketler.get(ozet["vakit"], "Namaza Gelmedi"),
                "talebeler": [k.talebe for k in ozet["gelmeyenler"]],
            }
        )
    return bildirimler


def yoklama_kaydet(
    user: User,
    tarih: date,
    vakit: str,
    durumlar: dict[int, str],
    talebe_ids: Iterable[int],
) -> NamazYoklamaOturum:
    oturum, _ = NamazYoklamaOturum.objects.update_or_create(
        tarih=tarih,
        vakit=vakit,
        defaults={"kaydeden": user},
    )

    izinli_ids = {int(i) for i in talebe_ids}
    oturum.kayitlar.exclude(talebe_id__in=izinli_ids).delete()

    for talebe_id in izinli_ids:
        durum = durumlar.get(talebe_id, "")
        if durum in dict(NamazDurumu.choices):
            NamazYoklamaKaydi.objects.update_or_create(
                oturum=oturum,
                talebe_id=talebe_id,
                defaults={"durum": durum},
            )
        else:
            oturum.kayitlar.filter(talebe_id=talebe_id).delete()

    return oturum


def rapor_kayitlari(user: User) -> QuerySet[NamazYoklamaKaydi]:
    if not namaz_yoklama_gorebilir(user):
        return NamazYoklamaKaydi.objects.none()

    qs = NamazYoklamaKaydi.objects.select_related(
        "oturum",
        "talebe",
        "talebe__sinif_sube",
        "talebe__etut_hocasi",
    )

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    hoca = etut_hocasi_for_user(user)
    if hoca:
        return qs.filter(talebe__etut_hocasi=hoca)

    talebe_ids = yetkili_talebeler(user, aktif_only=True).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def rapor_filtrele(
    qs: QuerySet[NamazYoklamaKaydi],
    *,
    vakit: str | None = None,
    vakitler: list[str] | None = None,
    baslangic: str | None = None,
    bitis: str | None = None,
    sinif_sube_id: str | None = None,
    sinif_sube_ids: list[int] | None = None,
    etut_hocasi_id: str | None = None,
    etut_hocasi_ids: list[int] | None = None,
    talebe_id: str | None = None,
    talebe_ids: list[int] | None = None,
    durum: str | None = None,
    durumlar: list[str] | None = None,
    donem: str | None = None,
) -> QuerySet[NamazYoklamaKaydi]:
    vakit_list = vakitler or ([vakit] if vakit else [])
    if vakit_list:
        qs = qs.filter(oturum__vakit__in=vakit_list)
    if baslangic:
        qs = qs.filter(oturum__tarih__gte=baslangic)
    if bitis:
        qs = qs.filter(oturum__tarih__lte=bitis)
    qs = qs_filtre_id(qs, "talebe__sinif_sube_id", sinif_sube_id, sinif_sube_ids)
    qs = qs_filtre_id(qs, "talebe__etut_hocasi_id", etut_hocasi_id, etut_hocasi_ids)
    qs = qs_filtre_id(qs, "talebe_id", talebe_id, talebe_ids)
    durum_list = durumlar or ([durum] if durum else [])
    if durum_list:
        qs = qs.filter(durum__in=durum_list)

    if donem == "haftalik":
        qs = qs.filter(oturum__tarih__gte=date.today() - timedelta(days=7))
    elif donem == "aylik":
        qs = qs.filter(oturum__tarih__gte=date.today().replace(day=1))
    elif donem == "donemlik":
        qs = qs.filter(oturum__tarih__gte=date.today() - timedelta(days=120))

    return qs.order_by("-oturum__tarih", "oturum__vakit", "talebe__ad_soyad")


def rapor_istatistik(qs: QuerySet[NamazYoklamaKaydi]) -> dict:
    toplam = qs.count()
    dagilim = {
        row["durum"]: row["adet"]
        for row in qs.values("durum").annotate(adet=Count("id"))
    }
    return {
        "toplam": toplam,
        "gelmedi": dagilim.get(NamazDurumu.GELMEDI, 0),
        "takke_tesbih": dagilim.get(NamazDurumu.TAKKE_TESBIH, 0),
        "izinli": dagilim.get(NamazDurumu.IZINLI, 0),
        "ogrenci_sayisi": qs.values("talebe_id").distinct().count(),
    }


def seed_namaz_demo() -> None:
    from takip.models import SinifSube

    hoca = EtutHocasi.objects.filter(ad_soyad__icontains="Yahya").first()
    if not hoca or not hoca.user_id:
        return

    siniflar = []
    for sinif, sube in [("5", "A"), ("6", "A"), ("7", "A"), ("7", "B"), ("8", "A")]:
        ss, _ = SinifSube.objects.get_or_create(
            sinif=sinif, sube=sube, defaults={"aktif": True}
        )
        siniflar.append(ss)
    hoca.sorumlu_sinif_subeler.add(*siniflar)

    ornek_isimler = [
        ("5", "A", "Abdülbari Miraç Çiçek", "501"),
        ("5", "A", "Ahmed Arif Küçük", "502"),
        ("5", "A", "Ahmet Deniz Coşkun", "503"),
        ("6", "A", "Mehmet Kaya", "601"),
        ("6", "A", "Yusuf Akın", "602"),
        ("7", "A", "Ahmet Yılmaz", "1034"),
        ("7", "A", "Abdullah Demir", "1035"),
        ("7", "B", "Ali Veli Yıldız", "1036"),
        ("8", "A", "Hasan Hüseyin Koç", "801"),
    ]

    talebeler = []
    ss_map = {(s.sinif, s.sube): s for s in siniflar}
    for sinif, sube, ad, no in ornek_isimler:
        ss = ss_map.get((sinif, sube))
        t, _ = Talebe.objects.update_or_create(
            ad_soyad=ad,
            defaults={
                "sinif": sinif,
                "sube": sube,
                "sinif_sube": ss,
                "talebe_no": no,
                "etut_hocasi": hoca,
                "dini_ders_hocasi": hoca,
                "aktif": True,
            },
        )
        talebeler.append(t)

    bugun = date.today()
    durumlar = {
        talebeler[6].id: NamazDurumu.GELMEDI,
        talebeler[5].id: NamazDurumu.GELMEDI,
        talebeler[7].id: NamazDurumu.GELMEDI,
        talebeler[2].id: NamazDurumu.TAKKE_TESBIH,
        talebeler[4].id: NamazDurumu.IZINLI,
    }
    yoklama_kaydet(
        hoca.user,
        bugun,
        NamazVakti.SABAH,
        durumlar,
        [t.id for t in talebeler],
    )
