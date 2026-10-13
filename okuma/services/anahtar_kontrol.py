"""Kitapçık anahtarı ile öğrenci cevaplarının tutarlılığı.

Bir kitapçıktaki öğrencilerin büyük çoğunluğu birçok soruda anahtardaki şıktan
farklı *aynı* şıkkı işaretliyorsa, o kitapçığın o dersteki anahtarı büyük
ihtimalle yanlıştır (ör. yayınevinin B kitapçığı anahtarı hatalı ya da başka
bir denemeye ait). Tek tek zor sorular bu ölçüte takılmaz.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from okuma.models import Deneme, OptikSatir
from okuma.services.puanlama import harita_kur, test_cevaplari

EN_AZ_OGRENCI = 5
COGUNLUK = 0.5  # sorunun bu orandan fazla öğrencide aynı (yanlış) şık
SUPHELI_ORAN = 0.3  # dersin bu orandan fazla sorusu böyleyse uyar


@dataclass
class AnahtarSuphesi:
    kitapcik: str
    ders: str
    supheli: int
    soru: int
    ogrenci: int
    cogunluk_anahtari: str  # öğrencilerin çoğunluğunun işaretlediği şıklar (kitapçık sırasıyla)


def anahtar_kontrol(deneme: Deneme) -> list[AnahtarSuphesi]:
    harita = harita_kur(deneme)
    if not harita.sorular:
        return []
    satirlar = OptikSatir.objects.filter(yukleme__deneme=deneme, dahil=True).exclude(kitapcik="").select_related("yukleme")
    sonuc = []
    for test in harita.testler:
        gruplar: dict[str, list[str]] = {}
        for satir in satirlar:
            if satir.yukleme.oturum and satir.yukleme.oturum != test.oturum:
                continue
            mod, parca = test_cevaplari(harita, test, satir.kitapcik, satir.cevaplar)
            if mod is None:
                continue
            gruplar.setdefault((satir.kitapcik, mod), []).append(parca)
        for (kitapcik, mod), parcalar in gruplar.items():
            if len(parcalar) < EN_AZ_OGRENCI:
                continue
            if mod == "bagimsiz":
                anahtar = harita.bagimsiz[kitapcik][test.pk]
                dogrular = [{c} for c in anahtar]
            else:
                dogrular = [set(sb.dogrular) for sb in harita.test_sorulari[test.pk]]
            supheli = 0
            cogunluk = []
            for i, dogru in enumerate(dogrular):
                sayac = Counter(p[i] for p in parcalar if i < len(p) and p[i] not in " *")
                if not sayac:
                    cogunluk.append(" ")
                    continue
                sik, adet = sayac.most_common(1)[0]
                cogunluk.append(sik)
                if dogru and sik not in dogru and "X" not in dogru and adet / len(parcalar) > COGUNLUK:
                    supheli += 1
            if supheli >= max(2, SUPHELI_ORAN * len(dogrular)):
                sonuc.append(
                    AnahtarSuphesi(kitapcik, test.ders, supheli, len(dogrular), len(parcalar), "".join(cogunluk))
                )
    return sonuc
