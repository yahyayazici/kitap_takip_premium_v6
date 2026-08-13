"""İletişim Merkezi — şablon, paket ve paylaşım servisi."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils.text import slugify

from config.branding import PANEL_ORG
from takip.iletisim_models import (
    IletisimEki,
    IletisimKurumAyar,
    IletisimOlay,
    IletisimPaketi,
    IletisimSablon,
)
from takip.permissions.service import can

PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")

DEGISKEN_ETIKETLER: dict[str, str] = {
    "talebe_adi": "Talebe adı",
    "veli_adi": "Veli adı",
    "sinif": "Sınıf",
    "grup": "Grup",
    "ders": "Ders",
    "konu": "Konu",
    "ktt_adi": "KTT adı",
    "deneme_adi": "Deneme adı",
    "kitap_adi": "Kitap adı",
    "puan": "Puan",
    "tarih": "Tarih",
    "kurum": "Kurum adı",
}

MODUL_DEGISKENLERI: dict[str, frozenset[str]] = {
    "ktt": frozenset(
        {"talebe_adi", "veli_adi", "sinif", "grup", "ders", "konu", "ktt_adi", "tarih", "kurum"}
    ),
    "deneme": frozenset(
        {"talebe_adi", "veli_adi", "sinif", "grup", "deneme_adi", "puan", "tarih", "kurum"}
    ),
    "kitap": frozenset({"talebe_adi", "veli_adi", "sinif", "kitap_adi", "tarih", "kurum"}),
    "karne": frozenset({"talebe_adi", "veli_adi", "sinif", "tarih", "kurum"}),
    "dini_egitim": frozenset({"talebe_adi", "veli_adi", "sinif", "tarih", "kurum"}),
    "program": frozenset({"sinif", "grup", "tarih", "kurum"}),
    "yazili": frozenset({"talebe_adi", "veli_adi", "sinif", "ders", "tarih", "kurum"}),
    "duyuru": frozenset({"sinif", "grup", "tarih", "kurum"}),
    "manuel": frozenset(DEGISKEN_ETIKETLER.keys()),
}


@dataclass
class SablonRenderSonuc:
    metin: str
    eksik: list[str] = field(default_factory=list)
    hata: str = ""


@dataclass
class PaylasimEkiVerisi:
    dosya_bytes: bytes
    dosya_adi: str
    mime_type: str = "application/pdf"
    talebe_id: int | None = None
    kaynak_modul: str = ""
    kaynak_id: str = ""


@dataclass
class PaylasimPaketVerisi:
    baslik: str
    kaynak_modul: str
    kaynak_tur: str
    kaynak_id: str
    kaynak_imza: str
    hedef_tur: str
    hedef_etiket: str
    sablon_kod: str
    mesaj_baglam: dict[str, str]
    ekler: list[PaylasimEkiVerisi] = field(default_factory=list)
    sinif_sube_id: int | None = None
    talebe_id: int | None = None
    durum: str = IletisimPaketi.Durum.HAZIR


def kurum_ayarlari() -> IletisimKurumAyar:
    ayar, _ = IletisimKurumAyar.objects.get_or_create(pk=1)
    return ayar


def sablon_degiskenleri(modul: str) -> list[tuple[str, str]]:
    keys = MODUL_DEGISKENLERI.get(modul, MODUL_DEGISKENLERI["manuel"])
    return [(k, DEGISKEN_ETIKETLER[k]) for k in sorted(keys) if k in DEGISKEN_ETIKETLER]


def sablon_render(
    sablon: IletisimSablon | str,
    baglam: dict[str, str],
    *,
    zorunlu: frozenset[str] | None = None,
) -> SablonRenderSonuc:
    metin = sablon.icerik if isinstance(sablon, IletisimSablon) else sablon
    ayar = kurum_ayarlari()
    tam_baglam = {
        "kurum": baglam.get("kurum") or ayar.kurum_imza or PANEL_ORG,
        **baglam,
    }
    eksik: list[str] = []
    for anahtar in PLACEHOLDER_RE.findall(metin):
        deger = (tam_baglam.get(anahtar) or "").strip()
        if not deger:
            eksik.append(anahtar)
    if zorunlu:
        for anahtar in zorunlu:
            if not (tam_baglam.get(anahtar) or "").strip():
                if anahtar not in eksik:
                    eksik.append(anahtar)
    if eksik:
        etiketler = ", ".join(f"{{{k}}}" for k in eksik)
        return SablonRenderSonuc(
            metin="",
            eksik=eksik,
            hata=f"Mesaj için eksik bilgi: {etiketler}",
        )
    cikti = metin
    for anahtar, deger in tam_baglam.items():
        cikti = cikti.replace("{" + anahtar + "}", deger)
    if ayar.varsayilan_kapanis and ayar.varsayilan_kapanis not in cikti:
        cikti = cikti.rstrip() + "\n\n" + ayar.varsayilan_kapanis
    imza = ayar.kurum_imza or PANEL_ORG
    if imza and imza not in cikti:
        cikti = cikti.rstrip() + "\n" + imza
    return SablonRenderSonuc(metin=cikti.strip(), eksik=[])


def varsayilan_sablon(modul: str, kod: str | None = None) -> IletisimSablon | None:
    qs = IletisimSablon.objects.filter(aktif=True)
    if kod:
        bulunan = qs.filter(kod=kod).first()
        if bulunan:
            return bulunan
    qs = qs.filter(Q(kaynak_moduller=[]) | Q(kaynak_moduller__contains=[modul]))
    sablon = qs.filter(varsayilan=True, kaynak_moduller__contains=[modul]).order_by("sira").first()
    if sablon:
        return sablon
    return qs.filter(kaynak_moduller__contains=[modul]).order_by("sira").first() or qs.filter(
        varsayilan=True
    ).order_by("sira").first()


def paket_yetkisi_var(user: User, paket: IletisimPaketi) -> bool:
    if not user.is_authenticated:
        return False
    if not can(user, "iletisim_merkezi", "view"):
        return False
    from takip.permissions.service import kullanici_birincil_rol_slug

    rol = kullanici_birincil_rol_slug(user)
    if rol in ("idareci", "ic_mesul") or user.is_superuser:
        return True
    return paket.olusturan_id == user.id


def yetkili_paketler(user: User) -> QuerySet[IletisimPaketi]:
    qs = IletisimPaketi.objects.select_related(
        "sinif_sube", "talebe", "sablon", "olusturan"
    ).prefetch_related("ekler")
    from takip.permissions.service import kullanici_birincil_rol_slug

    rol = kullanici_birincil_rol_slug(user)
    if rol in ("idareci", "ic_mesul") or user.is_superuser:
        return qs
    return qs.filter(olusturan=user)


def paket_indir_yetkisi(user: User, paket: IletisimPaketi, eki: IletisimEki) -> bool:
    if not paket_yetkisi_var(user, paket):
        return False
    if eki.talebe_id and paket.talebe_id and eki.talebe_id != paket.talebe_id:
        return False
    return True


def olay_kaydet(
    paket: IletisimPaketi,
    olay_tur: str,
    user: User | None,
    meta: dict | None = None,
) -> IletisimOlay:
    return IletisimOlay.objects.create(
        paket=paket,
        olay_tur=olay_tur,
        kullanici=user,
        meta=meta or {},
    )


def _paket_anahtari(veri: PaylasimPaketVerisi) -> dict[str, Any]:
    return {
        "kaynak_modul": veri.kaynak_modul,
        "kaynak_tur": veri.kaynak_tur,
        "kaynak_id": str(veri.kaynak_id),
        "hedef_tur": veri.hedef_tur,
        "sinif_sube_id": veri.sinif_sube_id,
        "talebe_id": veri.talebe_id,
    }


@transaction.atomic
def paket_bul_veya_guncelle(
    user: User,
    veri: PaylasimPaketVerisi,
) -> tuple[IletisimPaketi, bool]:
    sablon = varsayilan_sablon(veri.kaynak_modul, veri.sablon_kod)
    if not sablon:
        raise ValueError("Uygun mesaj şablonu bulunamadı. Yönetimden şablon ekleyin.")
    zorunlu = MODUL_DEGISKENLERI.get(veri.kaynak_modul, frozenset())
    if veri.kaynak_modul == "ktt":
        zorunlu = frozenset({"ktt_adi", "ders", "tarih"})
    render = sablon_render(sablon, veri.mesaj_baglam, zorunlu=zorunlu)
    if render.hata:
        raise ValueError(render.hata)

    filtre = _paket_anahtari(veri)
    paket = (
        IletisimPaketi.objects.filter(**filtre)
        .exclude(durum=IletisimPaketi.Durum.TASLAK)
        .order_by("-id")
        .first()
    )
    yeni = paket is None
    if paket and paket.kaynak_imza == veri.kaynak_imza and paket.mesaj == render.metin:
        return paket, False

    if not paket:
        paket = IletisimPaketi(**filtre, olusturan=user)

    paket.baslik = veri.baslik
    paket.hedef_etiket = veri.hedef_etiket
    paket.sablon = sablon
    paket.mesaj = render.metin
    paket.kaynak_imza = veri.kaynak_imza
    paket.durum = veri.durum
    paket.save()

    if veri.ekler:
        paket.ekler.all().delete()
        for ek in veri.ekler:
            dosya_adi = ek.dosya_adi or "ek.pdf"
            kayit = IletisimEki(
                paket=paket,
                dosya_adi=dosya_adi,
                mime_type=ek.mime_type,
                talebe_id=ek.talebe_id,
                kaynak_modul=ek.kaynak_modul or veri.kaynak_modul,
                kaynak_id=ek.kaynak_id or veri.kaynak_id,
            )
            kayit.dosya.save(dosya_adi, ContentFile(ek.dosya_bytes), save=False)
            kayit.save()
        olay_kaydet(paket, IletisimOlay.OlayTur.PDF_GENERATED, user)

    if yeni:
        olay_kaydet(paket, IletisimOlay.OlayTur.PACKAGE_CREATED, user)
    return paket, yeni


def paket_mesaj_guncelle(user: User, paket: IletisimPaketi, yeni_mesaj: str) -> IletisimPaketi:
    if not paket_yetkisi_var(user, paket):
        raise PermissionError("Bu paketi düzenleyemezsiniz.")
    paket.mesaj = (yeni_mesaj or "").strip()
    if not paket.mesaj:
        raise ValueError("Mesaj boş olamaz.")
    paket.save(update_fields=["mesaj", "guncellenme"])
    return paket


def paket_taslak_yap(user: User, paket: IletisimPaketi) -> IletisimPaketi:
    if not paket_yetkisi_var(user, paket):
        raise PermissionError("Bu paketi düzenleyemezsiniz.")
    paket.durum = IletisimPaketi.Durum.TASLAK
    paket.save(update_fields=["durum", "guncellenme"])
    olay_kaydet(paket, IletisimOlay.OlayTur.DRAFT_SAVED, user)
    return paket


def hazir_paketler(user: User, limit: int = 40) -> QuerySet[IletisimPaketi]:
    return (
        yetkili_paketler(user)
        .filter(durum=IletisimPaketi.Durum.HAZIR)
        .order_by("-guncellenme")[:limit]
    )


def taslak_paketler(user: User, limit: int = 30) -> QuerySet[IletisimPaketi]:
    return (
        yetkili_paketler(user)
        .filter(durum=IletisimPaketi.Durum.TASLAK)
        .order_by("-guncellenme")[:limit]
    )


def olay_gecmisi(user: User, limit: int = 50) -> QuerySet[IletisimOlay]:
    paket_ids = yetkili_paketler(user).values_list("id", flat=True)
    return (
        IletisimOlay.objects.filter(paket_id__in=paket_ids)
        .select_related("paket", "kullanici")
        .order_by("-olusturulma")[:limit]
    )


def kaynak_imza_uret(*parçalar: Any) -> str:
    ham = "|".join(str(p) for p in parçalar if p is not None)
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()[:32]


def paket_json(paket: IletisimPaketi) -> dict:
    ekler = [
        {
            "id": e.id,
            "ad": e.dosya_adi,
            "url": f"/iletisim/ek/{e.id}/indir/",
            "mime": e.mime_type,
            "talebe_id": e.talebe_id,
        }
        for e in paket.ekler.all()
    ]
    return {
        "id": paket.id,
        "baslik": paket.baslik,
        "kaynak_modul": paket.kaynak_modul,
        "kaynak_modul_label": paket.get_kaynak_modul_display(),
        "hedef_etiket": paket.hedef_etiket,
        "mesaj": paket.mesaj,
        "durum": paket.durum,
        "durum_label": paket.get_durum_display(),
        "talebe_ad": paket.talebe.ad_soyad if paket.talebe_id else "",
        "ekler": ekler,
        "guncellenme": paket.guncellenme.isoformat(),
    }


EKI_PUBLIC_SALT = "iletisim-ek-public-v1"
EKI_PUBLIC_MAX_AGE = 60 * 60 * 24 * 14


def eki_public_token(eki_pk: int) -> str:
    signer = TimestampSigner(salt=EKI_PUBLIC_SALT)
    signed = signer.sign(str(eki_pk))
    return base64.urlsafe_b64encode(signed.encode("utf-8")).decode("ascii").rstrip("=")


def eki_pk_from_public_token(token: str) -> int:
    signer = TimestampSigner(salt=EKI_PUBLIC_SALT)
    padding = "=" * (-len(token) % 4)
    try:
        signed = base64.urlsafe_b64decode(token + padding).decode("utf-8")
        raw = signer.unsign(signed, max_age=EKI_PUBLIC_MAX_AGE)
    except (BadSignature, SignatureExpired, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Geçersiz veya süresi dolmuş paylaşım linki.") from exc
    return int(raw)


def eki_public_indir_url(request, eki: IletisimEki) -> str:
    token = eki_public_token(eki.pk)
    return request.build_absolute_uri(reverse("iletisim_ek_public", kwargs={"token": token}))


def varsayilan_sablonlari_yukle() -> None:
    """İlk kurulum — varsayılan şablonları oluşturur."""
    sablonlar = [
        {
            "kod": "ktt-sonuc",
            "ad": "KTT Sonuç Bilgilendirmesi",
            "kategori": IletisimSablon.Kategori.AKADEMIK,
            "kaynak_moduller": ["ktt"],
            "varsayilan": True,
            "sira": 10,
            "icerik": (
                "{hitap}\n\n"
                "Bugün gerçekleştirilen {ktt_adi} ({ders} — {konu}) sonuç raporu hazırlanmıştır. "
                "Ekte sınıf sonuç listesini bulabilirsiniz.\n\n"
                "Tarih: {tarih}"
            ),
        },
        {
            "kod": "deneme-sonuc",
            "ad": "Deneme Sonucu",
            "kategori": IletisimSablon.Kategori.AKADEMIK,
            "kaynak_moduller": ["deneme"],
            "sira": 20,
            "icerik": (
                "{hitap}\n\n"
                "{deneme_adi} deneme sınavı sonuç raporu hazırlanmıştır.\n\n"
                "Tarih: {tarih}"
            ),
        },
        {
            "kod": "kitap-sinav-sonuc",
            "ad": "Kitap Sınavı Sonucu",
            "kategori": IletisimSablon.Kategori.KITAP,
            "kaynak_moduller": ["kitap"],
            "sira": 30,
            "icerik": (
                "{hitap}\n\n"
                "{kitap_adi} kitap sınavı sonuçları hazırlanmıştır.\n\n"
                "Tarih: {tarih}"
            ),
        },
        {
            "kod": "karne-bilgi",
            "ad": "Karne Bilgilendirmesi",
            "kategori": IletisimSablon.Kategori.AKADEMIK,
            "kaynak_moduller": ["karne"],
            "sira": 40,
            "icerik": (
                "{hitap}\n\n"
                "{talebe_adi} talebemizin dönem karnesi hazırlanmıştır. Ekte paylaşıyoruz.\n\n"
                "Tarih: {tarih}"
            ),
        },
        {
            "kod": "genel-duyuru",
            "ad": "Genel Bilgilendirme",
            "kategori": IletisimSablon.Kategori.IDARI,
            "kaynak_moduller": [],
            "sira": 90,
            "icerik": "{hitap}\n\n{mesaj_govdesi}\n\nTarih: {tarih}",
        },
    ]
    ayar = kurum_ayarlari()
    hitap = ayar.varsayilan_hitap or "Değerli Velimiz,"
    for veri in sablonlar:
        icerik = veri["icerik"].replace("{hitap}", hitap)
        IletisimSablon.objects.update_or_create(
            kod=veri["kod"],
            defaults={
                "ad": veri["ad"],
                "kategori": veri["kategori"],
                "kaynak_moduller": veri["kaynak_moduller"],
                "varsayilan": veri.get("varsayilan", False),
                "sira": veri["sira"],
                "icerik": icerik,
                "aktif": True,
            },
        )
