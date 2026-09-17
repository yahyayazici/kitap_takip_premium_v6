"""Dijital Duyuru Ekranı — sahne serileştirme, sürümleme ve yayın derleme.

Bu modül, yönetim paneli ile televizyon arasındaki **tek veri sözleşmesini**
üretir. Aynı JSON hem stüdyo önizlemesinde hem televizyonda aynı render
motoruna (``static/ekran/js/engine.js``) verilir; böylece stüdyoda görülen
ile ekrana çıkan birebir aynı olur.

Yayın akışı
-----------
1. Stüdyo, sahneyi ilişkisel tablolara kaydeder (taslak).
2. "Yayınla" denince ``paket_derle`` tüm sahneleri, öğeleri ve medya
   adreslerini tek JSON'a derler, SHA-256 damgasını hesaplar.
3. Televizyon 10 sn'de bir yalnız damgayı sorar. Damga değişmedikçe hiçbir
   şey indirilmez; değişince paketi bir kez çeker ve önbelleğe alır.

Bu tasarım kasıtlıdır: sunucu gunicorn WSGI üzerinde 2 worker × 2 thread ile
çalışıyor. WebSocket/SSE her televizyon için bir thread'i süresiz tutar ve
dört televizyonda panelin tamamını kilitler. Damga sorgusu ise milisaniyelik
bir okumadır.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time

from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.utils import timezone

from takip.ekran_models import (
    EkranAcilDuyuru,
    EkranCihaz,
    EkranCihazOlayi,
    EkranIslemKaydi,
    EkranMedya,
    EkranOge,
    EkranOgeGrubu,
    EkranOgeKaynagi,
    EkranOynatmaListesi,
    EkranOynatmaOgesi,
    EkranProje,
    EkranProjeSurumu,
    EkranSahne,
    EkranYayinHedefi,
    EkranYayinPaketi,
    EkranYayinPlani,
    OgeTuru,
    TUVAL_GENISLIK,
    TUVAL_YUKSEKLIK,
)

# Nabız her 10 sn'de gelir ama veritabanına en fazla bu sıklıkta yazılır.
NABIZ_YAZMA_ARALIGI_SN = 30

# Televizyonun damga sorgulama aralığı (viewer.js bu değeri sunucudan alır).
YOKLAMA_ARALIGI_SN = 10


class YayinHatasi(Exception):
    """Yayın derlenemedi — kullanıcıya gösterilebilecek Türkçe açıklama."""


# ---------------------------------------------------------------------------
# Öğe kataloğu — stüdyodaki "Öğe ekle" panelinin kaynağı
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OgeTanimi:
    tur: str
    ad: str
    aciklama: str
    ikon: str
    varsayilan_g: float
    varsayilan_y: float
    medya_gerekir: bool = False
    medya_turu: str = ""
    grup: str = "Temel"

    def varsayilan_oge(self) -> dict:
        return {
            "tur": self.tur,
            "ad": self.ad,
            "g": self.varsayilan_g,
            "y": self.varsayilan_y,
            "stil": dict(VARSAYILAN_STIL.get(self.tur, {})),
            "icerik": dict(VARSAYILAN_ICERIK.get(self.tur, {})),
        }


VARSAYILAN_STIL: dict[str, dict] = {
    OgeTuru.METIN: {
        "yazi_tipi": "Poppins",
        "punto": 64,
        "kalinlik": 600,
        "renk": "#ffffff",
        "hizalama": "center",
        "dikey_hizalama": "center",
        "satir_araligi": 1.25,
        "harf_araligi": 0,
        "arka_plan": "transparent",
        "arka_plan_opaklik": 1,
        "ic_bosluk": 24,
        "kose": 0,
        "kenarlik_kalinlik": 0,
        "kenarlik_renk": "#ffffff",
        "golge": "yok",
        "tasma": "kucult",
    },
    OgeTuru.GERI_SAYIM: {
        "punto": 96,
        "kalinlik": 700,
        "renk": "#ffffff",
        "etiket_renk": "#a9c2e8",
        "arka_plan": "rgba(255,255,255,0.06)",
        "kose": 18,
        "ic_bosluk": 28,
        "hizalama": "center",
    },
    OgeTuru.SAAT: {
        "punto": 72,
        "kalinlik": 600,
        "renk": "#ffffff",
        "tarih_renk": "#a9c2e8",
        "hizalama": "center",
        "arka_plan": "transparent",
        "kose": 14,
        "ic_bosluk": 16,
    },
    OgeTuru.KAYAN_BANT: {
        "punto": 34,
        "kalinlik": 500,
        "renk": "#ffffff",
        "arka_plan": "#15427f",
        "ic_bosluk": 16,
        "kose": 0,
        "ayirici": "•",
    },
    OgeTuru.SEKIL: {"arka_plan": "#15427f", "kose": 16, "kenarlik_kalinlik": 0, "kenarlik_renk": "#ffffff"},
    OgeTuru.CIZGI: {"renk": "#ffffff", "kalinlik_px": 3, "stil_tipi": "duz"},
    OgeTuru.QR: {"arka_plan": "#ffffff", "ic_bosluk": 16, "kose": 12},
    OgeTuru.BILGI_KUTUSU: {
        "arka_plan": "rgba(255,255,255,0.07)",
        "kose": 18,
        "ic_bosluk": 24,
        "renk": "#ffffff",
        "baslik_renk": "#a9c2e8",
        "punto": 30,
    },
}

VARSAYILAN_ICERIK: dict[str, dict] = {
    OgeTuru.METIN: {"sozler": [{"metin": "Buraya yazın", "sure": 0}], "dongu": True},
    OgeTuru.PDF: {"sayfalar": [], "sigdir": "icine", "ortak_sure": 10, "dongu": True, "tek_sayfa": None},
    OgeTuru.GORSEL: {"sigdir": "icine", "odak": "center", "gecis": "soldur", "ortak_sure": 8, "dongu": True},
    OgeTuru.VIDEO: {
        "sigdir": "icine",
        "sessiz": True,
        "dongu": True,
        "otomatik_baslat": True,
        "baslangic_sn": 0,
        "bitis_sn": 0,
    },
    OgeTuru.GERI_SAYIM: {
        "baslik": "LGS'ye kalan süre",
        "hedef": "",
        "gun": True,
        "saat": True,
        "dakika": True,
        "saniye": False,
        "bitince_metin": "Başladı",
        "bitince_gizle": False,
    },
    OgeTuru.SAAT: {"saat": True, "saniye": False, "tarih": True, "gun_adi": True, "format": "HH:mm"},
    OgeTuru.KAYAN_BANT: {"duyurular": ["Duyuru metnini buraya yazın"], "yon": "sola", "hiz": 60, "acil": False},
    OgeTuru.QR: {"adres": "https://cinilisarayproje.com"},
    OgeTuru.SEKIL: {"sekil": "dikdortgen"},
    OgeTuru.CIZGI: {"yon": "yatay"},
    OgeTuru.BILGI_KUTUSU: {"baslik": "Bilgi", "satirlar": ["Birinci satır", "İkinci satır"]},
    OgeTuru.GUNLUK_PROGRAM: {"kaynak": "elle", "baslik": "Günlük Program", "satirlar": []},
    OgeTuru.YEMEK_LISTESI: {"kaynak": "elle", "baslik": "Yemek Listesi", "satirlar": []},
    OgeTuru.SINAV_DUYURUSU: {"kaynak": "elle", "baslik": "Sınav Duyurusu", "satirlar": []},
    OgeTuru.NAMAZ_VAKITLERI: {"kaynak": "elle", "baslik": "Namaz Vakitleri", "satirlar": []},
}


OGE_KATALOGU: tuple[OgeTanimi, ...] = (
    OgeTanimi(OgeTuru.PDF, "PDF", "Sayfaları otomatik ilerleyen belge", "pdf", 1920, 1080, True, "pdf"),
    OgeTanimi(OgeTuru.GORSEL, "Görsel / afiş", "Tek görsel ya da slayt", "gorsel", 540, 960, True, "gorsel"),
    OgeTanimi(OgeTuru.VIDEO, "Video", "MP4 / WEBM oynatıcı", "video", 1280, 720, True, "video"),
    OgeTanimi(OgeTuru.METIN, "Metin / slogan", "Başlık, vecize, kısa söz", "metin", 1200, 300),
    OgeTanimi(OgeTuru.GERI_SAYIM, "Geri sayım", "Sınava kalan süre", "geri_sayim", 760, 320),
    OgeTanimi(OgeTuru.SAAT, "Saat ve tarih", "Dijital saat, Türkçe tarih", "saat", 620, 260),
    OgeTanimi(OgeTuru.KAYAN_BANT, "Kayan duyuru", "Alt bant, akan yazı", "kayan_bant", 1920, 96),
    OgeTanimi(OgeTuru.LOGO, "Kurum logosu", "Çinili Saray logosu", "logo", 280, 120, grup="Kurumsal"),
    OgeTanimi(OgeTuru.QR, "QR kod", "Adres veya bilgi karesi", "qr", 260, 260, grup="Kurumsal"),
    OgeTanimi(OgeTuru.SEKIL, "Şekil / renk bloğu", "Dolgu ve çerçeve", "sekil", 480, 320, grup="Biçim"),
    OgeTanimi(OgeTuru.CIZGI, "Çizgi / ayırıcı", "İnce ayraç", "cizgi", 600, 4, grup="Biçim"),
    OgeTanimi(OgeTuru.BILGI_KUTUSU, "Bilgi kutusu", "Başlık + satırlar", "bilgi_kutusu", 560, 420, grup="Bilgi"),
    OgeTanimi(OgeTuru.GUNLUK_PROGRAM, "Günlük program", "Gün akışı listesi", "gunluk_program", 700, 800, grup="Bilgi"),
    OgeTanimi(OgeTuru.YEMEK_LISTESI, "Yemek listesi", "Öğün listesi", "yemek_listesi", 620, 520, grup="Bilgi"),
    OgeTanimi(OgeTuru.SINAV_DUYURUSU, "Sınav duyurusu", "Sınav bilgi kartı", "sinav_duyurusu", 700, 520, grup="Bilgi"),
    OgeTanimi(OgeTuru.NAMAZ_VAKITLERI, "Namaz vakitleri", "Günün vakitleri", "namaz_vakitleri", 520, 620, grup="Bilgi"),
)

OGE_TANIMLARI: dict[str, OgeTanimi] = {t.tur: t for t in OGE_KATALOGU}


def oge_katalogu_verisi() -> list[dict]:
    """Stüdyo arayüzüne gönderilen öğe listesi."""
    return [
        {
            "tur": t.tur,
            "ad": t.ad,
            "aciklama": t.aciklama,
            "ikon": t.ikon,
            "grup": t.grup,
            "medya_gerekir": t.medya_gerekir,
            "medya_turu": t.medya_turu,
            "varsayilan": t.varsayilan_oge(),
        }
        for t in OGE_KATALOGU
    ]


# ---------------------------------------------------------------------------
# Serileştirme: veritabanı → render motoru sözleşmesi
# ---------------------------------------------------------------------------


def _medya_url(dosya) -> str:
    try:
        return dosya.url if dosya else ""
    except ValueError:  # dosya alanı boş
        return ""


def medya_kaynagi(medya: EkranMedya | None) -> dict | None:
    """Tek bir medyanın render motoruna gidecek özeti."""
    if medya is None:
        return None

    temel = {
        "id": medya.pk,
        "tur": medya.tur,
        "ad": medya.ad,
        "url": _medya_url(medya.dosya),
        "mime": medya.mime,
        "g": medya.genislik,
        "y": medya.yukseklik,
    }

    if medya.tur == EkranMedya.Tur.PDF:
        temel["sayfalar"] = [
            {"no": s.sira, "url": _medya_url(s.gorsel), "g": s.genislik, "y": s.yukseklik}
            for s in medya.sayfalar.all()
        ]
        temel["sayfa_sayisi"] = medya.sayfa_sayisi
    elif medya.tur == EkranMedya.Tur.VIDEO:
        temel["sure"] = medya.sure_sn

    return temel


def _varsayilan_oge_adi(tur: str) -> str:
    tanim = OGE_TANIMLARI.get(tur)
    return tanim.ad if tanim else tur


def oge_verisi(oge: EkranOge) -> dict:
    """Tek öğenin JSON gösterimi.

    Konum/ölçü tasarım uzayındadır (proje tuvali). Televizyon bunları kendi
    çözünürlüğüne ölçekler.
    """
    veri = {
        "id": oge.pk,
        "tur": oge.tur,
        "ad": oge.ad or _varsayilan_oge_adi(oge.tur),
        "x": oge.x,
        "y": oge.y,
        "g": oge.genislik,
        "h": oge.yukseklik,
        "donus": oge.donus,
        "katman": oge.katman,
        "opaklik": oge.opaklik,
        "kilitli": oge.kilitli,
        "gorunur": oge.gorunur,
        "grup": oge.grup_id,
        "stil": oge.stil or {},
        "icerik": oge.icerik or {},
        "zamanlama": oge.zamanlama or {},
        "animasyon": oge.animasyon or {},
    }

    kaynak = medya_kaynagi(oge.medya)
    if kaynak:
        veri["kaynak"] = kaynak

    kaynaklar = [
        {
            "medya": medya_kaynagi(k.medya),
            "sira": k.sira,
            "sure": k.sure_sn,
            "gorunur": k.gorunur,
        }
        for k in oge.kaynaklar.all()
        if k.gorunur
    ]
    if kaynaklar:
        veri["kaynaklar"] = kaynaklar

    return veri


def sahne_verisi(sahne: EkranSahne) -> dict:
    """Bir sahnenin tam JSON gösterimi — stüdyo ve televizyon aynı veriyi alır."""
    proje = sahne.proje
    return {
        "id": sahne.pk,
        "ad": sahne.ad,
        "sira": sahne.sira,
        "sure_tipi": sahne.sure_tipi,
        "sure_sn": sahne.sure_sn,
        "gecis": sahne.gecis,
        "tuval": {"g": proje.tuval_genislik, "y": proje.tuval_yukseklik},
        "arka_plan": {
            "renk": sahne.arka_plan_rengi,
            "gorsel": _medya_url(sahne.arka_plan_medya.dosya) if sahne.arka_plan_medya else "",
        },
        "gruplar": [
            {"id": g.pk, "ad": g.ad, "sira": g.sira, "kilitli": g.kilitli, "gorunur": g.gorunur}
            for g in sahne.gruplar.all()
        ],
        "ogeler": [oge_verisi(o) for o in sahne.ogeler.all()],
    }


def _sahne_sorgusu(temel):
    """Sahne + öğe + medya + PDF sayfalarını N+1 olmadan çeker."""
    return temel.select_related("proje", "arka_plan_medya").prefetch_related(
        "gruplar",
        Prefetch(
            "ogeler",
            queryset=EkranOge.objects.select_related("medya")
            .prefetch_related(
                "medya__sayfalar",
                Prefetch(
                    "kaynaklar",
                    queryset=EkranOgeKaynagi.objects.select_related("medya").prefetch_related(
                        "medya__sayfalar"
                    ),
                ),
            )
            .order_by("katman", "id"),
        ),
    )


def sahne_getir(sahne_id: int) -> EkranSahne:
    return _sahne_sorgusu(EkranSahne.objects.filter(pk=sahne_id)).get()


def proje_verisi(proje: EkranProje) -> dict:
    sahneler = _sahne_sorgusu(EkranSahne.objects.filter(proje=proje)).order_by("sira", "id")
    return {
        "id": proje.pk,
        "ad": proje.ad,
        "aciklama": proje.aciklama,
        "tuval": {"g": proje.tuval_genislik, "y": proje.tuval_yukseklik},
        "durum": proje.durum,
        "sahneler": [sahne_verisi(s) for s in sahneler],
    }


# ---------------------------------------------------------------------------
# Stüdyodan kayıt: JSON → veritabanı
# ---------------------------------------------------------------------------


def _sayi(deger, varsayilan: float = 0.0) -> float:
    try:
        sonuc = float(deger)
    except (TypeError, ValueError):
        return varsayilan
    if sonuc != sonuc or sonuc in (float("inf"), float("-inf")):  # NaN / sonsuz
        return varsayilan
    return sonuc


def _sozluk(deger) -> dict:
    return deger if isinstance(deger, dict) else {}


@transaction.atomic
def sahne_kaydet(sahne: EkranSahne, veri: dict, kullanici=None) -> EkranSahne:
    """Stüdyodan gelen sahne JSON'unu ilişkisel tablolara yazar.

    Öğeler tamamen yeniden yazılır (sil–yaz). Sahnedeki öğe sayısı onlarca
    mertebesinde olduğundan bu, kısmi güncellemenin karmaşıklığından daha
    güvenlidir: stüdyo neyi gönderdiyse ekranda o vardır.
    """
    proje = sahne.proje

    tuval = _sozluk(veri.get("tuval"))
    if tuval:
        proje.tuval_genislik = int(_sayi(tuval.get("g"), TUVAL_GENISLIK)) or TUVAL_GENISLIK
        proje.tuval_yukseklik = int(_sayi(tuval.get("y"), TUVAL_YUKSEKLIK)) or TUVAL_YUKSEKLIK

    if "ad" in veri:
        sahne.ad = str(veri["ad"])[:160].strip() or sahne.ad
    if veri.get("sure_tipi") in dict(EkranSahne.SureTipi.choices):
        sahne.sure_tipi = veri["sure_tipi"]
    if "sure_sn" in veri:
        sahne.sure_sn = max(1, min(86400, int(_sayi(veri.get("sure_sn"), sahne.sure_sn))))
    if veri.get("gecis") in dict(EkranSahne.Gecis.choices):
        sahne.gecis = veri["gecis"]

    arka = _sozluk(veri.get("arka_plan"))
    if "renk" in arka:
        sahne.arka_plan_rengi = str(arka["renk"])[:24]
    if "medya_id" in arka:
        sahne.arka_plan_medya = EkranMedya.objects.filter(pk=arka["medya_id"]).first()

    sahne.save()
    proje.save(update_fields=["tuval_genislik", "tuval_yukseklik", "guncellenme"])

    # —— Gruplar —— (geçici stüdyo kimliği → gerçek pk eşlemesi)
    grup_eslemesi: dict[str, int] = {}
    sahne.gruplar.all().delete()
    for sira, ham_grup in enumerate(veri.get("gruplar") or []):
        if not isinstance(ham_grup, dict):
            continue
        grup = EkranOgeGrubu.objects.create(
            sahne=sahne,
            ad=str(ham_grup.get("ad") or "Grup")[:120],
            sira=sira,
            kilitli=bool(ham_grup.get("kilitli")),
            gorunur=ham_grup.get("gorunur", True) is not False,
        )
        grup_eslemesi[str(ham_grup.get("id"))] = grup.pk

    # —— Öğeler ——
    EkranOgeKaynagi.objects.filter(oge__sahne=sahne).delete()
    sahne.ogeler.all().delete()

    gecerli_turler = dict(OgeTuru.choices)
    for sira, ham in enumerate(veri.get("ogeler") or []):
        if not isinstance(ham, dict):
            continue
        tur = ham.get("tur")
        if tur not in gecerli_turler:
            continue

        medya = None
        kaynak = _sozluk(ham.get("kaynak"))
        medya_id = ham.get("medya_id") or kaynak.get("id")
        if medya_id:
            medya = EkranMedya.objects.filter(pk=medya_id).first()

        oge = EkranOge.objects.create(
            sahne=sahne,
            grup_id=grup_eslemesi.get(str(ham.get("grup"))),
            tur=tur,
            ad=str(ham.get("ad") or "")[:120],
            x=_sayi(ham.get("x")),
            y=_sayi(ham.get("y")),
            genislik=max(1.0, _sayi(ham.get("g"), 100)),
            yukseklik=max(1.0, _sayi(ham.get("h"), 100)),
            donus=_sayi(ham.get("donus")) % 360,
            katman=int(_sayi(ham.get("katman"), sira)),
            opaklik=min(1.0, max(0.0, _sayi(ham.get("opaklik"), 1.0))),
            kilitli=bool(ham.get("kilitli")),
            gorunur=ham.get("gorunur", True) is not False,
            medya=medya,
            stil=_sozluk(ham.get("stil")),
            icerik=_sozluk(ham.get("icerik")),
            zamanlama=_sozluk(ham.get("zamanlama")),
            animasyon=_sozluk(ham.get("animasyon")),
        )

        for k_sira, ham_kaynak in enumerate(ham.get("kaynaklar") or []):
            if not isinstance(ham_kaynak, dict):
                continue
            ham_medya = _sozluk(ham_kaynak.get("medya"))
            k_medya_id = ham_kaynak.get("medya_id") or ham_medya.get("id")
            k_medya = EkranMedya.objects.filter(pk=k_medya_id).first() if k_medya_id else None
            if k_medya is None:
                continue
            EkranOgeKaynagi.objects.create(
                oge=oge,
                medya=k_medya,
                sira=k_sira,
                sure_sn=max(0.5, _sayi(ham_kaynak.get("sure"), 8)),
                gorunur=ham_kaynak.get("gorunur", True) is not False,
            )

    proje.kaydedilmemis_degisiklik = True
    proje.son_duzenleyen = kullanici if (kullanici and kullanici.is_authenticated) else None
    proje.save(update_fields=["kaydedilmemis_degisiklik", "son_duzenleyen", "guncellenme"])

    return sahne


# ---------------------------------------------------------------------------
# Sürüm geçmişi
# ---------------------------------------------------------------------------


@transaction.atomic
def surum_olustur(proje: EkranProje, kullanici=None, not_metni: str = "") -> EkranProjeSurumu:
    """Tasarımın o anki hâlini dondurur."""
    son_no = (
        EkranProjeSurumu.objects.filter(proje=proje)
        .order_by("-surum_no")
        .values_list("surum_no", flat=True)
        .first()
        or 0
    )
    return EkranProjeSurumu.objects.create(
        proje=proje,
        surum_no=son_no + 1,
        veri=proje_verisi(proje),
        not_metni=not_metni[:300],
        olusturan=kullanici if (kullanici and kullanici.is_authenticated) else None,
    )


@transaction.atomic
def surum_geri_yukle(surum: EkranProjeSurumu, kullanici=None) -> EkranProje:
    """Eski bir sürümü taslağa geri yazar.

    Yayındaki paket bundan etkilenmez — geri yükleme yalnız taslağı değiştirir;
    ekrana çıkması için yeniden "Yayınla" gerekir.
    """
    proje = surum.proje
    veri = surum.veri or {}

    tuval = _sozluk(veri.get("tuval"))
    proje.tuval_genislik = int(_sayi(tuval.get("g"), proje.tuval_genislik)) or proje.tuval_genislik
    proje.tuval_yukseklik = int(_sayi(tuval.get("y"), proje.tuval_yukseklik)) or proje.tuval_yukseklik
    proje.save(update_fields=["tuval_genislik", "tuval_yukseklik", "guncellenme"])

    EkranOgeKaynagi.objects.filter(oge__sahne__proje=proje).delete()
    EkranOge.objects.filter(sahne__proje=proje).delete()
    EkranSahne.objects.filter(proje=proje).delete()

    for sira, ham_sahne in enumerate(veri.get("sahneler") or []):
        if not isinstance(ham_sahne, dict):
            continue
        sahne = EkranSahne.objects.create(
            proje=proje,
            ad=str(ham_sahne.get("ad") or f"Sahne {sira + 1}")[:160],
            sira=sira,
        )
        sahne_kaydet(sahne, ham_sahne, kullanici=kullanici)

    proje.kaydedilmemis_degisiklik = True
    proje.save(update_fields=["kaydedilmemis_degisiklik", "guncellenme"])

    islem_kaydet(
        kullanici,
        EkranIslemKaydi.Eylem.SURUM_GERI_YUKLE,
        nesne=proje,
        aciklama=f"v{surum.surum_no} geri yüklendi",
    )
    return proje


# ---------------------------------------------------------------------------
# Yayın derleme
# ---------------------------------------------------------------------------


def _varliklari_topla(sahne_verileri: list[dict]) -> list[str]:
    """Paketteki tüm dosya adresleri — çevrim dışı önbelleğin ön yükleme listesi."""
    adresler: list[str] = []

    def ekle(url: str | None) -> None:
        if url and url not in adresler:
            adresler.append(url)

    for sahne in sahne_verileri:
        ekle(_sozluk(sahne.get("arka_plan")).get("gorsel"))
        for oge in sahne.get("ogeler") or []:
            kaynak = _sozluk(oge.get("kaynak"))
            if kaynak:
                if kaynak.get("tur") == EkranMedya.Tur.PDF:
                    for sayfa in kaynak.get("sayfalar") or []:
                        ekle(sayfa.get("url"))
                else:
                    ekle(kaynak.get("url"))
            for alt in oge.get("kaynaklar") or []:
                alt_medya = _sozluk(alt.get("medya"))
                if alt_medya.get("tur") == EkranMedya.Tur.PDF:
                    for sayfa in alt_medya.get("sayfalar") or []:
                        ekle(sayfa.get("url"))
                else:
                    ekle(alt_medya.get("url"))

    return adresler


def _damga(veri: dict) -> str:
    ham = json.dumps(veri, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()


def paket_dogrula(sahne_verileri: list[dict]) -> list[str]:
    """Yayın çıkmadan önce eksik/bozuk içerikleri bulur.

    "Yayın sırasında eksik dosya oluşmaması" gereği burada karşılanır:
    dosyası silinmiş bir medya ya da sayfası üretilememiş bir PDF varsa
    yayın hiç oluşturulmaz, kullanıcıya hangi sahnede olduğu söylenir.
    """
    sorunlar: list[str] = []

    for sahne in sahne_verileri:
        sahne_adi = sahne.get("ad") or "Sahne"
        gorunur_oge = False

        for oge in sahne.get("ogeler") or []:
            if not oge.get("gorunur", True):
                continue
            gorunur_oge = True
            tur = oge.get("tur")
            kaynak = _sozluk(oge.get("kaynak"))
            kaynaklar = oge.get("kaynaklar") or []

            tanim = OGE_TANIMLARI.get(tur)
            if tanim and tanim.medya_gerekir and not kaynak and not kaynaklar:
                sorunlar.append(f"“{sahne_adi}” sahnesindeki {tanim.ad} öğesine dosya seçilmemiş.")
                continue

            if tur == OgeTuru.PDF and kaynak and not kaynak.get("sayfalar"):
                sorunlar.append(
                    f"“{sahne_adi}” sahnesindeki “{kaynak.get('ad', 'PDF')}” dosyasının "
                    "sayfa görselleri üretilememiş. Dosyayı yeniden yükleyin."
                )

            if kaynak and kaynak.get("tur") != EkranMedya.Tur.PDF and not kaynak.get("url"):
                sorunlar.append(
                    f"“{sahne_adi}” sahnesindeki “{kaynak.get('ad', 'dosya')}” sunucuda bulunamadı."
                )

        if not gorunur_oge:
            sorunlar.append(f"“{sahne_adi}” sahnesi boş — en az bir görünür öğe eklemelisiniz.")

    return sorunlar


@transaction.atomic
def paket_derle(plan: EkranYayinPlani, kullanici=None) -> EkranYayinPaketi:
    """Planı televizyona gidecek tek JSON'a derler ve damgasını hesaplar."""
    ogeler = (
        plan.liste.ogeler.filter(aktif=True)
        .select_related("sahne__proje")
        .order_by("sira", "id")
    )
    if not ogeler:
        raise YayinHatasi(
            f"“{plan.liste.ad}” listesinde yayınlanacak sahne yok. Önce listeye sahne ekleyin."
        )

    sahne_verileri: list[dict] = []
    for oge in ogeler:
        sahne = sahne_getir(oge.sahne_id)
        veri = sahne_verisi(sahne)
        if oge.sure_sn:
            veri["sure_sn"] = oge.sure_sn
            veri["sure_tipi"] = EkranSahne.SureTipi.SANIYE
        veri["liste_sira"] = oge.sira
        sahne_verileri.append(veri)

    sorunlar = paket_dogrula(sahne_verileri)
    if sorunlar:
        raise YayinHatasi("Yayın hazırlanamadı:\n• " + "\n• ".join(sorunlar[:6]))

    varliklar = _varliklari_topla(sahne_verileri)

    govde = {
        "plan_id": plan.pk,
        "plan_ad": plan.ad,
        "liste_ad": plan.liste.ad,
        "dongu": plan.liste.donguye_al,
        "sahneler": sahne_verileri,
        "varliklar": varliklar,
        "yoklama_sn": YOKLAMA_ARALIGI_SN,
    }
    damga = _damga(govde)
    govde["damga"] = damga

    mevcut = EkranYayinPaketi.objects.filter(plan=plan, damga=damga).first()
    if mevcut is None:
        toplam_boyut = (
            EkranMedya.objects.filter(
                Q(ogeler__sahne__oynatma_ogeleri__liste=plan.liste)
                | Q(oge_kaynaklari__oge__sahne__oynatma_ogeleri__liste=plan.liste)
            )
            .distinct()
            .aggregate(toplam=Sum("boyut"))
            .get("toplam")
            or 0
        )
        mevcut = EkranYayinPaketi.objects.create(
            plan=plan,
            damga=damga,
            veri=govde,
            varlik_sayisi=len(varliklar),
            toplam_boyut=toplam_boyut,
            yayinlayan=kullanici if (kullanici and kullanici.is_authenticated) else None,
        )

    plan.aktif_paket = mevcut
    plan.durum = EkranYayinPlani.Durum.YAYINDA
    plan.save(update_fields=["aktif_paket", "durum", "guncellenme"])

    for liste_ogesi in ogeler:
        proje = liste_ogesi.sahne.proje
        if proje.kaydedilmemis_degisiklik or proje.durum != EkranProje.Durum.YAYINDA:
            surum = surum_olustur(proje, kullanici=kullanici, not_metni=f"“{plan.ad}” ile yayınlandı")
            surum.yayinlandi_mi = True
            surum.save(update_fields=["yayinlandi_mi"])
            proje.yayindaki_surum = surum
            proje.durum = EkranProje.Durum.YAYINDA
            proje.kaydedilmemis_degisiklik = False
            proje.save(
                update_fields=["yayindaki_surum", "durum", "kaydedilmemis_degisiklik", "guncellenme"]
            )

    islem_kaydet(
        kullanici,
        EkranIslemKaydi.Eylem.YAYINLA,
        nesne=plan,
        aciklama=f"{len(sahne_verileri)} sahne, {len(varliklar)} dosya",
    )
    return mevcut


