"""Optik .dat dosyasını form haritasına göre puanlar.

Okuyucu tektir. Kolonlar OptikForm kaydındadır. Örnek dosyanın düzeni
birinci form olarak tohumlanır. Sonuçlar bu uygulamanın kendi tablosuna
yazılır; ana sitedeki talebe veya deneme kayıtlarına dokunulmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

GECERLI_SIK = frozenset("ABCD")
TEK_ALANLAR = frozenset({"tc", "numara", "numara_kontrol", "kitapcik", "sinif", "sube", "ad"})
ALAN_ADLARI = {
    "tc": "tc",
    "numara": "numara",
    "ogrencino": "numara",
    "ogrencinumarasi": "numara",
    "numarakontrol": "numara_kontrol",
    "tasma": "numara_kontrol",
    "kitapcik": "kitapcik",
    "sinif": "sinif",
    "sube": "sube",
    "ad": "ad",
    "adsoyad": "ad",
    "sik": "sik",
    "cevap": "sik",
}

ORNEK_FORM_AD = "Örnek kayıt 150"
ORNEK_FORM_ACIKLAMA = "Örnek .dat dosyasındaki düzen. Satır 150 karakter, 75 şık."
ORNEK_SATIR = 150
ORNEK_KODLAMA = "cp1254"
ORNEK_ALANLAR = (
    ("tc", 2, 12),
    ("numara_kontrol", 13, 20),
    ("numara", 21, 25),
    ("kitapcik", 26, 26),
    ("sinif", 27, 27),
    ("sube", 28, 28),
    ("ad", 30, 50),
    ("sik", 51, 65),
    ("sik", 71, 115),
    ("sik", 121, 135),
)

DERS_ETIKETLERI = {
    "turkce": "Türkçe",
    "matematik": "Matematik",
    "fen": "Fen Bilimleri",
    "sosyal": "Sosyal Bilgiler",
    "din": "Din Kültürü",
    "ingilizce": "İngilizce",
}
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
    "dinkveab": "din",
    "dinkulturuvveahlakbilgisi": "din",
    "dinkulturuvveahlak": "din",
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
    ad_soyad: str
    kitapcik: str
    sinif: str
    sube: str
    cevaplar: str
    uyarilar: list[str] = field(default_factory=list)


@dataclass
class FormAlani:
    tur: str
    baslangic: int
    bitis: int


@dataclass
class FormHaritasi:
    satir_uzunluk: int
    kodlama: str
    alanlar: list[FormAlani]

    def dilim(self, alan: FormAlani) -> slice:
        return slice(alan.baslangic - 1, alan.bitis)

    def alan(self, tur: str) -> FormAlani | None:
        return next((a for a in self.alanlar if a.tur == tur), None)

    def sik_alanlari(self) -> list[FormAlani]:
        return [a for a in self.alanlar if a.tur == "sik"]

    @property
    def sik_sayisi(self) -> int:
        return sum(a.bitis - a.baslangic + 1 for a in self.sik_alanlari())


@dataclass
class OptikDosya:
    kayitlar: list[OptikKayit]
    uyarilar: list[str] = field(default_factory=list)

    @property
    def cevap_sayisi(self) -> int:
        if not self.kayitlar:
            return 0
        return len(self.kayitlar[0].cevaplar)


@dataclass
class PuanSatiri:
    satir_no: int
    ogrenci_no: str
    ad: str
    kitapcik: str
    sinif_metni: str
    uyarilar: list[str]
    cevaplar: str
    puanlandi: bool
    dogru: int = 0
    yanlis: int = 0
    bos: int = 0
    net: str = "0.00"
    puan: str = ""
    sorular: list[dict] = field(default_factory=list)


def ornek_harita() -> FormHaritasi:
    return FormHaritasi(
        satir_uzunluk=ORNEK_SATIR,
        kodlama=ORNEK_KODLAMA,
        alanlar=[FormAlani(*uc) for uc in ORNEK_ALANLAR],
    )


def ornek_dat_oku(ham: bytes) -> OptikDosya:
    return optik_oku(ham, ornek_harita())


def harita_from_form(form) -> FormHaritasi:
    return FormHaritasi(
        satir_uzunluk=form.satir_uzunluk,
        kodlama=form.kodlama or ORNEK_KODLAMA,
        alanlar=[FormAlani(a.tur, a.baslangic, a.bitis) for a in form.alanlar.all()],
    )


def _metin_oku(ham: bytes, kodlama: str) -> str:
    if not ham or not ham.strip():
        raise OptikHata("Dosya boş.")
    sirali = []
    for kod in (kodlama, "utf-8-sig", "cp1254"):
        if kod and kod not in sirali:
            sirali.append(kod)
    for kod in sirali:
        try:
            return ham.decode(kod)
        except (UnicodeDecodeError, LookupError):
            continue
    return ham.decode(kodlama or "cp1254", errors="replace")


def _parca(satir: str, harita: FormHaritasi, tur: str) -> str:
    alan = harita.alan(tur)
    if alan is None or alan.baslangic - 1 >= len(satir):
        return ""
    return satir[harita.dilim(alan)]


def optik_oku(ham: bytes, harita: FormHaritasi) -> OptikDosya:
    """Form haritasındaki kolonlardan kimlik ve şık şeridini ayırır."""
    if harita.sik_sayisi <= 0:
        raise OptikHata("Formda şık bölgesi yok.")
    metin = _metin_oku(ham, harita.kodlama)
    dosya = OptikDosya(kayitlar=[])
    for n, ham_satir in enumerate(metin.splitlines(), start=1):
        if not ham_satir.strip():
            continue
        if len(ham_satir) != harita.satir_uzunluk:
            dosya.uyarilar.append(
                f"{n}. satır {len(ham_satir)} karakter; "
                f"bu form {harita.satir_uzunluk} karakter bekler, atlandı."
            )
            continue
        dosya.kayitlar.append(_satir_ayir(n, ham_satir, harita))
    if not dosya.kayitlar:
        raise OptikHata(
            f"Optik kayıt yok. Her satır {harita.satir_uzunluk} karakter olmalı."
        )
    return dosya


def _satir_ayir(satir_no: int, satir: str, harita: FormHaritasi) -> OptikKayit:
    kontrol = _parca(satir, harita, "numara_kontrol")
    no_ham = _parca(satir, harita, "numara").strip()
    numara_guvenilir = bool(no_ham) and no_ham.isdigit() and not any(c.isdigit() for c in kontrol)
    kitapcik = _parca(satir, harita, "kitapcik").strip().upper()
    if kitapcik not in {"A", "B"}:
        kitapcik = ""
    sinif = _parca(satir, harita, "sinif").strip()
    if not sinif.isdigit():
        sinif = ""
    sube = _parca(satir, harita, "sube").strip().upper()
    if not sube.isalpha():
        sube = ""
    ad = " ".join(_parca(satir, harita, "ad").split())
    cevaplar = "".join(satir[harita.dilim(alan)] for alan in harita.sik_alanlari()).upper()
    uyarilar: list[str] = []
    if harita.alan("numara") and not numara_guvenilir:
        uyarilar.append("Numara alanı kaymış.")
    if harita.alan("ad") and not ad:
        uyarilar.append("Ad soyad okunamadı.")
    cift = cevaplar.count("*")
    if cift:
        uyarilar.append(f"{cift} soruda çift işaret var, yanlış sayıldı.")
    return OptikKayit(
        satir_no=satir_no,
        ogrenci_no=no_ham if numara_guvenilir else "",
        numara_guvenilir=numara_guvenilir,
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


def form_alanlarini_coz(metin: str, satir_uzunluk: int) -> list[FormAlani]:
    """«numara 21 25» satırlarını form alanına çevirir. Kolonlar 1'den başlar."""
    if satir_uzunluk < 1:
        raise OptikHata("Satır uzunluğu en az 1 olmalı.")
    if not (metin or "").strip():
        raise OptikHata("Alan yazın. Örnek: numara 21 25")
    alanlar: list[FormAlani] = []
    gorulen: set[str] = set()
    for ham in metin.splitlines():
        parca = ham.strip()
        if not parca or parca.startswith("#"):
            continue
        kelimeler = parca.replace("-", " ").replace(":", " ").split()
        if len(kelimeler) != 3 or not kelimeler[1].isdigit() or not kelimeler[2].isdigit():
            raise OptikHata(f"«{ham.strip()}» anlaşılmadı. Örnek: sik 51 65")
        tur = ALAN_ADLARI.get(_katla(kelimeler[0]))
        if not tur:
            raise OptikHata(
                f"«{kelimeler[0]}» alanı yok. "
                "numara, ad, kitapcik, sinif, sube, tc, sik, numara_kontrol yazın."
            )
        bas, bit = int(kelimeler[1]), int(kelimeler[2])
        if bas < 1 or bit < bas or bit > satir_uzunluk:
            raise OptikHata(f"{tur} {bas}-{bit} satırın dışında. Satır 1–{satir_uzunluk}.")
        if tur in TEK_ALANLAR and tur in gorulen:
            raise OptikHata(f"{tur} iki kez yazılmış.")
        gorulen.add(tur)
        alanlar.append(FormAlani(tur, bas, bit))
    if not any(a.tur == "sik" for a in alanlar):
        raise OptikHata("En az bir şık bölgesi yazın. Örnek: sik 51 65")
    _cakisma_yok(alanlar)
    return alanlar


