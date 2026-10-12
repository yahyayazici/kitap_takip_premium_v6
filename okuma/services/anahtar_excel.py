"""Kazanım tablolu cevap anahtarı Excel'ini içe aktarır.

Beklenen başlıklar (sıra önemli değil, büyük/küçük harf duyarsız):
    Test | Ders | A Soru | B Soru [| C Soru | D Soru] | Cevap | Kazanım Kodu | Kazanım-1 … Kazanım-n

Her satır bir sorudur; "Cevap" A kitapçığındaki doğru şıktır. "B Soru", aynı
sorunun B kitapçığındaki sırasıdır. Şıklar kitapçıklar arasında karışmaz.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import openpyxl
from django.db import transaction

from okuma.models import Deneme, Kazanim, KitapcikSira, Soru, Test

LGS_KATSAYI = {"turkce": 4, "matematik": 4, "fen": 4, "inkilap": 1, "din": 1, "yabanci_dil": 1}


class AnahtarHatasi(ValueError):
    pass


@dataclass
class AnahtarSoru:
    test: str
    ders: str
    a_no: int
    kitapcik_no: dict[str, int]
    cevap: str
    kazanim_kodu: str
    kazanimlar: list[str]


@dataclass
class AnahtarOzet:
    test_sayisi: int = 0
    soru_sayisi: int = 0
    kazanim_sayisi: int = 0
    kitapciklar: list[str] = field(default_factory=list)


def _norm(s) -> str:
    s = str(s or "").strip().lower()
    for a, b in zip("ıİçğöşü", "iicgosu"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", s)


def lgs_ders_tahmin(ders: str) -> str:
    d = _norm(ders)
    if "turkce" in d:
        return "turkce"
    if d.startswith("mat"):
        return "matematik"
    if "fen" in d:
        return "fen"
    if "inkilap" in d or "sosyal" in d or "tarih" in d:
        return "inkilap"
    if "din" in d:
        return "din"
    if "ingilizce" in d or "almanca" in d or "arapca" in d or "dil" in d:
        return "yabanci_dil"
    return ""


def excel_oku(veri: bytes) -> list[AnahtarSoru]:
    wb = openpyxl.load_workbook(io.BytesIO(veri), data_only=True, read_only=True)
    ws = wb.worksheets[0]
    satirlar = list(ws.iter_rows(values_only=True))

    baslik_idx = None
    for i, satir in enumerate(satirlar[:30]):
        normlar = [_norm(h) for h in satir]
        if "asoru" in normlar and "cevap" in normlar:
            baslik_idx = i
            break
    if baslik_idx is None:
        raise AnahtarHatasi("Başlık satırı bulunamadı ('A Soru' ve 'Cevap' sütunları gerekli).")

    basliklar = [_norm(h) for h in satirlar[baslik_idx]]

    def sutun(ad: str) -> int | None:
        return basliklar.index(ad) if ad in basliklar else None

    s_test, s_ders, s_a, s_cevap, s_kod = (sutun(x) for x in ("test", "ders", "asoru", "cevap", "kazanimkodu"))
    if s_ders is None and s_test is None:
        raise AnahtarHatasi("'Test' ya da 'Ders' sütunu gerekli.")
    kitapcik_sutun = {
        m.group(1).upper(): i for i, h in enumerate(basliklar) if (m := re.fullmatch(r"([b-e])soru", h))
    }
    kazanim_sutun = [i for i, h in enumerate(basliklar) if re.fullmatch(r"kazanim\d*", h)]

    sorular: list[AnahtarSoru] = []
    for satir_no, satir in enumerate(satirlar[baslik_idx + 1 :], start=baslik_idx + 2):
        if not satir or all(v in (None, "") for v in satir):
            continue
        a_no = satir[s_a]
        if a_no in (None, ""):
            continue
        try:
            a_no = int(a_no)
        except (TypeError, ValueError):
            raise AnahtarHatasi(f"{satir_no}. satır: A soru numarası sayı değil ({a_no!r}).")
        cevap = str(satir[s_cevap] or "").strip().upper()
        if cevap not in {"A", "B", "C", "D", "E", "X"}:
            raise AnahtarHatasi(f"{satir_no}. satır: geçersiz cevap {cevap!r}. İptal soru için X yazın.")
        ders = str(satir[s_ders] if s_ders is not None else satir[s_test]).strip()
        test = str(satir[s_test] if s_test is not None else ders).strip()
        kitapcik_no = {}
        for k, i in kitapcik_sutun.items():
            if satir[i] not in (None, ""):
                kitapcik_no[k] = int(satir[i])
        sorular.append(
            AnahtarSoru(
                test=test,
                ders=ders,
                a_no=a_no,
                kitapcik_no=kitapcik_no,
                cevap=cevap,
                kazanim_kodu=str(satir[s_kod] or "").strip() if s_kod is not None else "",
                kazanimlar=[str(satir[i]).strip() for i in kazanim_sutun if satir[i] not in (None, "")],
            )
        )
    if not sorular:
        raise AnahtarHatasi("Excel'de soru satırı bulunamadı.")
    return sorular


def _dogrula(sorular: list[AnahtarSoru]) -> dict[str, list[AnahtarSoru]]:
    testler: dict[str, list[AnahtarSoru]] = {}
    for s in sorular:
        testler.setdefault(s.test, []).append(s)
    for ad, liste in testler.items():
        n = len(liste)
        a_nolar = sorted(s.a_no for s in liste)
        if a_nolar != list(range(1, n + 1)):
            raise AnahtarHatasi(f"{ad}: A soru numaraları 1–{n} arasında eksiksiz olmalı.")
        kitapciklar = {k for s in liste for k in s.kitapcik_no}
        for k in kitapciklar:
            nolar = sorted(s.kitapcik_no.get(k, 0) for s in liste)
            if nolar != list(range(1, n + 1)):
                raise AnahtarHatasi(f"{ad}: {k} kitapçığı sıraları 1–{n} arasında eksiksiz ve tekrarsız olmalı.")
    return testler


def _yapiya_esle(mevcut: list[Test], testler: dict[str, list[AnahtarSoru]]) -> list[tuple[Test, list[AnahtarSoru]]]:
    """Excel'deki testleri deneme türünün hazır testlerine ders adına (yoksa sırasına) göre bağlar."""
    if len(testler) != len(mevcut):
        raise AnahtarHatasi(
            f"Excel'de {len(testler)} ders var, bu deneme türünde {len(mevcut)} ders var: "
            + ", ".join(t.ders for t in mevcut)
        )
    bos = list(mevcut)
    eslesme = []
    for ad, liste in testler.items():
        anahtar = lgs_ders_tahmin(liste[0].ders) or lgs_ders_tahmin(ad)
        test = next((t for t in bos if anahtar and t.lgs_ders == anahtar), None) or bos[0]
        bos.remove(test)
        if len(liste) != test.soru_sayisi:
            raise AnahtarHatasi(
                f"{test.ders}: Excel'de {len(liste)} soru var, bu deneme türünde {test.soru_sayisi} soru olmalı."
            )
        eslesme.append((test, liste))
    return sorted(eslesme, key=lambda x: x[0].sira)


