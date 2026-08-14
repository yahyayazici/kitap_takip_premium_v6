"""Ölçme ve Değerlendirme Merkezi — sınav, soru zimmeti, doğrulama servisleri."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db import transaction
from django.db.models import Count, QuerySet

from takip.konu_destek_models import KonuKatalogu
from takip.ktt_models import KttSinav, KttSonucu
from takip.models import Ders, Talebe
from takip.olcme_models import (
    OlcumCevapAnahtari,
    OlcumIslemGecmisi,
    OlcumKazanim,
    OlcumSablonDers,
    OlcumSablonSoru,
    OlcumSinavDers,
    OlcumSinavSablon,
    OlcumSoru,
    OlcumTalebeCevap,
    OlcumUnite,
)
from takip.ktt_service import yetkili_ktt_sinavlari


def yetkili_olcme_sinavlari(user) -> QuerySet[KttSinav]:
    return yetkili_ktt_sinavlari(user)


def net_hesapla(dogru: int, yanlis: int, goturme_orani: int = 4) -> Decimal:
    net = Decimal(int(dogru or 0))
    if goturme_orani and int(yanlis or 0):
        net -= Decimal(int(yanlis)) / Decimal(goturme_orani)
    return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def sorulari_olustur(sinav: KttSinav, *, varsayilan_ders: Ders | None = None) -> list[OlcumSoru]:
    """Toplam soru sayısına göre bağımsız soru kayıtları üretir."""
    mevcut = sinav.olcme_sorulari.count()
    if mevcut >= sinav.soru_sayisi:
        return list(sinav.olcme_sorulari.order_by("soru_no"))

    ders = varsayilan_ders or sinav.ders
    sinav_ders = sinav.olcme_dersleri.filter(ders=ders).first()
    if not sinav_ders and ders:
        sinav_ders = OlcumSinavDers.objects.create(
            sinav=sinav,
            ders=ders,
            soru_sayisi=sinav.soru_sayisi,
            sira=1,
        )

    konu = sinav.konu_katalog
    yeni: list[OlcumSoru] = []
    for no in range(mevcut + 1, sinav.soru_sayisi + 1):
        soru = OlcumSoru.objects.create(
            sinav=sinav,
            soru_no=no,
            sinav_ders=sinav_ders,
            konu=konu if sinav.sinav_turu == KttSinav.SinavTuru.KTT else None,
        )
        soru.zimmet_durumu_guncelle(sinav.kazanim_zorunlu)
        if sinav.kitapcik_turleri:
            ilk_kitapcik = sinav.kitapcik_turleri.split(",")[0].strip() or "A"
            OlcumCevapAnahtari.objects.get_or_create(
                soru=soru,
                kitapcik=ilk_kitapcik,
                defaults={"dogru_secenek": "A"},
            )
        yeni.append(soru)
    return yeni


def ders_bloklari_kaydet(sinav: KttSinav, bloklar: list[dict]) -> None:
    """[{ders_id, bolum, soru_sayisi, katsayi, sira}, ...]"""
    sinav.olcme_dersleri.all().delete()
    toplam = 0
    for i, blok in enumerate(bloklar, start=1):
        ders_id = blok.get("ders_id")
        if not ders_id:
            continue
        ss = int(blok.get("soru_sayisi") or 0)
        toplam += ss
        OlcumSinavDers.objects.create(
            sinav=sinav,
            ders_id=ders_id,
            bolum=blok.get("bolum") or OlcumSinavDers.Bolum.GENEL,
            soru_sayisi=ss,
            katsayi=blok.get("katsayi") or 1,
            sira=blok.get("sira") or i,
        )
    if toplam and toplam != sinav.soru_sayisi:
        raise ValueError(f"Ders soru toplamı ({toplam}) sınav soru sayısı ({sinav.soru_sayisi}) ile uyuşmuyor.")


def sorulari_ders_bloklarina_dagit(sinav: KttSinav) -> None:
    """Ders blokları tanımlıysa soru numaralarını sırayla derslere bağlar."""
    bloklar = list(sinav.olcme_dersleri.order_by("sira", "id"))
    if not bloklar:
        return
    sorulari_olustur(sinav)
    sorular = list(sinav.olcme_sorulari.order_by("soru_no"))
    idx = 0
    for blok in bloklar:
        for _ in range(blok.soru_sayisi):
            if idx >= len(sorular):
                break
            s = sorular[idx]
            s.sinav_ders = blok
            s.bolum = blok.bolum
            s.save(update_fields=["sinav_ders", "bolum"])
            s.zimmet_durumu_guncelle(sinav.kazanim_zorunlu)
            idx += 1


def zimmet_ozet(sinav: KttSinav) -> dict[str, int]:
    qs = sinav.olcme_sorulari.all()
    toplam = qs.count() or sinav.soru_sayisi
    tamam = qs.filter(zimmet_tamam=True).count()
    ders_eksik = qs.filter(sinav_ders__isnull=True).count()
    konu_eksik = qs.filter(konu__isnull=True).count()
    kazanim_eksik = qs.filter(kazanim__isnull=True).count() if sinav.kazanim_zorunlu else 0
    return {
        "toplam": toplam,
        "tamam": tamam,
        "eksik": max(0, toplam - tamam),
        "ders_eksik": ders_eksik,
        "konu_eksik": konu_eksik,
        "kazanim_eksik": kazanim_eksik,
    }


def _islem_kaydet(
    *,
    sinav: KttSinav,
    soru: OlcumSoru | None,
    islem: str,
    kullanici,
    eski: dict | None = None,
    yeni: dict | None = None,
    aciklama: str = "",
) -> None:
    OlcumIslemGecmisi.objects.create(
        sinav=sinav,
        soru=soru,
        islem=islem,
        aciklama=aciklama,
        eski_deger=eski or {},
        yeni_deger=yeni or {},
        kullanici=kullanici,
    )


@transaction.atomic
def soru_zimmet_guncelle(
    soru: OlcumSoru,
    *,
    kullanici,
    sinav_ders_id: int | None = None,
    unite_id: int | None = None,
    konu_id: int | None = None,
    kazanim_id: int | None = None,
    beceri_turu: str = "",
    zorluk: str = "",
    ogretmen_notu: str | None = None,
) -> OlcumSoru:
    eski = {
        "sinav_ders_id": soru.sinav_ders_id,
        "unite_id": soru.unite_id,
        "konu_id": soru.konu_id,
        "kazanim_id": soru.kazanim_id,
        "beceri_turu": soru.beceri_turu,
        "zorluk": soru.zorluk,
    }
    if sinav_ders_id is not None:
        soru.sinav_ders_id = sinav_ders_id or None
    if unite_id is not None:
        soru.unite_id = unite_id or None
    if konu_id is not None:
        soru.konu_id = konu_id or None
        if konu_id and not unite_id:
            konu = KonuKatalogu.objects.filter(pk=konu_id).first()
            if konu and konu.unite_id:
                soru.unite_id = konu.unite_id
    if kazanim_id is not None:
        soru.kazanim_id = kazanim_id or None
    if beceri_turu is not None:
        soru.beceri_turu = beceri_turu or ""
    if zorluk is not None:
        soru.zorluk = zorluk or ""
    if ogretmen_notu is not None:
        soru.ogretmen_notu = ogretmen_notu
    soru.save()
    soru.zimmet_durumu_guncelle(soru.sinav.kazanim_zorunlu)
    _islem_kaydet(
        sinav=soru.sinav,
        soru=soru,
        islem="zimmet_guncellendi",
        kullanici=kullanici,
        eski=eski,
        yeni={
            "sinav_ders_id": soru.sinav_ders_id,
            "unite_id": soru.unite_id,
            "konu_id": soru.konu_id,
            "kazanim_id": soru.kazanim_id,
            "beceri_turu": soru.beceri_turu,
            "zorluk": soru.zorluk,
        },
    )
    return soru


@transaction.atomic
def toplu_zimmet_guncelle(
    sinav: KttSinav,
    soru_ids: list[int],
    *,
    kullanici,
    **alanlar,
) -> int:
    """Çoklu seçim — her soru için ayrı kayıt güncellenir."""
    sayac = 0
    for sid in soru_ids:
        soru = OlcumSoru.objects.filter(pk=sid, sinav=sinav).first()
        if not soru:
            continue
        soru_zimmet_guncelle(soru, kullanici=kullanici, **alanlar)
        sayac += 1
    return sayac


def anahtar_satir_isle(sinav: KttSinav, kitapcik: str, metin: str) -> int:
    """Tek satır cevap anahtarı: ABCD..."""
    temiz = "".join(ch for ch in metin.upper() if ch in "ABCDE")
    sorulari_olustur(sinav)
    sorular = list(sinav.olcme_sorulari.order_by("soru_no"))
    guncellenen = 0
    for soru, secenek in zip(sorular, temiz):
        anahtar, _ = OlcumCevapAnahtari.objects.get_or_create(
            soru=soru,
            kitapcik=kitapcik,
            defaults={"dogru_secenek": secenek},
        )
        if anahtar.dogru_secenek != secenek:
            anahtar.dogru_secenek = secenek
            anahtar.save(update_fields=["dogru_secenek"])
        guncellenen += 1
    return guncellenen


def sinav_dogrulama(sinav: KttSinav) -> list[dict[str, Any]]:
    """Yayın öncesi eksikler listesi."""
    hatalar: list[dict[str, Any]] = []
    sorulari_olustur(sinav)
    ozet = zimmet_ozet(sinav)

    if ozet["toplam"] != sinav.soru_sayisi:
        hatalar.append(
            {
                "kod": "soru_sayisi",
                "mesaj": f"Soru kaydı ({ozet['toplam']}) ile hedef ({sinav.soru_sayisi}) uyuşmuyor.",
            }
        )

    eksik_anahtar = 0
    kitapciklar = [k.strip() for k in sinav.kitapcik_turleri.split(",") if k.strip()]
    for kit in kitapciklar:
        eksik = sinav.olcme_sorulari.exclude(
            cevap_anahtarlari__kitapcik=kit,
        ).count()
        if eksik:
            hatalar.append(
                {
                    "kod": "anahtar",
                    "mesaj": f"{kit} kitapçığında {eksik} sorunun cevap anahtarı eksik.",
                }
            )

    if ozet["ders_eksik"]:
        hatalar.append(
            {
                "kod": "ders",
                "mesaj": f"{ozet['ders_eksik']} soru derse zimmetlenmemiş.",
                "soru_filter": "ders_eksik",
            }
        )
    if ozet["konu_eksik"]:
        hatalar.append(
            {
                "kod": "konu",
                "mesaj": f"{ozet['konu_eksik']} sorunun konusu eksik.",
                "soru_filter": "konu_eksik",
            }
        )
    if ozet["kazanim_eksik"]:
        hatalar.append(
            {
                "kod": "kazanim",
                "mesaj": f"{ozet['kazanim_eksik']} sorunun kazanımı eksik.",
                "soru_filter": "kazanim_eksik",
            }
        )

    if not sinav.hedef_siniflar and not sinav.sinif_seviyesi:
        hatalar.append({"kod": "sinif", "mesaj": "Sınıf veya hedef grup seçilmemiş."})

    return hatalar


YAYIN_KRITIK_KODLAR = frozenset({"soru_sayisi", "anahtar", "sinif"})


def yayin_kontrolu(sinav: KttSinav) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Kritik (yayın engeli) ve uyarı (yayınlanır ama bildirilir) eksikler."""
    hatalar = sinav_dogrulama(sinav)
    kritik = [h for h in hatalar if h["kod"] in YAYIN_KRITIK_KODLAR]
    uyari = [h for h in hatalar if h["kod"] not in YAYIN_KRITIK_KODLAR]
    return kritik, uyari


