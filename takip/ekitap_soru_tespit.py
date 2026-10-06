"""PDF kitapçıklarında soru tespiti (yalnızca metin içeren PDF'ler).

Saf hesaplama modülüdür: veritabanına dokunmaz. ``tespit_et`` açık bir
pypdfium2 belgesi alır, soru taslaklarını ve sayfa uyarılarını döner.

Yöntem
1. Her sayfada satır başındaki "12." / "12)" biçimli numaralar konumlarıyla
   okunur (aday). Ondalık sayılar ("2.5 kg") ve sayfa numaraları elenir.
2. Adayların sol kenarları bölüm genelinde kümelenir. Soru numaraları her
   sayfada aynı hizada durur (sütun çapası); girintili madde numaraları
   ("1. madde") daha sağda ve seyrek olduğundan zayıf aday sayılır.
3. Okuma sırası: sayfa → sütun (soldan sağa) → yukarıdan aşağı.
4. Bu sırada en tutarlı numara zinciri dinamik programlamayla seçilir:
   n'den n+1'e geçiş ödüllendirilir; 1'e dönüş yeni test sayılır ama cezalıdır;
   tek numara atlama kabul edilir, sayfa "Kontrol edin" olarak işaretlenir.
5. Soru alanı: numaranın üstünden aynı sütundaki bir sonraki soruya (ya da
   sütundaki son içeriğe) kadar, sütun genişliğinde. Şekiller ve şıklar
   sayfa nesnelerinin sınırlarıyla kapsanır.
6. Sütunun başında, ilk sorudan önce kalan içerik önceki sorunun devamı
   sayılır (sayfa/sütun sonunda bölünen sorular) ve sayfa kontrole düşer.

Koordinatlar sayfaya göre 0–1 aralığında, sol üst köşe orijinlidir.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# —— Ayarlar ——————————————————————————————————————————————————————————————

KUME_TOLERANS = 0.018  # sütun çapası kümelemesinde yatay tolerans (sayfa genişliği oranı)
MIN_SORU_YUKSEKLIK = 0.03  # aynı sütunda iki soru numarası arası en az bu kadar olmalı
UST_PAY = 0.010
ALT_PAY = 0.012
YAN_PAY = 0.014
ALT_BOSLUK = 0.055  # sayfa altındaki bu bant (sayfa no, alt bilgi) içerik sayılmaz
UST_BOSLUK = 0.035
YENIDEN_BASLAMA_CEZASI = 1.5
BASLANGIC_CEZASI = 0.8
ATLAMA_CEZASI = 0.9
MAKS_SAYFA_ARALIGI = 2

_NUMARA = re.compile(r"^\s*(\d{1,3})\s*([.)])(?!\d)")
_CIPLAK_NUMARA = re.compile(r"^\s*(\d{1,2})\s*$")


@dataclass
class Kutu:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def yukseklik(self) -> float:
        return self.y1 - self.y0

    @property
    def genislik(self) -> float:
        return self.x1 - self.x0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def kesisim(self, diger: Kutu) -> float:
        w = min(self.x1, diger.x1) - max(self.x0, diger.x0)
        h = min(self.y1, diger.y1) - max(self.y0, diger.y0)
        return w * h if w > 0 and h > 0 else 0.0

    def alan(self) -> float:
        return max(self.genislik, 0) * max(self.yukseklik, 0)

    def yuvarla(self) -> tuple[float, float, float, float]:
        return tuple(round(min(max(v, 0.0), 1.0), 4) for v in (self.x0, self.y0, self.x1, self.y1))


@dataclass
class Aday:
    sayfa: int
    no: int
    kutu: Kutu
    kalin: bool
    ciplak: bool  # noktasız numara
    metin_izliyor: bool
    agirlik: float = 1.0
    sutun: int = 0


@dataclass
class SoruTaslagi:
    no: int
    test_no: int
    sira: int
    guven: float
    alanlar: list[tuple[int, Kutu]]  # (sayfa indeksi, kutu)
    numara_kutusu: Kutu
    sutun: int


@dataclass
class SayfaBilgisi:
    metinli: bool = True
    notlar: list[str] = field(default_factory=list)

    def uyar(self, not_: str) -> None:
        if not_ not in self.notlar:
            self.notlar.append(not_)


@dataclass
class TespitSonucu:
    durum: str  # "tamam" | "taranmis" | "bos"
    sorular: list[SoruTaslagi]
    sayfalar: dict[int, SayfaBilgisi]
    capalar: list[float]
    not_: str = ""

    def sutun_indeksi(self, x0: float) -> int:
        return _sutun_bul(self.capalar, x0)


# —— pypdfium2 sürüm uyumu ————————————————————————————————————————————————


def _sinirlar(nesne):
    if hasattr(nesne, "get_bounds"):
        return nesne.get_bounds()
    return nesne.get_pos()  # pypdfium2 4.x


def _ham():
    import pypdfium2.raw as pdfium_c

    return pdfium_c


# —— Sayfa okuma ——————————————————————————————————————————————————————————


@dataclass
class _SayfaVerisi:
    indeks: int
    genislik: float
    yukseklik: float
    adaylar: list[Aday]
    nesneler: list[tuple[int, Kutu, str]]  # (tür, kutu, bantta duran yazının metni)
    karakter: int
    gorsel_orani: float  # görsellerin kapladığı alan / sayfa


def _font_kalin_mi(pdfium_c, metin_sayfasi, i: int) -> bool:
    import ctypes

    try:
        agirlik = pdfium_c.FPDFText_GetFontWeight(metin_sayfasi, i)
        if agirlik and agirlik >= 600:
            return True
        tampon = ctypes.create_string_buffer(128)
        bayrak = ctypes.c_int(0)
        uzunluk = pdfium_c.FPDFText_GetFontInfo(metin_sayfasi, i, tampon, 128, ctypes.byref(bayrak))
        ad = tampon.raw[: max(uzunluk - 1, 0)].decode("latin-1", "ignore").lower()
        return any(k in ad for k in ("bold", "black", "heavy", "semibold", "demi"))
    except Exception:  # noqa: BLE001
        return False


def _sayfa_oku(belge, indeks: int) -> _SayfaVerisi:
    pdfium_c = _ham()
    sayfa = belge[indeks]
    W, H = sayfa.get_size()
    W = W or 1.0
    H = H or 1.0

    def normal(sol, alt, sag, ust) -> Kutu:
        return Kutu(sol / W, 1 - ust / H, sag / W, 1 - alt / H)

    adaylar: list[Aday] = []
    metin_sayfasi = sayfa.get_textpage()
    try:
        n = metin_sayfasi.count_chars()
        ham = metin_sayfasi.raw
        karakterler = [chr(pdfium_c.FPDFText_GetUnicode(ham, i) or 32) for i in range(n)]
        dolu = sum(1 for k in karakterler if not k.isspace())
        # Satırlara böl (pdfium satır sonlarına \r\n üretir).
        satirlar: list[list[int]] = [[]]
        for i, k in enumerate(karakterler):
            if k in "\r\n":
                if satirlar[-1]:
                    satirlar.append([])
                continue
            satirlar[-1].append(i)
        for satir in satirlar:
            if not satir:
                continue
            metin = "".join(karakterler[i] for i in satir)
            eslesme = _NUMARA.match(metin)
            ciplak = False
            if not eslesme:
                eslesme = _CIPLAK_NUMARA.match(metin)
                ciplak = bool(eslesme)
            if not eslesme:
                continue
            no = int(eslesme.group(1))
            if no < 1 or no > 200:
                continue
            bas = len(metin) - len(metin.lstrip())
            numara_idx = [satir[j] for j in range(bas, eslesme.end()) if not karakterler[satir[j]].isspace()]
            kutular = [metin_sayfasi.get_charbox(i) for i in numara_idx]
            kutular = [k for k in kutular if k and k[2] > k[0]]
            if not kutular:
                continue
            kutu = normal(
                min(k[0] for k in kutular), min(k[1] for k in kutular),
                max(k[2] for k in kutular), max(k[3] for k in kutular),
            )
            kalin = _font_kalin_mi(pdfium_c, ham, numara_idx[0])
            if ciplak and not kalin:
                continue
            adaylar.append(
                Aday(
                    sayfa=indeks,
                    no=no,
                    kutu=kutu,
                    kalin=kalin,
                    ciplak=ciplak,
                    metin_izliyor=bool(metin[eslesme.end():].strip()),
                )
            )
        nesneler: list[tuple[int, Kutu, str]] = []
        gorsel_alani = 0.0
        for nesne in sayfa.get_objects(max_depth=3):
            tur = nesne.type
            if tur == pdfium_c.FPDF_PAGEOBJ_FORM:
                continue
            try:
                sinir = _sinirlar(nesne)
            except Exception:  # noqa: BLE001
                continue
            kutu = normal(*sinir)
            kutu = Kutu(max(kutu.x0, 0), max(kutu.y0, 0), min(kutu.x1, 1), min(kutu.y1, 1))
            if kutu.genislik <= 0 and kutu.yukseklik <= 0:
                continue
            metin = ""
            if tur == pdfium_c.FPDF_PAGEOBJ_TEXT and _bantta_mi(kutu):
                try:
                    metin = metin_sayfasi.get_text_bounded(*sinir).strip()
                except Exception:  # noqa: BLE001
                    metin = ""
            nesneler.append((tur, kutu, metin))
            if tur == pdfium_c.FPDF_PAGEOBJ_IMAGE:
                gorsel_alani += kutu.alan()
    finally:
        metin_sayfasi.close()
    sayfa.close()
    return _SayfaVerisi(indeks, W, H, adaylar, nesneler, dolu, min(gorsel_alani, 1.0))


# —— Süsleme (bant, çerçeve, sayfa no) ayıklama ——————————————————————————


UST_BANT = 0.075
ALT_BANT = 0.93


def _imza(t: int, k: Kutu, metin: str = "") -> tuple:
    return (t, round(k.x0, 2), round(k.y0, 2), round(k.x1, 2), round(k.y1, 2), metin)


def _bantta_mi(k: Kutu) -> bool:
    return k.y1 <= UST_BANT or k.y0 >= ALT_BANT


def _susleme_imzalari(sayfalar: list[_SayfaVerisi]) -> set:
    """Üst/alt bantta birden çok sayfada aynı yerde duran nesneler (başlık, logo, alt bilgi).

    Yalnızca bantlara bakılır: soru metinleri sayfalar arasında aynı konumda
    tekrar edebilir (ör. şık harfleri) ve bunlar süsleme sayılmamalı.
    """
    sayac: Counter = Counter()
    for s in sayfalar:
        sayac.update({_imza(t, k, m) for t, k, m in s.nesneler if _bantta_mi(k)})
    return {imza for imza, adet in sayac.items() if adet >= 2}


def _susleme_mi(t: int, k: Kutu, m: str, suslemeler: set) -> bool:
    if _imza(t, k, m) in suslemeler:
        return True
    if k.genislik > 0.85 or k.yukseklik > 0.7:
        return True  # sayfa çerçevesi, zemin, tam genişlik bant, sütun ayırıcı çizgi
    if k.y0 > 1 - ALT_BOSLUK and k.yukseklik < 0.03:
        return True  # sayfa numarası / alt bilgi
    if k.y1 < UST_BOSLUK and k.yukseklik < 0.03:
        return True
    return False


def _icerik_nesneleri(s: _SayfaVerisi, suslemeler: set) -> list[Kutu]:
    return [k for t, k, m in s.nesneler if not _susleme_mi(t, k, m, suslemeler)]


def _susleme_icinde_mi(a: Aday, s: _SayfaVerisi, suslemeler: set, metin_turu: int) -> bool:
    """Aday numara tekrar eden bir başlık/alt bilgi yazısının parçası mı?"""
    for t, k, m in s.nesneler:
        if t != metin_turu or _imza(t, k, m) not in suslemeler:
            continue
        if k.x0 - 0.003 <= a.kutu.cx <= k.x1 + 0.003 and k.y0 - 0.003 <= a.kutu.cy <= k.y1 + 0.003:
            return True
    return False


# —— Sütun çapaları ———————————————————————————————————————————————————————


def _capalari_bul(adaylar: list[Aday]) -> list[float]:
    if not adaylar:
        return []
    xs = sorted(a.kutu.x0 for a in adaylar)
    kumeler: list[list[float]] = [[xs[0]]]
    for x in xs[1:]:
        if x - kumeler[-1][-1] <= KUME_TOLERANS:
            kumeler[-1].append(x)
        else:
            kumeler.append([x])
    en_buyuk = max(len(k) for k in kumeler)
    gucluler = [sum(k) / len(k) for k in kumeler if len(k) >= max(2, en_buyuk * 0.25) or len(k) == en_buyuk]
    # Birbirine çok yakın (aynı sütun içinde girintili) çapalardan soldakini tut.
    capalar: list[float] = []
    for x in sorted(gucluler):
        if capalar and x - capalar[-1] < 0.2:
            continue
        capalar.append(x)
    return capalar


def _sutun_bul(capalar: list[float], x0: float) -> int:
    indeks = 0
    for i, c in enumerate(capalar):
        if x0 >= c - KUME_TOLERANS * 1.5:
            indeks = i
    return indeks


def _capaya_yakin(capalar: list[float], x0: float) -> bool:
    return any(abs(x0 - c) <= KUME_TOLERANS for c in capalar)


# —— Numara zinciri ———————————————————————————————————————————————————————


def _gecis_uygun(onceki: Aday, sonraki: Aday) -> bool:
    if sonraki.sayfa - onceki.sayfa > MAKS_SAYFA_ARALIGI:
        return False
    if sonraki.sayfa == onceki.sayfa and sonraki.sutun == onceki.sutun:
        return sonraki.kutu.y0 - onceki.kutu.y0 >= MIN_SORU_YUKSEKLIK
    return True


def _zincir_sec(adaylar: list[Aday]) -> list[tuple[Aday, str]]:
    """Okuma sırasındaki adaylardan en tutarlı soru numarası dizisini seçer."""
    skor: list[float] = []
    geri: list[int | None] = []
    tur: list[str] = []
    numaraya_gore: dict[int, list[int]] = {}
    en_iyi = -1

    for i, a in enumerate(adaylar):
        secenekler = [(a.agirlik - (0.0 if a.no == 1 else BASLANGIC_CEZASI), None, "bas")]
        for fark, ceza, etiket in ((1, 0.0, "devam"), (2, ATLAMA_CEZASI, "atlama")):
            for j in numaraya_gore.get(a.no - fark, ()):
                if _gecis_uygun(adaylar[j], a):
                    secenekler.append((skor[j] + a.agirlik - ceza, j, etiket))
        if a.no == 1 and en_iyi >= 0 and a.agirlik >= 0.8:
            secenekler.append((skor[en_iyi] + a.agirlik - YENIDEN_BASLAMA_CEZASI, en_iyi, "yeniden"))
        s, j, etiket = max(secenekler, key=lambda t: t[0])
        skor.append(s)
        geri.append(j)
        tur.append(etiket)
        numaraya_gore.setdefault(a.no, []).append(i)
        if en_iyi < 0 or s > skor[en_iyi]:
            en_iyi = i

    if en_iyi < 0 or skor[en_iyi] <= 0:
        return []
    zincir: list[tuple[Aday, str]] = []
    i: int | None = en_iyi
    while i is not None:
        zincir.append((adaylar[i], tur[i]))
        i = geri[i]
    zincir.reverse()
    return zincir


# —— Soru alanları ————————————————————————————————————————————————————————


def _sutun_sinirlari(
    capalar: list[float], sutun: int, icerik: list[Kutu], ust: float, alt: float
) -> tuple[float, float]:
    sol = (capalar[sutun] if capalar else 0.05) - YAN_PAY
    sag_sinir = None
    for c in capalar[sutun + 1:]:
        sag_sinir = c - YAN_PAY - 0.004
        break
    if sag_sinir is not None:
        # Bu aralıkta sınırı aşan geniş içerik varsa sayfa burada tek sütundur.
        tasan = [
            k for k in icerik
            if k.y0 < alt and k.y1 > ust and k.x0 < sag_sinir - 0.05 and k.x1 > sag_sinir + 0.05
        ]
        if tasan:
            sag_sinir = None
    if sag_sinir is None:
        sagdakiler = [k.x1 for k in icerik if k.y0 < alt and k.y1 > ust and k.x1 > sol]
        sag_sinir = min(max(sagdakiler, default=1 - 0.05) + YAN_PAY, 1.0)
    return max(sol, 0.0), sag_sinir


def _saga_cek(icerik: list[Kutu], sol: float, sag: float) -> float:
    """Sağ kenarı sütundaki en sağ içeriğe çeker (ayırıcı çizgi / boşluk dışarıda kalır)."""
    sutun_icerigi = [k.x1 for k in icerik if sol - 0.005 <= k.cx <= sag + 0.005]
    return min(sag, max(sutun_icerigi) + YAN_PAY) if sutun_icerigi else sag


def _bolgedeki(icerik: list[Kutu], sol: float, sag: float, ust: float, alt: float) -> list[Kutu]:
    return [
        k for k in icerik
        if sol - 0.005 <= k.cx <= sag + 0.005 and k.y0 >= ust - 0.004 and k.y0 < alt
    ]


def tespit_et(belge, *, maks_sayfa: int | None = None) -> TespitSonucu:
    toplam = len(belge) if maks_sayfa is None else min(len(belge), maks_sayfa)
    sayfalar = [_sayfa_oku(belge, i) for i in range(toplam)]
    bilgiler = {s.indeks: SayfaBilgisi() for s in sayfalar}

    dolu_sayfalar = [s for s in sayfalar if s.nesneler]
    taranmis = [s for s in dolu_sayfalar if s.karakter < 8 and s.gorsel_orani > 0.4]
    for s in taranmis:
        bilgiler[s.indeks].metinli = False
        bilgiler[s.indeks].uyar("Taranmış sayfa: sorular elle işaretlenmeli.")
    if dolu_sayfalar and len(taranmis) >= max(1, len(dolu_sayfalar) * 0.5):
        return TespitSonucu("taranmis", [], bilgiler, [], "PDF taranmış görünüyor; yazı katmanı yok.")

    suslemeler = _susleme_imzalari(sayfalar)
    metin_turu = _ham().FPDF_PAGEOBJ_TEXT
    adaylar = [
        a for s in sayfalar for a in s.adaylar
        if not _susleme_icinde_mi(a, s, suslemeler, metin_turu)
    ]
    capalar = _capalari_bul([a for a in adaylar if not a.ciplak])
    kalin_var = any(a.kalin for a in adaylar)
    for a in adaylar:
        a.sutun = _sutun_bul(capalar, a.kutu.x0)
        w = 1.0
        if not _capaya_yakin(capalar, a.kutu.x0):
            w -= 0.4
        if kalin_var and not a.kalin:
            w -= 0.2
        if a.ciplak:
            w -= 0.25
        if not a.metin_izliyor and not a.ciplak:
            w -= 0.1
        a.agirlik = max(w, 0.1)
    adaylar.sort(key=lambda a: (a.sayfa, a.sutun, a.kutu.y0))

    zincir = _zincir_sec(adaylar)
    if not zincir:
        return TespitSonucu("bos", [], bilgiler, capalar, "Soru numarası bulunamadı.")

    icerikler = {s.indeks: _icerik_nesneleri(s, suslemeler) for s in sayfalar}

    # Test numaraları ve atlama uyarıları
    test_no = 0
    secilen: list[tuple[Aday, int]] = []
    onceki: Aday | None = None
    for a, etiket in zincir:
        if etiket in ("bas", "yeniden"):
            test_no += 1
        if etiket == "atlama" and onceki is not None:
            bilgiler[a.sayfa].uyar(f"Soru numarası atlanmış olabilir: {onceki.no} → {a.no}.")
        secilen.append((a, test_no))
        onceki = a

    secilen_kimlik = {id(a) for a, _ in secilen}
    for a in adaylar:
        if id(a) not in secilen_kimlik and a.kalin and _capaya_yakin(capalar, a.kutu.x0) and not a.ciplak:
            bilgiler[a.sayfa].uyar(f"{a.no}. numara soru dizisine uymadı; kontrol edin.")

    taslaklar: list[SoruTaslagi] = []
    for sira, (a, t) in enumerate(secilen):
        taslaklar.append(
            SoruTaslagi(no=a.no, test_no=t, sira=sira, guven=a.agirlik, alanlar=[],
                        numara_kutusu=a.kutu, sutun=a.sutun)
        )

    # Sayfa sayfa alanlar
    sayfa_sorulari: dict[int, list[int]] = {}
    for i, (a, _) in enumerate(secilen):
        sayfa_sorulari.setdefault(a.sayfa, []).append(i)

    for sayfa_indeksi, indeksler in sayfa_sorulari.items():
        icerik = icerikler.get(sayfa_indeksi, [])
        bilgi = bilgiler[sayfa_indeksi]
        sutunlar: dict[int, list[int]] = {}
        for i in indeksler:
            sutunlar.setdefault(secilen[i][0].sutun, []).append(i)
        kapsanan: list[Kutu] = []
        for sutun, sutun_indeksleri in sorted(sutunlar.items()):
            sutun_indeksleri.sort(key=lambda i: secilen[i][0].kutu.y0)
            ilk = secilen[sutun_indeksleri[0]][0]
            for sira_i, i in enumerate(sutun_indeksleri):
                a = secilen[i][0]
                ust = a.kutu.y0 - UST_PAY
                if sira_i + 1 < len(sutun_indeksleri):
                    sinir = secilen[sutun_indeksleri[sira_i + 1]][0].kutu.y0 - UST_PAY
                else:
                    sinir = 1 - ALT_BOSLUK + 0.01
                sol, sag = _sutun_sinirlari(capalar, sutun, icerik, ust, sinir)
                sol = min(sol, a.kutu.x0 - YAN_PAY)
                sag = _saga_cek(icerik, sol, sag)
                icindekiler = _bolgedeki(icerik, sol, sag, ust, sinir)
                alt = max([k.y1 for k in icindekiler] + [a.kutu.y1]) + ALT_PAY
                alt = min(alt, sinir if sira_i + 1 < len(sutun_indeksleri) else 1.0)
                kutu = Kutu(sol, max(ust, 0.0), sag, alt)
                taslaklar[i].alanlar.append((sayfa_indeksi, kutu))
                kapsanan.append(kutu)
                if kutu.yukseklik < 0.045:
                    taslaklar[i].guven *= 0.6
                    bilgi.uyar(f"{a.no}. sorunun alanı çok kısa; kontrol edin.")

            # Sütun başında ilk sorudan önce kalan içerik → önceki sorunun devamı
            sol, sag = _sutun_sinirlari(capalar, sutun, icerik, 0.0, ilk.kutu.y0)
            sag = _saga_cek(icerik, sol, sag)
            ustteki = [
                k for k in icerik
                if sol - 0.005 <= k.cx <= sag + 0.005 and k.y1 <= ilk.kutu.y0 - 0.002
            ]
            if not ustteki:
                continue
            blok = Kutu(sol, min(k.y0 for k in ustteki) - UST_PAY, sag, max(k.y1 for k in ustteki) + ALT_PAY)
            if blok.yukseklik < 0.03:
                continue
            ilk_i = sutun_indeksleri[0]
            onceki_i = ilk_i - 1
            yeni_test = ilk.no == 1 or (onceki_i >= 0 and secilen[onceki_i][1] != secilen[ilk_i][1])
            if yeni_test:
                kapsanan.append(blok)  # test başlığı / yönerge
                continue
            if onceki_i >= 0 and sayfa_indeksi - secilen[onceki_i][0].sayfa <= 1:
                onceki_taslak = taslaklar[onceki_i]
                onceki_taslak.alanlar.append((sayfa_indeksi, blok))
                onceki_taslak.guven = min(onceki_taslak.guven, 0.7)
                kapsanan.append(blok)
                bilgi.uyar(
                    f"{onceki_taslak.no}. sorunun devamı bu sayfada/sütunda bulundu; birleştirildi, kontrol edin."
                )
            else:
                bilgi.uyar("Sütun başında hiçbir soruya bağlanamayan içerik var.")

        # Hiçbir alana girmeyen içerik
        disarida = [k for k in icerik if not any(_icinde(k, b) for b in kapsanan)]
        ilk_ust = min(secilen[i][0].kutu.y0 for i in indeksler)
        disarida = [k for k in disarida if k.y0 >= ilk_ust - 0.002 and k.alan() > 0.0004]
        if disarida:
            bilgi.uyar("Soru alanlarının dışında kalan içerik var; eksik alan olabilir.")
        # Çakışan alanlar
        for x in range(len(kapsanan)):
            for y in range(x + 1, len(kapsanan)):
                ortak = kapsanan[x].kesisim(kapsanan[y])
                if ortak > 0.1 * min(kapsanan[x].alan(), kapsanan[y].alan()):
                    bilgi.uyar("Soru alanları çakışıyor.")

    for taslak in taslaklar:
        taslak.guven = round(max(0.05, min(taslak.guven, 1.0)), 2)
        if any(bilgiler[s].notlar for s, _ in taslak.alanlar):
            taslak.guven = round(taslak.guven * 0.9, 2)
    return TespitSonucu("tamam", taslaklar, bilgiler, capalar)


def _icinde(k: Kutu, b: Kutu) -> bool:
    return b.x0 - 0.004 <= k.cx <= b.x1 + 0.004 and b.y0 - 0.004 <= k.cy <= b.y1 + 0.004
