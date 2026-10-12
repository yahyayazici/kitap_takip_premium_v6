"""Net, puan ve sıralama hesabı.

Kurallar (MEB/ÖSYM uygulamasıyla uyumlu):
- Net = Doğru − Yanlış / k   (k = deneme.yanlis_katsayi; 0 ise götürmez). Negatif net kırpılmaz.
- Çift/hatalı işaretleme yanlış sayılır.
- İptal soru herkese doğru sayılmaz; değerlendirme dışı kalır.
- Ek doğru şıklar (iki doğru cevaplı soru) doğru sayılır.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from okuma.models import Deneme, OptikSatir, Sonuc, TestSonuc
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


def harita_kur(deneme: Deneme) -> DenemeHaritasi:
    testler = list(deneme.testler.prefetch_related("sorular__kitapcik_siralari").order_by("sira"))
    sorular: list[SoruBilgi] = []
    konum: dict[str, list[int]] = {k: [] for k in deneme.kitapcik_listesi}
    konum.setdefault("A", [])
    ofset = 0
    for test in testler:
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
    return DenemeHaritasi(testler=testler, sorular=sorular, konum=konum, toplam=ofset)


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


def kitapcik_tahmin_et(deneme: Deneme, cevaplar: str) -> str | None:
    """Kitapçık alanı boş/hatalıysa, cevapları her anahtarla puanlayıp açık ara öndekini seçer."""
    harita = harita_kur(deneme)
    if not harita.sorular:
        return None
    puanlar = []
    for k in harita.konum:
        if any(i < 0 for i in harita.konum[k]):
            continue
        sayim = _say(harita, a_sirasina_cevir(harita, k, cevaplar))
        puanlar.append((sum(v[0] for v in sayim.values()), k))
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
        .select_related("ogrenci")
        .order_by("yukleme__olusturma", "satir_no")
    )
    k = deneme.yanlis_katsayi
    tutulan: set[int] = set()
    netler: dict[int, dict[int, Decimal]] = {}
    sonuclar: dict[int, Sonuc] = {}

    for satir in satirlar:
        if satir.kitapcik not in harita.konum or any(i < 0 for i in harita.konum[satir.kitapcik]):
            continue
        cevaplar_a = a_sirasina_cevir(harita, satir.kitapcik, satir.cevaplar)
        sayim = _say(harita, cevaplar_a)
        d = sum(v[0] for v in sayim.values())
        y = sum(v[1] for v in sayim.values())
        b = sum(v[2] for v in sayim.values())
        test_netleri = {tid: net_hesapla(v[0], v[1], k) for tid, v in sayim.items()}
        sonuc, _ = Sonuc.objects.update_or_create(
            deneme=deneme,
            ogrenci=satir.ogrenci,
            defaults=dict(
                satir=satir,
                kitapcik=satir.kitapcik,
                sube=satir.ogrenci.sube or satir.sube,
                cevaplar_a=cevaplar_a,
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
