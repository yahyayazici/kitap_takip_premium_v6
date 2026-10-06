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

# Algoritma değiştikçe artırılır: daha eski sürümle taranmış bölümler sunucu
# açılışında (`ekitap_sorulari_bul --eski`) yeniden taranır.
# 3: satır/sütun sayfa düzeni, birleşik satırların bölünmesi, ortak bilgili gruplar.
TESPIT_SURUMU = 3

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
_SIK_A = re.compile(r"^\s*A\s*[).]")


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
    ocr_guven: float | None = None  # OCR'dan geldiyse Tesseract güveni (0–1)


@dataclass
class SoruTaslagi:
    no: int
    test_no: int
    sira: int
    guven: float
    alanlar: list[tuple[int, Kutu]]  # (sayfa indeksi, kutu)
    numara_kutusu: Kutu
    sutun: int
    # Şıkların başladığı yer: (alan indeksi, sayfaya göre y). Bulunamazsa None.
    siklar: tuple[int, float] | None = None
    # Büyüteç rozeti: (simgenin sağ kenarı x, merkez y, çap — sayfa genişliği oranı).
    rozet: tuple[float, float, float] | None = None
    rozet_sayfa: int | None = None
    numara_sayfa: int = 0


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
    # Sayfa okuma düzeni: "sutun" (önce sol sütun yukarıdan aşağı) ya da
    # "satir" (soru sıraları soldan sağa); satır düzeninde satırların üst y'leri.
    duzenler: dict[int, tuple[str, list[float]]] = field(default_factory=dict)

    def sutun_indeksi(self, x0: float) -> int:
        return _sutun_bul(self.capalar, x0)

    def konum_anahtari(self, sayfa: int, x0: float, y0: float) -> tuple:
        """Okuma sırası anahtarı (elle eklenen sorular dahil)."""
        return (sayfa,) + _sayfa_ici_anahtar(self.duzenler.get(sayfa), _sutun_bul(self.capalar, x0 + 0.015), y0)


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
    sik_kutulari: list[Kutu] = field(default_factory=list)  # "A)" satırlarının başı
    # "8, 9 ve 10. soruları aşağıdaki bilgiye göre cevaplayınız" başlıkları: (kutu, numaralar)
    grup_basliklari: list[tuple[Kutu, list[int]]] = field(default_factory=list)


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
    sik_kutulari: list[Kutu] = []
    grup_basliklari: list[tuple[Kutu, list[int]]] = []
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
        kutu_onbellek: dict[int, tuple] = {}

        def charbox(i):
            if i not in kutu_onbellek:
                kutu_onbellek[i] = metin_sayfasi.get_charbox(i)
            return kutu_onbellek[i]

        parcalar = _satirlari_bol(satirlar, karakterler, charbox, W)
        for satir in parcalar:
            metin = "".join(karakterler[i] for i in satir)
            baslik = _grup_basligi(metin)
            if baslik:
                bkutular = [charbox(i) for i in satir if not karakterler[i].isspace()]
                bkutular = [k for k in bkutular if k and k[2] > k[0]]
                if bkutular:
                    grup_basliklari.append((
                        normal(min(k[0] for k in bkutular), min(k[1] for k in bkutular),
                               max(k[2] for k in bkutular), max(k[3] for k in bkutular)),
                        baslik,
                    ))
            if _SIK_A.match(metin):
                bas = len(metin) - len(metin.lstrip())
                k = charbox(satir[bas])
                if k and k[2] > k[0]:
                    sik_kutulari.append(normal(*k))
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
            kutular = [charbox(i) for i in numara_idx]
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
    return _SayfaVerisi(
        indeks, W, H, adaylar, nesneler, dolu, min(gorsel_alani, 1.0), sik_kutulari, grup_basliklari
    )


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
    if t == _ham().FPDF_PAGEOBJ_PATH and (
        (k.yukseklik < 0.004 and k.genislik > 0.25) or (k.genislik < 0.004 and k.yukseklik > 0.25)
    ):
        return True  # soruları ayıran ince yatay/dikey çizgi
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
    sirali = sorted(adaylar, key=lambda a: a.kutu.x0)
    kumeler: list[list[Aday]] = [[sirali[0]]]
    for a in sirali[1:]:
        if a.kutu.x0 - kumeler[-1][-1].kutu.x0 <= KUME_TOLERANS:
            kumeler[-1].append(a)
        else:
            kumeler.append([a])
    en_buyuk = max(len(k) for k in kumeler)
    kalin_cogunluk = sum(1 for a in adaylar if a.kalin) >= len(adaylar) / 2
    gucluler = [
        sum(a.kutu.x0 for a in k) / len(k)
        for k in kumeler
        if len(k) >= max(2, en_buyuk * 0.25)
        or len(k) == en_buyuk
        # Kitapta o hizada tek soru olabilir (ör. sağ sütunda yalnız 3. soru): soru
        # numaraları kalın yazılıyorsa kalın ve ardından metin gelen numara yeter.
        or (kalin_cogunluk and any(a.kalin and a.metin_izliyor for a in k))
    ]
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