def _cakisma_yok(alanlar: list[FormAlani]) -> None:
    parcalar: list[tuple[int, int, str]] = []
    for alan in alanlar:
        if alan.tur == "numara_kontrol":
            continue
        parcalar.append((alan.baslangic, alan.bitis, alan.tur))
    parcalar.sort()
    for once, sonra in zip(parcalar, parcalar[1:]):
        if sonra[0] <= once[1]:
            raise OptikHata(
                f"{once[2]} ({once[0]}-{once[1]}) ile {sonra[2]} "
                f"({sonra[0]}-{sonra[1]}) aynı kolona denk geliyor."
            )


def alan_metni(alanlar: list[FormAlani]) -> str:
    return "\n".join(f"{a.tur} {a.baslangic} {a.bitis}" for a in alanlar)


def kazanim_listesi(metin: str, soru_sayisi: int) -> list[str]:
    """Boş metin kazanım yok demektir. Doluysa her soru için bir satır."""
    if not (metin or "").strip():
        return []
    satirlar = metin.split("\n")
    if metin.endswith("\n"):
        satirlar.pop()
    satirlar = [satir.strip() for satir in satirlar]
    if len(satirlar) != soru_sayisi:
        raise OptikHata(
            f"Kazanım {len(satirlar)} satır, optikte {soru_sayisi} soru var. "
            "Her soru bir satır olmalı; kazanımı olmayan soru boş satır kalır."
        )
    return satirlar


