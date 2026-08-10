"""Program planı sorguları, süre özeti ve dönem analizi."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any

from django.db.models import QuerySet
from django.utils.timezone import localdate

from .models import ProgramPlan, ProgramSatir


def tarihe_uygun_programlar(tarih: date | None = None) -> QuerySet[ProgramPlan]:
    tarih = tarih or localdate()

    return (
        ProgramPlan.objects.filter(
            aktif=True,
            baslangic_tarihi__lte=tarih,
            bitis_tarihi__gte=tarih,
        )
        .prefetch_related("satirlar")
        .order_by("-baslangic_tarihi", "ad")
    )


def bugunun_programi() -> ProgramPlan | None:
    return tarihe_uygun_programlar().first()


def program_arsivi() -> QuerySet[ProgramPlan]:
    return (
        ProgramPlan.objects.filter(aktif=True)
        .prefetch_related("satirlar")
        .order_by("-baslangic_tarihi", "ad")
    )


def _dakika_etiket(dakika: int) -> str:
    dakika = max(0, int(dakika or 0))
    saat, dk = divmod(dakika, 60)
    if saat and dk:
        return f"{saat} sa {dk} dk"
    if saat:
        return f"{saat} sa"
    return f"{dk} dk"


def _saat_ondalik(dakika: int) -> float:
    return round(max(0, int(dakika or 0)) / 60.0, 1)


def gunluk_tur_dakikalari(program: ProgramPlan) -> dict[str, int]:
    """Etkin satırların türe göre günlük dakika toplamı."""
    toplam: dict[str, int] = {}
    for satir in program.satirlar.all():
        if satir.faaliyet_durumu == ProgramSatir.FaaliyetDurumu.PASIF:
            continue
        kod = satir.faaliyet_turu
        toplam[kod] = toplam.get(kod, 0) + int(satir.sure_dakika or 0)
    return toplam


def _donem_aralik(donem: str, referans: date, program: ProgramPlan) -> tuple[date, date, str]:
    donem = (donem or "gun").lower()
    if donem == "hafta":
        bas = referans - timedelta(days=referans.weekday())
        bit = bas + timedelta(days=6)
        etiket = f"{bas.strftime('%d.%m')} – {bit.strftime('%d.%m.%Y')}"
    elif donem == "ay":
        bas = referans.replace(day=1)
        bit = referans.replace(day=monthrange(referans.year, referans.month)[1])
        ay_ad = [
            "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
        ][referans.month]
        etiket = f"{ay_ad} {referans.year}"
    elif donem == "yil":
        bas = date(referans.year, 1, 1)
        bit = date(referans.year, 12, 31)
        etiket = f"{referans.year}"
    else:
        bas = bit = referans
        etiket = referans.strftime("%d.%m.%Y")
        donem = "gun"

    # Program geçerlilik aralığı ile kesiştir
    bas = max(bas, program.baslangic_tarihi)
    bit = min(bit, program.bitis_tarihi)
    if bit < bas:
        return referans, referans - timedelta(days=1), etiket
    return bas, bit, etiket


def _gun_sayisi(bas: date, bit: date) -> int:
    if bit < bas:
        return 0
    return (bit - bas).days + 1


def program_sure_ozeti(
    program: ProgramPlan,
    *,
    donem: str = "gun",
    referans: date | None = None,
) -> dict[str, Any]:
    """
    Seçilen dönem için türe göre süre dağılımı.
    Program günlük şablon olduğundan: günlük_dakika × dönemdeki gün sayısı.
    """
    referans = referans or localdate()
    gunluk = gunluk_tur_dakikalari(program)
    bas, bit, donem_etiket = _donem_aralik(donem, referans, program)
    carpan = 1 if donem in {"gun", "günlük", "gunluk"} else _gun_sayisi(bas, bit)
    if donem == "gun":
        carpan = 1

    from .models import ProgramFaaliyetTuru

    tur_map = {
        t.kod: t.ad for t in ProgramFaaliyetTuru.objects.all()
    }
    if not tur_map:
        tur_map = dict(ProgramSatir.FaaliyetTuru.choices)
    satirlar: list[dict[str, Any]] = []
    toplam_dk = 0
    for kod, gun_dk in sorted(gunluk.items(), key=lambda x: -x[1]):
        donem_dk = gun_dk * carpan
        toplam_dk += donem_dk
        satirlar.append(
            {
                "kod": kod,
                "ad": tur_map.get(kod, kod),
                "gunluk_dakika": gun_dk,
                "dakika": donem_dk,
                "etiket": _dakika_etiket(donem_dk),
                "saat": _saat_ondalik(donem_dk),
                "gunluk_etiket": _dakika_etiket(gun_dk),
            }
        )

    for satir in satirlar:
        satir["yuzde"] = (
            round(100.0 * satir["dakika"] / toplam_dk, 1) if toplam_dk else 0.0
        )

    return {
        "donem": donem,
        "donem_etiket": donem_etiket,
        "gun_sayisi": carpan,
        "toplam_dakika": toplam_dk,
        "toplam_etiket": _dakika_etiket(toplam_dk),
        "toplam_saat": _saat_ondalik(toplam_dk),
        "satirlar": satirlar,
        "ai_ozet": program_ai_ozet_metni(satirlar, donem=donem, gun_sayisi=carpan),
    }


def program_tum_donem_ozetleri(
    program: ProgramPlan,
    *,
    referans: date | None = None,
) -> dict[str, dict[str, Any]]:
    referans = referans or localdate()
    return {
        "gun": program_sure_ozeti(program, donem="gun", referans=referans),
        "hafta": program_sure_ozeti(program, donem="hafta", referans=referans),
        "ay": program_sure_ozeti(program, donem="ay", referans=referans),
        "yil": program_sure_ozeti(program, donem="yil", referans=referans),
    }


def program_ai_ozet_metni(
    satirlar: list[dict[str, Any]],
    *,
    donem: str = "gun",
    gun_sayisi: int = 1,
) -> str:
    """Sayısal dağılımdan doğal dil özet (panel AI tarzı)."""
    if not satirlar:
        return "Bu programda etkin faaliyet satırı yok; süre dağılımı hesaplanamadı."

    donem_ad = {
        "gun": "günde",
        "hafta": "haftada",
        "ay": "ayda",
        "yil": "yılda",
    }.get(donem, "dönemde")

    onemli = satirlar[:5]
    parcalar = [f"{s['etiket']} {s['ad'].lower()}" for s in onemli]
    if len(parcalar) == 1:
        dagilim = parcalar[0]
    elif len(parcalar) == 2:
        dagilim = f"{parcalar[0]} ve {parcalar[1]}"
    else:
        dagilim = ", ".join(parcalar[:-1]) + f" ve {parcalar[-1]}"

    etut = next((s for s in satirlar if s["kod"] == "etut"), None)
    uyku = next((s for s in satirlar if s["kod"] == "uyku"), None)
    dinlenme = next((s for s in satirlar if s["kod"] == "dinlenme"), None)
    ders = next((s for s in satirlar if s["kod"] == "ders"), None)

    ekstra: list[str] = []
    if etut:
        ekstra.append(f"Etüte {etut['etiket']} ayrılmış")
    if uyku:
        ekstra.append(f"uykuya {uyku['etiket']}")
    elif dinlenme:
        ekstra.append(f"dinlenmeye {dinlenme['etiket']}")
    if ders:
        ekstra.append(f"derse {ders['etiket']}")

    bas = f"Bu programda {donem_ad} yaklaşık {dagilim} görünüyor."
    if ekstra:
        bas += " " + "; ".join(ekstra) + "."
    if donem != "gun" and gun_sayisi > 1:
        bas += f" Hesap, günlük şablonun dönemdeki {gun_sayisi} güne çarpımıdır."
    return bas


def program_excel_icerik(program: ProgramPlan) -> tuple[str, bytes]:
    """Kurum günlük programı — ortak logo/altın çizgi Excel düzeni."""
    from django.utils.text import slugify

    from takip.excel_rapor import basit_rapor_xlsx

    satirlar: list[list[Any]] = []
    for satir in program.satirlar.all():
        satirlar.append(
            [
                f"{satir.baslangic_saati:%H:%M} – {satir.bitis_saati:%H:%M}",
                satir.sure_goster,
                satir.tur_etiket,
                satir.faaliyet_adi or "",
            ]
        )

    icerik = basit_rapor_xlsx(
        baslik=f"Günlük Program — {program.ad}",
        kolon_basliklari=["Saat", "Süre", "Tür", "Faaliyet"],
        satirlar=satirlar,
        sayfa_adi="Program",
        ortala_kolonlari=[0, 1, 2],
        vurgu_kolonlari=[3],
        durum_kolonlari=[5],
        genislikler=[16, 12, 12, 24, 26, 12],
    )
    dosya = f"gunluk-program-{slugify(program.ad) or program.pk}.xlsx"
    return dosya, icerik
