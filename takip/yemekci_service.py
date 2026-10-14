"""Yemekçilik — sınıf döngüsü, havuz CRUD, günlük/toplu atama."""

from __future__ import annotations

from calendar import monthcalendar
from datetime import date, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.db.models import Max
from django.utils.timezone import localdate

from takip.models import Talebe
from takip.yemekci_sinif_models import (
    SINIF_ETIKET,
    SINIF_RENKLERI,
    SINIF_SEVIYELERI,
    YemekciAyar,
    YemekciGunAtama,
    YemekciHavuzKaydi,
    YemekciSinifHavuzu,
)

# Eski panel uyumluluğu
def bugunun_listesi():
    return None


def bugunun_atamalari() -> list:
    """Dashboard kartı için bugünkü sınıf görevlileri."""
    return [
        y
        for y in gunun_yemekcileri()
        if y.get("talebe") and not y.get("hafta_sonu")
    ]


def otomatik_dagit(liste=None) -> int:
    """Eski seed/yonetim çağrıları için no-op."""
    havuzlari_kur(seed_talebeler=True)
    return 0


def ayarlari_al() -> YemekciAyar:
    ayar = YemekciAyar.objects.order_by("id").first()
    if ayar:
        return ayar
    return YemekciAyar.objects.create(
        hafta_sonu_cikar=True,
        dongu_baslangic=localdate(),
    )


def _talebe_sinif_seviyesi(talebe: Talebe) -> str | None:
    """Talebenin yemekçi havuz seviyesi (5–8) veya None."""
    if getattr(talebe, "sinif_sube_id", None) and talebe.sinif_sube_id:
        raw = str(talebe.sinif_sube.sinif or "").strip()
    else:
        raw = str(getattr(talebe, "sinif", "") or "").strip()
    raw = raw.replace("Sınıf", "").replace("sinif", "").strip(" .")
    if raw in SINIF_SEVIYELERI:
        return raw
    return None


def _sinif_aktif_talebeler(sinif: str):
    qs = (
        Talebe.objects.filter(aktif=True, sinif_sube__sinif=sinif)
        .select_related("sinif_sube")
        .order_by("sinif_sube__sube", "ad_soyad", "pk")
    )
    if qs.exists():
        return qs
    return Talebe.objects.filter(aktif=True, sinif=sinif).order_by(
        "sube", "ad_soyad", "pk"
    )


@transaction.atomic
def havuzlari_kur(seed_talebeler: bool = True) -> list[YemekciSinifHavuzu]:
    """5–8 havuzlarını bir kez oluşturur; isteğe bağlı sınıf listesiyle senkronize eder."""
    havuzlar: list[YemekciSinifHavuzu] = []
    for sinif in SINIF_SEVIYELERI:
        havuz, _ = YemekciSinifHavuzu.objects.get_or_create(
            sinif=sinif,
            defaults={"renk": SINIF_RENKLERI[sinif], "aktif": True},
        )
        if not havuz.renk:
            havuz.renk = SINIF_RENKLERI[sinif]
            havuz.save(update_fields=["renk"])
        havuzlar.append(havuz)

    ayarlari_al()

    if seed_talebeler:
        havuz_senkronize()
    return havuzlar


