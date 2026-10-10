"""ÇİSA — seçilen denemelerin talebe raporu.

Kapak netleri kayıtlı branş netinden gelir. Konu dökümü soru karnesindeki
satırlardan toplanır; aynı soru iki kez sayılmaz.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Exists, OuterRef, Q

from takip.deneme_models import (
    DenemeBransSonucu,
    DenemeSinavi,
    DenemeSonucu,
    DenemeSoruSonucu,
)
from takip.deneme_service import DENEME_KARNE_DERSLERI, tr_ondalik
from takip.deneme_soru_karne import konu_ders_adi
from takip.models import Talebe

_DERS_SIRA = {kod: i for i, (kod, _etiket) in enumerate(DENEME_KARNE_DERSLERI)}
_DERS_AD = {
    "turkce": "Türkçe",
    "türkçe": "Türkçe",
    "matematik": "Matematik",
    "fen": "Fen Bilimleri",
    "fen bilimleri": "Fen Bilimleri",
    "fen bilgisi": "Fen Bilimleri",
    "sosyal": "Sosyal Bilgiler",
    "sosyal bilgiler": "Sosyal Bilgiler",
    "inkilap": "İnkılap",
    "inkılap": "İnkılap",
    "t.c. inkılap tarihi": "İnkılap",
    "din": "Din Kültürü",
    "din kültürü": "Din Kültürü",
    "din kulturu": "Din Kültürü",
    "ingilizce": "İngilizce",
}
_KOD = {
    "türkçe": "turkce",
    "turkce": "turkce",
    "matematik": "matematik",
    "fen": "fen",
    "fen bilimleri": "fen",
    "fen bilgisi": "fen",
    "sosyal": "sosyal",
    "sosyal bilgiler": "sosyal",
    "inkilap": "inkilap",
    "inkılap": "inkilap",
    "t.c. inkılap tarihi": "inkilap",
    "din": "din",
    "din kültürü": "din",
    "din kulturu": "din",
    "ingilizce": "ingilizce",
}


def _ort(degerler: list[Decimal]) -> Decimal | None:
    if not degerler:
        return None
    return (sum(degerler, Decimal("0")) / Decimal(len(degerler))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _yuzde(pay: int, payda: int) -> int | None:
    if payda <= 0:
        return None
    return int(
        (Decimal(pay) * Decimal(100) / Decimal(payda)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _ders_kodu(ders_key: str, ders_ad: str) -> str:
    ham = (ders_key or "").strip().lower()
    if ham in _DERS_SIRA or ham in _DERS_AD:
        return _KOD.get(ham, ham)
    ad = (ders_ad or "").strip().lower()
    return _KOD.get(ad, ham or ad or "diger")


def _ders_baslik(kod: str, ders_ad: str) -> str:
    if ders_ad.strip():
        return ders_ad.strip()
    return _DERS_AD.get(kod, kod)


_BILINEN_DERS = set(_KOD.values()) | set(_DERS_SIRA)


def _satir_ders(ders_key: str, ders_ad: str, konu: str) -> tuple[str, str]:
    """8. sınıf karnesinde ders «Sınıf» yazılmışsa konudan dersi ayır."""
    kod = _ders_kodu(ders_key, ders_ad)
    baslik = _ders_baslik(kod, ders_ad)
    if kod in _BILINEN_DERS:
        return kod, baslik
    ipucu = konu_ders_adi(konu)
    if not ipucu:
        return kod, baslik
    return _ders_kodu("", ipucu), ipucu


def cisa_deneme_listesi(talebe: Talebe) -> list[dict]:
    """Talebenin seçilebileceği denemeler. Taslak yok."""
    soru = DenemeSoruSonucu.objects.filter(
        deneme_id=OuterRef("deneme_id"),
        talebe_id=talebe.id,
    )
    kayitlar = (
        DenemeSonucu.objects.filter(
            talebe=talebe,
            deneme__durum=DenemeSinavi.Durum.AKTIF,
        )
        .select_related("deneme")
        .annotate(soru_karnesi=Exists(soru))
        .order_by("-deneme__sinav_tarihi", "-deneme_id")
    )
    return [
        {
            "id": kayit.deneme_id,
            "ad": kayit.deneme.ad,
            "tarih": kayit.deneme.sinav_tarihi,
            "net": tr_ondalik(kayit.toplam_net),
            "soru_karnesi": bool(kayit.soru_karnesi),
        }
        for kayit in kayitlar
    ]


def cisa_sinif_denemeleri(talebe_ids: list[int]) -> list[dict]:
    """Sınıftaki talebelerin ortak deneme listesi. Taslak ve arşiv yok."""
    if not talebe_ids:
        return []
    sayilar = {
        satir["deneme_id"]: satir["talebe_sayisi"]
        for satir in (
            DenemeSonucu.objects.filter(
                talebe_id__in=talebe_ids,
                deneme__durum=DenemeSinavi.Durum.AKTIF,
            )
            .values("deneme_id")
            .annotate(talebe_sayisi=Count("talebe_id", distinct=True))
        )
    }
    if not sayilar:
        return []
    denemeler = DenemeSinavi.objects.filter(pk__in=sayilar).order_by(
        "-sinav_tarihi", "-id"
    )
    return [
        {
            "id": deneme.id,
            "ad": deneme.ad,
            "tarih": deneme.sinav_tarihi,
            "talebe_sayisi": sayilar[deneme.id],
        }
        for deneme in denemeler
    ]


def _sinif_soru(talebe: Talebe) -> Q:
    if talebe.sinif_sube_id:
        return Q(talebe__sinif_sube_id=talebe.sinif_sube_id)
    return Q(talebe_id=talebe.id)


def _sinif_brans(talebe: Talebe) -> Q:
    if talebe.sinif_sube_id:
        return Q(sonuc__talebe__sinif_sube_id=talebe.sinif_sube_id)
    return Q(sonuc__talebe_id=talebe.id)


def cisa_rapor(talebe: Talebe, deneme_ids: list[int]) -> dict | None:
    """Seçilen denemelerden ÇİSA raporu. Seçim dışı deneme girmez."""
    istenen = {int(i) for i in deneme_ids if str(i).isdigit() or isinstance(i, int)}
    if not istenen:
        return None
    sonuclar = list(
        DenemeSonucu.objects.filter(
            talebe=talebe,
            deneme_id__in=istenen,
            deneme__durum=DenemeSinavi.Durum.AKTIF,
        )
        .select_related("deneme", "talebe", "talebe__sinif_sube")
        .prefetch_related("brans_satirlari")
        .order_by("deneme__sinav_tarihi", "deneme_id")
    )
    if not sonuclar:
        return None

    ids = [s.deneme_id for s in sonuclar]
    sinif_netleri: dict[tuple[int, str], list[Decimal]] = {}
    for satir in DenemeBransSonucu.objects.filter(
        _sinif_brans(talebe), sonuc__deneme_id__in=ids
    ).values("sonuc__deneme_id", "brans", "net"):
        anahtar = (satir["sonuc__deneme_id"], satir["brans"])
        sinif_netleri.setdefault(anahtar, [])
        sinif_netleri[anahtar].append(Decimal(satir["net"] or 0))

    ders_toplam: dict[str, dict] = {}
    for kod, etiket in DENEME_KARNE_DERSLERI:
        ders_toplam[kod] = {
            "ad": etiket.title() if etiket.isupper() else etiket,
            "dogru": 0,
            "yanlis": 0,
            "bos": 0,
            "netler": [],
            "sinif_netler": [],
        }
    # Karne etiketleri büyük harf. Raporda okunur başlık.
    _okunur = {
        "turkce": "Türkçe",
        "sosyal": "Sosyal Bilgiler",
        "din": "Din Kültürü",
        "ingilizce": "İngilizce",
        "matematik": "Matematik",
        "fen": "Fen Bilimleri",
    }
    for kod, kova in ders_toplam.items():
        kova["ad"] = _okunur.get(kod, kova["ad"])

    for sonuc in sonuclar:
        for brans in sonuc.brans_satirlari.all():
            kova = ders_toplam.get(brans.brans)
            if kova is None:
                continue
            kova["dogru"] += int(brans.dogru or 0)
            kova["yanlis"] += int(brans.yanlis or 0)
            kova["bos"] += int(brans.bos or 0)
            kova["netler"].append(Decimal(brans.net or 0))
            sinif_liste = sinif_netleri.get((sonuc.deneme_id, brans.brans))
            sinif_ort = _ort(sinif_liste) if sinif_liste else None
            if sinif_ort is not None:
                kova["sinif_netler"].append(sinif_ort)

    dersler = []
    for kod, _etiket in DENEME_KARNE_DERSLERI:
        kova = ders_toplam[kod]
        if not kova["netler"] and kova["dogru"] + kova["yanlis"] + kova["bos"] == 0:
            continue
        net = _ort(kova["netler"])
        sinif_net = _ort(kova["sinif_netler"])
        toplam = kova["dogru"] + kova["yanlis"] + kova["bos"]
        durum = ""
        fark = ""
        fark_yazi = ""
        if net is not None and sinif_net is not None and net != sinif_net:
            if net > sinif_net:
                durum = "iyi"
                fark_yazi = "üstünde"
            else:
                durum = "geri"
                fark_yazi = "altında"
            fark = tr_ondalik(abs(net - sinif_net))
        dersler.append(
            {
                "kod": kod,
                "ad": kova["ad"],
                "net": tr_ondalik(net) if net is not None else "—",
                "sinif_net": tr_ondalik(sinif_net) if sinif_net is not None else "—",
                "durum": durum,
                "fark": fark,
                "fark_yazi": fark_yazi,
                "dogru": kova["dogru"],
                "yanlis": kova["yanlis"],
                "bos": kova["bos"],
                "dogru_yuzde": _yuzde(kova["dogru"], toplam),
            }
        )

    soru_var_ids = set(
        DenemeSoruSonucu.objects.filter(deneme_id__in=ids, talebe=talebe)
        .values_list("deneme_id", flat=True)
        .distinct()
    )
    denemeler = [
        {
            "ad": s.deneme.ad,
            "tarih": s.deneme.sinav_tarihi,
            "net": tr_ondalik(s.toplam_net),
            "soru_karnesi": s.deneme_id in soru_var_ids,
        }
        for s in sonuclar
    ]

    konular, kayiplar = _konu_dokumu(talebe, ids, _sinif_soru(talebe))
    sube = getattr(talebe, "sinif_sube", None)
    sinif_yazi = str(sube) if sube is not None else (talebe.sinif or "—")
    return {
        "ad_soyad": talebe.ad_soyad,
        "sinif": sinif_yazi,
        "no": (talebe.talebe_no or "").strip(),
        "denemeler": denemeler,
        "baslangic": sonuclar[0].deneme.sinav_tarihi,
        "bitis": sonuclar[-1].deneme.sinav_tarihi,
        "ortalama_net": tr_ondalik(_ort([Decimal(s.toplam_net or 0) for s in sonuclar])),
        "dersler": dersler,
        "kayiplar": kayiplar,
        "konular": konular,
    }


def _konu_dokumu(talebe: Talebe, ids: list[int], sinif: Q):
    kendi: dict[tuple, dict] = {}
    for kayit in DenemeSoruSonucu.objects.filter(deneme_id__in=ids, talebe=talebe).only(
        "ders_key", "ders_ad", "konu_ad", "sonuc"
    ):
        konu = (kayit.konu_ad or "").strip() or "Belirtilmemiş"
        kod, ders_baslik = _satir_ders(kayit.ders_key, kayit.ders_ad, konu)
        anahtar = (kod, konu.casefold())
        kova = kendi.get(anahtar)
        if kova is None:
            kova = {
                "kod": kod,
                "ders": ders_baslik,
                "konu": konu,
                "dogru": 0,
                "yanlis": 0,
                "bos": 0,
            }
            kendi[anahtar] = kova
        if kayit.sonuc == DenemeSoruSonucu.Sonuc.DOGRU:
            kova["dogru"] += 1
        elif kayit.sonuc == DenemeSoruSonucu.Sonuc.YANLIS:
            kova["yanlis"] += 1
        else:
            kova["bos"] += 1

    sinif_kova: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for kayit in (
        DenemeSoruSonucu.objects.filter(sinif, deneme_id__in=ids)
        .only("ders_key", "ders_ad", "konu_ad", "sonuc")
    ):
        konu = (kayit.konu_ad or "").strip() or "Belirtilmemiş"
        kod, _yok = _satir_ders(kayit.ders_key, kayit.ders_ad, konu)
        anahtar = (kod, konu.casefold())
        sinif_kova[anahtar][1] += 1
        if kayit.sonuc == DenemeSoruSonucu.Sonuc.DOGRU:
            sinif_kova[anahtar][0] += 1

    satirlar = []
    for kova in kendi.values():
        toplam = kova["dogru"] + kova["yanlis"] + kova["bos"]
        yuzde = _yuzde(kova["dogru"], toplam)
        sinif_cift = sinif_kova.get((kova["kod"], kova["konu"].casefold()))
        sinif_yuzde = _yuzde(sinif_cift[0], sinif_cift[1]) if sinif_cift else None
        satirlar.append(
            {
                **kova,
                "soru": toplam,
                "yuzde": yuzde,
                "sinif_yuzde": sinif_yuzde,
                "net": DenemeBransSonucu.net_hesapla(kova["dogru"], kova["yanlis"]),
            }
        )

    gruplar: dict[str, dict] = {}
    for satir in satirlar:
        grup = gruplar.get(satir["kod"])
        if grup is None:
            grup = {"kod": satir["kod"], "ders": satir["ders"], "satirlar": []}
            gruplar[satir["kod"]] = grup
        grup["satirlar"].append(satir)
    for grup in gruplar.values():
        grup["satirlar"].sort(
            key=lambda s: (
                s["yuzde"] is None,
                s["yuzde"] if s["yuzde"] is not None else 0,
                s["konu"],
            )
        )
    konular = sorted(
        gruplar.values(),
        key=lambda g: (_DERS_SIRA.get(g["kod"], 50), g["ders"]),
    )

    kayiplar = []
    for satir in satirlar:
        kacirilan = satir["yanlis"] + satir["bos"]
        if kacirilan <= 0:
            continue
        kaynak = "yanlıştan" if satir["yanlis"] >= satir["bos"] else "boştan"
        kayiplar.append({**satir, "kaynak": kaynak, "kacirilan": kacirilan})
    kayiplar.sort(key=lambda s: (-s["kacirilan"], s["yuzde"] if s["yuzde"] is not None else 0))
    return konular, kayiplar[:5]


def _yuzde_ort(yuzdeler: list[int]) -> int | None:
    if not yuzdeler:
        return None
    return int(
        (Decimal(sum(yuzdeler)) / Decimal(len(yuzdeler))).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _net_renk(net: Decimal, en_yuksek: Decimal, en_dusuk: Decimal) -> str:
    """Sıralamada yüksek net yeşil, düştükçe kırmızıya gider."""
    if en_yuksek == en_dusuk:
        return _yuzde_renk(100)
    oran = (Decimal(net) - Decimal(en_dusuk)) / (Decimal(en_yuksek) - Decimal(en_dusuk))
    yuzde = int((oran * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return _yuzde_renk(yuzde)


def _yuzde_renk(yuzde: int | None) -> str:
    """Düşük toz kiremit, orta haki, yüksek toz yeşil."""
    if yuzde is None:
        return "#5c6b80"
    durak = (
        (30, 4, 48, 40),
        (55, 36, 26, 36),
        (80, 152, 40, 31),
    )
    y = min(80, max(30, int(yuzde)))
    for (alt, ah, ass, al), (ust, uh, us, ul) in zip(durak, durak[1:]):
        if y <= ust:
            pay = Decimal(y - alt) / Decimal(ust - alt)
            h = float(Decimal(ah) + (Decimal(uh) - Decimal(ah)) * pay)
            s = float(Decimal(ass) + (Decimal(us) - Decimal(ass)) * pay)
            l = float(Decimal(al) + (Decimal(ul) - Decimal(al)) * pay)
            return f"hsl({h:.0f} {s:.0f}% {l:.0f}%)"
    return "hsl(152 40% 31%)"


def cisa_sinif_raporu(talebeler: list[Talebe], deneme_ids: list[int], baslik: str) -> dict | None:
    """Seçilen denemelerin sınıf raporu. Doğru, yanlış ve boş öğrenci ortalamasıdır."""
    istenen = {int(i) for i in deneme_ids if str(i).isdigit() or isinstance(i, int)}
    talebe_ids = [t.id for t in talebeler]
    if not istenen or not talebe_ids:
        return None
    sonuclar = list(
        DenemeSonucu.objects.filter(
            talebe_id__in=talebe_ids,
            deneme_id__in=istenen,
            deneme__durum=DenemeSinavi.Durum.AKTIF,
        )
        .select_related("deneme", "talebe")
        .prefetch_related("brans_satirlari")
        .order_by("deneme__sinav_tarihi", "deneme_id", "talebe_id")
    )
    if not sonuclar:
        return None

    sinavlar = []
    gorulen_sinav: set[int] = set()
    for sonuc in sonuclar:
        if sonuc.deneme_id in gorulen_sinav:
            continue
        gorulen_sinav.add(sonuc.deneme_id)
        sinavlar.append(sonuc.deneme)

    adlar = {t.id: t.ad_soyad or "" for t in talebeler}
    toplam_net: dict[int, list[Decimal]] = defaultdict(list)
    brans: dict[int, dict[str, dict]] = defaultdict(dict)
    for sonuc in sonuclar:
        adlar[sonuc.talebe_id] = sonuc.talebe.ad_soyad or adlar.get(sonuc.talebe_id, "")
        toplam_net[sonuc.talebe_id].append(Decimal(sonuc.toplam_net or 0))
        for satir in sonuc.brans_satirlari.all():
            kova = brans[sonuc.talebe_id].get(satir.brans)
            if kova is None:
                kova = {"net": [], "d": [], "y": [], "b": [], "sinav": {}}
                brans[sonuc.talebe_id][satir.brans] = kova
            kova["net"].append(Decimal(satir.net or 0))
            kova["d"].append(Decimal(int(satir.dogru or 0)))
            kova["y"].append(Decimal(int(satir.yanlis or 0)))
            kova["b"].append(Decimal(int(satir.bos or 0)))
            kova["sinav"][sonuc.deneme_id] = Decimal(satir.net or 0)

    okunur = {
        "turkce": "Türkçe",
        "sosyal": "Sosyal Bilgiler",
        "din": "Din Kültürü",
        "ingilizce": "İngilizce",
        "matematik": "Matematik",
        "fen": "Fen Bilimleri",
    }
    dersler = []
    siralamalar = []
    son_id = sinavlar[-1].id if sinavlar else None
    onceki_id = sinavlar[-2].id if len(sinavlar) >= 2 else None
    for kod, _etiket in DENEME_KARNE_DERSLERI:
        ort_netler = []
        ort_dogru = []
        ort_yanlis = []
        ort_bos = []
        yuzdeler = []
        sira = []
        son_netler = []
        onceki_netler = []
        for tid, ders_map in brans.items():
            kova = ders_map.get(kod)
            if not kova or not kova["net"]:
                continue
            net = _ort(kova["net"])
            ort_netler.append(net)
            ort_dogru.append(_ort(kova["d"]))
            ort_yanlis.append(_ort(kova["y"]))
            ort_bos.append(_ort(kova["b"]))
            dogru_toplam = sum(kova["d"], Decimal("0"))
            yanlis_toplam = sum(kova["y"], Decimal("0"))
            bos_toplam = sum(kova["b"], Decimal("0"))
            yuzde = _yuzde(int(dogru_toplam), int(dogru_toplam + yanlis_toplam + bos_toplam))
            if yuzde is not None:
                yuzdeler.append(yuzde)
            sira.append({"ad": adlar.get(tid, ""), "net": net, "net_yazi": tr_ondalik(net)})
            if son_id in kova["sinav"]:
                son_netler.append(kova["sinav"][son_id])
            if onceki_id in kova["sinav"]:
                onceki_netler.append(kova["sinav"][onceki_id])
        if not ort_netler:
            continue
        sira.sort(key=lambda satir: (-satir["net"], satir["ad"]))
        if sira:
            en_yuksek = sira[0]["net"]
            en_dusuk = sira[-1]["net"]
            for satir in sira:
                satir["renk"] = _net_renk(satir["net"], en_yuksek, en_dusuk)
        cumle = "Tek deneme"
        yon = ""
        son = _ort(son_netler)
        onceki = _ort(onceki_netler)
        if son is not None and onceki is not None:
            cumle = f"Son deneme {tr_ondalik(son)} · önceki {tr_ondalik(onceki)}"
            if son > onceki:
                yon = "iyi"
            elif son < onceki:
                yon = "geri"
        dogru_yuzde = _yuzde_ort(yuzdeler)
        dersler.append(
            {
                "kod": kod,
                "ad": okunur.get(kod, kod),
                "net": tr_ondalik(_ort(ort_netler)),
                "dogru": tr_ondalik(_ort(ort_dogru)),
                "yanlis": tr_ondalik(_ort(ort_yanlis)),
                "bos": tr_ondalik(_ort(ort_bos)),
                "dogru_yuzde": dogru_yuzde,
                "renk": _yuzde_renk(dogru_yuzde),
                "cumle": cumle,
                "yon": yon,
            }
        )
        siralamalar.append({"kod": kod, "ad": okunur.get(kod, kod), "talebeler": sira})

    konu_ogrenci: dict[tuple, dict] = {}
    for kayit in DenemeSoruSonucu.objects.filter(
        deneme_id__in=gorulen_sinav,
        talebe_id__in=list(toplam_net),
    ).only("talebe_id", "ders_key", "ders_ad", "konu_ad", "sonuc"):
        konu = (kayit.konu_ad or "").strip() or "Belirtilmemiş"
        kod, ders_baslik = _satir_ders(kayit.ders_key, kayit.ders_ad, konu)
        anahtar = (kod, konu.casefold())
        kova = konu_ogrenci.get(anahtar)
        if kova is None:
            kova = {
                "kod": kod,
                "ders": ders_baslik,
                "konu": konu,
                "talebe": {},
            }
            konu_ogrenci[anahtar] = kova
        sayac = kova["talebe"].get(kayit.talebe_id)
        if sayac is None:
            sayac = {"dogru": 0, "yanlis": 0, "bos": 0}
            kova["talebe"][kayit.talebe_id] = sayac
        if kayit.sonuc == DenemeSoruSonucu.Sonuc.DOGRU:
            sayac["dogru"] += 1
        elif kayit.sonuc == DenemeSoruSonucu.Sonuc.YANLIS:
            sayac["yanlis"] += 1
        else:
            sayac["bos"] += 1

    sinif_n = len(toplam_net)
    satirlar = []
    for kova in konu_ogrenci.values():
        goren = len(kova["talebe"])
        dogru = yanlis = bos = 0
        zayif = 0
        for sayac in kova["talebe"].values():
            dogru += sayac["dogru"]
            yanlis += sayac["yanlis"]
            bos += sayac["bos"]
            kişisel = _yuzde(sayac["dogru"], sayac["dogru"] + sayac["yanlis"] + sayac["bos"])
            if kişisel is not None and kişisel < 50:
                zayif += 1
        yuzde = _yuzde(dogru, dogru + yanlis + bos)
        satirlar.append(
            {
                "kod": kova["kod"],
                "ders": kova["ders"],
                "konu": kova["konu"],
                "yuzde": yuzde,
                "renk": _yuzde_renk(yuzde),
                "zayif": zayif,
                "goren": goren,
                "yarisi": Decimal(goren) * 2 >= Decimal(sinif_n),
                "kaynak": "yanlıştan" if yanlis >= bos else "boştan",
                "kacirilan": yanlis + bos,
            }
        )

    kayiplar = [s for s in satirlar if s["yarisi"] and s["kacirilan"] > 0]
    kayiplar.sort(key=lambda s: (s["yuzde"] if s["yuzde"] is not None else 0, -s["kacirilan"], s["konu"]))
    kayiplar = kayiplar[:5]

    gruplar: dict[str, dict] = {}
    for satir in satirlar:
        grup = gruplar.get(satir["kod"])
        if grup is None:
            grup = {"kod": satir["kod"], "ders": satir["ders"], "satirlar": []}
            gruplar[satir["kod"]] = grup
        grup["satirlar"].append(satir)
    for grup in gruplar.values():
        grup["satirlar"].sort(
            key=lambda s: (s["yuzde"] is None, s["yuzde"] if s["yuzde"] is not None else 0, s["konu"])
        )
    konular = sorted(gruplar.values(), key=lambda g: (_DERS_SIRA.get(g["kod"], 50), g["ders"]))

    ogrenci_ort = [_ort(netler) for netler in toplam_net.values()]
    return {
        "baslik": baslik,
        "ogrenci": sinif_n,
        "deneme_sayisi": len(sinavlar),
        "baslangic": sinavlar[0].sinav_tarihi,
        "bitis": sinavlar[-1].sinav_tarihi,
        "ortalama_net": tr_ondalik(_ort(ogrenci_ort)),
        "dersler": dersler,
        "kayiplar": kayiplar,
        "konular": konular,
        "siralamalar": siralamalar,
    }