@transaction.atomic
def anahtar_yukle(deneme: Deneme, veri: bytes) -> AnahtarOzet:
    """Cevap anahtarını, kitapçık sıralarını ve kazanımları Excel'den kurar.

    Deneme türü seçilmişse dersler sabittir; Excel bu yapıya oturtulur.
    Tür yoksa testler Excel'e göre baştan oluşturulur.
    """
    testler = _dogrula(excel_oku(veri))
    deneme.sonuclar.all().delete()
    mevcut = list(deneme.testler.order_by("sira"))
    lgs = deneme.sinav_turu == Deneme.SinavTuru.LGS

    if deneme.tur_id and mevcut:
        eslesme = _yapiya_esle(mevcut, testler)
        Soru.objects.filter(test__deneme=deneme).delete()
    else:
        deneme.testler.all().delete()
        eslesme = []
        for sira, (ad, liste) in enumerate(testler.items(), start=1):
            ders = liste[0].ders
            lgs_ders = lgs_ders_tahmin(ders)
            eslesme.append((
                Test.objects.create(
                    deneme=deneme,
                    ad=ad,
                    ders=ders,
                    oturum=ad.split("(")[0].strip() if "(" in ad else "",
                    sira=sira,
                    soru_sayisi=len(liste),
                    katsayi=LGS_KATSAYI.get(lgs_ders, 1) if lgs else 1,
                    lgs_ders=lgs_ders,
                ),
                liste,
            ))

    ozet = AnahtarOzet()
    kitapciklar = {"A"}
    kazanim_idler = set()
    for test, liste in eslesme:
        for s in sorted(liste, key=lambda x: x.a_no):
            soru = Soru.objects.create(
                test=test,
                no=s.a_no,
                dogru="" if s.cevap == "X" else s.cevap,
                iptal=s.cevap == "X",
            )
            for k, no in s.kitapcik_no.items():
                KitapcikSira.objects.create(soru=soru, kitapcik=k, no=no)
                kitapciklar.add(k)
            for j, metin in enumerate(s.kazanimlar):
                kazanim, _ = Kazanim.objects.get_or_create(
                    ders=test.ders, kod=s.kazanim_kodu if j == 0 else "", metin=metin[:400]
                )
                soru.kazanimlar.add(kazanim)
                kazanim_idler.add(kazanim.pk)
        ozet.test_sayisi += 1
        ozet.soru_sayisi += len(liste)

    deneme.kitapciklar = ",".join(sorted(kitapciklar))
    deneme.hesaplanma = None
    deneme.save(update_fields=["kitapciklar", "hesaplanma"])
    ozet.kazanim_sayisi = len(kazanim_idler)
    ozet.kitapciklar = sorted(kitapciklar)
    return ozet