def _ocr_sayfasi(belge, s: _SayfaVerisi) -> _SayfaVerisi | None:
    """Taranmış sayfayı OCR ile okuyup metinli sayfa verisine çevirir."""
    from takip import ekitap_ocr

    sayfa = belge[s.indeks]
    try:
        olcek = ekitap_ocr.OCR_GENISLIK / (s.genislik or 1)
        gorsel = sayfa.render(scale=olcek, fill_color=(255, 255, 255, 255)).to_pil()
    finally:
        sayfa.close()
    try:
        okunan = ekitap_ocr.sayfayi_oku(gorsel)
    except Exception:  # noqa: BLE001
        return None
    metin_turu = _ham().FPDF_PAGEOBJ_TEXT
    adaylar = [
        Aday(
            sayfa=s.indeks, no=no, kutu=Kutu(w.x0, w.y0, w.x1, w.y1),
            kalin=True, ciplak=False, metin_izliyor=izliyor, ocr_guven=w.guven,
        )
        for no, w, izliyor in okunan.numaralar
    ]
    nesneler = [(metin_turu, Kutu(*k), "") for k in okunan.murekkep]
    siklar = [Kutu(w.x0, w.y0, w.x1, w.y1) for w in okunan.sik_baslari]
    gruplar = [(Kutu(*k), n) for k, n in (okunan.grup_basliklari or [])]
    return _SayfaVerisi(s.indeks, s.genislik, s.yukseklik, adaylar, nesneler, okunan.karakter, 0.0, siklar, gruplar)


