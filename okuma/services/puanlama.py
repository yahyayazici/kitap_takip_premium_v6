"""Net, puan ve sıralama hesabı.

Kurallar (MEB/ÖSYM uygulamasıyla uyumlu):
- Net = Doğru − Yanlış / k   (k = deneme.yanlis_katsayi; 0 ise götürmez). Negatif net kırpılmaz.
- Çift/hatalı işaretleme yanlış sayılır.
- İptal soru herkese doğru sayılmaz; değerlendirme dışı kalır.
- Ek doğru şıklar (iki doğru cevaplı soru) doğru sayılır.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from okuma.models import Deneme, KitapcikAnahtari, OptikSatir, Sonuc, TestSonuc
from okuma.services.lgs import LGS_KATSAYILARI, LGS_SORU_SAYISI

IKI = Decimal("0.01")
UC = Decimal("0.001")


@dataclass
class SoruBilgi:
    soru_id: int
    test_id: int
    a_index: int  # A sırasındaki global konum (cevaplar_a içinde)
    dogrular: frozenset[str]
    iptal: bool


@dataclass
class DenemeHaritasi:
    testler: list  # Test nesneleri, sıralı
    sorular: list[SoruBilgi]
    # kitapçık -> her A-index için optik dizideki konum
    konum: dict[str, list[int]]
    toplam: int
    # Eşleşmesiz kitapçık anahtarları: kitapçık -> {test_id: "CBDA…"} (kitapçığın kendi sırası)
    bagimsiz: dict[str, dict[int, str]] = field(default_factory=dict)
    # test_id -> optik dizide testin başladığı konum
    ofset: dict[int, int] = field(default_factory=dict)
    # test_id -> o testin soruları (A sırasıyla)
    test_sorulari: dict[int, list[SoruBilgi]] = field(default_factory=dict)

    def kitapcik_modu(self, kitapcik: str) -> str | None:
        """'a': A sırasına çevrilebilir; 'bagimsiz': kendi anahtarıyla puanlanır; None: puanlanamaz."""
        if kitapcik in self.konum and self.konum[kitapcik] and all(i >= 0 for i in self.konum[kitapcik]):
            return "a"
        anahtarlar = self.bagimsiz.get(kitapcik, {})
        if self.testler and all(t.pk in anahtarlar for t in self.testler):
            return "bagimsiz"
        return None


def harita_kur(deneme: Deneme) -> DenemeHaritasi:
    testler = list(deneme.testler.prefetch_related("sorular__kitapcik_siralari").order_by("sira"))
    sorular: list[SoruBilgi] = []
    konum: dict[str, list[int]] = {k: [] for k in deneme.kitapcik_listesi}
    konum.setdefault("A", [])
    ofset = 0
    ofsetler = {}
    for test in testler:
        ofsetler[test.pk] = ofset
        for soru in sorted(test.sorular.all(), key=lambda s: s.no):
            sorular.append(
                SoruBilgi(
                    soru_id=soru.pk,
                    test_id=test.pk,
                    a_index=len(sorular),
                    dogrular=frozenset(soru.dogru_kume - {""}),
                    iptal=soru.iptal,
                )
            )
            siralar = {ks.kitapcik: ks.no for ks in soru.kitapcik_siralari.all()}
            for k in konum:
                no = soru.no if k == "A" else siralar.get(k)
                konum[k].append(ofset + no - 1 if no else -1)
        ofset += test.blok
    bagimsiz: dict[str, dict[int, str]] = {}
    for ka in KitapcikAnahtari.objects.filter(test__deneme=deneme):
        bagimsiz.setdefault(ka.kitapcik, {})[ka.test_id] = ka.cevaplar
    test_sorulari: dict[int, list[SoruBilgi]] = {t.pk: [] for t in testler}
    for sb in sorular:
        test_sorulari[sb.test_id].append(sb)
    return DenemeHaritasi(
        testler=testler, sorular=sorular, konum=konum, toplam=ofset, bagimsiz=bagimsiz, ofset=ofsetler,
        test_sorulari=test_sorulari,
    )


def test_cevaplari(harita: DenemeHaritasi, test, kitapcik: str, cevaplar: str) -> tuple[str | None, str]:
    """Bir testin öğrenci cevapları: ('a', A sırasıyla) | ('bagimsiz', kitapçık sırasıyla) | (None, boşluk)."""
    sorular = harita.test_sorulari[test.pk]
    konumlar = harita.konum.get(kitapcik)
    if konumlar and sorular and all(konumlar[s.a_index] >= 0 for s in sorular):
        return "a", "".join(cevaplar[konumlar[s.a_index]] if konumlar[s.a_index] < len(cevaplar) else " " for s in sorular)
    anahtar = harita.bagimsiz.get(kitapcik, {}).get(test.pk)
    if anahtar:
        bas = harita.ofset[test.pk]
        return "bagimsiz", cevaplar[bas : bas + len(anahtar)].ljust(len(anahtar))
    return None, " " * len(sorular)


def test_say(harita: DenemeHaritasi, test, kitapcik: str, mod: str | None, parca: str) -> list[int]:
    """[doğru, yanlış, boş]; iptal sorular sayılmaz."""
    d = y = b = 0
    if mod == "bagimsiz":
        ciftler = zip(harita.bagimsiz[kitapcik][test.pk], parca)
        for dogru, c in ciftler:
            if dogru == "X":
                continue
            if c == " ":
                b += 1
            elif c == dogru:
                d += 1
            else:
                y += 1
        return [d, y, b]
    for sb, c in zip(harita.test_sorulari[test.pk], parca):
        if sb.iptal:
            continue
        if c == " ":
            b += 1
        elif c in sb.dogrular:
            d += 1
        else:
            y += 1
    return [d, y, b]


def bagimsiz_say(harita: DenemeHaritasi, kitapcik: str, cevaplar: str):
    """Eşleşmesiz kitapçığı kendi anahtarıyla sayar: (test bazında [d, y, b], kitapçık sırasıyla cevaplar)."""
    sayim = {}
    sirali = []
    for t in harita.testler:
        anahtar = harita.bagimsiz[kitapcik][t.pk]
        bas = harita.ofset[t.pk]
        d = y = b = 0
        for i, dogru in enumerate(anahtar):
            c = cevaplar[bas + i] if bas + i < len(cevaplar) else " "
            sirali.append(c)
            if dogru == "X":
                continue
            if c == " ":
                b += 1
            elif c == dogru:
                d += 1
            else:
                y += 1
        sayim[t.pk] = [d, y, b]
    return sayim, "".join(sirali)


def a_sirasina_cevir(harita: DenemeHaritasi, kitapcik: str, cevaplar: str) -> str:
    konumlar = harita.konum[kitapcik]
    return "".join(cevaplar[i] if 0 <= i < len(cevaplar) else " " for i in konumlar)


def _say(harita: DenemeHaritasi, cevaplar_a: str):
    """Test bazında (doğru, yanlış, boş) döndürür."""
    sayim = {t.pk: [0, 0, 0] for t in harita.testler}
    for s in harita.sorular:
        if s.iptal:
            continue
        c = cevaplar_a[s.a_index]
        if c == " ":
            sayim[s.test_id][2] += 1
        elif c in s.dogrular:
            sayim[s.test_id][0] += 1
        else:
            sayim[s.test_id][1] += 1
    return sayim


def net_hesapla(dogru: int, yanlis: int, k: int) -> Decimal:
    net = Decimal(dogru) - (Decimal(yanlis) / Decimal(k) if k else 0)
    return net.quantize(IKI, rounding=ROUND_HALF_UP)


def kitapcik_tahmin_et(deneme: Deneme, cevaplar: str, oturum: str = "") -> str | None:
    """Kitapçık alanı boş/hatalıysa, cevapları her anahtarla puanlayıp açık ara öndekini seçer.

    oturum verilirse yalnız o oturumun testlerine bakılır (sözel/sayısal ayrı okunduğunda)."""
    harita = harita_kur(deneme)
    if not harita.sorular:
        return None
    testler = [t for t in harita.testler if not oturum or t.oturum == oturum]
    puanlar = []
    for k in set(harita.konum) | set(harita.bagimsiz):
        toplam = 0
        for t in testler:
            mod, parca = test_cevaplari(harita, t, k, cevaplar)
            if mod is None:
                break
            toplam += test_say(harita, t, k, mod, parca)[0]
        else:
            puanlar.append((toplam, k))
    if not puanlar:
        return None
    puanlar.sort(reverse=True)
    if len(puanlar) == 1:
        return puanlar[0][1]
    (en_iyi, k), (ikinci, _) = puanlar[0], puanlar[1]
    # Rastgele eşleşme ~%25'tir; belirgin fark yoksa karar verme.
    if en_iyi >= 10 and en_iyi >= ikinci * 1.5:
        return k
    return None


def _sira_ver(degerler: list[tuple[Decimal, int]]) -> dict[int, int]:
    """Eşit değerler aynı sırayı alır (1, 2, 2, 4)."""
    sirali = sorted(degerler, key=lambda x: x[0], reverse=True)
    sonuc, onceki, sira = {}, None, 0
    for i, (deger, pk) in enumerate(sirali, start=1):
        if deger != onceki:
            sira, onceki = i, deger
        sonuc[pk] = sira
    return sonuc


def _lgs_tablo_puan(deneme: Deneme, harita, test_netleri: dict[int, Decimal]) -> Decimal | None:
    tablo = LGS_KATSAYILARI.get(deneme.lgs_yili)
    if not tablo:
        return None
    puan = Decimal(str(tablo["taban"]))
    for t in harita.testler:
        if t.lgs_ders and t.soru_sayisi:
            # 75 soruluk denemede net, LGS'deki soru sayısına oranlanır (15 soruda 12 net → 20 soruda 16).
            olcek = Decimal(LGS_SORU_SAYISI[t.lgs_ders]) / Decimal(t.soru_sayisi)
            puan += Decimal(str(tablo[t.lgs_ders])) * test_netleri[t.pk] * olcek
    return min(max(puan, Decimal(100)), Decimal(500)).quantize(UC)


def _deneme_ici_puanlar(harita, netler: dict[int, dict[int, Decimal]]) -> dict[int, Decimal]:
    """MEB zinciri, ortalama/SS bu denemeye girenlerden: SP → ×katsayı → TASP → 100–500."""
    sonuc_idler = list(netler)
    tasp = {sid: 0.0 for sid in sonuc_idler}
    for t in harita.testler:
        degerler = [float(netler[sid][t.pk]) for sid in sonuc_idler]
        ort = statistics.fmean(degerler)
        ss = statistics.pstdev(degerler)
        for sid, net in zip(sonuc_idler, degerler):
            sp = 50 + 10 * (net - ort) / ss if ss else 50.0
            tasp[sid] += sp * float(t.katsayi)
    en_kucuk, en_buyuk = min(tasp.values()), max(tasp.values())
    aralik = en_buyuk - en_kucuk
    return {
        sid: Decimal(100 + 400 * (v - en_kucuk) / aralik if aralik else 300).quantize(UC)
        for sid, v in tasp.items()
    }


@transaction.atomic
def deneme_hesapla(deneme: Deneme) -> int:
    harita = harita_kur(deneme)
    if not harita.sorular:
        raise ValueError("Cevap anahtarı yüklenmemiş.")

    satirlar = (
        OptikSatir.objects.filter(yukleme__deneme=deneme, dahil=True, ogrenci__isnull=False)
        .exclude(kitapcik="")
        .select_related("ogrenci", "yukleme")
        .order_by("yukleme__olusturma", "satir_no")
    )
    k = deneme.yanlis_katsayi
    tutulan: set[int] = set()
    netler: dict[int, dict[int, Decimal]] = {}
    sonuclar: dict[int, Sonuc] = {}

    # Öğrencinin satırları: tek optik (bütün oturumlar) ya da oturum oturum ayrı okunmuş olabilir.
    ogrenciye_gore: dict[int, list[OptikSatir]] = {}
    for satir in satirlar:
        ogrenciye_gore.setdefault(satir.ogrenci_id, []).append(satir)

    for liste in ogrenciye_gore.values():
        kaynak = {}
        for satir in liste:  # sonra okunan öncekinin yerine geçer
            for t in harita.testler:
                if not satir.yukleme.oturum or t.oturum == satir.yukleme.oturum:
                    kaynak[t.pk] = satir
        parcalar, sayim, test_kitapcik, eksik = [], {}, {}, []
        for t in harita.testler:
            satir = kaynak.get(t.pk)
            kitapcik = satir.kitapcik if satir else ""
            if satir is None:
                mod, parca = "", " " * len(harita.test_sorulari[t.pk])
                if (ad := t.oturum or t.ders) not in eksik:
                    eksik.append(ad)
            else:
                mod, parca = test_cevaplari(harita, t, kitapcik, satir.cevaplar)
                mod = mod or ""
            sayim[t.pk] = test_say(harita, t, kitapcik, mod, parca)
            test_kitapcik[str(t.pk)] = [kitapcik, mod]
            parcalar.append(parca)
        if not any(m for _, m in test_kitapcik.values()):
            continue  # hiçbir testi puanlanamadı (kitapçık anahtarı yok)

        oturum_kitapcik: dict[str, str] = {}
        for t in harita.testler:
            kit, _ = test_kitapcik[str(t.pk)]
            if kit:
                oturum_kitapcik.setdefault(t.oturum or t.ders, kit)
        if len(set(oturum_kitapcik.values())) <= 1:
            kitapcik_metni = next(iter(oturum_kitapcik.values()), "")
        else:
            kitapcik_metni = " · ".join(f"{o} {kit}" for o, kit in oturum_kitapcik.items())

        d = sum(v[0] for v in sayim.values())
        y = sum(v[1] for v in sayim.values())
        b = sum(v[2] for v in sayim.values())
        test_netleri = {tid: net_hesapla(v[0], v[1], k) for tid, v in sayim.items()}
        ogrenci = liste[0].ogrenci
        sonuc, _ = Sonuc.objects.update_or_create(
            deneme=deneme,
            ogrenci=ogrenci,
            defaults=dict(
                satir=liste[0],
                kitapcik=kitapcik_metni[:40],
                test_kitapcik=test_kitapcik,
                eksik_oturum=(", ".join(eksik) + " oturumuna katılmadı")[:80] if eksik else "",
                sube=ogrenci.sube or liste[0].sube,
                cevaplar_a="".join(parcalar),
                a_sirali=all(m in ("a", "") for _, m in test_kitapcik.values()),
                dogru=d,
                yanlis=y,
                bos=b,
                net=sum(test_netleri.values(), Decimal(0)),
                puan=None,
            ),
        )
        sonuc.test_sonuclari.all().delete()
        TestSonuc.objects.bulk_create(
            TestSonuc(sonuc=sonuc, test_id=tid, dogru=v[0], yanlis=v[1], bos=v[2], net=test_netleri[tid])
            for tid, v in sayim.items()
        )
        tutulan.add(sonuc.pk)
        netler[sonuc.pk] = test_netleri
        sonuclar[sonuc.pk] = sonuc

    Sonuc.objects.filter(deneme=deneme).exclude(pk__in=tutulan).delete()

    if sonuclar:
        if deneme.puan_modu == Deneme.PuanModu.LGS_TABLO:
            for sid, s in sonuclar.items():
                s.puan = _lgs_tablo_puan(deneme, harita, netler[sid])
        elif deneme.puan_modu == Deneme.PuanModu.DENEME_ICI:
            for sid, p in _deneme_ici_puanlar(harita, netler).items():
                sonuclar[sid].puan = p

        def olcut(s: Sonuc) -> Decimal:
            return s.puan if s.puan is not None else s.net

        n = len(sonuclar)
        kurum = _sira_ver([(olcut(s), sid) for sid, s in sonuclar.items()])
        subeler: dict[str, list] = {}
        for sid, s in sonuclar.items():
            subeler.setdefault(s.sube, []).append((olcut(s), sid))
        sube_sira = {}
        for liste in subeler.values():
            sube_sira.update(_sira_ver(liste))
        for sid, s in sonuclar.items():
            s.sira_kurum = kurum[sid]
            s.sira_sube = sube_sira[sid]
            s.katilimci = n
            s.yuzdelik = (Decimal(kurum[sid] * 100) / Decimal(n)).quantize(IKI)
        Sonuc.objects.bulk_update(
            sonuclar.values(), ["puan", "sira_kurum", "sira_sube", "katilimci", "yuzdelik"]
        )

    deneme.hesaplanma = timezone.now()
    deneme.save(update_fields=["hesaplanma"])
    return len(sonuclar)
