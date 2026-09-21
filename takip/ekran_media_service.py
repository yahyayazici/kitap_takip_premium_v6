"""Ekran medya kütüphanesi — yükleme, doğrulama, ön izleme üretimi.

Güvenlik notu
-------------
Dosya türü **uzantıya güvenilerek** belirlenmez. Her yüklemede içeriğin ilk
baytlarına (magic number) bakılır; uzantı ile içerik uyuşmazsa dosya
reddedilir. Bu, ``.jpg`` adıyla yüklenen bir HTML/SVG dosyasının medya
adresinden servis edilip tarayıcıda script çalıştırmasını (XSS) engeller.
SVG hiç kabul edilmez — script barındırabilen tek görsel formatıdır.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from takip.dosya_guvenlik import dosya_ozeti, icerik_turu_tespit_et, ilk_baytlar
from takip.ekran_models import EkranMedya, EkranMedyaSayfasi

logger = logging.getLogger(__name__)

# —— Sınırlar ——
MAKS_GORSEL_BAYT = 20 * 1024 * 1024        # 20 MB
MAKS_PDF_BAYT = 80 * 1024 * 1024           # 80 MB
# 400 MB'a kadar teknik olarak kabul edilebilirdi, ama sunucu yalnızca
# 4 eşzamanlı isteğe bakabiliyor (gunicorn 2 worker × 2 thread — bkz.
# start.sh). Django, dosyayı view çalışmadan ÖNCE tamamen okur; büyük bir
# video yavaş bir bağlantıdan yüklenirken o worker'ı DAKİKALARCA işgal
# eder ve aynı anda gelen diğer tüm istekler (site açma, panel, API)
# zaman aşımına uğrar — 2026-09-18'de tam bu yaşandı. 150 MB, ortalama
# bir tanıtım videosunu (1-2 dakika, 1080p, sıkıştırılmış) hâlâ
# karşılarken bu riski sınırlıyor.
MAKS_VIDEO_BAYT = 150 * 1024 * 1024        # 150 MB
MAKS_PDF_SAYFA = 120

# PDF sayfaları bu genişlikte PNG'ye çevrilir. 1600 px, 1920 tuvalde tam
# ekran gösterimde nettir ve dosya boyutunu makul tutar.
PDF_SAYFA_GENISLIK = 1600
ONIZLEME_GENISLIK = 480

GORSEL_UZANTILAR = {"png", "jpg", "jpeg", "webp"}
# .mov: Mac ve iPhone'un varsayılan biçimi. İçindeki kodek H.264 ise
# tarayıcılar MP4 gibi oynatır; HEVC ise oynatamaz (bkz. video_kodegi).
VIDEO_UZANTILAR = {"mp4", "webm", "m4v", "mov"}
PDF_UZANTILAR = {"pdf"}

VIDEO_MIME = {
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    # .mov, video/quicktime yerine video/mp4 olarak servis edilir: aynı
    # H.264 akışını taşır ve tarayıcılar bu MIME ile sorunsuz oynatır.
    "mov": "video/mp4",
    "webm": "video/webm",
}


class MedyaHatasi(Exception):
    """Kullanıcıya olduğu gibi gösterilebilecek, anlaşılır Türkçe hata."""


@dataclass
class YuklemeSonucu:
    medya: EkranMedya
    yeni_mi: bool


# ---------------------------------------------------------------------------
# İçerik tanıma
# ---------------------------------------------------------------------------


_UZANTI_ICERIK = {
    "png": {"png"},
    "jpg": {"jpeg"},
    "jpeg": {"jpeg"},
    "webp": {"webp"},
    "pdf": {"pdf"},
    # MP4 ve MOV aynı ISO taban biçimini paylaşır ("ftyp" imzası).
    "mp4": {"mp4"},
    "m4v": {"mp4"},
    "mov": {"mp4"},
    "webm": {"webm"},
}


def dosya_turunu_belirle(dosya: UploadedFile) -> tuple[str, str, str]:
    """(medya_turu, uzanti, mime) döndürür; uyumsuzsa MedyaHatasi yükseltir."""
    ad = (dosya.name or "").strip()
    if "." not in ad:
        raise MedyaHatasi("Dosyanın uzantısı okunamadı. Lütfen PNG, JPG, WEBP, PDF veya MP4 yükleyin.")

    uzanti = ad.rsplit(".", 1)[-1].lower()

    if uzanti in GORSEL_UZANTILAR:
        medya_turu = EkranMedya.Tur.GORSEL
        sinir, sinir_adi = MAKS_GORSEL_BAYT, "20 MB"
    elif uzanti in PDF_UZANTILAR:
        medya_turu = EkranMedya.Tur.PDF
        sinir, sinir_adi = MAKS_PDF_BAYT, "80 MB"
    elif uzanti in VIDEO_UZANTILAR:
        medya_turu = EkranMedya.Tur.VIDEO
        sinir, sinir_adi = MAKS_VIDEO_BAYT, "150 MB"
    else:
        raise MedyaHatasi(
            f"“.{uzanti}” dosyaları desteklenmiyor. "
            "Görsel için PNG, JPG veya WEBP; belge için PDF; "
            "video için MP4, MOV veya WEBM kullanın."
        )

    if dosya.size > sinir:
        raise MedyaHatasi(
            f"Dosya çok büyük ({dosya.size / 1024 / 1024:.1f} MB). "
            f"Bu tür için üst sınır {sinir_adi}."
        )

    gercek = icerik_turu_tespit_et(ilk_baytlar(dosya))
    if gercek is None or gercek not in _UZANTI_ICERIK[uzanti]:
        raise MedyaHatasi(
            "Dosyanın içeriği uzantısıyla uyuşmuyor. "
            "Dosya bozulmuş olabilir; lütfen kaynağından yeniden kaydedip deneyin."
        )

    if medya_turu == EkranMedya.Tur.VIDEO:
        mime = VIDEO_MIME.get(uzanti, "video/mp4")
    elif medya_turu == EkranMedya.Tur.PDF:
        mime = "application/pdf"
    else:
        mime = f"image/{'jpeg' if gercek == 'jpeg' else gercek}"

    return medya_turu, uzanti, mime


def video_kodegi(dosya: UploadedFile) -> str:
    """Videonun görüntü kodeğini dosyanın kendisinden okur.

    Neden gerekli: iPhone ve yeni Mac'ler videoyu varsayılan olarak HEVC
    (H.265) kaydeder. Bu kodek televizyon tarayıcılarının çoğunda ve
    Chrome'un birçok sürümünde oynatılamaz — dosya sorunsuz yüklenir, sonra
    televizyonda siyah kare olarak durur. Sorunu yükleme anında yakalamak,
    kurum koridorundaki ekranın sessizce bozulmasından iyidir.

    ISO taban biçiminde (MP4/MOV) kodek, ``stsd`` kutusundaki dört harflik
    etikettir: ``avc1`` H.264, ``hvc1``/``hev1`` HEVC. Bu etiketleri dosya
    içinde arıyoruz; ``moov`` kutusu bazı dosyalarda sonda olduğu için tüm
    dosya taranır (zaten özet için de baştan sona okunuyor).

    Döndürür: "h264", "hevc" ya da "bilinmiyor".
    """
    dosya.seek(0)
    bulunan = "bilinmiyor"
    onceki = b""
    try:
        while True:
            parca = dosya.read(1024 * 1024)
            if not parca:
                break
            # Etiket parça sınırına denk gelirse kaçmasın diye örtüşme.
            tampon = onceki + parca
            if b"avc1" in tampon:
                return "h264"
            if b"hvc1" in tampon or b"hev1" in tampon:
                bulunan = "hevc"
            onceki = tampon[-8:]
    finally:
        dosya.seek(0)
    return bulunan


# ---------------------------------------------------------------------------
# Ön izleme / sayfa üretimi
# ---------------------------------------------------------------------------


def _pillow():
    from PIL import Image  # yerel import: Pillow yalnız yükleme anında gerekir

    return Image


def _beyaza_yerlestir(gorsel):
    """Saydam alanları beyaza oturtur.

    PDF sayfaları ve saydam PNG'ler alfa kanalıyla gelir. Ön izleme JPEG'e
    çevrilirken doğrudan ``convert("RGB")`` demek saydam bölgeleri SİYAH
    yapar; belge sayfaları bu yüzden kapkara görünürdü.
    """
    Image = _pillow()
    if gorsel.mode in ("RGBA", "LA") or (gorsel.mode == "P" and "transparency" in gorsel.info):
        alfali = gorsel.convert("RGBA")
        zemin = Image.new("RGB", alfali.size, (255, 255, 255))
        zemin.paste(alfali, mask=alfali.split()[-1])
        return zemin
    if gorsel.mode not in ("RGB", "L"):
        return gorsel.convert("RGB")
    return gorsel


def _onizleme_uret(kaynak: "object", genislik: int = ONIZLEME_GENISLIK) -> tuple[bytes, int, int]:
    """PIL görüntüsünden JPEG ön izleme üretir."""
    Image = _pillow()
    gorsel = _beyaza_yerlestir(kaynak)
    asil_w, asil_h = gorsel.size
    if asil_w > genislik:
        oran = genislik / asil_w
        gorsel = gorsel.resize((genislik, max(1, int(asil_h * oran))), Image.LANCZOS)
    tampon = io.BytesIO()
    gorsel.save(tampon, format="JPEG", quality=82, optimize=True)
    return tampon.getvalue(), asil_w, asil_h


def gorsel_bilgisi(dosya: UploadedFile) -> tuple[int, int, bytes | None]:
    Image = _pillow()
    dosya.seek(0)
    try:
        with Image.open(dosya) as gorsel:
            gorsel.load()
            onizleme, w, h = _onizleme_uret(gorsel)
    except Exception as hata:  # bozuk/eksik görsel
        raise MedyaHatasi("Görsel açılamadı. Dosya bozuk olabilir.") from hata
    finally:
        dosya.seek(0)
    return w, h, onizleme


def pdf_sayfalarini_uret(medya: EkranMedya) -> int:
    """PDF'i sayfa sayfa PNG'ye çevirip ``EkranMedyaSayfasi`` kayıtları yazar.

    Televizyon tarafında PDF motoru çalıştırmamak için gereklidir: sayfalar
    hazır görsel olarak servis edilir, böylece geçişler akıcı olur ve
    çevrim dışı önbelleğe alınabilir.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        medya.islem_durumu = EkranMedya.IslemDurumu.HATA
        medya.islem_notu = (
            "PDF sayfa görselleri üretilemedi: sunucuda pypdfium2 kurulu değil. "
            "Dosya yüklendi ancak ekranda gösterilemez."
        )
        medya.save(update_fields=["islem_durumu", "islem_notu", "guncellenme"])
        logger.error("pypdfium2 kurulu değil — PDF #%s işlenemedi", medya.pk)
        return 0

    Image = _pillow()

    # Yeniden üretimde eski sayfa görselleri DİSKTEN de silinmeli.
    # Queryset.delete() yalnız satırları kaldırır; dosyalar sahipsiz kalıp
    # depoyu doldururdu (PDF her yeniden işlendiğinde bir kopya daha).
    for eski_sayfa in medya.sayfalar.all():
        eski_sayfa.gorsel.delete(save=False)
    medya.sayfalar.all().delete()

    if medya.onizleme:
        medya.onizleme.delete(save=False)

    try:
        medya.dosya.open("rb")
        ham = medya.dosya.read()
    finally:
        medya.dosya.close()

    try:
        belge = pdfium.PdfDocument(ham)
    except Exception as hata:
        medya.islem_durumu = EkranMedya.IslemDurumu.HATA
        medya.islem_notu = "PDF okunamadı. Dosya şifreli veya bozuk olabilir."
        medya.save(update_fields=["islem_durumu", "islem_notu", "guncellenme"])
        logger.warning("PDF #%s açılamadı: %s", medya.pk, hata)
        return 0

    yazilan = 0
    ilk_onizleme: bytes | None = None
    # Sayfa sayısı belge kapatılmadan okunmalı; finally bloğundan sonra
    # belge işaretçisi geçersiz olur.
    toplam_sayfa = len(belge)
    try:
        toplam = min(toplam_sayfa, MAKS_PDF_SAYFA)
        for indeks in range(toplam):
            sayfa = belge[indeks]
            genislik_pt = sayfa.get_width() or 1
            olcek = max(0.5, min(4.0, PDF_SAYFA_GENISLIK / genislik_pt))
            # fill_color: sayfa beyaz kâğıt üzerine çizilir. Aksi hâlde
            # görüntü saydam gelir ve koyu zeminli bir sahnede belge
            # siyah görünür.
            gorsel = sayfa.render(scale=olcek, fill_color=(255, 255, 255, 255)).to_pil()
            if gorsel.mode != "RGB":
                gorsel = _beyaza_yerlestir(gorsel)

            tampon = io.BytesIO()
            gorsel.save(tampon, format="PNG", optimize=True)
            sayfa_kaydi = EkranMedyaSayfasi(
                medya=medya,
                sira=indeks,
                genislik=gorsel.width,
                yukseklik=gorsel.height,
            )
            sayfa_kaydi.gorsel.save(
                f"{medya.pk}-s{indeks + 1}.png",
                ContentFile(tampon.getvalue()),
                save=False,
            )
            sayfa_kaydi.save()
            yazilan += 1

            if indeks == 0:
                ilk_onizleme, _, _ = _onizleme_uret(gorsel)
                medya.genislik = gorsel.width
                medya.yukseklik = gorsel.height

            sayfa.close()
    finally:
        belge.close()

    if ilk_onizleme:
        medya.onizleme.save(f"{medya.pk}-onizleme.jpg", ContentFile(ilk_onizleme), save=False)

    medya.sayfa_sayisi = yazilan
    medya.islem_durumu = EkranMedya.IslemDurumu.HAZIR
    medya.islem_notu = (
        f"İlk {MAKS_PDF_SAYFA} sayfa alındı." if toplam_sayfa > MAKS_PDF_SAYFA else ""
    )
    medya.save()
    return yazilan