@transaction.atomic
def havuz_senkronize(sinif: str | None = None) -> int:
    """Eksik aktif talebeleri ekler; sınıftan çıkan / pasifleri listeden düşürür.

    Elle çıkarılanlar (aktif=False kaydı) otomatik geri eklenmez; manuel Ekle ile döner.
    """
    # Havuz satırlarını seed döngüsüne girmeden oluştur
    for s in SINIF_SEVIYELERI:
        YemekciSinifHavuzu.objects.get_or_create(
            sinif=s,
            defaults={"renk": SINIF_RENKLERI[s], "aktif": True},
        )
    ayarlari_al()

    siniflar = [sinif] if sinif in SINIF_SEVIYELERI else list(SINIF_SEVIYELERI)
    eklenen = 0
    for s in siniflar:
        havuz = YemekciSinifHavuzu.objects.filter(sinif=s).first()
        if not havuz:
            continue

        for kayit in havuz.kayitlar.filter(aktif=True).select_related(
            "talebe", "talebe__sinif_sube"
        ):
            seviye = (
                _talebe_sinif_seviyesi(kayit.talebe) if kayit.talebe.aktif else None
            )
            if seviye != s:
                kayit.aktif = False
                kayit.save(update_fields=["aktif"])

        mevcut_ids = set(havuz.kayitlar.values_list("talebe_id", flat=True))
        max_sira = (
            YemekciHavuzKaydi.objects.filter(havuz=havuz).aggregate(m=Max("sira")).get(
                "m"
            )
            or -1
        )
        for talebe in _sinif_aktif_talebeler(s):
            if talebe.pk in mevcut_ids:
                continue
            max_sira += 1
            YemekciHavuzKaydi.objects.create(
                havuz=havuz, talebe=talebe, sira=max_sira, aktif=True
            )
            eklenen += 1
            mevcut_ids.add(talebe.pk)

        for idx, k in enumerate(
            havuz.kayitlar.filter(aktif=True).order_by("sira", "id")
        ):
            if k.sira != idx:
                k.sira = idx
                k.save(update_fields=["sira"])
    return eklenen


def talebe_havuza_senkronize(talebe: Talebe) -> None:
    """Tek talebe kaydı sonrası: doğru sınıfa ekle (yeni ise), diğer havuzlardan çıkar."""
    if not talebe or not talebe.pk:
        return
    havuzlari_kur(seed_talebeler=False)
    seviye = _talebe_sinif_seviyesi(talebe) if talebe.aktif else None

    for kayit in YemekciHavuzKaydi.objects.filter(
        talebe=talebe, aktif=True
    ).select_related("havuz"):
        if seviye is None or kayit.havuz.sinif != seviye:
            kayit.aktif = False
            kayit.save(update_fields=["aktif"])

    if seviye is None:
        return

    havuz = YemekciSinifHavuzu.objects.filter(sinif=seviye).first()
    if not havuz:
        return
    # Elle çıkarılmış veya zaten listede → dokunma
    if YemekciHavuzKaydi.objects.filter(havuz=havuz, talebe=talebe).exists():
        return
    kayit_ekle(seviye, talebe.pk)


def sinif_havuzlari() -> list[YemekciSinifHavuzu]:
    havuzlari_kur(seed_talebeler=True)
    return list(
        YemekciSinifHavuzu.objects.filter(aktif=True, sinif__in=SINIF_SEVIYELERI).order_by(
            "sinif"
        )
    )


def havuz_kayitlari(sinif: str) -> list[YemekciHavuzKaydi]:
    havuz = YemekciSinifHavuzu.objects.filter(sinif=sinif, aktif=True).first()
    if not havuz:
        return []
    return list(
        havuz.kayitlar.filter(aktif=True)
        .select_related("talebe", "talebe__sinif_sube")
        .order_by("sira", "id")
    )


def _cikar_bayraklari(
    hafta_sonu_cikar: bool | None = None,
    *,
    cumartesi_cikar: bool | None = None,
    pazar_cikar: bool | None = None,
    ayar: YemekciAyar | None = None,
) -> tuple[bool, bool]:
    """Cumartesi ve pazar ayrı. Eski tek bayrak ikisini birden yönetir."""
    if cumartesi_cikar is None and pazar_cikar is None:
        if hafta_sonu_cikar is not None:
            return bool(hafta_sonu_cikar), bool(hafta_sonu_cikar)
        if ayar is None:
            ayar = ayarlari_al()
        return ayar.cumartesi_cikar, ayar.pazar_cikar
    if cumartesi_cikar is None or pazar_cikar is None:
        if ayar is not None:
            taban_cmt, taban_paz = ayar.cumartesi_cikar, ayar.pazar_cikar
        elif hafta_sonu_cikar is not None:
            taban_cmt = taban_paz = bool(hafta_sonu_cikar)
        else:
            taban_cmt = taban_paz = True
        if cumartesi_cikar is None:
            cumartesi_cikar = taban_cmt
        if pazar_cikar is None:
            pazar_cikar = taban_paz
    return bool(cumartesi_cikar), bool(pazar_cikar)