# ---------------------------------------------------------------------------
# Yayın çözümleme — bir cihazın şu an ne oynatması gerektiği
# ---------------------------------------------------------------------------


def _saat_araliginda_mi(plan: EkranYayinPlani, simdi_saat: time) -> bool:
    bas, bit = plan.baslangic_saat, plan.bitis_saat
    if bas is None and bit is None:
        return True
    if bas is None:
        return simdi_saat <= bit
    if bit is None:
        return simdi_saat >= bas
    if bas <= bit:
        return bas <= simdi_saat <= bit
    # Gece yarısını aşan aralık (ör. 22:00–06:00)
    return simdi_saat >= bas or simdi_saat <= bit


def uygun_planlar(cihaz: EkranCihaz, an: datetime | None = None) -> list[EkranYayinPlani]:
    """Cihaza şu an uyan yayın planları, öncelik sırasıyla."""
    an = an or timezone.localtime()
    bugun: date = an.date()
    simdi_saat: time = an.time()
    hafta_gunu = bugun.weekday()

    hedef_kosulu = Q(tum_ekranlar=True) | Q(hedefler__cihaz=cihaz)
    if cihaz.konum_id:
        hedef_kosulu |= Q(hedefler__konum_id=cihaz.konum_id)

    adaylar = (
        EkranYayinPlani.objects.filter(
            Q(durum=EkranYayinPlani.Durum.YAYINDA),
            Q(aktif_paket__isnull=False),
            Q(baslangic_tarih__isnull=True) | Q(baslangic_tarih__lte=bugun),
            Q(bitis_tarih__isnull=True) | Q(bitis_tarih__gte=bugun),
            hedef_kosulu,
        )
        .select_related("aktif_paket", "liste")
        .distinct()
        .order_by("-oncelik", "-guncellenme")
    )

    sonuc = []
    for plan in adaylar:
        gunler = plan.gunler or []
        if gunler and hafta_gunu not in [int(g) for g in gunler]:
            continue
        if not _saat_araliginda_mi(plan, simdi_saat):
            continue
        sonuc.append(plan)
    return sonuc


