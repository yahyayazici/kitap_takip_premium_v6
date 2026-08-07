from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO

from django.contrib.auth.models import User
from django.db import transaction

from .models import EtutHocasi, SinifSube, Talebe
from .wave0_models import VeliHesap, VeliKisi, VeliTalebeBaglantisi

EXCEL_BASLIKLAR = [
    "Talebe No",
    "Ad Soyad",
    "Sınıf",
    "Şube",
    "Talebe TC",
    "Talebe Telefon",
    "Anne Ad Soyad",
    "Anne Telefon",
    "Baba Ad Soyad",
    "Baba Telefon",
    "Etüt Hocası",
    "Aktif",
]

ORNEK_SATIR = [
    "1",
    "Ahmet Yılmaz",
    "7",
    "A",
    "12345678901",
    "05xx xxx xx xx",
    "Ayşe Yılmaz",
    "05xx xxx xx xx",
    "Mehmet Yılmaz",
    "05xx xxx xx xx",
    "Yahya Yazıcı",
    "Evet",
]


@dataclass
class TalebeExcelSonuc:
    eklenen: int = 0
    guncellenen: int = 0
    veli_hesap: int = 0
    atlanan: int = 0
    hatalar: list[str] = field(default_factory=list)
    bilgi: list[str] = field(default_factory=list)


def _hucre_degeri(deger) -> str:
    if deger is None:
        return ""
    if isinstance(deger, float) and deger.is_integer():
        return str(int(deger))
    return str(deger).strip()


def _tc_normalize(deger: str) -> str:
    return re.sub(r"\D", "", deger or "")


def _aktif_mi(deger: str) -> bool:
    if not deger:
        return True

    normalized = deger.strip().lower()
    if normalized in {"evet", "e", "1", "true", "aktif", "yes", "y"}:
        return True
    if normalized in {"hayır", "hayir", "h", "0", "false", "pasif", "no", "n"}:
        return False
    raise ValueError(f"Geçersiz aktif değeri: {deger}")


def _baslik_eslestir(satir: list[str]) -> dict[str, int]:
    eslesme = {}
    for index, hucre in enumerate(satir):
        anahtar = _hucre_degeri(hucre).lower()
        if anahtar in {"ad soyad", "ad_soyad", "adsoyad", "isim"}:
            eslesme["ad_soyad"] = index
        elif anahtar in {"sınıf", "sinif", "class"}:
            eslesme["sinif"] = index
        elif anahtar in {"şube", "sube"}:
            eslesme["sube"] = index
        elif anahtar in {"talebe tc", "talebe_tc", "tc", "tc kimlik", "tc_kimlik"}:
            eslesme["talebe_tc"] = index
        elif anahtar in {"talebe telefon", "talebe_telefon", "telefon"}:
            eslesme["talebe_telefon"] = index
        elif anahtar in {"anne ad soyad", "anne_ad_soyad", "anne"}:
            eslesme["anne_ad"] = index
        elif anahtar in {"anne telefon", "anne_telefon"}:
            eslesme["anne_telefon"] = index
        elif anahtar in {"baba ad soyad", "baba_ad_soyad", "baba"}:
            eslesme["baba_ad"] = index
        elif anahtar in {"baba telefon", "baba_telefon"}:
            eslesme["baba_telefon"] = index
        elif anahtar in {"etüt hocası", "etut hocasi", "etut_hocasi", "hoca"}:
            eslesme["etut_hocasi"] = index
        elif anahtar in {"talebe no", "talebe_no", "numara", "no"}:
            eslesme["talebe_no"] = index
        elif anahtar in {"aktif", "durum"}:
            eslesme["aktif"] = index
    return eslesme


def _satir_degeri(satir: list, index: int | None) -> str:
    if index is None or index >= len(satir):
        return ""
    return _hucre_degeri(satir[index])


def _excel_satirlari(dosya) -> list[list]:
    from openpyxl import load_workbook

    workbook = load_workbook(dosya, read_only=True, data_only=True)
    sayfa = workbook.active
    satirlar = []

    for satir in sayfa.iter_rows(values_only=True):
        if not satir:
            continue
        degerler = [_hucre_degeri(hucre) for hucre in satir]
        if any(degerler):
            satirlar.append(degerler)

    workbook.close()
    return satirlar