def yayinlanabilir_mi(sinav: KttSinav) -> tuple[bool, list[str]]:
    kritik, uyari = yayin_kontrolu(sinav)
    if kritik:
        return False, [h["mesaj"] for h in kritik]
    if not KttSonucu.objects.filter(ktt=sinav).exists():
        return False, ["Yayınlamak için en az bir talebe sonucu gerekli."]
    return True, [h["mesaj"] for h in uyari]


def konu_ara(sinif: str, brans: str, q: str = "", limit: int = 20) -> list[dict]:
    qs = KonuKatalogu.objects.filter(aktif=True, sinif_seviyesi=sinif)
    if brans:
        qs = qs.filter(brans=brans)
    if q:
        qs = qs.filter(konu_ad__icontains=q)
    return [
        {
            "id": k.id,
            "konu_ad": k.konu_ad,
            "brans": k.brans,
            "brans_etiket": k.brans_etiket,
            "unite_id": k.unite_id,
            "unite_ad": k.unite.unite_ad if k.unite_id else "",
        }
        for k in qs.select_related("unite")[:limit]
    ]


def kazanim_ara(konu_id: int, q: str = "", limit: int = 20) -> list[dict]:
    qs = OlcumKazanim.objects.filter(aktif=True, konu_id=konu_id)
    if q:
        qs = qs.filter(kazanim_ad__icontains=q)
    return [{"id": k.id, "kazanim_ad": k.kazanim_ad, "kod": k.kod} for k in qs[:limit]]