def cakisan_planlar(cihaz: EkranCihaz, an: datetime | None = None) -> list[EkranYayinPlani]:
    """Aynı anda aynı cihaza denk gelen, kazanan dışındaki planlar.

    Yönetim paneli bunları "bu saatte iki yayın çakışıyor" uyarısı olarak
    gösterir; sistem yine de en yüksek öncelikliyi oynatır.
    """
    return uygun_planlar(cihaz, an)[1:]


def aktif_acil_duyuru(cihaz: EkranCihaz, an: datetime | None = None) -> EkranAcilDuyuru | None:
    an = an or timezone.now()
    kosul = Q(tum_ekranlar=True) | Q(cihazlar=cihaz)
    if cihaz.konum_id:
        kosul |= Q(konumlar__id=cihaz.konum_id)

    return (
        EkranAcilDuyuru.objects.filter(
            Q(aktif=True),
            Q(baslangic__lte=an),
            Q(bitis__isnull=True) | Q(bitis__gte=an),
            kosul,
        )
        .select_related("gorsel", "video")
        .distinct()
        .order_by("-baslangic")
        .first()
    )


def acil_duyuru_verisi(duyuru: EkranAcilDuyuru) -> dict:
    return {
        "id": duyuru.pk,
        "baslik": duyuru.baslik,
        "mesaj": duyuru.mesaj,
        "ton": duyuru.ton,
        "arka_plan_rengi": duyuru.arka_plan_rengi,
        "gorsel": _medya_url(duyuru.gorsel.dosya) if duyuru.gorsel else "",
        "video": _medya_url(duyuru.video.dosya) if duyuru.video else "",
        "sesli_uyari": duyuru.sesli_uyari,
        "bitis": duyuru.bitis.isoformat() if duyuru.bitis else None,
    }


