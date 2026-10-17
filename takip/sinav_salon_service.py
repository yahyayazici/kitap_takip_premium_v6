"""Seviye Tespit — kelebek sistemiyle salon yerleşimi.

Kelebek sistemi: aynı sınıftan öğrenciler yan yana / arka arkaya oturmaz ve her salona
sınıflar karışık dağılır. Yöntem:

1. Her sınıfın öğrencileri karıştırılır, aynı okuldan olanlar birbirinden uzaklaştırılır.
2. Her sınıf, tüm sıranın boyuna eşit aralıklarla yayılır (8. sınıf kalabalıksa bile
   sona yığılmaz). Ardından komşu iki koltukta aynı sınıf kalırsa ileriden uygun biriyle
   yer değiştirilir.
3. Öğrenciler salonlara kapasiteleri oranında dağıtılır; boş koltuklar da salonlara
   eşit yayılır. Salon içinde öğrenci masadan azsa herkes ayrı masaya oturur.
"""

from __future__ import annotations

import random
from collections import defaultdict

from django.db import transaction

from takip.sinav_basvuru_models import SinavBasvuru
from takip.sinav_salon_models import SinavSalon, SinavYerlesim


class YerlesimHatasi(Exception):
    pass


def _okula_gore_ayir(ogrenciler: list[SinavBasvuru], rnd: random.Random) -> list[SinavBasvuru]:
    """Aynı okuldan olanları sıra içinde birbirinden uzaklaştırır (karışık sırayla)."""
    okullar: dict[str, list[SinavBasvuru]] = defaultdict(list)
    for o in ogrenciler:
        okullar[(o.okul_adi or "").strip().casefold()].append(o)
    gruplar = list(okullar.values())
    for g in gruplar:
        rnd.shuffle(g)
    return _esit_yay(gruplar, rnd)


def _esit_yay(gruplar: list[list], rnd: random.Random) -> list:
    """Her grubun elemanlarını tüm sıranın boyuna eşit aralıklarla dağıtır."""
    konumlu = []
    for g in gruplar:
        n = len(g)
        kayma = rnd.random() * 0.5
        for i, eleman in enumerate(g):
            konumlu.append(((i + 0.25 + kayma) / n, rnd.random(), eleman))
    konumlu.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in konumlu]


def _komsulari_ayir(sira: list[SinavBasvuru]) -> list[SinavBasvuru]:
    """Arka arkaya aynı sınıf düşerse ileriden uygun biriyle yer değiştirir."""
    sira = list(sira)
    for i in range(1, len(sira)):
        if sira[i].sinif != sira[i - 1].sinif:
            continue
        for j in range(i + 1, len(sira)):
            aday = sira[j]
            if aday.sinif == sira[i - 1].sinif:
                continue
            if i + 1 < len(sira) and j != i + 1 and aday.sinif == sira[i + 1].sinif:
                continue
            # j'nin yeni komşuları sira[i] ile çakışmasın
            if sira[j - 1].sinif == sira[i].sinif and j - 1 != i:
                continue
            if j + 1 < len(sira) and sira[j + 1].sinif == sira[i].sinif:
                continue
            sira[i], sira[j] = sira[j], sira[i]
            break
    return sira


def kelebek_sirasi(ogrenciler: list[SinavBasvuru], tohum: int | None = None) -> list[SinavBasvuru]:
    rnd = random.Random(tohum)
    siniflar: dict[str, list[SinavBasvuru]] = defaultdict(list)
    for o in ogrenciler:
        siniflar[o.sinif or ""].append(o)
    gruplar = [_okula_gore_ayir(g, rnd) for _, g in sorted(siniflar.items())]
    return _komsulari_ayir(_esit_yay(gruplar, rnd))


def _paylari_hesapla(kapasiteler: list[int], toplam: int) -> list[int]:
    """Öğrenci sayısını salonlara kapasite oranında böler (en büyük kalan yöntemi)."""
    kap_toplam = sum(kapasiteler)
    if not kap_toplam:
        return [0] * len(kapasiteler)
    ham = [toplam * k / kap_toplam for k in kapasiteler]
    paylar = [min(int(h), k) for h, k in zip(ham, kapasiteler)]
    kalan = toplam - sum(paylar)
    sirali = sorted(range(len(kapasiteler)), key=lambda i: ham[i] - int(ham[i]), reverse=True)
    while kalan > 0:
        ilerledi = False
        for i in sirali:
            if kalan and paylar[i] < kapasiteler[i]:
                paylar[i] += 1
                kalan -= 1
                ilerledi = True
        if not ilerledi:
            break
    return paylar


def _salon_koltuklari(salon: SinavSalon, adet: int) -> list[tuple[int, int]]:
    """Salonda `adet` öğrenci için (masa, koltuk) listesi.

    Öğrenci masadan azsa her öğrenci ayrı masaya oturur; çoksa masalar doldurulur.
    """
    kisi = max(salon.masa_kisi, 1)
    if adet <= salon.masa_sayisi:
        return [(m, 1) for m in range(1, adet + 1)]
    koltuklar = []
    for m in range(1, salon.masa_sayisi + 1):
        for k in range(1, kisi + 1):
            koltuklar.append((m, k))
    # Masa başına önce bir kişi, sonra ikinci koltuklar: komşu masalar da karışık olur.
    koltuklar.sort(key=lambda mk: (mk[1], mk[0]))
    secilen = sorted(koltuklar[:adet])
    return secilen


def salonlar(sinav_adi: str) -> list[SinavSalon]:
    return list(SinavSalon.objects.filter(sinav_adi=sinav_adi).order_by("sira", "id"))