def sablondan_sinav_kopyala(sinav: KttSinav, sablon: OlcumSinavSablon, kullanici) -> None:
    """Şablondaki soru zimmetlerini yeni sınava bağımsız kopyalar."""
    sorulari_olustur(sinav)
    sablon_sorular = list(sablon.sorular.select_related("ders", "unite", "konu", "kazanim"))
    hedef = {s.soru_no: s for s in sinav.olcme_sorulari.all()}
    for ss in sablon_sorular:
        soru = hedef.get(ss.soru_no)
        if not soru:
            continue
        ders_blok = None
        if ss.ders_id:
            ders_blok, _ = OlcumSinavDers.objects.get_or_create(
                sinav=sinav,
                ders_id=ss.ders_id,
                defaults={"soru_sayisi": 0, "sira": ss.soru_no, "bolum": ss.bolum},
            )
        soru_zimmet_guncelle(
            soru,
            kullanici=kullanici,
            sinav_ders_id=ders_blok.id if ders_blok else None,
            unite_id=ss.unite_id,
            konu_id=ss.konu_id,
            kazanim_id=ss.kazanim_id,
            beceri_turu=ss.beceri_turu,
            zorluk=ss.zorluk,
        )
        if ss.dogru_secenek:
            sec = ss.dogru_secenek.upper()[:1]
            if sec in "ABCDE":
                OlcumCevapAnahtari.objects.update_or_create(
                    soru=soru,
                    kitapcik="A",
                    defaults={"dogru_secenek": sec},
                )