@dataclass
class CihazDurumu:
    """Televizyonun yoklama isteğine verilen yanıt."""

    damga: str
    plan: EkranYayinPlani | None
    acil: EkranAcilDuyuru | None
    yeniden_yukle: bool

    def sozluk(self, sunucu_zamani: datetime) -> dict:
        veri = {
            "damga": self.damga,
            "sunucu_zamani": sunucu_zamani.isoformat(),
            "yoklama_sn": YOKLAMA_ARALIGI_SN,
            "yeniden_yukle": self.yeniden_yukle,
            "acil": acil_duyuru_verisi(self.acil) if self.acil else None,
        }
        if self.plan:
            veri["plan_ad"] = self.plan.ad
        return veri


def cihaz_durumu(cihaz: EkranCihaz, an: datetime | None = None) -> CihazDurumu:
    """Cihazın oynatması gereken yayının damgası + acil duyuru durumu.

    Damga; yayın paketini, acil duyuruyu ve yeniden yükleme isteğini birlikte
    özetler. Televizyon damgayı karşılaştırır, değiştiyse paketi çeker.
    """
    an = an or timezone.localtime()
    planlar = uygun_planlar(cihaz, an)
    plan = planlar[0] if planlar else None
    acil = aktif_acil_duyuru(cihaz, an)

    parcalar = [
        plan.aktif_paket.damga if plan and plan.aktif_paket else "bos",
        f"acil:{acil.pk}:{acil.baslangic.isoformat()}" if acil else "acil:yok",
    ]
    damga = hashlib.sha256("|".join(parcalar).encode("utf-8")).hexdigest()[:32]

    return CihazDurumu(
        damga=damga,
        plan=plan,
        acil=acil,
        yeniden_yukle=cihaz.yeniden_yukle_istegi,
    )