def kazanim_metni(satirlar: list[str]) -> str:
    metin = "\n".join(satirlar)
    if satirlar and satirlar[-1] == "":
        metin += "\n"
    return metin


def ders_kodu(ad: str) -> str:
    kod = _DERS_ADLARI.get(_katla(ad))
    if not kod:
        raise OptikHata(
            f"«{ad}» dersi yok. Türkçe, Matematik, Fen, Sosyal, Din, İngilizce yazın."
        )
    return kod


def dagilim_coz(metin: str, cevap_sayisi: int) -> list[tuple[str, int]]:
    """«turkce 15» satırlarını optikteki ders sırasına çevirir."""
    if not (metin or "").strip():
        raise OptikHata("Soru dağılımını yazın. Her satır bir ders: turkce 15")
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
        kod = ders_kodu(ad)
        if kod in gorulen:
            raise OptikHata(f"{DERS_ETIKETLERI[kod]} iki kez yazılmış.")
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


def dagilim_metni(dagilim: list[tuple[str, int]]) -> str:
    return "\n".join(f"{kod} {adet}" for kod, adet in dagilim)


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


def _net_hesapla(dogru: int, yanlis: int) -> Decimal:
    net = Decimal(int(dogru or 0)) - (Decimal(int(yanlis or 0)) / Decimal("4"))
    if net < 0:
        net = Decimal("0.00")
    return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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