@transaction.atomic
def sablondan_sinav_olustur(
    sablon: OlcumSinavSablon,
    *,
    ad: str,
    sinav_tarihi,
    ders: Ders,
    sinif_etiketleri: list[str],
    kullanici,
    etut_hocasi=None,
) -> KttSinav:
    """Şablondan yeni sınav oluşturur; ders blokları ve zimmetleri kopyalar."""
    from takip.ktt_service import hedef_siniflar_kaydet

    sinav = KttSinav.objects.create(
        ad=ad.strip() or sablon.ad,
        ders=ders,
        sinif_seviyesi=sablon.sinif_seviyesi,
        soru_sayisi=sablon.soru_sayisi,
        secenek_sayisi=sablon.secenek_sayisi,
        sinav_tarihi=sinav_tarihi,
        sinav_turu=sablon.sinav_turu,
        durum=KttSinav.SinavDurum.ZIMMETLEME,
        etut_hocasi=etut_hocasi,
        olusturan=kullanici,
        aciklama=sablon.aciklama or "",
        kitapcik_turleri="A",
    )
    if sinif_etiketleri:
        hedef_siniflar_kaydet(sinav, sinif_etiketleri)

    sablon_dersler = list(sablon.dersler.select_related("ders").order_by("sira"))
    if sablon_dersler:
        ders_bloklari_kaydet(
            sinav,
            [
                {
                    "ders_id": sd.ders_id,
                    "bolum": sd.bolum,
                    "soru_sayisi": sd.soru_sayisi,
                    "katsayi": sd.katsayi,
                    "sira": sd.sira,
                }
                for sd in sablon_dersler
            ],
        )
    sorulari_olustur(sinav, varsayilan_ders=ders)
    if sablon_dersler:
        sorulari_ders_bloklarina_dagit(sinav)
    sablondan_sinav_kopyala(sinav, sablon, kullanici)
    return sinav


def mevcut_ktt_backfill(sinav: KttSinav) -> int:
    """Mevcut KTT kaydı için soru satırları üretir (idempotent)."""
    once = sinav.olcme_sorulari.count()
    sorulari_olustur(sinav, varsayilan_ders=sinav.ders)
    if sinav.konu_katalog_id:
        sinav.olcme_sorulari.filter(konu__isnull=True).update(konu_id=sinav.konu_katalog_id)
    for soru in sinav.olcme_sorulari.all():
        soru.zimmet_durumu_guncelle(sinav.kazanim_zorunlu)
    return sinav.olcme_sorulari.count() - once


def sinav_durum_guncelle(sinav: KttSinav, yeni_durum: str, kullanici, aciklama: str = "") -> None:
    eski = sinav.durum
    sinav.durum = yeni_durum
    update_fields = ["durum", "guncellenme"]
    if yeni_durum == KttSinav.SinavDurum.YAYINLANDI and not sinav.veliye_goster:
        sinav.veliye_goster = True
        update_fields.append("veliye_goster")
    sinav.save(update_fields=update_fields)
    _islem_kaydet(
        sinav=sinav,
        soru=None,
        islem="durum_degisti",
        kullanici=kullanici,
        eski={"durum": eski},
        yeni={"durum": yeni_durum},
        aciklama=aciklama,
    )


def _dogru_secenek(soru: OlcumSoru, kitapcik: str = "A") -> str | None:
    anahtar = soru.cevap_anahtarlari.filter(kitapcik=kitapcik).first()
    if not anahtar or anahtar.iptal:
        return None
    return anahtar.dogru_secenek