def yayin_paketi_verisi(cihaz: EkranCihaz, an: datetime | None = None) -> dict:
    """Televizyonun indireceği tam paket.

    Yayın yoksa boş bir "bekleme" paketi döner; televizyonda asla teknik hata
    metni görünmez, kurumsal bekleme ekranı gösterilir.
    """
    durum = cihaz_durumu(cihaz, an)
    plan = durum.plan

    if plan is None or plan.aktif_paket is None:
        govde = {
            "damga": durum.damga,
            "bos": True,
            "sahneler": [],
            "varliklar": [],
            "dongu": True,
            "mesaj": "Bu ekran için planlanmış bir yayın yok.",
        }
    else:
        govde = dict(plan.aktif_paket.veri or {})
        govde["bos"] = False
        govde["damga"] = durum.damga
        govde["paket_damgasi"] = plan.aktif_paket.damga

    govde["acil"] = acil_duyuru_verisi(durum.acil) if durum.acil else None
    govde["sunucu_zamani"] = (an or timezone.localtime()).isoformat()
    govde["yoklama_sn"] = YOKLAMA_ARALIGI_SN
    govde["cihaz"] = {
        "ad": cihaz.gorunen_ad,
        "konum": cihaz.konum.ad if cihaz.konum else "",
        "yonelim": cihaz.yonelim,
    }
    return govde