def _is_workday(
    gun: date,
    hafta_sonu_cikar: bool | None = None,
    *,
    cumartesi_cikar: bool | None = None,
    pazar_cikar: bool | None = None,
) -> bool:
    cmt, paz = _cikar_bayraklari(
        hafta_sonu_cikar,
        cumartesi_cikar=cumartesi_cikar,
        pazar_cikar=pazar_cikar,
    )
    wd = gun.weekday()
    if wd == 5:
        return not cmt
    if wd == 6:
        return not paz
    return True


def workday_index(
    tarih: date,
    baslangic: date,
    hafta_sonu_cikar: bool | None = None,
    *,
    cumartesi_cikar: bool | None = None,
    pazar_cikar: bool | None = None,
) -> int:
    """baslangic dahil, tarih gününe kadar (dahil) kaçıncı görev günü (0-based)."""
    if tarih < baslangic:
        return 0
    cmt, paz = _cikar_bayraklari(
        hafta_sonu_cikar,
        cumartesi_cikar=cumartesi_cikar,
        pazar_cikar=pazar_cikar,
    )
    idx = 0
    gun = baslangic
    while gun < tarih:
        if _is_workday(gun, cumartesi_cikar=cmt, pazar_cikar=paz):
            idx += 1
        gun += timedelta(days=1)
    if not _is_workday(tarih, cumartesi_cikar=cmt, pazar_cikar=paz):
        return max(0, idx - 1) if idx else 0
    return idx


def dongu_sira(
    tarih: date,
    baslangic: date,
    toplam: int,
    *,
    hafta_sonu_cikar: bool | None = None,
    cumartesi_cikar: bool | None = None,
    pazar_cikar: bool | None = None,
) -> dict[str, Any]:
    """Görev atamasını değiştirmez. 1 tabanlı döngü konumunu söyler.

    Görev gününde ``bugun`` o günün sırasıdır. Görev olmayan günde
    ``bugun`` boştur; ``kalinan`` son görev gününün sırası, ``siradaki``
    bir sonraki görev gününün sırasıdır.
    """
    if toplam <= 0:
        return {
            "gorev_gunu": False,
            "bugun": None,
            "kalinan": None,
            "siradaki": None,
            "toplam": 0,
        }
    cmt, paz = _cikar_bayraklari(
        hafta_sonu_cikar,
        cumartesi_cikar=cumartesi_cikar,
        pazar_cikar=pazar_cikar,
    )
    gorev = _is_workday(tarih, cumartesi_cikar=cmt, pazar_cikar=paz)
    idx = workday_index(
        tarih,
        baslangic,
        cumartesi_cikar=cmt,
        pazar_cikar=paz,
    )
    kalinan = (idx % toplam) + 1
    siradaki = ((idx + 1) % toplam) + 1
    return {
        "gorev_gunu": gorev,
        "bugun": kalinan if gorev else None,
        "kalinan": kalinan,
        "siradaki": siradaki,
        "toplam": toplam,
    }


def aralik_gunleri(
    baslangic: date,
    bitis: date,
    *,
    hafta_sonu_cikar: bool | None = None,
    cumartesi_cikar: bool | None = None,
    pazar_cikar: bool | None = None,
) -> list[date]:
    cmt, paz = _cikar_bayraklari(
        hafta_sonu_cikar,
        cumartesi_cikar=cumartesi_cikar,
        pazar_cikar=pazar_cikar,
    )
    gunler: list[date] = []
    gun = baslangic
    while gun <= bitis:
        if _is_workday(gun, cumartesi_cikar=cmt, pazar_cikar=paz):
            gunler.append(gun)
        gun += timedelta(days=1)
    return gunler


def _talebe_karti(talebe: Talebe | None) -> dict[str, Any] | None:
    if not talebe:
        return None
    sinif_label = ""
    if getattr(talebe, "sinif_sube_id", None) and talebe.sinif_sube_id:
        ss = talebe.sinif_sube
        sinif_label = f"{ss.sinif}-{ss.sube}"
    else:
        sinif_label = f"{talebe.sinif or ''}-{talebe.sube or ''}".strip("-")
    return {
        "id": talebe.pk,
        "ad": talebe.ad_soyad,
        "sinif_label": sinif_label or "—",
    }