def yerlestirilecekler(sinav_adi: str):
    return SinavBasvuru.objects.filter(sinav_adi=sinav_adi)


@transaction.atomic
def kelebek_yerlestir(sinav_adi: str, tohum: int | None = None) -> dict:
    salon_listesi = salonlar(sinav_adi)
    if not salon_listesi:
        raise YerlesimHatasi("Önce salonları ve masa sayılarını girin.")
    ogrenciler = list(yerlestirilecekler(sinav_adi))
    if not ogrenciler:
        raise YerlesimHatasi("Yerleştirilecek başvuru yok.")
    kapasiteler = [s.kapasite for s in salon_listesi]
    if sum(kapasiteler) < len(ogrenciler):
        eksik = len(ogrenciler) - sum(kapasiteler)
        raise YerlesimHatasi(
            f"{len(ogrenciler)} öğrenci için {sum(kapasiteler)} kişilik yer var; "
            f"{eksik} kişilik yer daha gerekiyor."
        )

    sira = kelebek_sirasi(ogrenciler, tohum)
    paylar = _paylari_hesapla(kapasiteler, len(sira))

    SinavYerlesim.objects.filter(salon__sinav_adi=sinav_adi).delete()
    SinavYerlesim.objects.filter(basvuru__in=ogrenciler).delete()

    yeni = []
    bas = 0
    for salon, pay in zip(salon_listesi, paylar):
        grup = sira[bas : bas + pay]
        bas += pay
        for ogrenci, (masa, koltuk) in zip(grup, _salon_koltuklari(salon, pay)):
            yeni.append(SinavYerlesim(basvuru=ogrenci, salon=salon, masa_no=masa, koltuk=koltuk))
    SinavYerlesim.objects.bulk_create(yeni)
    return {"ogrenci": len(yeni), "salon": sum(1 for p in paylar if p)}


@transaction.atomic
def salonlari_kaydet(sinav_adi: str, satirlar: list[tuple[str, int]], masa_kisi: int) -> bool:
    """Salon listesini kaydeder. Yapı değiştiyse mevcut yerleşim silinir; değiştiyse True."""
    masa_kisi = 2 if masa_kisi == 2 else 1
    mevcut = salonlar(sinav_adi)
    once = [(s.ad, s.masa_sayisi, s.masa_kisi) for s in mevcut]
    sonra = [(ad, masa, masa_kisi) for ad, masa in satirlar]
    if once == sonra:
        return False
    yapi_degisti = [(m, k) for _, m, k in once] != [(m, k) for _, m, k in sonra]
    if yapi_degisti:
        SinavSalon.objects.filter(sinav_adi=sinav_adi).delete()
        SinavSalon.objects.bulk_create(
            [
                SinavSalon(sinav_adi=sinav_adi, ad=ad, sira=i, masa_sayisi=masa, masa_kisi=masa_kisi)
                for i, (ad, masa) in enumerate(satirlar, start=1)
            ]
        )
    else:
        for salon, (ad, _) in zip(mevcut, satirlar):
            if salon.ad != ad:
                salon.ad = ad
                salon.save(update_fields=["ad"])
    return yapi_degisti


def salon_ozeti(sinav_adi: str) -> dict:
    salon_listesi = salonlar(sinav_adi)
    ogrenci_sayisi = yerlestirilecekler(sinav_adi).count()
    yerlesimler = list(
        SinavYerlesim.objects.filter(salon__sinav_adi=sinav_adi)
        .select_related("salon", "basvuru")
        .order_by("salon__sira", "masa_no", "koltuk")
    )
    salon_yerlesim: dict[int, list[SinavYerlesim]] = defaultdict(list)
    for y in yerlesimler:
        salon_yerlesim[y.salon_id].append(y)

    kartlar = []
    for salon in salon_listesi:
        liste = salon_yerlesim.get(salon.pk, [])
        masalar: dict[int, list] = {m: [None] * max(salon.masa_kisi, 1) for m in range(1, salon.masa_sayisi + 1)}
        for y in liste:
            if y.masa_no in masalar and 1 <= y.koltuk <= len(masalar[y.masa_no]):
                masalar[y.masa_no][y.koltuk - 1] = y
        sinif_dagilimi: dict[str, int] = defaultdict(int)
        for y in liste:
            sinif_dagilimi[y.basvuru.sinif or "—"] += 1
        kartlar.append(
            {
                "salon": salon,
                "yerlesimler": liste,
                "masalar": [{"no": no, "koltuklar": k} for no, k in masalar.items()],
                "siniflar": sorted(sinif_dagilimi.items()),
                "dolu": len(liste),
            }
        )

    kapasite = sum(s.kapasite for s in salon_listesi)
    yerlesen = len(yerlesimler)
    return {
        "salonlar": kartlar,
        "kapasite": kapasite,
        "ogrenci": ogrenci_sayisi,
        "yerlesen": yerlesen,
        "yerlesmeyen": max(ogrenci_sayisi - yerlesen, 0),
        "yer_yetmiyor": kapasite < ogrenci_sayisi,
        "eksik_yer": max(ogrenci_sayisi - kapasite, 0),
        "masa_kisi": salon_listesi[0].masa_kisi if salon_listesi else 1,
        "yerlesim_var": yerlesen > 0,
    }


def yerlesim_bul(basvuru: SinavBasvuru) -> SinavYerlesim | None:
    try:
        return SinavYerlesim.objects.select_related("salon").get(basvuru=basvuru)
    except SinavYerlesim.DoesNotExist:
        return None