# ---------------------------------------------------------------------------
# Cihaz nabzı
# ---------------------------------------------------------------------------


def nabiz_isle(
    cihaz: EkranCihaz,
    *,
    ip: str | None = None,
    tarayici: str = "",
    surum: str = "",
    cozunurluk: tuple[int, int] | None = None,
) -> None:
    """Nabzı kaydeder — ama en fazla ``NABIZ_YAZMA_ARALIGI_SN`` sıklıkta.

    Televizyon 10 sn'de bir yoklama yapar. Her yoklamada satır yazmak veya
    tabloyu güncellemek, 256 MB'lık veritabanında gereksiz yazma yüküdür.
    Çevrim içi/dışı geçişi ise her zaman olay olarak kaydedilir.
    """
    simdi = timezone.now()
    onceki_cevrimici = cihaz.cevrimici_mi

    guncellenecek = []
    if (
        cihaz.son_baglanti is None
        or (simdi - cihaz.son_baglanti).total_seconds() >= NABIZ_YAZMA_ARALIGI_SN
    ):
        cihaz.son_baglanti = simdi
        guncellenecek.append("son_baglanti")

    if ip and cihaz.son_ip != ip:
        cihaz.son_ip = ip
        guncellenecek.append("son_ip")
    if tarayici and cihaz.tarayici != tarayici[:255]:
        cihaz.tarayici = tarayici[:255]
        guncellenecek.append("tarayici")
    if surum and cihaz.uygulama_surumu != surum[:40]:
        cihaz.uygulama_surumu = surum[:40]
        guncellenecek.append("uygulama_surumu")
    if cozunurluk and tuple(cozunurluk) != (cihaz.cozunurluk_genislik, cihaz.cozunurluk_yukseklik):
        cihaz.cozunurluk_genislik, cihaz.cozunurluk_yukseklik = cozunurluk
        cihaz.yonelim = (
            EkranCihaz.Yonelim.DIKEY if cozunurluk[1] > cozunurluk[0] else EkranCihaz.Yonelim.YATAY
        )
        guncellenecek += ["cozunurluk_genislik", "cozunurluk_yukseklik", "yonelim"]

    if guncellenecek:
        cihaz.save(update_fields=guncellenecek + ["guncellenme"])

    if not onceki_cevrimici:
        EkranCihazOlayi.objects.create(cihaz=cihaz, tur=EkranCihazOlayi.Tur.CEVRIMICI)