def gorevli_hesapla(
    tarih: date,
    sinif: str,
    ayar: YemekciAyar | None = None,
    *,
    cumartesi_cikar: bool | None = None,
    pazar_cikar: bool | None = None,
) -> dict[str, Any]:
    """Bir sınıf için o günün görevlisi (manuel override öncelikli).

    ``ayar`` verilmezse tek satırlık YemekciAyar tekrar sorgulanır — bu
    fonksiyon bir tarih/sınıf döngüsü içinde çağrılıyorsa (bkz.
    gunun_yemekcileri/aralik_uret) çağıran tarafın ``ayar``'ı bir kez çekip
    geçmesi gereksiz tekrar sorguyu önler.
    """
    if ayar is None:
        ayar = ayarlari_al()
    cmt, paz = _cikar_bayraklari(
        cumartesi_cikar=cumartesi_cikar,
        pazar_cikar=pazar_cikar,
        ayar=ayar,
    )
    gorev_gunu = _is_workday(tarih, cumartesi_cikar=cmt, pazar_cikar=paz)
    kayitlar = havuz_kayitlari(sinif)
    konum = dongu_sira(
        tarih,
        ayar.dongu_baslangic,
        len(kayitlar),
        cumartesi_cikar=cmt,
        pazar_cikar=paz,
    )
    kalinan_ad = None
    siradaki_ad = None
    if konum["kalinan"]:
        kalinan_ad = kayitlar[konum["kalinan"] - 1].talebe.ad_soyad
    if konum["siradaki"]:
        siradaki_ad = kayitlar[konum["siradaki"] - 1].talebe.ad_soyad
    sira_alan = {
        "sira": konum["bugun"],
        "sira_toplam": konum["toplam"],
        "kalinan_sira": konum["kalinan"],
        "siradaki_sira": konum["siradaki"],
        "kalinan_ad": kalinan_ad,
        "siradaki_ad": siradaki_ad,
    }
    override = (
        YemekciGunAtama.objects.filter(tarih=tarih, sinif=sinif)
        .select_related("talebe", "talebe__sinif_sube")
        .first()
    )
    if override and override.manuel:
        return {
            "sinif": sinif,
            "etiket": SINIF_ETIKET.get(sinif, sinif),
            "renk": SINIF_RENKLERI.get(sinif, "#64748b"),
            "talebe": _talebe_karti(override.talebe),
            "manuel": True,
            "atama_id": override.pk,
            "hafta_sonu": not gorev_gunu,
            **sira_alan,
        }

    talebe = None
    if kayitlar and gorev_gunu:
        idx = workday_index(
            tarih,
            ayar.dongu_baslangic,
            cumartesi_cikar=cmt,
            pazar_cikar=paz,
        )
        kayit = kayitlar[idx % len(kayitlar)]
        talebe = kayit.talebe
    elif override:
        talebe = override.talebe

    return {
        "sinif": sinif,
        "etiket": SINIF_ETIKET.get(sinif, sinif),
        "renk": SINIF_RENKLERI.get(sinif, "#64748b"),
        "talebe": _talebe_karti(talebe),
        "manuel": bool(override and override.manuel),
        "atama_id": override.pk if override else None,
        "hafta_sonu": not gorev_gunu,
        **sira_alan,
    }