@transaction.atomic
def talebe_cevaplari_kaydet(
    sinav: KttSinav,
    talebe: Talebe,
    cevaplar: dict[int, str],
    *,
    kitapcik: str = "A",
    kullanici,
) -> KttSonucu:
    """cevaplar: {soru_no: A|B|C|D|E|BOS}"""
    sorular = {s.soru_no: s for s in sinav.olcme_sorulari.all()}
    for soru_no, secim in cevaplar.items():
        soru = sorular.get(int(soru_no))
        if not soru:
            continue
        secim = (secim or "BOS").upper()
        if secim not in {"A", "B", "C", "D", "E", "BOS"}:
            continue
        dogru_mu = None
        anahtar = _dogru_secenek(soru, kitapcik)
        if secim == "BOS":
            pass
        elif anahtar:
            dogru_mu = secim == anahtar
        OlcumTalebeCevap.objects.update_or_create(
            sinav=sinav,
            talebe=talebe,
            soru=soru,
            defaults={
                "secilen": secim,
                "dogru_mu": dogru_mu,
                "kitapcik": kitapcik,
            },
        )

    kayitli = OlcumTalebeCevap.objects.filter(sinav=sinav, talebe=talebe)
    dogru = kayitli.filter(dogru_mu=True).count()
    yanlis = kayitli.filter(dogru_mu=False).count()
    bos = kayitli.filter(secilen="BOS").count()
    if dogru + yanlis + bos != sinav.soru_sayisi:
        return None

    sonuc, _ = KttSonucu.objects.update_or_create(
        ktt=sinav,
        talebe=talebe,
        defaults={
            "dogru": dogru,
            "yanlis": yanlis,
            "bos": bos,
            "kaydeden": kullanici,
        },
    )
    from takip.ktt_akilli_service import ktt_sonuc_sonrasi_isle

    ktt_sonuc_sonrasi_isle(sonuc)
    olcme_sonuc_sonrasi_konu_eksikleri(sonuc)
    return sonuc


def satir_cevap_parcala(metin: str, soru_sayisi: int) -> dict[int, str]:
    temiz = "".join(ch.upper() if ch.upper() in "ABCDE" else " " for ch in metin)
    parcalar = [p for p in temiz.split() if p]
    if len(parcalar) == 1 and len(parcalar[0]) >= soru_sayisi:
        parcalar = list(parcalar[0][:soru_sayisi])
    return {i + 1: (p if p in "ABCDE" else "BOS") for i, p in enumerate(parcalar[:soru_sayisi])}


@transaction.atomic
def sinav_sablon_kaydet(sinav: KttSinav, ad: str, kullanici) -> OlcumSinavSablon:
    sablon = OlcumSinavSablon.objects.create(
        ad=ad.strip() or sinav.ad,
        sinav_turu=sinav.sinav_turu,
        sinif_seviyesi=sinav.sinif_seviyesi,
        soru_sayisi=sinav.soru_sayisi,
        secenek_sayisi=sinav.secenek_sayisi,
        aciklama=sinav.aciklama,
        olusturan=kullanici,
    )
    for d in sinav.olcme_dersleri.select_related("ders"):
        OlcumSablonDers.objects.create(
            sablon=sablon,
            bolum=d.bolum,
            ders=d.ders,
            soru_sayisi=d.soru_sayisi,
            katsayi=d.katsayi,
            sira=d.sira,
        )
    for soru in sinav.olcme_sorulari.select_related("sinav_ders", "unite", "konu", "kazanim"):
        anahtar = soru.cevap_anahtarlari.filter(kitapcik="A").first()
        OlcumSablonSoru.objects.create(
            sablon=sablon,
            soru_no=soru.soru_no,
            bolum=soru.bolum,
            ders=soru.sinav_ders.ders if soru.sinav_ders_id else None,
            unite=soru.unite,
            konu=soru.konu,
            kazanim=soru.kazanim,
            beceri_turu=soru.beceri_turu,
            zorluk=soru.zorluk,
            dogru_secenek=anahtar.dogru_secenek if anahtar else "",
        )
    return sablon