def yayin_alindi_bildir(cihaz: EkranCihaz, damga: str, paket: EkranYayinPaketi | None = None) -> None:
    if cihaz.son_yayin_damgasi == damga:
        return
    cihaz.son_yayin_damgasi = damga
    cihaz.son_basarili_guncelleme = timezone.now()
    cihaz.yeniden_yukle_istegi = False
    cihaz.save(
        update_fields=[
            "son_yayin_damgasi",
            "son_basarili_guncelleme",
            "yeniden_yukle_istegi",
            "guncellenme",
        ]
    )
    EkranCihazOlayi.objects.create(
        cihaz=cihaz,
        tur=EkranCihazOlayi.Tur.YAYIN_ALINDI,
        yayin_damgasi=damga,
    )


# ---------------------------------------------------------------------------
# İşlem kaydı
# ---------------------------------------------------------------------------


def islem_kaydet(kullanici, eylem: str, *, nesne=None, aciklama: str = "", ip: str | None = None) -> None:
    EkranIslemKaydi.objects.create(
        kullanici=kullanici if (kullanici and getattr(kullanici, "is_authenticated", False)) else None,
        eylem=eylem,
        nesne_tipi=type(nesne).__name__ if nesne is not None else "",
        nesne_id=getattr(nesne, "pk", None),
        aciklama=aciklama[:500],
        ip=ip,
    )


def istek_ip(request) -> str | None:
    iletilen = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return iletilen or request.META.get("REMOTE_ADDR") or None