def tespit_et(belge, *, maks_sayfa: int | None = None, ocr: bool | None = None) -> TespitSonucu:
    """ocr=None: Tesseract kuruluysa taranmış sayfalar OCR ile okunur."""
    toplam = len(belge) if maks_sayfa is None else min(len(belge), maks_sayfa)
    sayfalar = [_sayfa_oku(belge, i) for i in range(toplam)]
    bilgiler = {s.indeks: SayfaBilgisi() for s in sayfalar}

    dolu_sayfalar = [s for s in sayfalar if s.nesneler]
    taranmis = [s for s in dolu_sayfalar if s.karakter < 8 and s.gorsel_orani > 0.4]
    for s in taranmis:
        bilgiler[s.indeks].metinli = False
    if ocr is None:
        from takip.ekitap_ocr import ocr_kullanilabilir

        ocr = ocr_kullanilabilir()
    ocr_ile = set()
    if taranmis and ocr:
        for s in taranmis:
            yeni = _ocr_sayfasi(belge, s)
            if yeni is not None and yeni.adaylar:
                sayfalar[sayfalar.index(s)] = yeni
                ocr_ile.add(s.indeks)
    for s in taranmis:
        if s.indeks not in ocr_ile:
            bilgiler[s.indeks].uyar("Taranmış sayfa: sorular elle işaretlenmeli.")
    cogu_taranmis = dolu_sayfalar and len(taranmis) >= max(1, len(dolu_sayfalar) * 0.5)
    if cogu_taranmis and not ocr_ile:
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
        if a.ocr_guven is not None:
            w *= 0.6 + 0.4 * min(max(a.ocr_guven, 0.0), 1.0)
        a.agirlik = max(w, 0.1)
    duzenler = _duzenleri_bul(adaylar)
    adaylar.sort(key=lambda a: (a.sayfa,) + _sayfa_ici_anahtar(duzenler.get(a.sayfa), a.sutun, a.kutu.y0))

    zincir = _zincir_sec(adaylar)
    if not zincir:
        if cogu_taranmis:
            return TespitSonucu("taranmis", [], bilgiler, [], "Taranmış PDF; OCR soru numarası bulamadı.")
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
                        numara_kutusu=a.kutu, sutun=a.sutun, numara_sayfa=a.sayfa)
        )

    # Sayfa sayfa alanlar
    sayfa_sorulari: dict[int, list[int]] = {}
    for i, (a, _) in enumerate(secilen):
        sayfa_sorulari.setdefault(a.sayfa, []).append(i)

    basliklar_sayfa = {s.indeks: s.grup_basliklari for s in sayfalar}
    for sayfa_indeksi, indeksler in sayfa_sorulari.items():
        icerik = icerikler.get(sayfa_indeksi, [])
        bilgi = bilgiler[sayfa_indeksi]
        basliklar = basliklar_sayfa.get(sayfa_indeksi, [])
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
                # Altta yeni bir soru grubu başlıyorsa ("9 ve 10. soruları ...") soru orada biter.
                for hb, _ in basliklar:
                    if a.kutu.y0 + 0.01 < hb.y0 < sinir and hb.x0 < (capalar[sutun + 1] if sutun + 1 < len(capalar) else 1.0) \
                            and hb.x1 > (capalar[sutun] if capalar else 0.0) - 0.02:
                        sinir = hb.y0 - UST_PAY
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
                # üstteki tam genişlik bir sorunun alanına giren içerik devam değildir
                and not any(_icinde(k, b) for b in kapsanan)
            ]
            if not ustteki:
                continue
            blok = Kutu(sol, min(k.y0 for k in ustteki) - UST_PAY, sag, max(k.y1 for k in ustteki) + ALT_PAY)
            if blok.yukseklik < 0.03:
                continue
            if any(blok.y0 - 0.01 <= hb.y0 <= blok.y1 and hb.x1 > blok.x0 and hb.x0 < blok.x1 for hb, _ in basliklar):
                kapsanan.append(blok)  # soru grubunun ortak bilgisi/görseli; aşağıda gruba bağlanır
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

    grup_rozeti = _gruplari_bagla(sayfalar, secilen, taslaklar, icerikler, capalar)

    sik_kutulari = {s.indeks: s.sik_kutulari for s in sayfalar}
    oranlar = {s.indeks: (s.genislik / s.yukseklik if s.yukseklik else 0.707) for s in sayfalar}
    yol_turu = _ham().FPDF_PAGEOBJ_PATH
    # Rozet için engeller: içerik + sütun ayırıcı dikey çizgiler (içerikten ayıklanmıştı)
    ayiricilar = {
        s.indeks: [k for t, k, _ in s.nesneler if t == yol_turu and k.genislik < 0.004 and k.yukseklik > 0.25]
        for s in sayfalar
    }
    for taslak in taslaklar:
        taslak.siklar = _siklari_bul(taslak, sik_kutulari)
        # Rozet numaranın sayfasında; grubun ilk sorusunda ortak bilginin başlığında.
        grup = grup_rozeti.get(id(taslak))
        sayfa_indeksi = grup[0] if grup else taslak.numara_sayfa
        if taslak.alanlar:
            taslak.rozet_sayfa = sayfa_indeksi
            taslak.rozet = _rozet_yeri(
                grup[1] if grup else taslak.numara_kutusu,
                icerikler.get(sayfa_indeksi, []) + ayiricilar.get(sayfa_indeksi, []),
                oranlar.get(sayfa_indeksi, 0.707),
            )
    # OCR sonuçları belirsizdir: sayfalar yönetimde doğrulanmak üzere işaretlenir.
    for sayfa_indeksi in ocr_ile:
        bilgiler[sayfa_indeksi].uyar("Sorular OCR ile bulundu; alanları ve numaraları doğrulayın.")
    for taslak in taslaklar:
        taslak.guven = round(max(0.05, min(taslak.guven, 1.0)), 2)
        if any(s in ocr_ile for s, _ in taslak.alanlar):
            taslak.guven = round(min(taslak.guven, 0.85), 2)
        if any(bilgiler[s].notlar for s, _ in taslak.alanlar):
            taslak.guven = round(taslak.guven * 0.9, 2)
    durum = "ocr" if cogu_taranmis else "tamam"
    not_ = "Taranmış PDF; sorular OCR ile bulundu, yönetimde doğrulayın." if cogu_taranmis else ""
    return TespitSonucu(durum, taslaklar, bilgiler, capalar, not_, duzenler)