def sinav_konu_analizi(sinav: KttSinav) -> list[dict]:
    """Soru zimmetlerinden konu bazlı analiz."""
    sorular = list(
        sinav.olcme_sorulari.filter(konu__isnull=False).select_related("konu", "kazanim")
    )
    if not sorular:
        return []

    cevaplar = OlcumTalebeCevap.objects.filter(sinav=sinav).select_related("soru")
    by_konu: dict[int, dict] = {}

    for soru in sorular:
        kid = soru.konu_id
        kayit = by_konu.setdefault(
            kid,
            {
                "konu_id": kid,
                "konu_ad": soru.konu.konu_ad,
                "brans_etiket": soru.konu.brans_etiket,
                "soru_sayisi": 0,
                "dogru": 0,
                "yanlis": 0,
                "bos": 0,
                "soru_nolar": [],
            },
        )
        kayit["soru_sayisi"] += 1
        kayit["soru_nolar"].append(soru.soru_no)

    for c in cevaplar:
        if not c.soru.konu_id:
            continue
        kayit = by_konu.get(c.soru.konu_id)
        if not kayit:
            continue
        if c.secilen == "BOS":
            kayit["bos"] += 1
        elif c.dogru_mu:
            kayit["dogru"] += 1
        elif c.dogru_mu is False:
            kayit["yanlis"] += 1

    sonuc = []
    for kayit in by_konu.values():
        toplam_cevap = kayit["dogru"] + kayit["yanlis"] + kayit["bos"]
        basari = int(round(100 * kayit["dogru"] / toplam_cevap)) if toplam_cevap else 0
        kayit["basari_yuzde"] = basari
        kayit["kanit_dusuk"] = kayit["soru_sayisi"] == 1
        sonuc.append(kayit)
    return sorted(sonuc, key=lambda x: (x["basari_yuzde"], x["konu_ad"]))


def konu_havuzu_listesi(sinif: str = "", brans: str = "") -> QuerySet[KonuKatalogu]:
    qs = KonuKatalogu.objects.filter(aktif=True).select_related("unite")
    if sinif:
        qs = qs.filter(sinif_seviyesi=sinif)
    if brans:
        qs = qs.filter(brans=brans)
    return qs.order_by("sinif_seviyesi", "brans", "konu_ad")


def talebe_kimlik_eslestir(talebeler: list[Talebe] | QuerySet[Talebe], kimlik: str) -> Talebe | None:
    """Talebe no, pk veya ad soyad ile eşleştirir."""
    kimlik = (kimlik or "").strip()
    if not kimlik:
        return None
    liste = list(talebeler)
    for talebe in liste:
        if talebe.talebe_no and str(talebe.talebe_no) == kimlik:
            return talebe
    if kimlik.isdigit():
        hedef_pk = int(kimlik)
        for talebe in liste:
            if talebe.pk == hedef_pk:
                return talebe
    kimlik_lower = kimlik.lower()
    tam = [t for t in liste if t.ad_soyad.lower() == kimlik_lower]
    if len(tam) == 1:
        return tam[0]
    kismi = [t for t in liste if kimlik_lower in t.ad_soyad.lower()]
    if len(kismi) == 1:
        return kismi[0]
    return None


def optik_satirlar_parcala(metin: str, soru_sayisi: int) -> list[tuple[str, dict[int, str]]]:
    """Her satır: kimlik|cevaplar veya kimlik cevaplar."""
    satirlar: list[tuple[str, dict[int, str]]] = []
    for ham in metin.splitlines():
        line = ham.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            kimlik, cevap_metin = line.split("|", 1)
        elif "\t" in line:
            kimlik, cevap_metin = line.split("\t", 1)
        else:
            parcalar = line.split(None, 1)
            if len(parcalar) < 2:
                continue
            kimlik, cevap_metin = parcalar
        cevaplar = satir_cevap_parcala(cevap_metin, soru_sayisi)
        for no in range(1, soru_sayisi + 1):
            cevaplar.setdefault(no, "BOS")
        satirlar.append((kimlik.strip(), cevaplar))
    return satirlar


@transaction.atomic
def toplu_optik_kaydet(
    sinav: KttSinav,
    talebeler: list[Talebe] | QuerySet[Talebe],
    satirlar: list[tuple[str, dict[int, str]]],
    *,
    kullanici,
    kitapcik: str = "A",
) -> dict[str, Any]:
    kaydedilen = 0
    eksik = 0
    hatalar: list[str] = []
    for kimlik, cevaplar in satirlar:
        talebe = talebe_kimlik_eslestir(talebeler, kimlik)
        if not talebe:
            hatalar.append(f"Eşleşmedi: {kimlik}")
            continue
        sonuc = talebe_cevaplari_kaydet(
            sinav,
            talebe,
            cevaplar,
            kitapcik=kitapcik,
            kullanici=kullanici,
        )
        if sonuc:
            kaydedilen += 1
        else:
            eksik += 1
    return {"kaydedilen": kaydedilen, "eksik": eksik, "hatalar": hatalar}


