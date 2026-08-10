"""Konu destek merkezi — eksik konu analizi, video ve test servisleri."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django.utils import timezone
from django.utils.timezone import localdate

from takip.deneme_models import DenemeBransSonucu
from takip.deneme_service import talebe_deneme_sonuclari
from takip.konu_destek_models import (
    KonuEgitimVideosu,
    KonuKatalogu,
    KonuSorusu,
    KonuTestCevabi,
    KonuTestOturu,
    KonuVideoIzleme,
    TalebeKonuEksigi,
)
from takip.models import KttSonucu, Talebe


ZAYIF_KTT_PUAN = Decimal("70")
ZAYIF_DENEME_ORAN = Decimal("45")

# Branş + video türüne göre panel içi oynatılabilir örnek videolar (oEmbed doğrulanmış ID’ler)
BRANS_VARSAYILAN_YOUTUBE: dict[str, dict[str, str]] = {
    "din": {
        KonuEgitimVideosu.Tur.ANLATIM: "YDFthrRPKhA",
        KonuEgitimVideosu.Tur.COZUM: "P_sBqAcMZqo",
        KonuEgitimVideosu.Tur.TEKRAR: "G719VamMJnQ",
    },
    "matematik": {
        KonuEgitimVideosu.Tur.ANLATIM: "4TmlPkb9VXU",  # Oran ve Orantı
        KonuEgitimVideosu.Tur.COZUM: "tqWCEmlqZYI",  # Kesirler
        KonuEgitimVideosu.Tur.TEKRAR: "ERYDkz8Ts64",
    },
    "turkce": {
        # Sınıf dışı / lise videosu bağlanmaz; arama sorgusu kullanılır
        KonuEgitimVideosu.Tur.ANLATIM: "",
        KonuEgitimVideosu.Tur.COZUM: "",
        KonuEgitimVideosu.Tur.TEKRAR: "",
    },
    "fen": {
        KonuEgitimVideosu.Tur.ANLATIM: "yZ2mgHxk1JM",  # Madde ve ısı
        KonuEgitimVideosu.Tur.COZUM: "yZ2mgHxk1JM",
        KonuEgitimVideosu.Tur.TEKRAR: "yZ2mgHxk1JM",
    },
    "sosyal": {
        KonuEgitimVideosu.Tur.ANLATIM: "YDFthrRPKhA",
        KonuEgitimVideosu.Tur.COZUM: "YDFthrRPKhA",
        KonuEgitimVideosu.Tur.TEKRAR: "YDFthrRPKhA",
    },
    "ingilizce": {
        KonuEgitimVideosu.Tur.ANLATIM: "gnImk-2WEyw",
        KonuEgitimVideosu.Tur.COZUM: "gnImk-2WEyw",
        KonuEgitimVideosu.Tur.TEKRAR: "gnImk-2WEyw",
    },
}

KONU_ANAHTAR_YOUTUBE: dict[str, str] = {
    "namaz": "P_sBqAcMZqo",
    "vakit": "P_sBqAcMZqo",
    "ibadet": "YDFthrRPKhA",
    "oran": "4TmlPkb9VXU",
    "orantı": "4TmlPkb9VXU",
    "oranti": "4TmlPkb9VXU",
    "kesir": "tqWCEmlqZYI",
    "madde": "yZ2mgHxk1JM",
}


# Sınıf + branş (+ konu anahtarı) — yanlış sınıf videosu vermemek için
# Bilinmeyen eşleşmede boş dönülür; panel arama sorgusu kullanılır.
SINIF_BRANS_YOUTUBE: dict[str, dict[str, dict[str, str]]] = {
    "5": {
        "matematik": {
            "kesir": "tqWCEmlqZYI",
            "_": "tqWCEmlqZYI",
        },
        "fen": {
            "madde": "yZ2mgHxk1JM",
            "ısı": "yZ2mgHxk1JM",
            "_": "yZ2mgHxk1JM",
        },
        # 9. sınıf edebiyat videosu ASLA bağlanmaz; ID boş → sınıf+konu araması
        "turkce": {},
    },
    "7": {
        "matematik": {
            "oran": "4TmlPkb9VXU",
            "orantı": "4TmlPkb9VXU",
            "oranti": "4TmlPkb9VXU",
            "_": "4TmlPkb9VXU",
        },
    },
    "8": {
        "matematik": {
            "üs": "4TmlPkb9VXU",
            "_": "ERYDkz8Ts64",
        },
    },
}

# Yanlış seviye / demo bozuk ID’ler — temizlenir
YASAK_YOUTUBE_ID = frozenset(
    {
        "kWOT9tF8yes",
        "xGcfBRkJS-E",
        "Hk9j9L0cQ0E",
        "jNQXAC9IVRw",
        "gnImk-2WEyw",  # 9. sınıf edebiyat — 5. sınıfa verilmez
    }
)


def _varsayilan_youtube_id(konu: KonuKatalogu, tur: str) -> str:
    sinif = str(konu.sinif_seviyesi or "").strip()
    konu_lower = (konu.konu_ad or "").casefold()

    sinif_map = SINIF_BRANS_YOUTUBE.get(sinif, {}).get(konu.brans) or {}
    for anahtar, video_id in sinif_map.items():
        if anahtar != "_" and anahtar in konu_lower:
            return video_id
    if sinif_map.get("_"):
        return sinif_map["_"]

    # Sınıfa özel yoksa yalnızca anahtar kelime (oran→7. sınıf videosu vb.)
    # ama 5. sınıfa 7/9. sınıf videosu verme
    if sinif in {"5", "6"}:
        return ""

    for anahtar, video_id in KONU_ANAHTAR_YOUTUBE.items():
        if anahtar in konu_lower and video_id and video_id not in YASAK_YOUTUBE_ID:
            return video_id
    aday = (BRANS_VARSAYILAN_YOUTUBE.get(konu.brans) or {}).get(tur, "")
    if aday in YASAK_YOUTUBE_ID:
        return ""
    return aday or ""


def _video_youtube_id_tamamla(video: KonuEgitimVideosu, konu: KonuKatalogu) -> KonuEgitimVideosu:
    mevcut = (video.youtube_id or "").strip()
    yasak_temizlendi = mevcut in YASAK_YOUTUBE_ID
    if yasak_temizlendi:
        mevcut = ""

    oneri = _varsayilan_youtube_id(konu, video.tur)
    if oneri in YASAK_YOUTUBE_ID:
        oneri = ""

    sorgu = (
        f"{konu.sinif_seviyesi}. sınıf {konu.brans_etiket} "
        f"{konu.konu_ad} konu anlatımı"
    )
    yeni_id = oneri or ""
    alanlar: list[str] = []

    if (video.youtube_id or "").strip() != yeni_id:
        video.youtube_id = yeni_id
        alanlar.append("youtube_id")
    if not (video.arama_sorgusu or "").strip() or yasak_temizlendi:
        if (video.arama_sorgusu or "").strip() != sorgu:
            video.arama_sorgusu = sorgu
            alanlar.append("arama_sorgusu")

    if alanlar:
        video.save(update_fields=alanlar)
    return video

DERS_BRANS_HARITASI = {
    "türkçe": KonuKatalogu.Brans.TURKCE,
    "turkce": KonuKatalogu.Brans.TURKCE,
    "matematik": KonuKatalogu.Brans.MATEMATIK,
    "fen": KonuKatalogu.Brans.FEN,
    "fen bilimleri": KonuKatalogu.Brans.FEN,
    "sosyal": KonuKatalogu.Brans.SOSYAL,
    "sosyal bilgiler": KonuKatalogu.Brans.SOSYAL,
    "din": KonuKatalogu.Brans.DIN,
    "din kültürü": KonuKatalogu.Brans.DIN,
    "ingilizce": KonuKatalogu.Brans.INGILIZCE,
}

BRANS_DENEME_HARITASI = {
    DenemeBransSonucu.Brans.TURKCE: KonuKatalogu.Brans.TURKCE,
    DenemeBransSonucu.Brans.MATEMATIK: KonuKatalogu.Brans.MATEMATIK,
    DenemeBransSonucu.Brans.FEN: KonuKatalogu.Brans.FEN,
    DenemeBransSonucu.Brans.SOSYAL: KonuKatalogu.Brans.SOSYAL,
    DenemeBransSonucu.Brans.DIN: KonuKatalogu.Brans.DIN,
    DenemeBransSonucu.Brans.INGILIZCE: KonuKatalogu.Brans.INGILIZCE,
}


def talebe_sinif_seviyesi(talebe: Talebe) -> str:
    if talebe.sinif_sube_id and talebe.sinif_sube:
        return str(talebe.sinif_sube.sinif).strip() or "8"
    if talebe.sinif:
        return str(talebe.sinif).strip().split("-")[0].strip() or "8"
    return "8"


def ders_adindan_brans(ders_ad: str) -> str | None:
    anahtar = (ders_ad or "").strip().lower()
    for parca, brans in DERS_BRANS_HARITASI.items():
        if parca in anahtar:
            return brans
    return None


def konu_getir_veya_olustur(
    sinif_seviyesi: str,
    brans: str,
    konu_ad: str,
) -> KonuKatalogu:
    konu, _ = KonuKatalogu.objects.get_or_create(
        sinif_seviyesi=sinif_seviyesi,
        brans=brans,
        konu_ad=konu_ad.strip(),
        defaults={"aktif": True},
    )
    return konu


def _eksik_kaydet(
    talebe: Talebe,
    konu: KonuKatalogu,
    kaynak: str,
    skor: Decimal,
    oncelik: int,
    tarih,
) -> TalebeKonuEksigi:
    kayit, _ = TalebeKonuEksigi.objects.update_or_create(
        talebe=talebe,
        konu=konu,
        kaynak=kaynak,
        defaults={
            "skor": skor,
            "oncelik": oncelik,
            "tespit_tarihi": tarih,
            "cozuldu": False,
        },
    )
    return kayit


def ktt_eksiklerini_tespit(talebe: Talebe) -> list[TalebeKonuEksigi]:
    sinif = talebe_sinif_seviyesi(talebe)
    kayitlar: list[TalebeKonuEksigi] = []
    sonuclar = (
        KttSonucu.objects.filter(talebe=talebe, ktt__aktif=True)
        .select_related("ktt", "ktt__ders")
        .order_by("-ktt__sinav_tarihi")[:12]
    )

    for sonuc in sonuclar:
        puan = Decimal(str(sonuc.puan or 0))
        if puan >= ZAYIF_KTT_PUAN:
            continue
        ders_ad = sonuc.ktt.ders.ad if sonuc.ktt.ders_id else ""
        brans = ders_adindan_brans(ders_ad)
        if not brans:
            continue
        konu_ad = sonuc.ktt.ad.strip() or ders_ad or "Genel tekrar"
        konu = konu_getir_veya_olustur(sinif, brans, konu_ad)
        oncelik = max(10, 100 - int(puan))
        kayitlar.append(
            _eksik_kaydet(
                talebe,
                konu,
                TalebeKonuEksigi.Kaynak.KTT,
                puan,
                oncelik,
                sonuc.ktt.sinav_tarihi,
            )
        )
    return kayitlar


def deneme_eksiklerini_tespit(talebe: Talebe) -> list[TalebeKonuEksigi]:
    sinif = talebe_sinif_seviyesi(talebe)
    kayitlar: list[TalebeKonuEksigi] = []
    sonuclar = list(talebe_deneme_sonuclari(talebe)[:3])
    if not sonuclar:
        return kayitlar

    brans_netleri: dict[str, list[Decimal]] = {}
    brans_tarih: dict[str, Any] = {}

    for sonuc in sonuclar:
        for satir in sonuc.brans_satirlari.all():
            kod = satir.brans
            net = Decimal(str(satir.net or 0))
            brans_netleri.setdefault(kod, []).append(net)
            brans_tarih[kod] = sonuc.deneme.sinav_tarihi

    if not brans_netleri:
        return kayitlar

    ort_netler = {k: sum(v) / len(v) for k, v in brans_netleri.items()}
    en_yuksek = max(ort_netler.values()) if ort_netler else Decimal("0")
    if en_yuksek <= 0:
        return kayitlar

    for brans_kod, ort in sorted(ort_netler.items(), key=lambda x: x[1]):
        oran = (ort / en_yuksek) * Decimal("100")
        if oran > ZAYIF_DENEME_ORAN + Decimal("20"):
            continue
        brans = BRANS_DENEME_HARITASI.get(brans_kod)
        if not brans:
            continue
        etiket = dict(DenemeBransSonucu.Brans.choices).get(brans_kod, brans_kod)
        konu_ad = f"{etiket} genel tekrar"
        konu = konu_getir_veya_olustur(sinif, brans, konu_ad)
        oncelik = max(20, int(100 - float(oran)))
        kayitlar.append(
            _eksik_kaydet(
                talebe,
                konu,
                TalebeKonuEksigi.Kaynak.DENEME,
                oran.quantize(Decimal("0.01")),
                oncelik,
                brans_tarih.get(brans_kod, localdate()),
            )
        )
    return kayitlar


def talebe_konu_eksiklerini_guncelle(talebe: Talebe) -> None:
    ktt_eksiklerini_tespit(talebe)
    deneme_eksiklerini_tespit(talebe)


def _konu_videolari(konu: KonuKatalogu) -> list[KonuEgitimVideosu]:
    videolar = list(
        konu.videolar.filter(aktif=True).order_by("sira", "id")[:3]
    )
    videolar = [_video_youtube_id_tamamla(v, konu) for v in videolar]
    if len(videolar) >= 3:
        return videolar

    mevcut_sira = {v.sira for v in videolar}
    turler = [
        KonuEgitimVideosu.Tur.ANLATIM,
        KonuEgitimVideosu.Tur.COZUM,
        KonuEgitimVideosu.Tur.TEKRAR,
    ]
    basliklar = [
        f"{konu.konu_ad} — konu anlatımı",
        f"{konu.konu_ad} — soru çözümü",
        f"{konu.konu_ad} — kısa tekrar",
    ]
    sorgular = [
        f"{konu.sinif_seviyesi}. sınıf {konu.brans_etiket} {konu.konu_ad} konu anlatımı",
        f"{konu.sinif_seviyesi}. sınıf {konu.brans_etiket} {konu.konu_ad} soru çözümü",
        f"{konu.sinif_seviyesi}. sınıf {konu.brans_etiket} {konu.konu_ad} tekrar",
    ]

    for sira in (1, 2, 3):
        if sira in mevcut_sira:
            continue
        yeni = KonuEgitimVideosu.objects.create(
            konu=konu,
            baslik=basliklar[sira - 1],
            arama_sorgusu=sorgular[sira - 1],
            youtube_id=_varsayilan_youtube_id(konu, turler[sira - 1]),
            tur=turler[sira - 1],
            sira=sira,
            sure_dk=8 + sira * 2,
            aktif=True,
        )
        videolar.append(yeni)
    return sorted(videolar, key=lambda v: v.sira)[:3]


def talebe_konu_destek_listesi(talebe: Talebe) -> list[dict[str, Any]]:
    talebe_konu_eksiklerini_guncelle(talebe)

    eksikler = (
        TalebeKonuEksigi.objects.filter(talebe=talebe, cozuldu=False)
        .select_related("konu")
        .prefetch_related(
            Prefetch(
                "konu__videolar",
                queryset=KonuEgitimVideosu.objects.filter(aktif=True).order_by("sira"),
            )
        )
        .order_by("-oncelik", "-tespit_tarihi")[:8]
    )

    sonuc: list[dict[str, Any]] = []
    gorulen_konu: set[int] = set()

    for eksik in eksikler:
        if eksik.konu_id in gorulen_konu:
            continue
        gorulen_konu.add(eksik.konu_id)
        konu = eksik.konu
        videolar = _konu_videolari(konu)
        izlenen = KonuVideoIzleme.objects.filter(talebe=talebe, konu=konu).exists()
        son_test = (
            KonuTestOturu.objects.filter(talebe=talebe, konu=konu)
            .order_by("-baslama")
            .first()
        )

        sonuc.append(
            {
                "eksik": eksik,
                "konu": konu,
                "videolar": videolar,
                "video_izlendi": izlenen,
                "son_test": son_test,
                "test_hazir": True,
                "kaynak_etiket": eksik.get_kaynak_display(),
            }
        )
    return sonuc


def konu_detay_verisi(talebe: Talebe, konu_id: int) -> dict[str, Any] | None:
    konu = KonuKatalogu.objects.filter(pk=konu_id, aktif=True).first()
    if not konu:
        return None

    videolar = _konu_videolari(konu)
    izlemeler = {
        i.video_id: i
        for i in KonuVideoIzleme.objects.filter(talebe=talebe, konu=konu).order_by("-baslama")
        if i.video_id
    }
    video_satirlari = []
    for video in videolar:
        izleme = izlemeler.get(video.pk) if video.pk else None
        video_satirlari.append(
            {
                "video": video,
                "izlendi": bool(izleme),
                "sure_sn": izleme.sure_sn if izleme else 0,
                "tamamlandi": izleme.tamamlandi if izleme else False,
            }
        )

    son_test = (
        KonuTestOturu.objects.filter(talebe=talebe, konu=konu).order_by("-baslama").first()
    )
    # Detayda kişiselleştirilmiş tam üretim yapma; ortak havuz / etiket yeterli.
    test_meta = konu_test_meta(konu, talebe=None)
    return {
        "konu": konu,
        "videolar": video_satirlari,
        "son_test": son_test,
        "video_izlendi": KonuVideoIzleme.objects.filter(talebe=talebe, konu=konu).exists(),
        **test_meta,
    }


def video_izleme_baslat(
    talebe: Talebe,
    konu: KonuKatalogu,
    video: KonuEgitimVideosu | None,
    video_baslik: str,
) -> KonuVideoIzleme:
    return KonuVideoIzleme.objects.create(
        talebe=talebe,
        konu=konu,
        video=video if video and video.pk else None,
        video_baslik=video_baslik,
        baslama=timezone.now(),
    )


def video_izleme_guncelle(
    izleme_id: int,
    talebe: Talebe,
    sure_sn: int,
    tamamlandi: bool = False,
) -> KonuVideoIzleme | None:
    izleme = KonuVideoIzleme.objects.filter(pk=izleme_id, talebe=talebe).first()
    if not izleme:
        return None
    izleme.sure_sn = max(izleme.sure_sn, sure_sn)
    if tamamlandi:
        izleme.tamamlandi = True
        izleme.bitis = timezone.now()
    izleme.save(update_fields=["sure_sn", "tamamlandi", "bitis"])
    return izleme


def konu_test_sorulari(
    konu: KonuKatalogu,
    limit: int = 10,
    *,
    talebe: Talebe | None = None,
) -> tuple[list[KonuSorusu], str]:
    from takip.konu_destek_ai import konu_ai_sorulari_hazirla

    return konu_ai_sorulari_hazirla(konu, hedef=min(limit, 5), talebe=talebe)


def konu_test_meta(konu: KonuKatalogu, *, talebe: Talebe | None = None) -> dict:
    sorular, kaynak = konu_test_sorulari(konu, talebe=talebe)
    return {
        "soru_sayisi": len(sorular),
        "kaynak": kaynak,
        "ai_etiket": {
            "ai": "Yapay zeka · denetimli yeni nesil set",
            "kural": "Bağlam temelli soru seti",
            "havuz": "Hazır soru bankası",
        }.get(kaynak, ""),
    }


@transaction.atomic
def konu_test_oturumu_baslat(talebe: Talebe, konu: KonuKatalogu) -> KonuTestOturu | None:
    sorular, _ = konu_test_sorulari(konu, talebe=talebe)
    if not sorular:
        return None
    return KonuTestOturu.objects.create(
        talebe=talebe,
        konu=konu,
        toplam_soru=len(sorular),
    )


def konu_test_cevabi_kaydet(
    oturum: KonuTestOturu,
    soru: KonuSorusu,
    secilen: str,
) -> KonuTestCevabi:
    secilen = (secilen or "").strip().upper()[:1]
    dogru = secilen == soru.dogru_secenek
    cevap, _ = KonuTestCevabi.objects.update_or_create(
        oturum=oturum,
        soru=soru,
        defaults={"secilen": secilen, "dogru_mu": dogru},
    )
    return cevap


def konu_test_oturumu_bitir(oturum: KonuTestOturu) -> KonuTestOturu:
    oturum.bitis = timezone.now()
    oturum.save(update_fields=["bitis"])
    oturum.guncelle_sonuc()

    if oturum.basari_yuzde >= Decimal("70"):
        TalebeKonuEksigi.objects.filter(
            talebe=oturum.talebe,
            konu=oturum.konu,
            cozuldu=False,
        ).update(cozuldu=True)

    return oturum


def etut_hocasi_konu_destek_raporu(hoca) -> dict[str, Any]:
    talebeler = Talebe.objects.filter(etut_hocasi=hoca, aktif=True).order_by("ad_soyad")
    talebe_ids = list(talebeler.values_list("id", flat=True))
    bugun = localdate()
    hafta_baslangic = bugun - timedelta(days=6)

    izlemeler = (
        KonuVideoIzleme.objects.filter(talebe_id__in=talebe_ids, baslama__date__gte=hafta_baslangic)
        .select_related("talebe", "konu")
        .order_by("-baslama")[:100]
    )
    testler = (
        KonuTestOturu.objects.filter(
            talebe_id__in=talebe_ids,
            bitis__isnull=False,
            baslama__date__gte=hafta_baslangic,
        )
        .select_related("talebe", "konu")
        .order_by("-bitis")[:100]
    )

    eksikler = (
        TalebeKonuEksigi.objects.filter(talebe_id__in=talebe_ids, cozuldu=False)
        .select_related("talebe", "konu")
        .order_by("-oncelik")[:50]
    )

    izleyen_talebe = set(izlemeler.values_list("talebe_id", flat=True))
    izlemeyen = [t for t in talebeler if t.id not in izleyen_talebe]

    return {
        "talebeler": talebeler,
        "izlemeler": izlemeler,
        "testler": testler,
        "eksikler": eksikler,
        "izlemeyen_talebeler": izlemeyen[:20],
        "hafta_baslangic": hafta_baslangic,
        "bugun": bugun,
    }


def seed_konu_destek_ornek_verisi() -> None:
    """Demo konu, video ve soru havuzu."""
    ornek_konular = [
        ("7", KonuKatalogu.Brans.MATEMATIK, "Kesirler"),
        ("7", KonuKatalogu.Brans.TURKCE, "Paragraf"),
        ("7", KonuKatalogu.Brans.FEN, "Madde ve özellikleri"),
        ("8", KonuKatalogu.Brans.MATEMATIK, "Üslü ifadeler"),
        ("8", KonuKatalogu.Brans.TURKCE, "Yazım kuralları"),
    ]

    for sinif, brans, konu_ad in ornek_konular:
        konu = konu_getir_veya_olustur(sinif, brans, konu_ad)
        if konu.videolar.exists():
            continue
        sorgular = [
            (f"{sinif}. sınıf {konu.brans_etiket} {konu_ad} konu anlatımı", KonuEgitimVideosu.Tur.ANLATIM),
            (f"{sinif}. sınıf {konu.brans_etiket} {konu_ad} soru çözümü", KonuEgitimVideosu.Tur.COZUM),
            (f"{sinif}. sınıf {konu.brans_etiket} {konu_ad} tekrar", KonuEgitimVideosu.Tur.TEKRAR),
        ]
        for sira, (sorgu, tur) in enumerate(sorgular, start=1):
            KonuEgitimVideosu.objects.create(
                konu=konu,
                baslik=f"{konu_ad} — {dict(KonuEgitimVideosu.Tur.choices).get(tur, tur)}",
                arama_sorgusu=sorgu,
                tur=tur,
                sira=sira,
                sure_dk=8 + sira * 2,
                aktif=True,
            )

        if not konu.sorular.exists() and konu_ad == "Kesirler":
            sorular = [
                (
                    "1/2 + 1/4 işleminin sonucu kaçtır?",
                    "1/6",
                    "3/4",
                    "1/2",
                    "2/3",
                    "B",
                    "Paydalar eşitlenerek toplanır.",
                ),
                (
                    "3/5 kesrinin ondalık karşılığı kaçtır?",
                    "0,3",
                    "0,6",
                    "0,5",
                    "0,35",
                    "B",
                    "3 ÷ 5 = 0,6",
                ),
                (
                    "2/3 kesri ile 1/3 kesrinin farkı kaçtır?",
                    "1/3",
                    "1/2",
                    "1/6",
                    "2/3",
                    "A",
                    "Paydalar aynı; paylar çıkarılır.",
                ),
            ]
            for sira, satir in enumerate(sorular, start=1):
                KonuSorusu.objects.create(
                    konu=konu,
                    soru_metni=satir[0],
                    secenek_a=satir[1],
                    secenek_b=satir[2],
                    secenek_c=satir[3],
                    secenek_d=satir[4],
                    dogru_secenek=satir[5],
                    aciklama=satir[6],
                    sira=sira,
                    aktif=True,
                )