def _icinde(k: Kutu, b: Kutu) -> bool:
    return b.x0 - 0.004 <= k.cx <= b.x1 + 0.004 and b.y0 - 0.004 <= k.cy <= b.y1 + 0.004


def _siklari_bul(taslak: SoruTaslagi, sik_kutulari: dict[int, list[Kutu]]) -> tuple[int, float] | None:
    """Sorunun alanları içindeki ilk "A)" satırı: şık perdesi buradan aşağısını örter."""
    for i, (sayfa, alan) in enumerate(taslak.alanlar):
        icindekiler = [
            k for k in sik_kutulari.get(sayfa, ())
            if alan.x0 <= k.cx <= alan.x1 and alan.y0 + 0.01 < k.y0 < alan.y1
        ]
        if icindekiler:
            ilk = min(icindekiler, key=lambda k: k.y0)
            return i, round(max(ilk.y0 - 0.006, alan.y0), 4)
    return None


# —— Sayfa okuma düzeni ———————————————————————————————————————————————————

SATIR_TOLERANS = 0.03


def _satir_baslari(ys: list[float]) -> list[float]:
    baslar: list[float] = []
    for y in sorted(ys):
        if not baslar or y - baslar[-1] > SATIR_TOLERANS:
            baslar.append(y)
    return baslar


def _sayfa_ici_anahtar(duzen, sutun: int, y0: float) -> tuple:
    if duzen and duzen[0] == "satir":
        satir = sum(1 for b in duzen[1] if b <= y0 + SATIR_TOLERANS) - 1
        return (max(satir, 0), sutun, y0)
    return (sutun, y0, 0)


def _ters_sirali(numaralar: list[int]) -> int:
    return sum(1 for i in range(len(numaralar)) for j in range(i + 1, len(numaralar)) if numaralar[i] > numaralar[j])


def _duzenleri_bul(adaylar: list[Aday]) -> dict[int, tuple[str, list[float]]]:
    """Her sayfa için sütun ya da satır okuma düzenini seçer.

    Kitapçıklarda iki düzen bir arada olabilir: bir sayfada önce sol sütun
    (1, 2) sonra sağ sütun (3); diğerinde sorular satır satır (4 | 5, 6 | 7).
    Güçlü adayların numaralarının hangi okuma sırasında daha düzgün arttığına
    bakılır; eşitlikte sütun düzeni seçilir.
    """
    sayfalar: dict[int, list[Aday]] = {}
    for a in adaylar:
        if a.agirlik >= 0.8:
            sayfalar.setdefault(a.sayfa, []).append(a)
    duzenler: dict[int, tuple[str, list[float]]] = {}
    for sayfa, liste in sayfalar.items():
        sutunlar = {a.sutun for a in liste}
        if len(liste) < 3 or len(sutunlar) < 2:
            continue
        baslar = _satir_baslari([a.kutu.y0 for a in liste])
        sutun_sira = sorted(liste, key=lambda a: _sayfa_ici_anahtar(None, a.sutun, a.kutu.y0))
        satir_sira = sorted(liste, key=lambda a: _sayfa_ici_anahtar(("satir", baslar), a.sutun, a.kutu.y0))
        if _ters_sirali([a.no for a in satir_sira]) < _ters_sirali([a.no for a in sutun_sira]):
            duzenler[sayfa] = ("satir", baslar)
    return duzenler


# —— Büyüteç rozeti yeri ——————————————————————————————————————————————————