def sinav_sonuc_ozet(sinav: KttSinav, talebeler: list[Talebe] | QuerySet[Talebe]) -> list[dict]:
    talebe_list = list(talebeler)
    if not talebe_list:
        return []
    ids = [t.pk for t in talebe_list]
    sonuc_map = {
        s.talebe_id: s
        for s in KttSonucu.objects.filter(ktt=sinav, talebe_id__in=ids)
    }
    cevap_map = dict(
        OlcumTalebeCevap.objects.filter(sinav=sinav, talebe_id__in=ids)
        .values("talebe_id")
        .annotate(adet=Count("id"))
        .values_list("talebe_id", "adet")
    )
    ozet = []
    for talebe in talebe_list:
        sonuc = sonuc_map.get(talebe.pk)
        cevap_adet = int(cevap_map.get(talebe.pk, 0))
        ozet.append(
            {
                "talebe": talebe,
                "cevap_adet": cevap_adet,
                "tamam": cevap_adet >= sinav.soru_sayisi and sonuc is not None,
                "kismi": 0 < cevap_adet < sinav.soru_sayisi,
                "sonuc": sonuc,
                "dogru": int(sonuc.dogru) if sonuc else None,
                "yanlis": int(sonuc.yanlis) if sonuc else None,
                "bos": int(sonuc.bos) if sonuc else None,
                "net": sonuc.net if sonuc else None,
            }
        )
    return ozet


def sinav_kazanim_analizi(sinav: KttSinav) -> list[dict]:
    sorular = list(
        sinav.olcme_sorulari.filter(kazanim__isnull=False).select_related("konu", "kazanim")
    )
    if not sorular:
        return []

    cevaplar = OlcumTalebeCevap.objects.filter(sinav=sinav).select_related("soru__kazanim")
    by_kazanim: dict[int, dict] = {}

    for soru in sorular:
        kid = soru.kazanim_id
        kayit = by_kazanim.setdefault(
            kid,
            {
                "kazanim_id": kid,
                "kazanim_ad": soru.kazanim.kazanim_ad,
                "konu_ad": soru.konu.konu_ad if soru.konu_id else "",
                "soru_sayisi": 0,
                "dogru": 0,
                "yanlis": 0,
                "bos": 0,
                "soru_nolar": [],
            },
        )
        kayit["soru_sayisi"] += 1
        kayit["soru_nolar"].append(soru.soru_no)

    for c in cevaplar:
        if not c.soru.kazanim_id:
            continue
        kayit = by_kazanim.get(c.soru.kazanim_id)
        if not kayit:
            continue
        if c.secilen == "BOS":
            kayit["bos"] += 1
        elif c.dogru_mu:
            kayit["dogru"] += 1
        elif c.dogru_mu is False:
            kayit["yanlis"] += 1

    sonuc = []
    for kayit in by_kazanim.values():
        toplam_cevap = kayit["dogru"] + kayit["yanlis"] + kayit["bos"]
        basari = int(round(100 * kayit["dogru"] / toplam_cevap)) if toplam_cevap else 0
        kayit["basari_yuzde"] = basari
        kayit["kanit_dusuk"] = kayit["soru_sayisi"] == 1
        sonuc.append(kayit)
    return sorted(sonuc, key=lambda x: (x["basari_yuzde"], x["kazanim_ad"]))


def olcme_sonuc_sonrasi_konu_eksikleri(sonuc: KttSonucu) -> int:
    """Soru bazlı yanlışlardan konu eksiklerini KTT akıllı takibe yansıtır."""
    from decimal import Decimal

    from takip.konu_destek_models import TalebeKonuEksigi
    from takip.ktt_akilli_service import _zayif_esik

    sinav = sonuc.ktt
    cevaplar = OlcumTalebeCevap.objects.filter(
        sinav=sinav,
        talebe=sonuc.talebe,
        soru__konu__isnull=False,
    ).select_related("soru__konu")
    if not cevaplar.exists():
        return 0

    zayif = float(_zayif_esik())
    guncellenen = 0
    by_konu: dict[int, dict] = {}
    for cevap in cevaplar:
        kid = cevap.soru.konu_id
        veri = by_konu.setdefault(
            kid,
            {"konu": cevap.soru.konu, "dogru": 0, "toplam": 0},
        )
        veri["toplam"] += 1
        if cevap.dogru_mu:
            veri["dogru"] += 1

    for veri in by_konu.values():
        basari = 100 * veri["dogru"] / veri["toplam"]
        puan = Decimal(str(round(basari, 2)))
        konu = veri["konu"]
        eksik = TalebeKonuEksigi.objects.filter(
            talebe=sonuc.talebe,
            konu=konu,
            kaynak=TalebeKonuEksigi.Kaynak.KTT,
        ).first()
        if basari < zayif:
            oncelik = max(10, 100 - int(basari))
            if eksik:
                eksik.skor = puan
                eksik.oncelik = oncelik
                eksik.tespit_tarihi = sinav.sinav_tarihi
                eksik.son_ktt_sonuc = sonuc
                eksik.cozuldu = False
                if eksik.mudahale_durumu in {"", "kapandi"}:
                    eksik.mudahale_durumu = "bekliyor"
                eksik.save()
            else:
                TalebeKonuEksigi.objects.create(
                    talebe=sonuc.talebe,
                    konu=konu,
                    kaynak=TalebeKonuEksigi.Kaynak.KTT,
                    skor=puan,
                    oncelik=oncelik,
                    tespit_tarihi=sinav.sinav_tarihi,
                    son_ktt_sonuc=sonuc,
                    mudahale_durumu="bekliyor",
                )
            guncellenen += 1
        elif eksik and not eksik.cozuldu and basari >= zayif:
            eksik.cozuldu = True
            eksik.mudahale_durumu = "kapandi"
            eksik.kapanma_skor = puan
            eksik.save(update_fields=["cozuldu", "mudahale_durumu", "kapanma_skor"])
            guncellenen += 1
    return guncellenen


