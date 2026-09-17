"""Yerleşik ekran şablonlarını oluşturur / günceller.

Deploy adımlarına eklenir (bkz. docker-start.sh). Yerleşik şablonlar
``yerlesik_mi=True`` ile işaretlenir; kullanıcının kendi şablonlarına
dokunulmaz.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from takip.ekran_models import EkranSablon, OgeTuru, TUVAL_GENISLIK, TUVAL_YUKSEKLIK
from takip.ekran_service import VARSAYILAN_ICERIK, VARSAYILAN_STIL

G = TUVAL_GENISLIK
Y = TUVAL_YUKSEKLIK


def oge(tur, ad, x, y, g, h, katman, *, stil=None, icerik=None):
    """Şablon öğesi. Stil/içerik varsayılanları üstüne yazılır."""
    temel_stil = dict(VARSAYILAN_STIL.get(tur, {}))
    temel_stil.update(stil or {})
    temel_icerik = dict(VARSAYILAN_ICERIK.get(tur, {}))
    temel_icerik.update(icerik or {})
    return {
        "tur": tur,
        "ad": ad,
        "x": x,
        "y": y,
        "g": g,
        "h": h,
        "donus": 0,
        "katman": katman,
        "opaklik": 1,
        "kilitli": False,
        "gorunur": True,
        "stil": temel_stil,
        "icerik": temel_icerik,
        "zamanlama": {},
        "animasyon": {},
    }


def sahne(ad, ogeler, arka_plan="#0f203c", sure_tipi="saniye", sure_sn=30):
    return {
        "ad": ad,
        "sure_tipi": sure_tipi,
        "sure_sn": sure_sn,
        "gecis": "soldur",
        "tuval": {"g": G, "y": Y},
        "arka_plan": {"renk": arka_plan, "gorsel": ""},
        "gruplar": [],
        "ogeler": ogeler,
    }


BANT_YUKSEKLIK = 88


def alt_bant(katman, metin="Duyuru metnini buraya yazın"):
    return oge(
        OgeTuru.KAYAN_BANT, "Alt duyuru bandı",
        0, Y - BANT_YUKSEKLIK, G, BANT_YUKSEKLIK, katman,
        stil={"punto": 34, "arka_plan": "#15427f", "ic_bosluk": 16},
        icerik={"duyurular": [metin]},
    )


def logo(katman, x=G - 300, y=36):
    return oge(OgeTuru.LOGO, "Kurum logosu", x, y, 240, 96, katman)


SABLONLAR = [
    {
        "anahtar": "tam-ekran-video",
        "ad": "Tam ekran video",
        "aciklama": "Video ekranı baştan sona kaplar, döngüde oynar.",
        "kategori": "Video",
        "sira": 10,
        "veri": sahne("Tam ekran video", [
            oge(OgeTuru.VIDEO, "Video", 0, 0, G, Y, 0,
                icerik={"sigdir": "doldur", "sessiz": True, "dongu": True}),
        ], sure_tipi="video_bitene"),
    },
    {
        "anahtar": "video-afis-soz",
        "ad": "Video + dikey afiş + alt söz",
        "aciklama": "Solda video, sağda dikey afiş, altta tek satır söz.",
        "kategori": "Karma",
        "sira": 20,
        "veri": sahne("Video + afiş + söz", [
            oge(OgeTuru.VIDEO, "Video", 40, 40, 1300, 780, 0,
                icerik={"sigdir": "doldur", "sessiz": True, "dongu": True}),
            oge(OgeTuru.GORSEL, "Dikey afiş", 1380, 40, 500, 780, 1,
                icerik={"sigdir": "doldur"}),
            oge(OgeTuru.METIN, "Söz", 40, 850, 1840, 180, 2,
                stil={"punto": 56, "kalinlik": 500, "hizalama": "center",
                      "arka_plan": "rgba(255,255,255,0.06)", "kose": 16, "ic_bosluk": 24},
                icerik={"sozler": [{"metin": "Sözü buraya yazın", "sure": 0}]}),
        ]),
    },
    {
        "anahtar": "tam-ekran-afis",
        "ad": "Tam ekran afiş",
        "aciklama": "Tek görsel ekranı kaplar.",
        "kategori": "Görsel",
        "sira": 30,
        "veri": sahne("Tam ekran afiş", [
            oge(OgeTuru.GORSEL, "Afiş", 0, 0, G, Y, 0, icerik={"sigdir": "doldur"}),
        ]),
    },
    {
        "anahtar": "tam-ekran-sunum",
        "ad": "Tam ekran sunum",
        "aciklama": "PDF sunum ekranı kaplar, sayfalar kendiliğinden ilerler.",
        "kategori": "Sunum",
        "sira": 40,
        "veri": sahne("Tam ekran sunum", [
            oge(OgeTuru.PDF, "Sunum", 0, 0, G, Y, 0,
                icerik={"sigdir": "icine", "ortak_sure": 12}),
        ], sure_tipi="pdf_bitene"),
    },
    {
        "anahtar": "sunum-afis",
        "ad": "Sunum + dikey afiş",
        "aciklama": "Solda sunum dönüyor, sağda dikey afiş, altta kayan duyuru.",
        "kategori": "Sunum",
        "sira": 50,
        "veri": sahne("Sunum + afiş", [
            oge(OgeTuru.PDF, "Sunum", 40, 40, 1300, Y - 80 - BANT_YUKSEKLIK, 0,
                icerik={"sigdir": "icine", "ortak_sure": 12}),
            oge(OgeTuru.GORSEL, "Dikey afiş", 1380, 40, 500, Y - 80 - BANT_YUKSEKLIK, 1,
                icerik={"sigdir": "doldur"}),
            alt_bant(2),
        ], sure_tipi="pdf_bitene"),
    },
    {
        "anahtar": "tam-ekran-soz",
        "ad": "Tam ekran söz",
        "aciklama": "Büyük punto vecize ya da kısa söz.",
        "kategori": "Metin",
        "sira": 60,
        "veri": sahne("Tam ekran söz", [
            oge(OgeTuru.METIN, "Söz", 160, 340, G - 320, 400, 0,
                stil={"punto": 110, "kalinlik": 600, "hizalama": "center", "golge_metin": True},
                icerik={"sozler": [{"metin": "Sözü buraya yazın", "sure": 0}]}),
            logo(1, 840, 820),
        ], arka_plan="#0b1a33", sure_sn=36),
    },
    {
        "anahtar": "geri-sayim",
        "ad": "Geri sayım",
        "aciklama": "Sınava kalan süre, yanında saat.",
        "kategori": "Bilgi",
        "sira": 70,
        "veri": sahne("Geri sayım", [
            oge(OgeTuru.GERI_SAYIM, "Geri sayım", 160, 300, G - 320, 420, 0,
                stil={"punto": 140, "arka_plan": "rgba(255,255,255,0.06)", "kose": 24, "ic_bosluk": 40},
                icerik={"baslik": "LGS'ye kalan süre"}),
            oge(OgeTuru.SAAT, "Saat", 760, 760, 400, 200, 1,
                stil={"punto": 64}),
        ]),
    },
    {
        "anahtar": "bos-tahta",
        "ad": "Boş tahta",
        "aciklama": "Sıfırdan kendin yerleştir.",
        "kategori": "Boş",
        "sira": 90,
        "veri": sahne("Boş tahta", []),
    },
]


class Command(BaseCommand):
    help = "Yerleşik ekran şablonlarını oluşturur veya günceller."

    def handle(self, *args, **secenekler):
        olusan = guncellenen = 0

        for tanim in SABLONLAR:
            sablon, yeni = EkranSablon.objects.update_or_create(
                anahtar=tanim["anahtar"],
                defaults={
                    "ad": tanim["ad"],
                    "aciklama": tanim["aciklama"],
                    "kategori": tanim["kategori"],
                    "sira": tanim["sira"],
                    "veri": tanim["veri"],
                    "yerlesik_mi": True,
                },
            )
            if yeni:
                olusan += 1
            else:
                guncellenen += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Ekran şablonları hazır: {olusan} yeni, {guncellenen} güncellendi."
            )
        )