ROZET_CAP = 0.03  # tercih edilen simge çapı (sayfa genişliği oranı)
ROZET_EN_AZ = 0.016


def _rozet_yeri(numara: Kutu, icerik: list[Kutu], oran: float) -> tuple[float, float, float]:
    """Rozeti metni örtmeden yerleştirir.

    1) Numaranın solundaki boşluk (sayfa kenarı ya da sütun oluğu) yeterliyse
       oraya, numara satırının ortasına; boşluk darsa simge küçülür.
    2) Değilse numaranın hemen üstündeki boşluğa.
    3) İkisi de yoksa en küçük boyutta numaranın soluna.
    Dönüş: (simgenin sağ kenarı x, merkez y, çap); x ve çap sayfa genişliğine,
    y sayfa yüksekliğine oranlıdır. oran = genişlik / yükseklik.
    """
    pay = 0.005
    satirdaki = [
        k for k in icerik
        if k.y1 > numara.y0 - 0.004 and k.y0 < numara.y1 + 0.004 and k.x1 <= numara.x0 + 0.002
    ]
    sol_engel = max((k.x1 for k in satirdaki), default=0.0)
    yatay = numara.x0 - sol_engel - 2 * pay
    if yatay >= ROZET_EN_AZ:
        cap = min(ROZET_CAP, yatay)
        return (round(numara.x0 - pay, 4), round(numara.cy, 4), round(cap, 4))
    ustteki = [
        k for k in icerik
        if k.y1 <= numara.y0 + 0.001 and k.x1 > numara.x0 - 0.02 and k.x0 < numara.x1 + 0.02
    ]
    ust_engel = max((k.y1 for k in ustteki), default=0.0)
    dikey = (numara.y0 - ust_engel - 2 * pay * oran) / oran  # genişlik birimine çevrilmiş
    if dikey >= ROZET_EN_AZ:
        cap = min(ROZET_CAP, dikey)
        merkez_y = numara.y0 - pay * oran - cap * oran / 2
        return (round(numara.cx + cap / 2, 4), round(merkez_y, 4), round(cap, 4))
    return (round(numara.x0 - 0.002, 4), round(numara.cy, 4), ROZET_EN_AZ)


# —— Satır bölme ve soru grubu başlıkları —————————————————————————————————

SUTUN_BOSLUGU = 0.025  # aynı satırda bu kadar boşluk: farklı sütunun yazısı


def _satirlari_bol(satirlar, karakterler, charbox, genislik: float) -> list[list[int]]:
    """pdfium satırlarını büyük yatay boşluklardan böler.

    İki sütunun aynı yükseklikteki satırları PDF'te çoğu zaman tek satır olarak
    gelir ("...sayıların toplamı   3. Aşağıdaki termometrenin..."). Sağ
    sütundaki soru numarasının satır başı sayılabilmesi için satır, sütun
    boşluğu kadar açıklıkta parçalanır.
    """
    esik = SUTUN_BOSLUGU * genislik
    parcalar: list[list[int]] = []
    for satir in satirlar:
        if not satir:
            continue
        parca: list[int] = []
        onceki_sag = None
        for i in satir:
            if karakterler[i].isspace():
                if parca:
                    parca.append(i)
                continue
            k = charbox(i)
            if k and k[2] > k[0] and onceki_sag is not None:
                bosluk = k[0] - onceki_sag
                yukseklik = (k[3] - k[1]) or 1.0
                if bosluk > max(esik, 2.5 * yukseklik) or bosluk < -0.2 * genislik:
                    parcalar.append(parca)
                    parca = []
            if k and k[2] > k[0]:
                onceki_sag = k[2]
            parca.append(i)
        if parca:
            parcalar.append(parca)
    return [p for p in parcalar if p]


_GRUP_BASLIGI = re.compile(
    r"(\d{1,3})(?:\s*[,.]\s*(\d{1,3}))*\s*(?:ve|ile|-|–|—)\s*(\d{1,3})\s*\.?\s*sorular",
    re.IGNORECASE,
)
_GRUP_BASLIGI_ARALIK = re.compile(r"(\d{1,3})\s*[-–—]\s*(\d{1,3})\s*\.?\s*sorular", re.IGNORECASE)


