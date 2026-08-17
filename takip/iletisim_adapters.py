"""İletişim Merkezi — kaynak modül adaptörleri."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.utils.formats import date_format

from config.branding import PANEL_ORG
from takip.iletisim_service import (
    PaylasimEkiVerisi,
    PaylasimPaketVerisi,
    kaynak_imza_uret,
    kurum_ayarlari,
    paket_bul_veya_guncelle,
)
from takip.iletisim_models import IletisimPaketi
from takip.ktt_models import KttSinav, KttSonucu
from takip.ktt_service import yetkili_ktt_sinavlari


def _hitap_metni() -> str:
    return kurum_ayarlari().varsayilan_hitap or "Değerli Velilerimiz,"


def ktt_hedef_etiket(ktt: KttSinav) -> str:
    if ktt.hedef_siniflar.strip():
        return f"{ktt.hedef_siniflar.strip()} Velileri"
    return f"{ktt.sinif_seviyesi}. Sınıf Velileri"


def ktt_konu_metni(ktt: KttSinav) -> str:
    if ktt.konu_katalog_id:
        try:
            ad = (ktt.konu_katalog.konu_ad or "").strip()
        except ObjectDoesNotExist:
            ad = ""
        if ad:
            return ad
    ham = (ktt.konu_ham_ad or "").strip()
    if ham:
        return ham
    return ktt.ad


def ktt_mesaj_baglam(ktt: KttSinav) -> dict[str, str]:
    return {
        "hitap": _hitap_metni().replace("Velimiz", "Velilerimiz"),
        "ktt_adi": ktt.ad,
        "ders": ktt.ders.ad,
        "konu": ktt_konu_metni(ktt),
        "sinif": ktt.hedef_siniflar or ktt.sinif_seviyesi,
        "grup": ktt.hedef_siniflar or ktt.sinif_seviyesi,
        "tarih": date_format(ktt.sinav_tarihi, "d F Y"),
        "kurum": PANEL_ORG,
    }


def ktt_paylasim_hazir_mi(ktt: KttSinav) -> bool:
    return KttSonucu.objects.filter(ktt=ktt).exists()


def ktt_kaynak_imza(ktt: KttSinav) -> str:
    sonuc_say = KttSonucu.objects.filter(ktt=ktt).count()
    return kaynak_imza_uret(
        ktt.pk,
        ktt.guncellenme.isoformat(),
        sonuc_say,
        ktt.soru_sayisi,
        ktt.hedef_siniflar,
    )


def ktt_paket_hazirla(user: User, ktt: KttSinav, request) -> IletisimPaketi:
    from takip.iletisim_pdf_service import ktt_pdf_bytes

    if not ktt_paylasim_hazir_mi(ktt):
        raise ValueError("KTT sonuçları henüz girilmemiş.")

    pdf_bytes, dosya_adi = ktt_pdf_bytes(request, ktt)
    if not pdf_bytes:
        raise ValueError("KTT PDF oluşturulamadı.")

    baslik = f"{ktt.hedef_siniflar or ktt.sinif_seviyesi} · {ktt.ders.ad} · {ktt.ad}"
    veri = PaylasimPaketVerisi(
        baslik=baslik,
        kaynak_modul=IletisimPaketi.KaynakModul.KTT,
        kaynak_tur="ktt_sonuc_grup",
        kaynak_id=str(ktt.pk),
        kaynak_imza=ktt_kaynak_imza(ktt),
        hedef_tur=IletisimPaketi.HedefTur.SINIF_VELILERI,
        hedef_etiket=ktt_hedef_etiket(ktt),
        sablon_kod="ktt-sonuc",
        mesaj_baglam=ktt_mesaj_baglam(ktt),
        ekler=[
            PaylasimEkiVerisi(
                dosya_bytes=pdf_bytes,
                dosya_adi=dosya_adi,
                kaynak_modul="ktt",
                kaynak_id=str(ktt.pk),
            )
        ],
    )
    paket, _ = paket_bul_veya_guncelle(user, veri)
    return paket


def ktt_hazir_kuyruk(user: User, limit: int = 12) -> list[dict]:
    """Paylaşılmaya hazır KTT kayıtları — hafif sorgu."""
    ktt_ids = list(
        KttSonucu.objects.values_list("ktt_id", flat=True)
        .distinct()[:50]
    )
    if not ktt_ids:
        return []
    sinavlar = (
        yetkili_ktt_sinavlari(user)
        .filter(pk__in=ktt_ids, aktif=True)
        .select_related("ders")
        .order_by("-sinav_tarihi")[:limit]
    )
    sonuc: list[dict] = []
    for ktt in sinavlar:
        sonuc.append(
            {
                "modul": "ktt",
                "modul_label": "KTT Sonuçları",
                "baslik": ktt.ad,
                "alt": f"{ktt.hedef_siniflar or ktt.sinif_seviyesi} · {ktt.ders.ad} · {ktt_konu_metni(ktt)}",
                "kaynak_id": ktt.pk,
                "tarih": ktt.sinav_tarihi,
                "hazirla_url": f"/iletisim/hazirla/ktt/{ktt.pk}/",
                "onizleme_url": None,
            }
        )
    return sonuc


def kaynak_paket_hazirla(user: User, modul: str, kaynak_id: int, request) -> IletisimPaketi:
    if modul == "ktt":
        ktt = yetkili_ktt_sinavlari(user).filter(pk=kaynak_id).first()
        if not ktt:
            raise PermissionError("Bu KTT kaydına erişiminiz yok.")
        return ktt_paket_hazirla(user, ktt, request)
    raise ValueError(f"Henüz desteklenmeyen modül: {modul}")