# ---------------------------------------------------------------------------
# Tek tıkla gönderme
# ---------------------------------------------------------------------------
#
# Kullanıcı bir pano hazırlayıp "Ekranlara gönder" dediğinde araya oynatma
# listesi ve yayın planı kurma adımları girmemeli. Aşağıdaki yardımcılar bu
# kayıtları panonun arkasında sessizce yönetir: kullanıcı yalnız panoyu ve
# hangi ekranlara gideceğini bilir.
#
# Zamanlama/öncelik katmanı yerinde duruyor; bu sadece onun üzerine geçilmiş
# kısa yol. İleride "sınav haftası akışı" gibi bir ihtiyaç çıkarsa aynı
# modeller üzerinden kurulabilir.

PANO_LISTE_ONEKI = "__pano__"
PANO_PLAN_ONEKI = "__pano__"


def _pano_listesi(proje: EkranProje, kullanici=None) -> EkranOynatmaListesi:
    """Panoya ait gizli oynatma listesi; sahneleri sırayla içerir."""
    liste, _ = EkranOynatmaListesi.objects.get_or_create(
        ad=f"{PANO_LISTE_ONEKI}{proje.pk}",
        defaults={
            "aciklama": f"“{proje.ad}” panosunun yayın akışı (otomatik)",
            "donguye_al": True,
            "olusturan": kullanici if (kullanici and kullanici.is_authenticated) else None,
        },
    )

    # Sahneler değişmiş olabilir; listeyi panonun güncel hâline eşitle.
    sahneler = list(EkranSahne.objects.filter(proje=proje, aktif=True).order_by("sira", "id"))
    EkranOynatmaOgesi.objects.filter(liste=liste).exclude(
        sahne_id__in=[s.pk for s in sahneler]
    ).delete()
    for sira, sahne in enumerate(sahneler):
        EkranOynatmaOgesi.objects.update_or_create(
            liste=liste, sahne=sahne, defaults={"sira": sira, "aktif": True}
        )
    return liste


def _pano_plani(proje: EkranProje, kullanici=None) -> EkranYayinPlani:
    liste = _pano_listesi(proje, kullanici=kullanici)
    plan, yeni = EkranYayinPlani.objects.get_or_create(
        ad=f"{PANO_PLAN_ONEKI}{proje.pk}",
        defaults={
            "liste": liste,
            "oncelik": 10,
            "tum_ekranlar": False,
            "olusturan": kullanici if (kullanici and kullanici.is_authenticated) else None,
        },
    )
    if not yeni and plan.liste_id != liste.pk:
        plan.liste = liste
        plan.save(update_fields=["liste", "guncellenme"])
    return plan


@transaction.atomic
def panoyu_ekranlara_gonder(
    proje: EkranProje,
    *,
    tum_ekranlar: bool = False,
    cihazlar=None,
    konumlar=None,
    kullanici=None,
) -> tuple[EkranYayinPaketi, list[EkranCihaz]]:
    """Panoyu seçilen ekranlara yayınlar. Hedef seçilmezse ``YayinHatasi``.

    Döndürdüğü ikinci değer, yayının gideceği ekranların listesidir; arayüz
    kullanıcıya "şu kadar ekrana gönderildi" diyebilsin diye.
    """
    cihazlar = list(cihazlar or [])
    konumlar = list(konumlar or [])

    if not tum_ekranlar and not cihazlar and not konumlar:
        raise YayinHatasi(
            "Yayının gideceği ekranı seçin. Hiç ekran bağlı değilse önce "
            "televizyonu bağlamanız gerekir."
        )

    plan = _pano_plani(proje, kullanici=kullanici)
    plan.tum_ekranlar = tum_ekranlar
    plan.save(update_fields=["tum_ekranlar", "guncellenme"])

    EkranYayinHedefi.objects.filter(plan=plan).delete()
    if not tum_ekranlar:
        for konum in konumlar:
            EkranYayinHedefi.objects.create(plan=plan, konum=konum)
        for cihaz in cihazlar:
            EkranYayinHedefi.objects.create(plan=plan, cihaz=cihaz)

    paket = paket_derle(plan, kullanici=kullanici)
    return paket, pano_hedef_cihazlari(plan)


def pano_hedef_cihazlari(plan: EkranYayinPlani) -> list[EkranCihaz]:
    temel = EkranCihaz.objects.filter(durum=EkranCihaz.Durum.AKTIF).select_related("konum")
    if plan.tum_ekranlar:
        return list(temel)
    return list(
        temel.filter(
            Q(yayin_hedefleri__plan=plan) | Q(konum__yayin_hedefleri__plan=plan)
        ).distinct()
    )


def pano_yayin_durumu(proje: EkranProje) -> dict:
    """Panonun şu anki yayın durumu — arayüzdeki rozet için."""
    plan = EkranYayinPlani.objects.filter(ad=f"{PANO_PLAN_ONEKI}{proje.pk}").first()
    if plan is None or plan.aktif_paket is None:
        return {"yayinda": False, "ekranlar": [], "guncel": False, "zaman": None}

    cihazlar = pano_hedef_cihazlari(plan)
    return {
        "yayinda": plan.durum == EkranYayinPlani.Durum.YAYINDA,
        "ekranlar": cihazlar,
        # Pano yayınlandıktan sonra düzenlendiyse kullanıcı uyarılmalı.
        "guncel": not proje.kaydedilmemis_degisiklik,
        "zaman": plan.aktif_paket.olusturulma,
        "tum_ekranlar": plan.tum_ekranlar,
    }


def pano_getir(kullanici=None) -> EkranProje:
    """Kurumun panosu. Yoksa boş bir tane açar.

    Tek pano varsayımı kasıtlı: kullanıcı panele girdiğinde liste değil,
    doğrudan çalışma alanı görmeli. Birden çok pano gerekirse üstteki
    seçiciden yeni pano açılabilir.
    """
    proje = EkranProje.objects.exclude(durum=EkranProje.Durum.ARSIV).order_by("pk").first()
    if proje is None:
        proje = EkranProje.objects.create(
            ad="Duyuru Panosu",
            olusturan=kullanici if (kullanici and kullanici.is_authenticated) else None,
        )
    if not EkranSahne.objects.filter(proje=proje).exists():
        EkranSahne.objects.create(proje=proje, ad="Ekran 1", sira=0)
    return proje