def _xlsx_kaydet(satirlar: list[list], *, sayfa_adi: str = "Talebeler") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sayfa = workbook.active
    sayfa.title = sayfa_adi

    baslik_font = Font(bold=True, color="FFFFFF")
    baslik_fill = PatternFill("solid", fgColor="1A4FA8")

    for row_idx, satir in enumerate(satirlar, start=1):
        for col_idx, deger in enumerate(satir, start=1):
            hucre = sayfa.cell(row=row_idx, column=col_idx, value=deger)
            if row_idx == 1:
                hucre.font = baslik_font
                hucre.fill = baslik_fill

    genislikler = [10, 28, 8, 8, 14, 16, 24, 16, 24, 16, 22, 8]
    for col, genislik in enumerate(genislikler, start=1):
        harf = chr(64 + col) if col <= 26 else "L"
        sayfa.column_dimensions[harf].width = genislik

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def sablon_xlsx_olustur() -> bytes:
    return _xlsx_kaydet([EXCEL_BASLIKLAR, ORNEK_SATIR])


def mevcut_talebeler_xlsx_olustur(*, talebe_qs=None) -> bytes:
    if talebe_qs is None:
        talebe_qs = (
            Talebe.objects.filter(aktif=True)
            .select_related("sinif_sube", "etut_hocasi")
            .prefetch_related("veli_kisileri")
            .order_by("sinif", "sube", "ad_soyad")
        )

    satirlar = [EXCEL_BASLIKLAR]
    for talebe in talebe_qs:
        anne = baba = None
        for veli in talebe.veli_kisileri.all():
            if veli.yakinlik == VeliKisi.Yakinlik.ANNE:
                anne = veli
            elif veli.yakinlik == VeliKisi.Yakinlik.BABA:
                baba = veli

        sinif = talebe.sinif_sube.sinif if talebe.sinif_sube_id else talebe.sinif
        sube = talebe.sinif_sube.sube if talebe.sinif_sube_id else talebe.sube
        satirlar.append(
            [
                talebe.talebe_no or "",
                talebe.ad_soyad,
                sinif,
                sube,
                talebe.tc_kimlik or "",
                talebe.telefon or "",
                anne.ad_soyad if anne else "",
                anne.telefon if anne else "",
                baba.ad_soyad if baba else "",
                baba.telefon if baba else "",
                talebe.etut_hocasi.ad_soyad if talebe.etut_hocasi_id else "",
                "Evet" if talebe.aktif else "Hayır",
            ]
        )

    return _xlsx_kaydet(satirlar)


def _veli_kisi_guncelle(
    talebe: Talebe,
    yakinlik: str,
    ad_soyad: str,
    telefon: str,
) -> None:
    if not ad_soyad:
        return

    veli = VeliKisi.objects.filter(talebe=talebe, yakinlik=yakinlik).first()
    if veli:
        veli.ad_soyad = ad_soyad
        if telefon:
            veli.telefon = telefon
        veli.save(update_fields=["ad_soyad", "telefon"])
        return

    VeliKisi.objects.create(
        talebe=talebe,
        yakinlik=yakinlik,
        ad_soyad=ad_soyad,
        telefon=telefon,
        birincil=yakinlik == VeliKisi.Yakinlik.ANNE,
    )


def _veli_panel_ensure(
    talebe: Talebe,
    tc: str,
    veli_ad: str,
    veli_telefon: str,
) -> bool:
    tc = _tc_normalize(tc)
    if len(tc) != 11:
        return False

    username = tc
    sifre = tc[-4:]
    mevcut_user = User.objects.filter(username__iexact=username).exclude(
        veli_hesabi__talebe_baglantilari__talebe=talebe
    ).first()
    if mevcut_user:
        return False

    user = User.objects.filter(username__iexact=username).first()
    if user:
        user.set_password(sifre)
        if veli_ad:
            user.first_name = veli_ad[:150]
        user.save()
    else:
        user = User(username=username[:150], first_name=(veli_ad or "")[:150])
        user.set_password(sifre)
        user.save()

    veli_hesap, olusturuldu = VeliHesap.objects.get_or_create(
        user=user,
        defaults={
            "ad_soyad": veli_ad or talebe.ad_soyad,
            "telefon": veli_telefon,
            "aktif": True,
        },
    )
    if not olusturuldu:
        if veli_ad:
            veli_hesap.ad_soyad = veli_ad
        if veli_telefon:
            veli_hesap.telefon = veli_telefon
        veli_hesap.aktif = True
        veli_hesap.save()

    VeliTalebeBaglantisi.objects.get_or_create(
        veli=veli_hesap,
        talebe=talebe,
        defaults={"yakinlik": VeliKisi.Yakinlik.VELI},
    )
    return True