def _sira_listesi(metin: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", metin or "")]


@transaction.atomic
def anahtar_elle(test: Test, a_cevaplar: str, b_sirasi: str = "") -> None:
    """Tek bir testin anahtarını elle kurar. Mevcut kazanım bağları korunur.

    a_cevaplar: A kitapçığı cevapları (ör. "ABCD AXCB…"; X = iptal). Boşluk ve rakamlar yok sayılır.
    b_sirasi:   isteğe bağlı; A'daki 1., 2., … sorunun B kitapçığındaki sırası (ör. "13 14 18 19 …").
    """
    cevaplar = re.sub(r"[^A-EX]", "", a_cevaplar.upper().replace("İ", "I"))
    if len(cevaplar) != test.soru_sayisi:
        raise AnahtarHatasi(f"{test.ders}: {test.soru_sayisi} cevap gerekli, {len(cevaplar)} girildi.")
    b = _sira_listesi(b_sirasi)
    if b and sorted(b) != list(range(1, test.soru_sayisi + 1)):
        raise AnahtarHatasi(f"{test.ders}: B sırası 1–{test.soru_sayisi} sayılarını birer kez içermeli.")

    test.sorular.filter(no__gt=test.soru_sayisi).delete()
    for no, cevap in enumerate(cevaplar, start=1):
        soru, _ = Soru.objects.update_or_create(
            test=test, no=no, defaults={"dogru": "" if cevap == "X" else cevap, "iptal": cevap == "X"}
        )
        if b:
            KitapcikSira.objects.update_or_create(soru=soru, kitapcik="B", defaults={"no": b[no - 1]})
        elif b_sirasi is not None and not b_sirasi.strip():
            KitapcikSira.objects.filter(soru=soru, kitapcik="B").delete()

    deneme = test.deneme
    var_b = KitapcikSira.objects.filter(soru__test__deneme=deneme, kitapcik="B").exists()
    deneme.kitapciklar = "A,B" if var_b else "A"
    deneme.save(update_fields=["kitapciklar"])