def _sik_durum(verilen: str, beklenen: str) -> str:
    if verilen in {" ", ""}:
        return "bos"
    if verilen == "*":
        return "yanlis"
    if verilen == beklenen:
        return "dogru"
    if verilen in GECERLI_SIK:
        return "yanlis"
    return "bos"


def _puan(net: Decimal, soru: int) -> str:
    if soru <= 0:
        return "0.00"
    puan = (net / Decimal(soru) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(puan, "f")


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


def _sorulari_say(
    cevaplar: str,
    anahtar: str,
    dagilim: list[tuple[str, int]],
    kazanimlar: list[str],
) -> tuple[list[dict], int, int, int, Decimal]:
    imlec = 0
    sorular: list[dict] = []
    t_dogru = t_yanlis = t_bos = 0
    t_net = Decimal("0")
    for kod, adet in dagilim:
        parca = cevaplar[imlec : imlec + adet]
        kilit = anahtar[imlec : imlec + adet]
        for yer, (verilen, beklenen) in enumerate(zip(parca, kilit), start=1):
            konu = ""
            if kazanimlar and imlec + yer - 1 < len(kazanimlar):
                konu = kazanimlar[imlec + yer - 1]
            sorular.append(
                {
                    "ders_key": kod,
                    "soru_no": yer,
                    "sonuc": _sik_durum(verilen, beklenen),
                    "konu_ad": konu,
                    "sira": imlec + yer,
                }
            )
        imlec += adet
        dogru, yanlis, bos = _sik_say(parca, kilit)
        t_dogru += dogru
        t_yanlis += yanlis
        t_bos += bos
        t_net += _net_hesapla(dogru, yanlis)
    t_net = t_net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return sorular, t_dogru, t_yanlis, t_bos, t_net


def satirlari_puanla(
    dosya: OptikDosya,
    dagilim: list[tuple[str, int]],
    anahtar_a: str,
    anahtar_b: str = "",
    kazanimlar: list[str] | None = None,
    kazanimlar_b: list[str] | None = None,
) -> list[PuanSatiri]:
    """Her optik satırını saklanacak puan satırına çevirir.

    B kitapçığın anahtarı yoksa satır yine döner; puan boş kalır.
    Numara kayması bir nottur, satır atılmaz.
    """
    satirlar: list[PuanSatiri] = []
    soru_sayisi = sum(adet for _, adet in dagilim)
    for kayit in dosya.kayitlar:
        kitap = kayit.kitapcik or "A"
        anahtar = anahtar_a if kitap == "A" else anahtar_b
        uyarilar = list(kayit.uyarilar)
        puanlandi = True
        if kitap == "B" and not anahtar_b:
            uyarilar.append("B kitapçık anahtarı yok, puan yazılmadı.")
            puanlandi = False
        elif not anahtar:
            uyarilar.append("Cevap anahtarı yok, puan yazılmadı.")
            puanlandi = False
        sorular: list[dict] = []
        dogru = yanlis = bos = 0
        net = Decimal("0.00")
        puan = ""
        if puanlandi:
            kazanim = kazanimlar or []
            if kitap == "B" and kazanimlar_b is not None:
                kazanim = kazanimlar_b
            sorular, dogru, yanlis, bos, net = _sorulari_say(
                kayit.cevaplar, anahtar, dagilim, kazanim
            )
            puan = _puan(net, soru_sayisi)
        satirlar.append(
            PuanSatiri(
                satir_no=kayit.satir_no,
                ogrenci_no=kayit.ogrenci_no,
                ad=kayit.ad_soyad or f"Satır {kayit.satir_no}",
                kitapcik=kayit.kitapcik,
                sinif_metni=_sinif_metni(kayit),
                uyarilar=uyarilar,
                cevaplar=kayit.cevaplar,
                puanlandi=puanlandi,
                dogru=dogru,
                yanlis=yanlis,
                bos=bos,
                net=format(net, "f"),
                puan=puan,
                sorular=sorular,
            )
        )
    return satirlar
