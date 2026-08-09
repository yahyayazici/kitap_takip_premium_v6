"""Personel oluşturma — otomatik kullanıcı adı/şifre ve giriş PDF'leri."""

from __future__ import annotations

import re
import secrets
import string
import zipfile
from dataclasses import dataclass
from io import BytesIO

from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from config.branding import PANEL_ORG, PANEL_SHORT

from .models import EtutHocasi, PersonelProfili, SinifSube
from .ogretmen_odeme_models import OgretmenOdemeProfili
from .panel_permissions import PERSONEL_ROLLER, ROL_ETUT_MESUL, ROL_SINIF_MESUL
from .pdf_utils import html_to_pdf
from .wave0_models import Brans


@dataclass
class PersonelGirisKaydi:
    personel: PersonelProfili
    kullanici_adi: str
    sifre: str

    @property
    def rol_etiket(self) -> str:
        return self.personel.get_ana_rol_display()

    @property
    def ad_soyad(self) -> str:
        return self.personel.ad_soyad


@dataclass
class OgretmenGirisKaydi:
    hoca: EtutHocasi
    kullanici_adi: str
    sifre: str

    @property
    def rol_etiket(self) -> str:
        return "Ana Ders Öğretmeni"

    @property
    def ad_soyad(self) -> str:
        return self.hoca.ad_soyad


def _normalize_parca(metin: str) -> str:
    harita = {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "c",
        "Ğ": "g",
        "İ": "i",
        "I": "i",
        "Ö": "o",
        "Ş": "s",
        "Ü": "u",
    }
    sonuc = metin.strip().lower()
    for kaynak, hedef in harita.items():
        sonuc = sonuc.replace(kaynak, hedef)
    return re.sub(r"[^a-z0-9]", "", sonuc)


def kullanici_adi_uret(ad_soyad: str) -> str:
    parcalar = [
        _normalize_parca(parca)
        for parca in ad_soyad.replace("'", "").split()
        if parca.strip()
    ]
    parcalar = [p for p in parcalar if p]
    if len(parcalar) >= 2:
        taban = f"{parcalar[0]}.{parcalar[-1]}"
    elif parcalar:
        taban = parcalar[0]
    else:
        taban = "personel"

    aday = taban[:140]
    sayac = 1
    while User.objects.filter(username__iexact=aday).exists():
        sayac += 1
        aday = f"{taban[:130]}{sayac}"

    return aday[:150]


def sifre_uret(uzunluk: int = 10) -> str:
    alfabe = string.ascii_letters + string.digits
    while True:
        aday = "".join(secrets.choice(alfabe) for _ in range(uzunluk))
        if (
            any(c.islower() for c in aday)
            and any(c.isupper() for c in aday)
            and any(c.isdigit() for c in aday)
        ):
            return aday