def _talebe_bul(
    *,
    talebe_no: str,
    ad_soyad: str,
    sinif: str,
    sube: str,
) -> Talebe | None:
    if talebe_no:
        talebe = Talebe.objects.filter(talebe_no=talebe_no).first()
        if talebe:
            return talebe

    if ad_soyad and sinif and sube:
        return (
            Talebe.objects.filter(
                ad_soyad__iexact=ad_soyad,
                sinif__iexact=sinif,
                sube__iexact=sube,
            )
            .select_related("sinif_sube", "etut_hocasi")
            .first()
        )
    return None


@transaction.atomic
def talebe_excel_ice_aktar(dosya) -> TalebeExcelSonuc:
    sonuc = TalebeExcelSonuc()

    try:
        satirlar = _excel_satirlari(dosya)
    except Exception as exc:
        sonuc.hatalar.append(f"Dosya okunamadı: {exc}")
        return sonuc

    if not satirlar:
        sonuc.hatalar.append("Excel dosyası boş görünüyor.")
        return sonuc

    basliklar = _baslik_eslestir(satirlar[0])
    if "ad_soyad" not in basliklar:
        sonuc.hatalar.append(
            "Başlık satırında en az «Ad Soyad» sütunu olmalı."
        )
        return sonuc

    hoca_haritasi = {
        hoca.ad_soyad.strip().lower(): hoca
        for hoca in EtutHocasi.objects.filter(aktif=True)
    }
    sinif_haritasi = {
        (grup.sinif.strip().lower(), grup.sube.strip().lower()): grup
        for grup in SinifSube.objects.filter(aktif=True)
    }

    siradaki_no = Talebe._yeni_talebe_no()

    def _sonraki_no() -> str:
        nonlocal siradaki_no
        mevcut = siradaki_no
        siradaki_no = str(int(siradaki_no) + 1)
        return mevcut

    for satir_no, satir in enumerate(satirlar[1:], start=2):
        ad_soyad = _satir_degeri(satir, basliklar.get("ad_soyad"))
        talebe_no = _satir_degeri(satir, basliklar.get("talebe_no"))
        sinif = _satir_degeri(satir, basliklar.get("sinif"))
        sube = _satir_degeri(satir, basliklar.get("sube"))
        talebe_tc = _tc_normalize(_satir_degeri(satir, basliklar.get("talebe_tc")))
        talebe_telefon = _satir_degeri(satir, basliklar.get("talebe_telefon"))
        anne_ad = _satir_degeri(satir, basliklar.get("anne_ad"))
        anne_tel = _satir_degeri(satir, basliklar.get("anne_telefon"))
        baba_ad = _satir_degeri(satir, basliklar.get("baba_ad"))
        baba_tel = _satir_degeri(satir, basliklar.get("baba_telefon"))
        hoca_adi = _satir_degeri(satir, basliklar.get("etut_hocasi"))
        aktif_raw = _satir_degeri(satir, basliklar.get("aktif"))

        if not ad_soyad and not talebe_no:
            continue

        mevcut = _talebe_bul(
            talebe_no=talebe_no,
            ad_soyad=ad_soyad,
            sinif=sinif,
            sube=sube,
        )

        if mevcut:
            degisti = False
            islem_yapildi = False

            if talebe_tc and len(talebe_tc) == 11 and mevcut.tc_kimlik != talebe_tc:
                mevcut.tc_kimlik = talebe_tc
                degisti = True
            elif talebe_tc and len(talebe_tc) != 11:
                sonuc.bilgi.append(
                    f"Satır {satir_no}: TC geçersiz ({talebe_tc}), atlandı."
                )

            if talebe_telefon and mevcut.telefon != talebe_telefon:
                mevcut.telefon = talebe_telefon
                degisti = True

            if aktif_raw:
                try:
                    aktif = _aktif_mi(aktif_raw)
                    if mevcut.aktif != aktif:
                        mevcut.aktif = aktif
                        degisti = True
                except ValueError as exc:
                    sonuc.bilgi.append(f"Satır {satir_no}: {exc}")

            if degisti:
                mevcut.save()
                islem_yapildi = True

            if anne_ad or anne_tel:
                _veli_kisi_guncelle(mevcut, VeliKisi.Yakinlik.ANNE, anne_ad, anne_tel)
                islem_yapildi = True
            if baba_ad or baba_tel:
                _veli_kisi_guncelle(mevcut, VeliKisi.Yakinlik.BABA, baba_ad, baba_tel)
                islem_yapildi = True

            if talebe_tc and len(talebe_tc) == 11:
                veli_ad = anne_ad or baba_ad or ""
                veli_tel = anne_tel or baba_tel or talebe_telefon
                if _veli_panel_ensure(mevcut, talebe_tc, veli_ad, veli_tel):
                    sonuc.veli_hesap += 1
                    islem_yapildi = True
                else:
                    sonuc.bilgi.append(
                        f"Satır {satir_no}: {talebe_tc} kullanıcı adı başka hesapta, "
                        "veli paneli atlandı."
                    )

            if islem_yapildi:
                sonuc.guncellenen += 1
            continue

        if not ad_soyad:
            sonuc.bilgi.append(
                f"Satır {satir_no}: Talebe bulunamadı, ad soyad boş — atlandı."
            )
            sonuc.atlanan += 1
            continue

        if not sinif or not sube or not hoca_adi:
            sonuc.bilgi.append(
                f"Satır {satir_no}: Yeni kayıt için sınıf, şube ve etüt hocası gerekli — atlandı."
            )
            sonuc.atlanan += 1
            continue

        sinif_sube = sinif_haritasi.get((sinif.lower(), sube.lower()))
        if not sinif_sube:
            sonuc.bilgi.append(
                f"Satır {satir_no}: {sinif}/{sube} sınıfı bulunamadı — atlandı."
            )
            sonuc.atlanan += 1
            continue

        etut_hocasi = hoca_haritasi.get(hoca_adi.lower())
        if not etut_hocasi:
            sonuc.bilgi.append(
                f"Satır {satir_no}: '{hoca_adi}' etüt hocası bulunamadı — atlandı."
            )
            sonuc.atlanan += 1
            continue

        if not etut_hocasi.sorumlu_sinif_subeler.filter(pk=sinif_sube.pk).exists():
            sonuc.bilgi.append(
                f"Satır {satir_no}: {etut_hocasi.ad_soyad} bu sınıftan sorumlu değil — atlandı."
            )
            sonuc.atlanan += 1
            continue

        try:
            aktif = _aktif_mi(aktif_raw)
        except ValueError as exc:
            sonuc.bilgi.append(f"Satır {satir_no}: {exc}")
            aktif = True

        if talebe_no and Talebe.objects.filter(talebe_no=talebe_no).exists():
            sonuc.atlanan += 1
            sonuc.bilgi.append(
                f"Satır {satir_no}: {talebe_no} numarası kullanılıyor — atlandı."
            )
            continue

        if Talebe.objects.filter(
            ad_soyad__iexact=ad_soyad,
            sinif_sube=sinif_sube,
        ).exists():
            sonuc.atlanan += 1
            sonuc.bilgi.append(
                f"Satır {satir_no}: {ad_soyad} zaten kayıtlı — atlandı."
            )
            continue

        if not talebe_no:
            talebe_no = _sonraki_no()

        talebe = Talebe(
            ad_soyad=ad_soyad,
            talebe_no=talebe_no,
            sinif_sube=sinif_sube,
            etut_hocasi=etut_hocasi,
            dini_ders_hocasi=etut_hocasi,
            aktif=aktif,
            telefon=talebe_telefon,
            tc_kimlik=talebe_tc if len(talebe_tc) == 11 else "",
        )
        talebe.save()
        sonuc.eklenen += 1

        _veli_kisi_guncelle(talebe, VeliKisi.Yakinlik.ANNE, anne_ad, anne_tel)
        _veli_kisi_guncelle(talebe, VeliKisi.Yakinlik.BABA, baba_ad, baba_tel)

        if talebe_tc and len(talebe_tc) == 11:
            veli_ad = anne_ad or baba_ad or ""
            veli_tel = anne_tel or baba_tel or talebe_telefon
            if _veli_panel_ensure(talebe, talebe_tc, veli_ad, veli_tel):
                sonuc.veli_hesap += 1

    return sonuc
