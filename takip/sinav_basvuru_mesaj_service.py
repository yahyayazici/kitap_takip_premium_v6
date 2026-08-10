"""Sınav başvurusu mesaj anı tetikleme ve gönderim."""

from __future__ import annotations

from typing import Iterable

from takip.models import (
    SinavBasvuru,
    SinavBasvuruMesajLog,
    SinavBasvuruMesajSablon,
)
from takip.whatsapp_service import (
    mesaj_gonder_metin,
    mesaj_gonder_template,
    telefon_normalize,
    whatsapp_yapilandirilmis,
)


def sablon_metnini_doldur(sablon: SinavBasvuruMesajSablon, basvuru: SinavBasvuru) -> str:
    ctx = {
        "ad_soyad": basvuru.ad_soyad or "",
        "sinav_adi": basvuru.sinav_adi or "",
        "il": basvuru.il or "",
        "ilce": basvuru.ilce or "",
        "baba_adi": basvuru.baba_adi or "",
        "anne_adi": basvuru.anne_adi or "",
    }
    try:
        return (sablon.metin or "").format(**ctx)
    except (KeyError, ValueError):
        metin = sablon.metin or ""
        for key, val in ctx.items():
            metin = metin.replace("{" + key + "}", val)
        return metin


def _alicilar(
    sablon: SinavBasvuruMesajSablon, basvuru: SinavBasvuru
) -> list[tuple[str, str]]:
    """(telefon, etiket) listesi."""
    sonuc: list[tuple[str, str]] = []
    if sablon.alici in (
        SinavBasvuruMesajSablon.Alici.BABA,
        SinavBasvuruMesajSablon.Alici.IKISI,
    ):
        if basvuru.baba_telefon:
            sonuc.append((basvuru.baba_telefon, "baba"))
    if sablon.alici in (
        SinavBasvuruMesajSablon.Alici.ANNE,
        SinavBasvuruMesajSablon.Alici.IKISI,
    ):
        if basvuru.anne_telefon:
            sonuc.append((basvuru.anne_telefon, "anne"))

    # Aynı numara iki kez gitmesin
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for tel, etiket in sonuc:
        norm = telefon_normalize(tel)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        uniq.append((tel, etiket))
    return uniq


def _gonder_bir(
    *,
    basvuru: SinavBasvuru,
    sablon: SinavBasvuruMesajSablon,
    telefon: str,
    alici_etiket: str,
    metin: str,
) -> SinavBasvuruMesajLog:
    log = SinavBasvuruMesajLog.objects.create(
        basvuru=basvuru,
        sablon=sablon,
        an_kodu=sablon.an_kodu,
        telefon=telefon_normalize(telefon) or telefon,
        alici_etiket=alici_etiket,
        metin=metin,
        durum=SinavBasvuruMesajLog.Durum.BEKLEMEDE,
    )

    if not whatsapp_yapilandirilmis():
        log.durum = SinavBasvuruMesajLog.Durum.ATLANDI
        log.provider_yanit = "WhatsApp pasif veya yapılandırılmamış."
        log.save(update_fields=["durum", "provider_yanit"])
        return log

    if sablon.wa_template_name:
        # Tek gövde parametreli genel template varsayımı: {{1}} = tam metin
        sonuc = mesaj_gonder_template(
            telefon,
            template_name=sablon.wa_template_name,
            language=sablon.wa_template_lang or "tr",
            body_params=[metin],
        )
    else:
        sonuc = mesaj_gonder_metin(telefon, metin)

    if sonuc.ok:
        log.durum = SinavBasvuruMesajLog.Durum.GONDERILDI
    else:
        log.durum = SinavBasvuruMesajLog.Durum.HATA
    log.provider_yanit = sonuc.yanit
    if sonuc.message_id:
        log.provider_yanit = f"{sonuc.message_id}\n{sonuc.yanit}"[:2000]
    log.save(update_fields=["durum", "provider_yanit"])
    return log


def basvuru_mesaji_gonder(
    basvuru: SinavBasvuru,
    an_kodu: str,
    *,
    sadece_aktif: bool = True,
) -> list[SinavBasvuruMesajLog]:
    try:
        sablon = SinavBasvuruMesajSablon.objects.get(an_kodu=an_kodu)
    except SinavBasvuruMesajSablon.DoesNotExist:
        return []

    if sadece_aktif and not sablon.aktif:
        return []

    metin = sablon_metnini_doldur(sablon, basvuru)
    loglar: list[SinavBasvuruMesajLog] = []
    for telefon, etiket in _alicilar(sablon, basvuru):
        loglar.append(
            _gonder_bir(
                basvuru=basvuru,
                sablon=sablon,
                telefon=telefon,
                alici_etiket=etiket,
                metin=metin,
            )
        )
    return loglar


def basvurularda_mesaj_gonder(
    basvurular: Iterable[SinavBasvuru],
    an_kodu: str,
    *,
    sadece_aktif: bool = True,
) -> dict[str, int]:
    ozet = {"gonderildi": 0, "hata": 0, "atlandi": 0, "toplam": 0}
    for basvuru in basvurular:
        for log in basvuru_mesaji_gonder(
            basvuru, an_kodu, sadece_aktif=sadece_aktif
        ):
            ozet["toplam"] += 1
            if log.durum == SinavBasvuruMesajLog.Durum.GONDERILDI:
                ozet["gonderildi"] += 1
            elif log.durum == SinavBasvuruMesajLog.Durum.HATA:
                ozet["hata"] += 1
            else:
                ozet["atlandi"] += 1
    return ozet


def durum_icin_mesaj_an(durum) -> str | None:
    """Durum nesnesi veya koduna göre tetiklenecek mesaj anı."""
    if durum is None:
        return None
    mesaj_kod = getattr(durum, "mesaj_an_kodu", None)
    if mesaj_kod:
        return str(mesaj_kod).strip() or None
    kod = getattr(durum, "kod", None) or str(durum)
    if kod in (
        SinavBasvuruMesajSablon.AnKodu.KABUL,
        SinavBasvuruMesajSablon.AnKodu.RED,
    ):
        return kod
    return None