def gunun_yemekcileri(tarih: date | None = None) -> list[dict[str, Any]]:
    """Dashboard kartı için bugünkü sınıf görevlileri.

    Bu fonksiyon (havuz senkronizasyonu dahil) tek bir dashboard
    render'ında 2 farklı yerden (kısayol rozeti + günlük görevler kartı)
    art arda çağrılıyor — 10 saniyelik kısa bir cache, aynı render
    içindeki bu tekrarı önlüyor. Manuel bir atama kaydedildikten hemen
    sonra görüntülenirse en fazla ~10sn eski veri görünebilir; bu kadar
    kısa bir pencerede kabul edilebilir bir risk (senkronizasyon
    mantığının KENDİSİ değişmedi, sadece ne sıklıkla çalıştığı).
    """
    tarih = tarih or localdate()
    ayar = ayarlari_al()
    cache_key = (
        f"yemekci:gunun_yemekcileri:{tarih.isoformat()}"
        f":{int(ayar.cumartesi_cikar)}:{int(ayar.pazar_cikar)}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    havuzlari_kur(seed_talebeler=True)
    sonuc = [gorevli_hesapla(tarih, s, ayar) for s in SINIF_SEVIYELERI]
    cache.set(cache_key, sonuc, 10)
    return sonuc


def aralik_uret(
    baslangic: date,
    bitis: date,
    *,
    hafta_sonu_cikar: bool | None = None,
    cumartesi_cikar: bool | None = None,
    pazar_cikar: bool | None = None,
    kaydet: bool = False,
    user: User | None = None,
) -> list[dict[str, Any]]:
    """Tarih aralığı için satır listesi; kaydet=True ise YemekciGunAtama yazar."""
    cmt, paz = _cikar_bayraklari(
        hafta_sonu_cikar,
        cumartesi_cikar=cumartesi_cikar,
        pazar_cikar=pazar_cikar,
    )
    gunler = aralik_gunleri(
        baslangic,
        bitis,
        cumartesi_cikar=cmt,
        pazar_cikar=paz,
    )
    satirlar: list[dict[str, Any]] = []
    ayar = ayarlari_al()
    for gun in gunler:
        hucreler = {}
        for sinif in SINIF_SEVIYELERI:
            kart = gorevli_hesapla(
                gun,
                sinif,
                ayar,
                cumartesi_cikar=cmt,
                pazar_cikar=paz,
            )
            hucreler[sinif] = kart
            if kaydet and kart.get("talebe"):
                YemekciGunAtama.objects.update_or_create(
                    tarih=gun,
                    sinif=sinif,
                    defaults={
                        "talebe_id": kart["talebe"]["id"],
                        "manuel": False,
                        "olusturan": user,
                    },
                )
        satirlar.append({"tarih": gun, "hucreler": hucreler})
    return satirlar


@transaction.atomic
def kayit_ekle(sinif: str, talebe_id: int) -> YemekciHavuzKaydi:
    havuzlari_kur(seed_talebeler=False)
    havuz = YemekciSinifHavuzu.objects.get(sinif=sinif)
    talebe = Talebe.objects.get(pk=talebe_id, aktif=True)
    mevcut = YemekciHavuzKaydi.objects.filter(havuz=havuz, talebe=talebe).first()
    if mevcut:
        if not mevcut.aktif:
            mevcut.aktif = True
            mevcut.save(update_fields=["aktif"])
        return mevcut
    max_sira = (
        YemekciHavuzKaydi.objects.filter(havuz=havuz).aggregate(m=Max("sira")).get("m")
        or -1
    )
    return YemekciHavuzKaydi.objects.create(
        havuz=havuz, talebe=talebe, sira=max_sira + 1, aktif=True
    )


@transaction.atomic
def kayit_sil(kayit_id: int) -> None:
    """Listeden çıkar — soft delete (senkron tekrar eklemesin)."""
    kayit = YemekciHavuzKaydi.objects.filter(pk=kayit_id).first()
    if not kayit:
        return
    havuz = kayit.havuz
    if kayit.aktif:
        kayit.aktif = False
        kayit.save(update_fields=["aktif"])
    for sira, k in enumerate(havuz.kayitlar.filter(aktif=True).order_by("sira", "id")):
        if k.sira != sira:
            k.sira = sira
            k.save(update_fields=["sira"])


@transaction.atomic
def kayitlari_sirala(sinif: str, kayit_ids: list[int]) -> bool:
    havuz = YemekciSinifHavuzu.objects.filter(sinif=sinif).first()
    if not havuz:
        return False
    izinli = set(havuz.kayitlar.filter(aktif=True).values_list("id", flat=True))
    if not set(kayit_ids).issubset(izinli):
        return False
    for sira, kid in enumerate(kayit_ids):
        YemekciHavuzKaydi.objects.filter(pk=kid, havuz=havuz).update(sira=sira)
    return True


def gorevli_degistir(
    tarih: date, sinif: str, talebe_id: int, user: User | None = None
) -> YemekciGunAtama:
    talebe = Talebe.objects.get(pk=talebe_id, aktif=True)
    atama, _ = YemekciGunAtama.objects.update_or_create(
        tarih=tarih,
        sinif=sinif,
        defaults={"talebe": talebe, "manuel": True, "olusturan": user},
    )
    return atama


def gun_atama_sil(tarih: date, sinif: str) -> None:
    YemekciGunAtama.objects.filter(tarih=tarih, sinif=sinif).delete()


def takvim_ay(yil: int, ay: int) -> list[list[dict[str, Any] | None]]:
    """Ay ızgarası: her hücre {gun, yemekciler} veya None."""
    weeks = monthcalendar(yil, ay)
    grid: list[list[dict[str, Any] | None]] = []
    for week in weeks:
        row: list[dict[str, Any] | None] = []
        for day in week:
            if day == 0:
                row.append(None)
            else:
                d = date(yil, ay, day)
                row.append({"tarih": d, "yemekciler": gunun_yemekcileri(d)})
        grid.append(row)
    return grid


def secilebilir_talebeler(sinif: str) -> list[Talebe]:
    qs = Talebe.objects.filter(aktif=True).select_related("sinif_sube")
    filtered = qs.filter(sinif_sube__sinif=sinif).order_by(
        "sinif_sube__sube", "ad_soyad"
    )
    if filtered.exists():
        return list(filtered)
    return list(qs.filter(sinif=sinif).order_by("sube", "ad_soyad"))


def panel_baglami(
    *,
    tarih: date | None = None,
    sekme: str = "bugun",
    ay: int | None = None,
    yil: int | None = None,
) -> dict[str, Any]:
    havuzlari_kur(seed_talebeler=True)
    ayar = ayarlari_al()
    tarih = tarih or localdate()
    bugun = localdate()
    yil = yil or tarih.year
    ay = ay or tarih.month

    havuz_detay = []
    for h in sinif_havuzlari():
        kayitlar = [
            {
                "id": k.id,
                "sira": k.sira,
                "talebe_id": k.talebe_id,
                "ad": k.talebe.ad_soyad,
                "sinif_label": (
                    f"{k.talebe.sinif_sube.sinif}-{k.talebe.sinif_sube.sube}"
                    if k.talebe.sinif_sube_id
                    else f"{k.talebe.sinif}-{k.talebe.sube}"
                ),
            }
            for k in havuz_kayitlari(h.sinif)
        ]
        konum = dongu_sira(
            bugun,
            ayar.dongu_baslangic,
            len(kayitlar),
            cumartesi_cikar=ayar.cumartesi_cikar,
            pazar_cikar=ayar.pazar_cikar,
        )
        if konum["kalinan"]:
            konum["kalinan_ad"] = kayitlar[konum["kalinan"] - 1]["ad"]
        else:
            konum["kalinan_ad"] = None
        if konum["siradaki"]:
            konum["siradaki_ad"] = kayitlar[konum["siradaki"] - 1]["ad"]
        else:
            konum["siradaki_ad"] = None
        havuz_detay.append(
            {
                "sinif": h.sinif,
                "etiket": h.etiket,
                "renk": h.renk_kod,
                "kayitlar": kayitlar,
                "sira": konum,
                "secenekler": [
                    {"id": t.pk, "ad": t.ad_soyad}
                    for t in secilebilir_talebeler(h.sinif)
                    if t.pk not in {k["talebe_id"] for k in kayitlar}
                ],
            }
        )

    return {
        "sekme": sekme,
        "tarih": tarih,
        "bugun": bugun,
        "ayar": ayar,
        "yemekciler": gunun_yemekcileri(tarih),
        "havuzlar": havuz_detay,
        "takvim": takvim_ay(yil, ay) if sekme == "takvim" else None,
        "takvim_yil": yil,
        "takvim_ay": ay,
        "sinif_renkleri": SINIF_RENKLERI,
        "sinif_etiket": SINIF_ETIKET,
        "sure_secenekleri": [
            (7, "7 Günlük (1 Hafta)"),
            (15, "15 Günlük (2 Hafta)"),
            (30, "30 Günlük (1 Ay)"),
            (60, "60 Günlük (2 Ay)"),
        ],
    }
