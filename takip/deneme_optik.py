"""Günay optik okuyucu .dat dosyasını deneme sonucuna çevirir.

Düzen, Günay-2024.dat örneğinden çıkarıldı: her satır 150 karakter,
Windows-1254. Cevap anahtarı dosyada yoktur; yükleyen yazar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from takip.deneme_excel import DenemeImportOnizleme, DenemeImportSatir, talebe_eslestir
from takip.deneme_models import DenemeBransSonucu
from takip.deneme_service import BRANS_ETIKETLERI
from takip.models import Talebe

KAYIT_UZUNLUK = 150
# Üç şık bloğu: 15 + 45 + 15. Aradaki boşluklar formdaki ayraçtır, soru değildir.
CEVAP_DILIMLERI = (slice(50, 65), slice(70, 115), slice(120, 135))
GECERLI_SIK = frozenset("ABCD")

_DERS_ADLARI = {
    "turkce": "turkce",
    "matematik": "matematik",
    "mat": "matematik",
    "fen": "fen",
    "fenbilimleri": "fen",
    "sosyal": "sosyal",
    "sosyalbilgiler": "sosyal",
    "inkilap": "sosyal",
    "din": "din",
    "dinkulturu": "din",
    "ingilizce": "ingilizce",
    "ing": "ingilizce",
}


class OptikHata(Exception):
    """Kullanıcıya gösterilen, düzeltilebilir optik dosya / anahtar hatası."""


@dataclass
class OptikKayit:
    satir_no: int
    ogrenci_no: str
    numara_guvenilir: bool
    tc: str
    ad_soyad: str
    kitapcik: str
    sinif: str
    sube: str
    cevaplar: str
    uyarilar: list[str] = field(default_factory=list)


@dataclass
class OptikDosya:
    kayitlar: list[OptikKayit]
    uyarilar: list[str] = field(default_factory=list)

    @property
    def cevap_sayisi(self) -> int:
        if not self.kayitlar:
            return 0
        return len(self.kayitlar[0].cevaplar)


def _metin_oku(ham: bytes) -> str:
    if not ham or not ham.strip():
        raise OptikHata("Dosya boş.")
    for kod in ("utf-8-sig", "cp1254"):
        try:
            return ham.decode(kod)
        except UnicodeDecodeError:
            continue
    return ham.decode("cp1254", errors="replace")


def _cevap_seridi(satir: str) -> str:
    return "".join(satir[dilim] for dilim in CEVAP_DILIMLERI)


def gunay_dat_oku(ham: bytes) -> OptikDosya:
    """150 karakterlik Günay satırlarını talebe + şık şeridine ayırır."""
    metin = _metin_oku(ham)
    dosya = OptikDosya(kayitlar=[])
    for n, ham_satir in enumerate(metin.splitlines(), start=1):
        if not ham_satir.strip():
            continue
        if len(ham_satir) != KAYIT_UZUNLUK:
            dosya.uyarilar.append(
                f"{n}. satır {len(ham_satir)} karakter; Günay kaydı 150 karakter olmalı, atlandı."
            )
            continue
        dosya.kayitlar.append(_satir_ayir(n, ham_satir))
    if not dosya.kayitlar:
        raise OptikHata(
            "Günay optik kaydı yok. Her satır 150 karakter olmalı (.dat, Türkçe Windows)."
        )
    return dosya


def _satir_ayir(satir_no: int, satir: str) -> OptikKayit:
    tc = satir[1:12].strip()
    if not (tc.isdigit() and len(tc) == 11):
        tc = ""
    ara = satir[12:20]
    no_ham = satir[20:25].strip()
    numara_guvenilir = no_ham.isdigit() and not any(c.isdigit() for c in ara)
    kitapcik = satir[25].strip().upper()
    if kitapcik not in {"A", "B"}:
        kitapcik = ""
    sinif = satir[26].strip()
    if not sinif.isdigit():
        sinif = ""
    sube = satir[27].strip().upper()
    if not sube.isalpha():
        sube = ""
    ad = " ".join(satir[29:50].split())
    cevaplar = _cevap_seridi(satir).upper()
    uyarilar: list[str] = []
    if not numara_guvenilir:
        uyarilar.append("Numara alanı kaymış, isimle aranacak.")
    if not ad:
        uyarilar.append("Ad soyad okunamadı.")
    cift = cevaplar.count("*")
    if cift:
        uyarilar.append(f"{cift} soruda çift işaret var, yanlış sayıldı.")
    return OptikKayit(
        satir_no=satir_no,
        ogrenci_no=no_ham if numara_guvenilir else "",
        numara_guvenilir=numara_guvenilir,
        tc=tc,
        ad_soyad=ad,
        kitapcik=kitapcik,
        sinif=sinif,
        sube=sube,
        cevaplar=cevaplar,
        uyarilar=uyarilar,
    )


def _katla(metin: str) -> str:
    s = metin.strip().replace("İ", "i").replace("I", "ı")
    s = s.lower().translate(str.maketrans("ışğüöçâîû", "isguocaiu"))
    return "".join(ch for ch in s if ch.isalnum())


def dagilim_coz(metin: str, cevap_sayisi: int) -> list[tuple[str, int]]:
    """«turkce 15» satırlarını optikteki ders sırasına çevirir."""
    if not (metin or "").strip():
        raise OptikHata(
            "Soru dağılımını yazın. Her satır bir ders: turkce 15"
        )
    dagilim: list[tuple[str, int]] = []
    gorulen: set[str] = set()
    for ham in metin.splitlines():
        parca = ham.strip()
        if not parca or parca.startswith("#"):
            continue
        parca = parca.replace(":", " ").replace("=", " ")
        kelimeler = parca.split()
        if len(kelimeler) < 2:
            raise OptikHata(f"«{ham.strip()}» anlaşılmadı. Örnek: turkce 15")
        if kelimeler[0].isdigit():
            adet_metin, ad = kelimeler[0], " ".join(kelimeler[1:])
        elif kelimeler[-1].isdigit():
            adet_metin, ad = kelimeler[-1], " ".join(kelimeler[:-1])
        else:
            raise OptikHata(f"«{ham.strip()}» satırında soru sayısı yok.")
        kod = _DERS_ADLARI.get(_katla(ad))
        if not kod:
            raise OptikHata(
                f"«{ad}» dersi yok. Türkçe, Matematik, Fen, Sosyal, Din, İngilizce yazın."
            )
        if kod in gorulen:
            raise OptikHata(f"{BRANS_ETIKETLERI[kod]} iki kez yazılmış.")
        adet = int(adet_metin)
        if adet < 0:
            raise OptikHata("Soru sayısı eksi olamaz.")
        if adet == 0:
            continue
        gorulen.add(kod)
        dagilim.append((kod, adet))
    if not dagilim:
        raise OptikHata("En az bir dersin soru sayısı yazılmalı.")
    toplam = sum(adet for _, adet in dagilim)
    if toplam != cevap_sayisi:
        raise OptikHata(
            f"Soru sayıları toplamı {toplam}, optikte {cevap_sayisi} işaret var. "
            "İkisi eşit olmalı."
        )
    return dagilim


def anahtar_temizle(metin: str, cevap_sayisi: int, *, kitapcik: str) -> str:
    anahtar = "".join((metin or "").split()).upper().replace("İ", "I")
    if not anahtar:
        raise OptikHata(f"{kitapcik} kitapçık cevap anahtarı boş.")
    yabanci = sorted({ch for ch in anahtar if ch not in GECERLI_SIK})
    if yabanci:
        raise OptikHata(
            f"{kitapcik} kitapçık anahtarında yalnızca A, B, C, D olabilir "
            f"({', '.join(yabanci)} var)."
        )
    if len(anahtar) != cevap_sayisi:
        raise OptikHata(
            f"{kitapcik} kitapçık anahtarı {len(anahtar)} harf, "
            f"optikte {cevap_sayisi} soru var."
        )
    return anahtar


def _sik_say(cevaplar: str, anahtar: str) -> tuple[int, int, int]:
    dogru = yanlis = bos = 0
    for verilen, beklenen in zip(cevaplar, anahtar):
        if verilen in {" ", ""}:
            bos += 1
        elif verilen == "*":
            yanlis += 1
        elif verilen == beklenen:
            dogru += 1
        elif verilen in GECERLI_SIK:
            yanlis += 1
        else:
            bos += 1
    return dogru, yanlis, bos


def _puan(net: Decimal, soru: int) -> str:
    if soru <= 0:
        return "0.00"
    puan = (net / Decimal(soru) * Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return format(puan, "f")


def _no_ile_bul(ogrenci_no: str) -> Talebe | None:
    yalin = ogrenci_no.strip().lstrip("0") or "0"
    bicimler = {ogrenci_no.strip(), yalin, yalin.zfill(3), yalin.zfill(4), yalin.zfill(5)}
    adaylar = list(Talebe.objects.filter(aktif=True, talebe_no__in=bicimler))
    if len(adaylar) == 1:
        return adaylar[0]
    return None


def _tc_ile_bul(tc: str) -> Talebe | None:
    if not tc:
        return None
    adaylar = list(Talebe.objects.filter(aktif=True, tc_kimlik=tc))
    if len(adaylar) == 1:
        return adaylar[0]
    return None


def _sinif_metni(kayit: OptikKayit) -> str:
    parcalar = []
    if kayit.sinif and kayit.sube:
        parcalar.append(f"{kayit.sinif}{kayit.sube}")
    elif kayit.sinif:
        parcalar.append(f"{kayit.sinif}. sınıf")
    if kayit.kitapcik:
        parcalar.append(f"{kayit.kitapcik} kitapçık")
    if kayit.ogrenci_no:
        parcalar.append(f"no {kayit.ogrenci_no.lstrip('0') or '0'}")
    return " · ".join(parcalar)


def optik_onizleme(
    dosya: OptikDosya,
    dagilim: list[tuple[str, int]],
    anahtar_a: str,
    anahtar_b: str = "",
) -> DenemeImportOnizleme:
    """Şıkları doğru/yanlış/boş ve nete çevirip Excel aktarımının önizlemesine koyar."""
    onizleme = DenemeImportOnizleme(
        format="optik",
        hatalar=list(dosya.uyarilar),
        aciklama=_dagilim_metni(dagilim),
    )
    for kayit in dosya.kayitlar:
        kitap = kayit.kitapcik or "A"
        anahtar = anahtar_a if kitap == "A" else anahtar_b
        satir = DenemeImportSatir(
            satir_no=kayit.satir_no,
            excel_ad_soyad=kayit.ad_soyad or f"No {kayit.ogrenci_no or kayit.satir_no}",
            sinif=_sinif_metni(kayit),
            hatalar=list(kayit.uyarilar),
        )
        if kitap == "B" and not anahtar_b:
            satir.puan = ""
            satir.hatalar.append("B kitapçık anahtarı yok, puan yazılmadı.")
        elif not anahtar:
            satir.puan = ""
            satir.hatalar.append("Cevap anahtarı yok, puan yazılmadı.")
        else:
            _puanlari_yaz(satir, kayit.cevaplar, anahtar, dagilim)

        sinif_eslesme = ""
        if kayit.sinif and kayit.sube:
            sinif_eslesme = f"{kayit.sinif}{kayit.sube}"
        elif kayit.sinif:
            sinif_eslesme = kayit.sinif

        talebe = _no_ile_bul(kayit.ogrenci_no) if kayit.numara_guvenilir else None
        if talebe:
            satir.talebe_id = talebe.id
            satir.eslesme = "otomatik"
        else:
            talebe = _tc_ile_bul(kayit.tc)
            if talebe:
                satir.talebe_id = talebe.id
                satir.eslesme = "otomatik"
            else:
                bulunan, eslesme, oneriler = talebe_eslestir(
                    kayit.ad_soyad, sinif_eslesme
                )
                satir.eslesme = eslesme
                satir.oneriler = oneriler
                if bulunan:
                    satir.talebe_id = bulunan.id
                elif oneriler:
                    en_iyi = oneriler[0]
                    satir.oneri_talebe_id = en_iyi["id"]
                    satir.oneri_ad_soyad = en_iyi["ad_soyad"]
                    satir.oneri_sinif = en_iyi.get("sinif", "")
                    satir.oneri_oran = int(en_iyi.get("oran", 0))
                    satir.eslesme = "oneri"
                    satir.hatalar.append(
                        f"«{kayit.ad_soyad}» sitedeki «{en_iyi['ad_soyad']}» "
                        f"(%{en_iyi['oran']}) talebesine benziyor — doğru mu?"
                    )
        onizleme.satirlar.append(satir)
    return onizleme


def _dagilim_metni(dagilim: list[tuple[str, int]]) -> str:
    parcalar = [f"{BRANS_ETIKETLERI[kod]} {adet}" for kod, adet in dagilim]
    return " · ".join(parcalar)


def _puanlari_yaz(
    satir: DenemeImportSatir,
    cevaplar: str,
    anahtar: str,
    dagilim: list[tuple[str, int]],
) -> None:
    imlec = 0
    for kod, adet in dagilim:
        parca = cevaplar[imlec : imlec + adet]
        kilit = anahtar[imlec : imlec + adet]
        imlec += adet
        dogru, yanlis, bos = _sik_say(parca, kilit)
        net = DenemeBransSonucu.net_hesapla(dogru, yanlis)
        satir.branslar[kod] = {
            "dogru": dogru,
            "yanlis": yanlis,
            "bos": bos,
            "net": str(net),
        }
    t_dogru = sum(v["dogru"] for v in satir.branslar.values())
    t_yanlis = sum(v["yanlis"] for v in satir.branslar.values())
    t_bos = sum(v["bos"] for v in satir.branslar.values())
    t_net = sum(
        (Decimal(v["net"]) for v in satir.branslar.values()),
        Decimal("0"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    soru = sum(adet for _, adet in dagilim)
    satir.toplam = {
        "dogru": t_dogru,
        "yanlis": t_yanlis,
        "bos": t_bos,
        "net": str(t_net),
    }
    satir.puan = _puan(t_net, soru)