def _dosya_adi(ad_soyad: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", ad_soyad.lower())
    slug = re.sub(r"[\s_]+", "-", slug.strip())
    slug = slug or "personel"
    return f"giris-{slug}.pdf"


@transaction.atomic
def personel_olustur(
    *,
    ad_soyad: str,
    ana_rol: str,
    aktif: bool = True,
    siniflar: list[SinifSube] | None = None,
    dini_ders_seviyeleri: list | None = None,
) -> PersonelGirisKaydi | None:
    ad_soyad = ad_soyad.strip()
    if not ad_soyad:
        return None

    kullanici_adi = kullanici_adi_uret(ad_soyad)
    sifre = sifre_uret()

    user = User.objects.create_user(
        username=kullanici_adi,
        password=sifre,
        first_name=ad_soyad,
        is_staff=True,
        is_active=aktif,
    )

    personel = PersonelProfili.objects.create(
        user=user,
        ad_soyad=ad_soyad,
        ana_rol=ana_rol,
        aktif=aktif,
    )

    if ana_rol in {ROL_ETUT_MESUL, ROL_SINIF_MESUL}:
        hoca = EtutHocasi.objects.create(
            user=user,
            ad_soyad=ad_soyad,
            aktif=aktif,
        )
        if siniflar:
            hoca.sorumlu_sinif_subeler.set(siniflar)
        if ana_rol == ROL_ETUT_MESUL:
            for seviye in dini_ders_seviyeleri or []:
                seviye.hocalar.add(hoca)
        personel.etut_hocasi = hoca
        personel.save(update_fields=["etut_hocasi"])

    return PersonelGirisKaydi(
        personel=personel,
        kullanici_adi=kullanici_adi,
        sifre=sifre,
    )


def toplu_personel_olustur(
    isimler: list[str],
    *,
    ana_rol: str,
    aktif: bool = True,
    siniflar: list[SinifSube] | None = None,
    dini_ders_seviyeleri: list | None = None,
) -> tuple[list[PersonelGirisKaydi], list[str]]:
    kayitlar: list[PersonelGirisKaydi] = []
    hatalar: list[str] = []

    for satir_no, isim in enumerate(isimler, start=1):
        ad = isim.strip()
        if not ad:
            continue
        try:
            kayit = personel_olustur(
                ad_soyad=ad,
                ana_rol=ana_rol,
                aktif=aktif,
                siniflar=siniflar,
                dini_ders_seviyeleri=dini_ders_seviyeleri,
            )
        except Exception as exc:
            hatalar.append(f"Satır {satir_no} ({ad}): {exc}")
            continue

        if kayit:
            kayitlar.append(kayit)

    return kayitlar, hatalar


@transaction.atomic
def ogretmen_olustur(
    *,
    ad_soyad: str,
    brans: Brans | None = None,
    saatlik_ucret=None,
) -> OgretmenGirisKaydi | None:
    from decimal import Decimal

    ad_soyad = ad_soyad.strip()
    if not ad_soyad:
        return None

    kullanici_adi = kullanici_adi_uret(ad_soyad)
    sifre = sifre_uret()

    user = User.objects.create_user(
        username=kullanici_adi,
        password=sifre,
        first_name=ad_soyad,
        is_active=True,
    )
    hoca = EtutHocasi.objects.create(user=user, ad_soyad=ad_soyad, aktif=True)

    OgretmenOdemeProfili.objects.create(
        etut_hocasi=hoca,
        brans=brans,
        saatlik_ucret=saatlik_ucret or Decimal("0"),
        aktif=True,
    )

    return OgretmenGirisKaydi(
        hoca=hoca,
        kullanici_adi=kullanici_adi,
        sifre=sifre,
    )


def toplu_ogretmen_olustur(
    isimler: list[str],
    *,
    brans: Brans | None = None,
    saatlik_ucret=None,
) -> tuple[list[OgretmenGirisKaydi], list[str]]:
    kayitlar: list[OgretmenGirisKaydi] = []
    hatalar: list[str] = []

    for satir_no, isim in enumerate(isimler, start=1):
        ad = isim.strip()
        if not ad:
            continue
        try:
            kayit = ogretmen_olustur(
                ad_soyad=ad,
                brans=brans,
                saatlik_ucret=saatlik_ucret,
            )
        except Exception as exc:
            hatalar.append(f"Satır {satir_no} ({ad}): {exc}")
            continue

        if kayit:
            kayitlar.append(kayit)

    return kayitlar, hatalar


def personel_giris_pdf_html(
    kayit: PersonelGirisKaydi | OgretmenGirisKaydi,
    *,
    request: HttpRequest,
    panel_giris_url: str | None = None,
    belge_baslik: str | None = None,
) -> str:
    if panel_giris_url is None:
        panel_giris_url = request.build_absolute_uri(reverse("login"))

    if belge_baslik is None:
        belge_baslik = (
            "Öğretmen Giriş Bilgileri"
            if isinstance(kayit, OgretmenGirisKaydi)
            else "Personel Giriş Bilgileri"
        )

    return render_to_string(
        "personel_giris_pdf.html",
        {
            "panel_org": PANEL_ORG,
            "panel_short": PANEL_SHORT,
            "ad_soyad": kayit.ad_soyad,
            "rol_etiket": kayit.rol_etiket,
            "kullanici_adi": kayit.kullanici_adi,
            "sifre": kayit.sifre,
            "panel_giris_url": panel_giris_url,
            "belge_baslik": belge_baslik,
            "tarih": timezone.localdate(),
        },
        request=request,
    )


def personel_giris_pdf_olustur(
    kayit: PersonelGirisKaydi | OgretmenGirisKaydi,
    *,
    request: HttpRequest,
) -> bytes | None:
    html = personel_giris_pdf_html(kayit, request=request)
    return html_to_pdf(html, base_url=request.build_absolute_uri("/"))


@transaction.atomic
def personel_giris_kayitlari_yenile(
    personeller,
) -> list[PersonelGirisKaydi]:
    """Aktif personel için yeni şifre üretir ve giriş kaydı döner."""
    kayitlar: list[PersonelGirisKaydi] = []
    for personel in personeller:
        if not personel.aktif or not personel.user_id:
            continue
        user = personel.user
        if not user.is_active:
            continue
        sifre = sifre_uret()
        user.set_password(sifre)
        user.save(update_fields=["password"])
        kayitlar.append(
            PersonelGirisKaydi(
                personel=personel,
                kullanici_adi=user.username,
                sifre=sifre,
            )
        )
    return kayitlar


def personel_giris_kaydi_yenile(
    personel: PersonelProfili,
) -> PersonelGirisKaydi | None:
    kayitlar = personel_giris_kayitlari_yenile([personel])
    return kayitlar[0] if kayitlar else None


def personel_giris_zip_olustur(
    kayitlar: list[PersonelGirisKaydi | OgretmenGirisKaydi],
    *,
    request: HttpRequest,
) -> bytes | None:
    if not kayitlar:
        return None

    panel_giris_url = request.build_absolute_uri(reverse("login"))
    buffer = BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as arsiv:
        for kayit in kayitlar:
            html = personel_giris_pdf_html(
                kayit,
                request=request,
                panel_giris_url=panel_giris_url,
            )
            pdf = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
            if not pdf:
                continue
            arsiv.writestr(_dosya_adi(kayit.ad_soyad), pdf)

    return buffer.getvalue()


def rol_secenekleri() -> list[tuple[str, str]]:
    return list(PERSONEL_ROLLER)