# ---------------------------------------------------------------------------
# Yükleme
# ---------------------------------------------------------------------------


@transaction.atomic
def medya_yukle(
    dosya: UploadedFile,
    *,
    kullanici=None,
    ad: str = "",
    klasor=None,
    video_sure_sn: float = 0,
) -> YuklemeSonucu:
    """Dosyayı doğrular, aynısı varsa mevcut kaydı döndürür, yoksa kaydeder.

    ``video_sure_sn`` tarayıcının okuduğu süredir (stüdyo yükleme sırasında
    gönderir); sunucuda ffmpeg bulundurmamak için böyle çözülmüştür.
    """
    medya_turu, uzanti, mime = dosya_turunu_belirle(dosya)
    ozet = dosya_ozeti(dosya)

    mevcut = EkranMedya.objects.filter(sha256=ozet).first()
    if mevcut is not None:
        return YuklemeSonucu(medya=mevcut, yeni_mi=False)

    gorunen_ad = (ad or "").strip() or (dosya.name or "medya").rsplit(".", 1)[0]

    medya = EkranMedya(
        ad=gorunen_ad[:200],
        orijinal_ad=(dosya.name or "")[:255],
        tur=medya_turu,
        klasor=klasor,
        sha256=ozet,
        boyut=dosya.size,
        mime=mime,
        yukleyen=kullanici if (kullanici and kullanici.is_authenticated) else None,
    )

    if medya_turu == EkranMedya.Tur.GORSEL:
        genislik, yukseklik, onizleme = gorsel_bilgisi(dosya)
        medya.genislik, medya.yukseklik = genislik, yukseklik
        medya.dosya.save(f"{ozet[:16]}.{uzanti}", dosya, save=False)
        if onizleme:
            medya.onizleme.save(f"{ozet[:16]}-onizleme.jpg", ContentFile(onizleme), save=False)
        medya.save()

    elif medya_turu == EkranMedya.Tur.PDF:
        medya.islem_durumu = EkranMedya.IslemDurumu.ISLENIYOR
        medya.dosya.save(f"{ozet[:16]}.pdf", dosya, save=False)
        medya.save()
        pdf_sayfalarini_uret(medya)

    else:  # video
        if video_kodegi(dosya) == "hevc":
            raise MedyaHatasi(
                "Bu video HEVC (H.265) biçiminde kaydedilmiş; televizyon "
                "tarayıcıları bu biçimi oynatamaz, ekranda siyah kalır.\n"
                "Mac'te çözüm: videoyu QuickTime Player ile açın → "
                "Dosya → Dışa Aktar → 1080p seçin. Çıkan dosyayı yükleyin.\n"
                "iPhone'da kalıcı çözüm: Ayarlar → Kamera → Biçimler → "
                "“En Uyumlu”."
            )
        medya.sure_sn = max(0.0, float(video_sure_sn or 0))
        medya.dosya.save(f"{ozet[:16]}.{uzanti}", dosya, save=False)
        medya.save()

    return YuklemeSonucu(medya=medya, yeni_mi=True)


def medya_silinebilir_mi(medya: EkranMedya) -> tuple[bool, str]:
    """Kullanımdaki dosya silinemez — kullanıcıya nerede kullanıldığı söylenir."""
    kullanan_ogeler = list(
        medya.ogeler.select_related("sahne__proje")[:5]
    ) + list(medya.oge_kaynaklari.select_related("oge__sahne__proje")[:5])

    if not kullanan_ogeler:
        arka_planlar = list(medya.arka_plan_sahneleri.select_related("proje")[:5])
        if arka_planlar:
            adlar = ", ".join(sorted({s.proje.ad for s in arka_planlar}))
            return False, f"Bu dosya şu tasarımlarda arka plan olarak kullanılıyor: {adlar}"
        return True, ""

    proje_adlari = set()
    for kayit in kullanan_ogeler:
        oge = getattr(kayit, "oge", kayit)
        proje_adlari.add(oge.sahne.proje.ad)

    adlar = ", ".join(sorted(proje_adlari))
    return False, f"Bu dosya şu tasarımlarda kullanılıyor: {adlar}. Önce oradan çıkarın."
