"""Hatim Takip Merkezi — dönem üretimi, dağıtım ve ilerleme servisi."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable
from urllib.parse import quote

from django.contrib.auth.models import AbstractBaseUser, User
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from config.branding import PANEL_ORG
from takip.bildirim_models import Bildirim
from takip.bildirim_service import bildirim_gonder, bildirim_gonder_coklu
from takip.hatim_models import (
    CuzAtamasi,
    DonemTamamlamaKaydi,
    HatimDonemi,
    HatimHatirlatmasi,
    HatimKatilimcisi,
    HatimProgrami,
)
from takip.models import PersonelProfili
from takip.permissions.service import can


CUZ_SAYISI = 30


def hatim_yonetebilir(user: User | AbstractBaseUser | None) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return can(user, "hatim_takip", "create") or can(user, "hatim_takip", "edit")


def hatim_gorebilir(user: User | AbstractBaseUser | None) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return can(user, "hatim_takip", "view")


def _profil_for_user(user: User | AbstractBaseUser | None) -> PersonelProfili | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.personel_profili
    except PersonelProfili.DoesNotExist:
        return None


def yetkili_hatim_programlari(user: User | AbstractBaseUser | None) -> QuerySet[HatimProgrami]:
    qs = HatimProgrami.objects.all()
    if hatim_yonetebilir(user):
        return qs
    profil = _profil_for_user(user)
    if not profil:
        return qs.none()
    return qs.filter(
        katilimcilar__personel=profil,
        katilimcilar__aktif=True,
    ).distinct()


def aktif_hatim_programlari(user: User | AbstractBaseUser | None) -> QuerySet[HatimProgrami]:
    return yetkili_hatim_programlari(user).filter(durum=HatimProgrami.Durum.AKTIF)


def gecmis_hatim_programlari(user: User | AbstractBaseUser | None) -> QuerySet[HatimProgrami]:
    qs = yetkili_hatim_programlari(user)
    if hatim_yonetebilir(user):
        return qs.filter(
            durum__in=[
                HatimProgrami.Durum.TAMAMLANDI,
                HatimProgrami.Durum.DURDURULDU,
            ]
        )
    profil = _profil_for_user(user)
    if not profil:
        return qs.none()
    return qs.filter(
        katilimcilar__personel=profil,
        durum__in=[
            HatimProgrami.Durum.TAMAMLANDI,
            HatimProgrami.Durum.DURDURULDU,
        ],
    ).distinct()


def _aware(dt: datetime) -> datetime:
    tz = timezone.get_current_timezone()
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, tz)
    return dt


def _program_bitis_dt(program: HatimProgrami) -> datetime | None:
    if not program.program_bitis_tarihi:
        return None
    return _aware(
        datetime.combine(program.program_bitis_tarihi, program.son_tamamlama_saati)
    )


def _donem_bitisi(
    baslangic: datetime,
    gun_sayisi: int,
    son_saat: time,
    *,
    hafta_sonu_dahil: bool,
) -> datetime:
    """Dönem bitiş anı: başlangıç + N gün, son tamamlama saatinde."""
    hedef_gun = baslangic.date()
    kalan = max(gun_sayisi, 1)
    while kalan > 0:
        hedef_gun += timedelta(days=1)
        if not hafta_sonu_dahil and hedef_gun.weekday() >= 5:
            continue
        kalan -= 1
    return _aware(datetime.combine(hedef_gun, son_saat))


def donem_planlari_uret(program: HatimProgrami) -> list[tuple[datetime, datetime]]:
    """Program ayarlarına göre dönem başlangıç/bitiş çiftleri."""
    if program.tekrar_turu == HatimProgrami.Tekrar.BIR_KEZ:
        bas = _aware(datetime.combine(program.baslangic_tarihi, time.min))
        bitis_dt = _program_bitis_dt(program)
        if bitis_dt is None:
            bitis_dt = _aware(
                datetime.combine(
                    program.baslangic_tarihi + timedelta(days=7),
                    program.son_tamamlama_saati,
                )
            )
        return [(bas, bitis_dt)]

    gun = program.tekrar_gun_sayisi() or 1
    planlar: list[tuple[datetime, datetime]] = []
    current = _aware(datetime.combine(program.baslangic_tarihi, time.min))
    program_end = _program_bitis_dt(program)

    while True:
        bitis = _donem_bitisi(
            current,
            gun,
            program.son_tamamlama_saati,
            hafta_sonu_dahil=program.hafta_sonu_dahil,
        )
        if program_end and current > program_end:
            break
        if program_end and bitis > program_end:
            if program.yarim_son_donem:
                planlar.append((current, program_end))
            break
        planlar.append((current, bitis))
        current = bitis
        if program_end is None:
            break
        if program_end and current >= program_end:
            break

    return planlar


def donemleri_olustur(program: HatimProgrami, *, ilk_sayi: int | None = None) -> list[HatimDonemi]:
    """Planlanan dönemleri veritabanına yazar (mevcut sıraları atlar)."""
    mevcut = program.donemler.count()
    planlar = donem_planlari_uret(program)
    if program.program_bitis_tarihi is None and planlar:
        planlar = planlar[:1]
    elif ilk_sayi:
        planlar = planlar[:ilk_sayi]

    olusturulan: list[HatimDonemi] = []
    for idx, (bas, bit) in enumerate(planlar, start=mevcut + 1):
        if program.donemler.filter(sira=idx).exists():
            continue
        durum = HatimDonemi.Durum.AKTIF
        if not program.yeni_donem_otomatik and idx > 1:
            durum = HatimDonemi.Durum.BEKLEMEDE
        olusturulan.append(
            HatimDonemi.objects.create(
                program=program,
                sira=idx,
                baslangic=bas,
                bitis=bit,
                durum=durum,
            )
        )
    return olusturulan


def _katilimci_sirali(program: HatimProgrami) -> list[HatimKatilimcisi]:
    return list(program.katilimcilar.filter(aktif=True).order_by("sira", "id"))


def _otomatik_cuz_bloklari(
    katilimcilar: list[HatimKatilimcisi],
    kisi_basina: int,
) -> list[tuple[HatimKatilimcisi, int, int]]:
    """Sırayla 1–30 arası cüzleri dağıt."""
    sonuc: list[tuple[HatimKatilimcisi, int, int]] = []
    cuz = 1
    for kat in katilimcilar:
        if cuz > CUZ_SAYISI:
            break
        bit = min(cuz + kisi_basina - 1, CUZ_SAYISI)
        sonuc.append((kat, cuz, bit))
        cuz = bit + 1
    return sonuc


def cuz_cakisma_kontrolu(donem: HatimDonemi) -> list[str]:
    """Aynı cüzün birden fazla kişiye verilip verilmediğini kontrol eder."""
    sayac: Counter[int] = Counter()
    for atama in donem.cuz_atamalari.exclude(
        durum__in=[CuzAtamasi.Durum.MUAF, CuzAtamasi.Durum.DEVREDILDI]
    ):
        for num in atama.cuz_numaralari():
            sayac[num] += 1
    return [f"Cüz {n} birden fazla kişiye atanmış." for n, adet in sayac.items() if adet > 1]


def dagitilmayan_cuzler(donem: HatimDonemi) -> list[int]:
    atanan: set[int] = set()
    for atama in donem.cuz_atamalari.exclude(
        durum__in=[CuzAtamasi.Durum.MUAF, CuzAtamasi.Durum.DEVREDILDI]
    ):
        atanan.update(atama.cuz_numaralari())
    return [n for n in range(1, CUZ_SAYISI + 1) if n not in atanan]


@transaction.atomic
def cuzleri_dagit(
    program: HatimProgrami,
    donem: HatimDonemi,
    *,
    manuel: dict[int, tuple[int, int]] | None = None,
    onceki_donem: HatimDonemi | None = None,
) -> list[CuzAtamasi]:
    """Dönem için cüz atamalarını oluşturur veya yeniler."""
    donem.cuz_atamalari.all().delete()
    katilimcilar = _katilimci_sirali(program)
    atamalar: list[CuzAtamasi] = []

    if manuel:
        for kat in katilimcilar:
            if kat.pk not in manuel:
                continue
            bas, bit = manuel[kat.pk]
            atama = CuzAtamasi.objects.create(
                donem=donem,
                katilimci=kat,
                cuz_baslangic=bas,
                cuz_bitis=bit,
            )
            kat.varsayilan_cuz_bas = bas
            kat.varsayilan_cuz_bit = bit
            kat.save(update_fields=["varsayilan_cuz_bas", "varsayilan_cuz_bit"])
            atamalar.append(atama)
        return atamalar

    strateji = program.cuz_donem_stratejisi
    if strateji == HatimProgrami.CuzStrateji.AYNI:
        for kat in katilimcilar:
            if kat.varsayilan_cuz_bas and kat.varsayilan_cuz_bit:
                bas, bit = kat.varsayilan_cuz_bas, kat.varsayilan_cuz_bit
            else:
                continue
            atamalar.append(
                CuzAtamasi.objects.create(
                    donem=donem,
                    katilimci=kat,
                    cuz_baslangic=bas,
                    cuz_bitis=bit,
                )
            )
        if atamalar:
            return atamalar

    if (
        strateji == HatimProgrami.CuzStrateji.DON
        and onceki_donem
        and onceki_donem.cuz_atamalari.exists()
    ):
        eski = list(
            onceki_donem.cuz_atamalari.select_related("katilimci").order_by(
                "katilimci__sira", "id"
            )
        )
        if eski:
            kaydir = 1
            for i, kat in enumerate(katilimcilar):
                kaynak = eski[(i - kaydir) % len(eski)]
                atamalar.append(
                    CuzAtamasi.objects.create(
                        donem=donem,
                        katilimci=kat,
                        cuz_baslangic=kaynak.cuz_baslangic,
                        cuz_bitis=kaynak.cuz_bitis,
                    )
                )
            return atamalar

    bloklar = _otomatik_cuz_bloklari(katilimcilar, program.kisi_basina_cuz)
    for kat, bas, bit in bloklar:
        atama = CuzAtamasi.objects.create(
            donem=donem,
            katilimci=kat,
            cuz_baslangic=bas,
            cuz_bitis=bit,
        )
        kat.varsayilan_cuz_bas = bas
        kat.varsayilan_cuz_bit = bit
        kat.save(update_fields=["varsayilan_cuz_bas", "varsayilan_cuz_bit"])
        atamalar.append(atama)
    return atamalar


@transaction.atomic
def program_baslat(
    program: HatimProgrami,
    katilimci_profiller: Iterable[PersonelProfili],
    *,
    olusturan: User | None = None,
) -> HatimProgrami:
    program.katilimcilar.all().delete()
    for sira, profil in enumerate(katilimci_profiller, start=1):
        HatimKatilimcisi.objects.create(
            program=program,
            personel=profil,
            user=profil.user,
            sira=sira,
        )
    program.durum = HatimProgrami.Durum.AKTIF
    if olusturan:
        program.olusturan = olusturan
    program.save(update_fields=["durum", "olusturan", "guncellenme"])

    donemler = donemleri_olustur(program)
    if donemler:
        onceki = None
        for donem in donemler:
            cuzleri_dagit(program, donem, onceki_donem=onceki)
            onceki = donem

    if program.hatirlatma_program_baslangic:
        _hatim_bildirim_gonder(
            program,
            tetik=HatimHatirlatmasi.Tetik.PROGRAM_BASLANGIC,
            baslik=f"{program.ad} başladı",
            mesaj="Hatim programınız başlamıştır. Cüz görevinizi panelden takip edebilirsiniz.",
        )
    return program


def aktif_donem(program: HatimProgrami) -> HatimDonemi | None:
    simdi = timezone.now()
    donem = (
        program.donemler.filter(durum=HatimDonemi.Durum.AKTIF, baslangic__lte=simdi)
        .order_by("-sira")
        .first()
    )
    if donem:
        return donem
    return program.donemler.order_by("-sira").first()


def kullanici_atamalari(
    user: User | AbstractBaseUser,
    *,
    program: HatimProgrami | None = None,
) -> QuerySet[CuzAtamasi]:
    qs = CuzAtamasi.objects.select_related(
        "donem",
        "donem__program",
        "katilimci",
        "katilimci__personel",
    ).filter(katilimci__user=user, katilimci__aktif=True)
    if program:
        qs = qs.filter(donem__program=program)
    return qs


def personel_aktif_gorevleri(
    user: User | AbstractBaseUser,
    *,
    bugun: date | None = None,
) -> list[dict]:
    """Dashboard kartı için personelin aktif cüz görevleri."""
    bugun = bugun or timezone.localdate()
    kartlar: list[dict] = []
    for program in aktif_hatim_programlari(user):
        donem = aktif_donem(program)
        if not donem:
            continue
        atama = (
            kullanici_atamalari(user, program=program)
            .filter(donem=donem)
            .exclude(durum__in=[CuzAtamasi.Durum.MUAF, CuzAtamasi.Durum.DEVREDILDI])
            .first()
        )
        if not atama:
            continue
        simdi = timezone.now()
        kalan = donem.bitis - simdi
        kartlar.append(
            {
                "program_id": program.pk,
                "program_ad": program.ad,
                "tur_etiket": program.get_tur_display(),
                "cuz_etiketi": atama.cuz_etiketi,
                "tekrar": program.tekrar_etiketi(),
                "strateji_etiket": program.get_cuz_donem_stratejisi_display(),
                "donem_sira": donem.sira,
                "donem_baslangic": donem.baslangic,
                "donem_bitis": donem.bitis,
                "program_bitis": program.program_bitis_tarihi,
                "son_saat": program.son_tamamlama_saati,
                "durum": atama.durum,
                "durum_etiket": atama.get_durum_display(),
                "atama_id": atama.pk,
                "kalan_saniye": max(int(kalan.total_seconds()), 0),
                "gecikti": simdi > donem.bitis
                and atama.durum != CuzAtamasi.Durum.TAMAMLANDI,
            }
        )
    return kartlar


@dataclass
class CuzOzet:
    numara: int
    durum: str
    durum_etiket: str
    katilimci: str


def donem_cuz_ozeti(donem: HatimDonemi) -> list[CuzOzet]:
    """1–30 cüz için özet durum."""
    durum_map: dict[int, tuple[str, str, str]] = {}
    for atama in donem.cuz_atamalari.select_related("katilimci"):
        for num in atama.cuz_numaralari():
            durum_map[num] = (
                atama.durum,
                atama.get_durum_display(),
                atama.katilimci.gorunen_ad,
            )
    sonuc: list[CuzOzet] = []
    for num in range(1, CUZ_SAYISI + 1):
        if num in durum_map:
            d, de, k = durum_map[num]
        else:
            d, de, k = "bos", "Dağıtılmadı", ""
        sonuc.append(CuzOzet(numara=num, durum=d, durum_etiket=de, katilimci=k))
    return sonuc


def donem_ilerleme_istatistik(donem: HatimDonemi) -> dict[str, int]:
    sayac: dict[str, int] = defaultdict(int)
    for ozet in donem_cuz_ozeti(donem):
        if ozet.durum == "bos":
            sayac["dagitilmayan"] += 1
        elif ozet.durum == CuzAtamasi.Durum.TAMAMLANDI:
            sayac["tamamlanan"] += 1
        elif ozet.durum == CuzAtamasi.Durum.OKUNUYOR:
            sayac["okunuyor"] += 1
        elif ozet.durum == CuzAtamasi.Durum.GECIKMIS:
            sayac["geciken"] += 1
        elif ozet.durum == CuzAtamasi.Durum.DEVREDILDI:
            sayac["devredildi"] += 1
        else:
            sayac["baslanmadi"] += 1
    tamamlanan_kisi = donem.cuz_atamalari.filter(
        durum=CuzAtamasi.Durum.TAMAMLANDI
    ).count()
    toplam_kisi = donem.cuz_atamalari.exclude(
        durum__in=[CuzAtamasi.Durum.MUAF, CuzAtamasi.Durum.DEVREDILDI]
    ).count()
    yuzde = int(round(100 * tamamlanan_kisi / toplam_kisi)) if toplam_kisi else 0
    return {
        **sayac,
        "toplam_cuz": CUZ_SAYISI,
        "donem_yuzde": yuzde,
        "tamamlanan_donem_sayisi": donem.program.donemler.filter(
            durum=HatimDonemi.Durum.TAMAMLANDI
        ).count(),
        "toplam_donem_sayisi": donem.program.donemler.count(),
    }


@transaction.atomic
def atama_basladi(atama: CuzAtamasi, user: User) -> CuzAtamasi:
    if atama.katilimci.user_id != user.pk and not hatim_yonetebilir(user):
        raise PermissionError("Bu atamayı işaretleyemezsiniz.")
    simdi = timezone.now()
    atama.durum = CuzAtamasi.Durum.OKUNUYOR
    atama.baslama_zamani = simdi
    atama.save(update_fields=["durum", "baslama_zamani", "guncellenme"])
    DonemTamamlamaKaydi.objects.create(
        atama=atama,
        islem=DonemTamamlamaKaydi.Islem.BASLADI,
        yapan=user,
        zaman=simdi,
    )
    return atama


@transaction.atomic
def atama_tamamla(atama: CuzAtamasi, user: User) -> CuzAtamasi:
    if atama.katilimci.user_id != user.pk and not hatim_yonetebilir(user):
        raise PermissionError("Bu atamayı tamamlayamazsınız.")
    simdi = timezone.now()
    atama.durum = CuzAtamasi.Durum.TAMAMLANDI
    atama.tamamlama_zamani = simdi
    if not atama.baslama_zamani:
        atama.baslama_zamani = simdi
    atama.save(
        update_fields=["durum", "tamamlama_zamani", "baslama_zamani", "guncellenme"]
    )
    DonemTamamlamaKaydi.objects.create(
        atama=atama,
        islem=DonemTamamlamaKaydi.Islem.TAMAMLADI,
        yapan=user,
        zaman=simdi,
    )
    _donem_tamamlanma_kontrol(atama.donem)
    return atama


@transaction.atomic
def atama_geri_al(atama: CuzAtamasi, user: User) -> CuzAtamasi:
    if not hatim_yonetebilir(user):
        raise PermissionError("Geri alma yetkisi yok.")
    atama.durum = CuzAtamasi.Durum.OKUNUYOR if atama.baslama_zamani else CuzAtamasi.Durum.BASLANMADI
    atama.tamamlama_zamani = None
    atama.save(update_fields=["durum", "tamamlama_zamani", "guncellenme"])
    DonemTamamlamaKaydi.objects.create(
        atama=atama,
        islem=DonemTamamlamaKaydi.Islem.GERI_ALINDI,
        yapan=user,
    )
    return atama


def _donem_tamamlanma_kontrol(donem: HatimDonemi) -> None:
    bekleyen = donem.cuz_atamalari.exclude(
        durum__in=[
            CuzAtamasi.Durum.TAMAMLANDI,
            CuzAtamasi.Durum.MUAF,
            CuzAtamasi.Durum.DEVREDILDI,
        ]
    ).exists()
    if bekleyen:
        return
    donem.durum = HatimDonemi.Durum.TAMAMLANDI
    donem.save(update_fields=["durum", "guncellenme"])
    program = donem.program
    if program.donemler.exclude(durum=HatimDonemi.Durum.TAMAMLANDI).exists():
        return
    if program.program_bitis_tarihi and timezone.localdate() < program.program_bitis_tarihi:
        return
    # Otomatik kapanmaz — yetkili onayı bekler; bildirim gönderilir.


@transaction.atomic
def gecikmisleri_isaretle(donem: HatimDonemi) -> int:
    """Süresi geçmiş tamamlanmamış atamaları gecikmiş yap."""
    simdi = timezone.now()
    if simdi <= donem.bitis:
        return 0
    guncellenen = 0
    for atama in donem.cuz_atamalari.filter(
        durum__in=[CuzAtamasi.Durum.BASLANMADI, CuzAtamasi.Durum.OKUNUYOR]
    ):
        atama.durum = CuzAtamasi.Durum.GECIKMIS
        atama.save(update_fields=["durum", "guncellenme"])
        DonemTamamlamaKaydi.objects.create(
            atama=atama,
            islem=DonemTamamlamaKaydi.Islem.GECIKMIS,
        )
        guncellenen += 1
    return guncellenen


@transaction.atomic
def yeni_donem_baslat(program: HatimProgrami) -> HatimDonemi | None:
    """Sonraki dönemi oluşturur; önceki eksikleri gecikmiş olarak işaretler."""
    son = program.donemler.order_by("-sira").first()
    if son and son.durum == HatimDonemi.Durum.AKTIF:
        if program.gecikmis_sakla:
            gecikmisleri_isaretle(son)
        if not program.donemler.filter(durum=HatimDonemi.Durum.TAMAMLANDI, sira=son.sira).exists():
            if son.cuz_atamalari.exclude(
                durum__in=[
                    CuzAtamasi.Durum.TAMAMLANDI,
                    CuzAtamasi.Durum.MUAF,
                    CuzAtamasi.Durum.DEVREDILDI,
                ]
            ).exists():
                son.durum = HatimDonemi.Durum.TAMAMLANDI if False else HatimDonemi.Durum.AKTIF

    planlar = donem_planlari_uret(program)
    yeni_sira = (son.sira if son else 0) + 1
    if yeni_sira > len(planlar) and program.program_bitis_tarihi:
        return None
    if yeni_sira > len(planlar) and program.program_bitis_tarihi is None:
        if son:
            bas, bit = son.bitis, _donem_bitisi(
                son.bitis,
                program.tekrar_gun_sayisi() or 1,
                program.son_tamamlama_saati,
                hafta_sonu_dahil=program.hafta_sonu_dahil,
            )
        else:
            bas, bit = planlar[0]
    elif yeni_sira <= len(planlar):
        bas, bit = planlar[yeni_sira - 1]
    else:
        return None

    durum = (
        HatimDonemi.Durum.AKTIF
        if program.yeni_donem_otomatik
        else HatimDonemi.Durum.BEKLEMEDE
    )
    donem = HatimDonemi.objects.create(
        program=program,
        sira=yeni_sira,
        baslangic=bas,
        bitis=bit,
        durum=durum,
    )
    onceki = son if son and son.pk != donem.pk else None
    cuzleri_dagit(program, donem, onceki_donem=onceki)

    if program.hatirlatma_yeni_donem:
        _hatim_bildirim_gonder(
            program,
            tetik=HatimHatirlatmasi.Tetik.YENI_DONEM,
            baslik=f"{program.ad} · Yeni dönem",
            mesaj=f"Dönem {donem.sira} başladı. Son tarih: {date_format(donem.bitis, 'd F Y H:i')}.",
            donem=donem,
        )
    return donem


@transaction.atomic
def program_tamamla(program: HatimProgrami, *, dua_yapildi: bool = False) -> HatimProgrami:
    program.durum = HatimProgrami.Durum.TAMAMLANDI
    program.tamamlanma_zamani = timezone.now()
    program.dua_yapildi = dua_yapildi
    program.save(update_fields=["durum", "tamamlanma_zamani", "dua_yapildi", "guncellenme"])
    if program.hatirlatma_program_tamamlandi:
        _hatim_bildirim_gonder(
            program,
            tetik=HatimHatirlatmasi.Tetik.PROGRAM_TAMAMLANDI,
            baslik=f"{program.ad} tamamlandı",
            mesaj="Hatim programı tamamlanmıştır.",
        )
    return program


def _hatim_bildirim_gonder(
    program: HatimProgrami,
    *,
    tetik: str,
    baslik: str,
    mesaj: str,
    donem: HatimDonemi | None = None,
) -> int:
    link = reverse("hatim_detay", kwargs={"pk": program.pk})
    alicilar = [
        k.user
        for k in program.katilimcilar.filter(aktif=True, user__isnull=False)
    ]
    sayac = bildirim_gonder_coklu(
        alicilar,
        baslik=baslik,
        mesaj=mesaj,
        tur=Bildirim.Tur.PROGRAM,
        link=link,
        kaynak_model="HatimProgrami",
        kaynak_id=program.pk,
    )
    for user in alicilar:
        if not user:
            continue
        HatimHatirlatmasi.objects.create(
            program=program,
            tetik=tetik,
            donem=donem,
            alici=user,
        )
    return sayac


def grup_mesaj_taslagi(program: HatimProgrami, donem: HatimDonemi | None = None) -> str:
    donem = donem or aktif_donem(program)
    if not donem:
        return ""
    istat = donem_ilerleme_istatistik(donem)
    tamamlanan = istat.get("tamamlanan", 0)
    bitis = date_format(donem.bitis, "H:i")
    tarih = date_format(donem.bitis, "d F Y")
    return (
        f"Kıymetli Hocalarımız,\n"
        f"{program.ad} hatmimizin bu döneminde 30 cüzün {tamamlanan}'i tamamlanmıştır. "
        f"Henüz tamamlanmayan cüzlerimizin bugün saat {bitis}'ye kadar okunmasını rica ederiz.\n"
        f"— {PANEL_ORG}"
    )


def kisisel_mesaj_taslagi(atama: CuzAtamasi) -> str:
    program = atama.donem.program
    bitis = date_format(atama.donem.bitis, "d F Y H:i")
    return (
        f"Sayın {atama.katilimci.gorunen_ad},\n"
        f"{program.ad} kapsamında size verilen {atama.cuz_etiketi} "
        f"bu dönem {bitis} tarihine kadar tamamlanmalıdır.\n"
        f"— {PANEL_ORG}"
    )


def whatsapp_paylas_url(metin: str) -> str:
    return f"https://wa.me/?text={quote(metin)}"


def gecmis_rapor_satirlari(program: HatimProgrami) -> dict:
    donem_sayisi = program.donemler.count()
    tamamlanan_donem = program.donemler.filter(
        durum=HatimDonemi.Durum.TAMAMLANDI
    ).count()
    zamaninda = 0
    top_atama = 0
    for donem in program.donemler.prefetch_related("cuz_atamalari"):
        for atama in donem.cuz_atamalari.all():
            top_atama += 1
            if atama.durum == CuzAtamasi.Durum.TAMAMLANDI:
                if atama.tamamlama_zamani and atama.tamamlama_zamani <= donem.bitis:
                    zamaninda += 1
    oran = int(round(100 * zamaninda / top_atama)) if top_atama else 0
    eksik = []
    devredilen = 0
    for donem in program.donemler.all():
        eksik.extend(dagitilmayan_cuzler(donem))
        devredilen += donem.cuz_atamalari.filter(
            durum=CuzAtamasi.Durum.DEVREDILDI
        ).count()
    return {
        "ad": program.ad,
        "tur": program.get_tur_display(),
        "baslangic": program.baslangic_tarihi,
        "bitis": program.program_bitis_tarihi or (
            program.tamamlanma_zamani.date() if program.tamamlanma_zamani else None
        ),
        "tekrar": program.tekrar_etiketi(),
        "donem_sayisi": donem_sayisi,
        "tamamlanan_donem": tamamlanan_donem,
        "zamaninda_oran": oran,
        "eksik_cuzler": sorted(set(eksik)),
        "devredilen": devredilen,
        "katilimci_sayisi": program.katilimcilar.count(),
    }


def personel_listesi_secenekleri() -> QuerySet[PersonelProfili]:
    return PersonelProfili.objects.filter(aktif=True).order_by("ad_soyad")
