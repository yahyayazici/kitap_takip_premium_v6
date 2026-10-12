"""Optik okuyucu çıktısını (sabit genişlikli TXT/DAT) şablona göre okur."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.db import transaction

from okuma.models import Deneme, Ogrenci, OptikSablon, OptikSatir, OptikYukleme

GECERLI_SIK = set("ABCDE")


@dataclass
class OkunanSatir:
    satir_no: int
    ham: str
    numara_ham: str = ""
    numara: str = ""
    kitapcik: str = ""
    sinif: str = ""
    sube: str = ""
    ad_soyad: str = ""
    cevaplar: str = ""
    uyarilar: list[str] = field(default_factory=list)
    hatalar: list[str] = field(default_factory=list)


def metni_coz(veri: bytes, kodlama: str = "cp1254") -> str:
    """UTF-8 BOM'lu ya da UTF-8 gelen dosyaları da kabul et; yoksa şablon kodlaması."""
    if veri.startswith(b"\xef\xbb\xbf"):
        return veri[3:].decode("utf-8")
    try:
        return veri.decode("utf-8")
    except UnicodeDecodeError:
        return veri.decode(kodlama, errors="replace")


def _alan(satir: str, bas: int | None, uzunluk: int) -> str:
    if not bas or uzunluk <= 0:
        return ""
    return satir[bas - 1 : bas - 1 + uzunluk]


def numara_normalize(deger: str) -> str:
    deger = deger.strip()
    return deger.lstrip("0") or ("0" if deger else "")


def satir_ayristir(satir_no: int, satir: str, sablon: OptikSablon, soru_sayisi: int) -> OkunanSatir:
    okunan = OkunanSatir(satir_no=satir_no, ham=satir)

    numara_ham = _alan(satir, sablon.numara_bas, sablon.numara_uzunluk)
    okunan.numara_ham = numara_ham
    parcalar = numara_ham.split()
    if not parcalar:
        okunan.hatalar.append("Numara boş")
    else:
        if len(parcalar) > 1:
            # Numara alanında fazladan işaret var: en sağdaki grup gerçek numara kabul edilir.
            okunan.uyarilar.append(f"Numara alanında fazladan işaret: '{numara_ham.strip()}' → {parcalar[-1]}")
        aday = parcalar[-1]
        if not aday.isdigit():
            okunan.hatalar.append(f"Numara rakam değil: '{aday}'")
        okunan.numara = numara_normalize(aday)

    okunan.kitapcik = _alan(satir, sablon.kitapcik_bas, 1).strip().upper()
    okunan.sinif = _alan(satir, sablon.sinif_bas, sablon.sinif_uzunluk).strip()
    okunan.sube = _alan(satir, sablon.sube_bas, sablon.sube_uzunluk).strip().upper()
    okunan.ad_soyad = re.sub(r"\s+", " ", _alan(satir, sablon.ad_bas, sablon.ad_uzunluk)).strip()

    cevap = satir[sablon.cevap_bas - 1 : sablon.cevap_bas - 1 + soru_sayisi]
    if len(cevap.rstrip()) and len(cevap) < soru_sayisi:
        okunan.uyarilar.append(f"Satır kısa: {len(cevap)}/{soru_sayisi} cevap alanı okundu")
    # Geçerli şık dışındaki işaretler (*, X, rakam) çift/hatalı işaretleme sayılır.
    okunan.cevaplar = "".join(
        c if c in GECERLI_SIK or c == " " else "*" for c in cevap.upper().ljust(soru_sayisi)
    )
    return okunan


def dosyayi_ayristir(metin: str, sablon: OptikSablon, soru_sayisi: int) -> list[OkunanSatir]:
    sonuc = []
    for i, satir in enumerate(metin.splitlines(), start=1):
        if not satir.strip():
            continue
        sonuc.append(satir_ayristir(i, satir, sablon, soru_sayisi))
    return sonuc


@transaction.atomic
def optik_yukle(
    deneme: Deneme,
    sablon: OptikSablon,
    dosya_adi: str,
    veri: bytes,
    *,
    kullanici=None,
    otomatik_ogrenci: bool = True,
) -> OptikYukleme:
    from okuma.services.puanlama import kitapcik_tahmin_et

    soru_sayisi = deneme.optik_uzunluk
    if not deneme.toplam_soru:
        raise ValueError("Önce cevap anahtarını yükleyin; soru sayısı bilinmiyor.")

    okunanlar = dosyayi_ayristir(metni_coz(veri, sablon.kodlama), sablon, soru_sayisi)
    yukleme = OptikYukleme.objects.create(deneme=deneme, sablon=sablon, dosya_adi=dosya_adi, yukleyen=kullanici)

    gorulen = set(
        OptikSatir.objects.filter(yukleme__deneme=deneme, dahil=True)
        .exclude(yukleme=yukleme)
        .values_list("numara", flat=True)
    )
    kitapciklar = deneme.kitapcik_listesi

    for o in okunanlar:
        ogrenci = None
        if o.numara and not o.hatalar:
            ogrenci = Ogrenci.objects.filter(numara=o.numara).first()
            if ogrenci is None and otomatik_ogrenci:
                ogrenci = Ogrenci.objects.create(
                    numara=o.numara,
                    ad_soyad=o.ad_soyad,
                    sinif_seviyesi=o.sinif or deneme.sinif_seviyesi,
                    sube=o.sube,
                )
                o.uyarilar.append("Yeni öğrenci kaydı açıldı")
            elif ogrenci is None:
                o.hatalar.append(f"{o.numara} numaralı öğrenci kayıtlı değil")
            elif ogrenci and o.sube and not ogrenci.sube:
                ogrenci.sube = o.sube
                ogrenci.save(update_fields=["sube"])
            if ogrenci and o.ad_soyad and not ogrenci.ad_soyad:
                ogrenci.ad_soyad = o.ad_soyad
                ogrenci.save(update_fields=["ad_soyad"])

        if o.kitapcik not in kitapciklar:
            tahmin = kitapcik_tahmin_et(deneme, o.cevaplar)
            eski = o.kitapcik or "boş"
            if tahmin:
                o.kitapcik = tahmin
                o.uyarilar.append(f"Kitapçık {eski}; cevaplara göre {tahmin} olarak belirlendi")
            else:
                o.hatalar.append(f"Kitapçık {eski} ve cevaplardan belirlenemedi")
                o.kitapcik = ""

        dahil = True
        if o.numara and o.numara in gorulen:
            o.hatalar.append("Bu numara bu denemede zaten okundu")
            dahil = False
        if o.numara:
            gorulen.add(o.numara)

        durum = OptikSatir.Durum.HATA if o.hatalar else (OptikSatir.Durum.UYARI if o.uyarilar else OptikSatir.Durum.TAMAM)
        OptikSatir.objects.create(
            yukleme=yukleme,
            satir_no=o.satir_no,
            ham=o.ham,
            numara=o.numara,
            kitapcik=o.kitapcik,
            sinif=o.sinif,
            sube=o.sube,
            ad_soyad=o.ad_soyad,
            cevaplar=o.cevaplar,
            ogrenci=ogrenci,
            durum=durum,
            mesaj="; ".join(o.hatalar + o.uyarilar)[:300],
            dahil=dahil and not o.hatalar,
        )
    return yukleme