def zayif_konulari_etut_planina_aktar(
    user,
    sinav: KttSinav,
    *,
    max_konu: int = 5,
    esik: float | None = None,
) -> dict[str, Any]:
    """Sınav konu analizindeki zayıf konuları bu haftanın etüt planına boş slotlara yazar."""
    from takip.etut_plan_service import (
        faaliyet_ata,
        faaliyet_havuzu,
        hocanin_saat_bloklari,
        mevcut_hafta_plani,
        plan_grid_verisi,
        plan_olustur,
        plan_olusturabilir,
        saat_bloklari_otomatik_olustur,
    )
    from takip.ktt_akilli_service import _zayif_esik
    from takip.permissions.service import can
    from takip.user_helpers import etut_hocasi_for_user

    if not can(user, "etut_plani", "edit"):
        return {"hata": "Etüt planı düzenleme yetkiniz yok.", "atanan": 0}

    if not sinav.talebe_cevaplari.exists():
        return {"hata": "Soru bazlı sonuç girilmedi.", "atanan": 0}

    hoca = sinav.etut_hocasi or etut_hocasi_for_user(user)
    if not hoca:
        return {"hata": "Etüt hocası bulunamadı.", "atanan": 0}

    esik_deger = float(esik if esik is not None else _zayif_esik())
    analiz = sinav_konu_analizi(sinav)
    zayiflar = [
        kayit
        for kayit in analiz
        if kayit["basari_yuzde"] < esik_deger
        and kayit["dogru"] + kayit["yanlis"] + kayit["bos"] > 0
    ]
    zayiflar.sort(key=lambda x: (x["basari_yuzde"], x["konu_ad"]))
    zayiflar = zayiflar[:max_konu]

    if not zayiflar:
        return {
            "hata": None,
            "atanan": 0,
            "zayif_sayisi": 0,
            "mesaj": f"Eşik altında zayıf konu yok (<%{int(esik_deger)}).",
        }

    if not plan_olusturabilir(user, hoca):
        return {"hata": "Bu grup için etüt planı oluşturma yetkiniz yok.", "atanan": 0}

    plan = mevcut_hafta_plani(user, hoca) or plan_olustur(user, hoca)

    if not hocanin_saat_bloklari(hoca).exists():
        saat_bloklari_otomatik_olustur(hoca)

    grid = plan_grid_verisi(plan, hoca)
    bos_hucreler = [
        hucre
        for satir in grid["satirlar"]
        for hucre in satir["hucreler"]
        if hucre.get("bos") and hucre.get("blok_id")
    ]

    havuz_kart = next(
        (kart for kart in faaliyet_havuzu(user, hoca) if "konu" in kart.baslik.lower()),
        None,
    )

    atanan = 0
    konu_adlari: list[str] = []
    for konu, hucre in zip(zayiflar, bos_hucreler):
        baslik = f"Konu Tekrarı: {konu['konu_ad'][:48]}"
        faaliyet_ata(
            plan,
            saat_bloku_id=hucre["blok_id"],
            havuz_id=havuz_kart.pk if havuz_kart else None,
            baslik=baslik,
            aciklama=f"{sinav.ad} · başarı %{konu['basari_yuzde']}",
            hedef=f"{konu['soru_sayisi']} soru",
            renk="#fef9c3",
        )
        atanan += 1
        konu_adlari.append(konu["konu_ad"])

    return {
        "hata": None,
        "atanan": atanan,
        "zayif_sayisi": len(zayiflar),
        "plan_id": plan.pk,
        "konu_adlari": konu_adlari,
        "bos_yetersiz": len(zayiflar) > len(bos_hucreler),
    }