def _grup_basligi(metin: str) -> list[int] | None:
    """"8, 9 ve 10. soruları ..." → [8, 9, 10]; "9-12. sorular" → [9, 10, 11, 12]."""
    yalin = metin.replace("İ", "I").replace("ı", "i")
    if "sorular" not in yalin.lower():
        return None
    e = _GRUP_BASLIGI_ARALIK.search(yalin)
    if e:
        bas, son = int(e.group(1)), int(e.group(2))
        return list(range(bas, son + 1)) if 0 < son - bas <= 8 else None
    e = _GRUP_BASLIGI.search(yalin)
    if not e:
        return None
    sayilar = [int(n) for n in re.findall(r"\d{1,3}", e.group(0))]
    sayilar = sorted(set(sayilar))
    if len(sayilar) < 2 or sayilar[-1] - sayilar[0] > 8:
        return None
    return list(range(sayilar[0], sayilar[-1] + 1))



def _gruplari_bagla(sayfalar, secilen, taslaklar, icerikler, capalar) -> dict[int, tuple[int, Kutu]]:
    """Ortak bilgili soru grupları: başlıktan ilk soruya kadarki blok (bilgi metni,
    görsel, tablo) gruptaki her sorunun ilk alanı olur.

    Dönüş: grubun ilk sorusu → rozetin dayanacağı başlık kutusu (rozet görselin
    üstünde, grubun başında durur).
    """
    rozet: dict[int, tuple[int, Kutu]] = {}
    for s in sayfalar:
        icerik = icerikler.get(s.indeks, [])
        for hb, numaralar in s.grup_basliklari:
            uyeler = [
                i for i, (a, _) in enumerate(secilen)
                if a.no in numaralar and (
                    (a.sayfa == s.indeks and a.kutu.y0 > hb.y0 - 0.005) or a.sayfa == s.indeks + 1
                )
            ]
            if not uyeler:
                continue
            ilk = min(uyeler)
            test = secilen[ilk][1]
            uyeler = [i for i in uyeler if secilen[i][1] == test]
            a0 = secilen[ilk][0]
            genis = hb.genislik > 0.45 or (hb.x0 < 0.45 and hb.x1 > 0.55)  # ortalanmış başlık da tam genişlik
            if genis:
                sol, sag = 0.0, 1.0
            else:
                sutun = _sutun_bul(capalar, hb.x0 + 0.015)
                sol, sag = _sutun_sinirlari(capalar, sutun, icerik, hb.y0, 1.0)
            ayni_yerde = a0.sayfa == s.indeks and (genis or a0.sutun == _sutun_bul(capalar, hb.x0 + 0.015))
            ust = hb.y0 - UST_PAY
            alt = a0.kutu.y0 - UST_PAY if ayni_yerde else 1 - ALT_BOSLUK
            iceride = [
                k for k in icerik
                if sol - 0.005 <= k.cx <= sag + 0.005 and k.y0 >= ust - 0.004 and k.y1 <= alt + 0.004
            ]
            if not iceride:
                continue
            if genis:
                # Başlık çoğu zaman sayfa genişliğinde bir çerçeve içindedir; çerçeve de bloğa girer.
                iceride += [
                    k for _, k, _ in s.nesneler
                    if k.genislik <= 0.95 and k.y0 >= ust - 0.004 and k.y1 <= alt + 0.004 and k.yukseklik < 0.5
                ]
            blok = Kutu(
                max(min(k.x0 for k in iceride) - YAN_PAY, 0.0) if genis else sol,
                max(ust, 0.0),
                min(max(k.x1 for k in iceride) + YAN_PAY, 1.0) if genis else _saga_cek(icerik, sol, sag),
                min(alt, max(k.y1 for k in iceride) + ALT_PAY),
            )
            if blok.yukseklik < 0.02:
                continue
            for i in uyeler:
                alanlar = taslaklar[i].alanlar
                if not any(sayfa == s.indeks and k.kesisim(blok) > 0.5 * blok.alan() for sayfa, k in alanlar):
                    alanlar.insert(0, (s.indeks, blok))
            rozet[id(taslaklar[ilk])] = (s.indeks, hb)
    return rozet
