"""Veli paneli görüntüleme kaydı ve yönetim özeti."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from django.db.models import Max, QuerySet
from django.utils import timezone

from takip.duyuru_service import veli_duyurulari
from takip.models import KttSonucu, Talebe, VeliHesap
from takip.deneme_service import talebe_deneme_sonuclari
from takip.veli_goruntuleme_models import VeliIcerikGoruntuleme
from takip.veli_service import veli_talebeleri
from takip.yazili_takip_service import talebe_yazili_sonuclari


def sayfa_goruntulendi(
    veli: VeliHesap,
    sayfa: str,
    *,
    talebe: Talebe | None = None,
    meta: dict | None = None,
) -> None:
    _kaydet(
        veli,
        VeliIcerikGoruntuleme.Tur.SAYFA,
        0,
        talebe=talebe,
        sayfa=sayfa,
        meta=meta,
    )


def duyurular_goruntulendi(veli: VeliHesap, duyurular, *, sayfa: str) -> None:
    sayfa_goruntulendi(veli, sayfa)
    for duyuru in duyurular:
        _kaydet(
            veli,
            VeliIcerikGoruntuleme.Tur.DUYURU,
            duyuru.pk,
            sayfa=sayfa,
            meta={"baslik": duyuru.baslik},
        )


def sinav_sayfasi_goruntulendi(
    veli: VeliHesap,
    talebe: Talebe,
    tab: str,
    *,
    ktt_sonuclari,
    deneme_sonuclari,
    yazili_sonuclari,
) -> None:
    sayfa = f"veli_talebe_sinavlar:{tab}"
    sayfa_goruntulendi(veli, sayfa, talebe=talebe, meta={"tab": tab})

    if tab == "ktt":
        for sonuc in ktt_sonuclari:
            _kaydet(
                veli,
                VeliIcerikGoruntuleme.Tur.KTT,
                sonuc.pk,
                talebe=talebe,
                sayfa=sayfa,
                meta={"ktt_id": sonuc.ktt_id},
            )
    elif tab == "deneme":
        for sonuc in deneme_sonuclari:
            _kaydet(
                veli,
                VeliIcerikGoruntuleme.Tur.DENEME,
                sonuc.pk,
                talebe=talebe,
                sayfa=sayfa,
                meta={"deneme_id": sonuc.deneme_id},
            )
    elif tab == "yazili":
        for sonuc in yazili_sonuclari:
            _kaydet(
                veli,
                VeliIcerikGoruntuleme.Tur.YAZILI,
                sonuc.pk,
                talebe=talebe,
                sayfa=sayfa,
                meta={"sinav_id": sonuc.sinav_id},
            )


def dini_ders_goruntulendi(veli: VeliHesap, talebe: Talebe, *, alan_id: int | None) -> None:
    sayfa_goruntulendi(
        veli,
        "veli_talebe_dini_ders",
        talebe=talebe,
        meta={"alan_id": alan_id},
    )
    if alan_id:
        _kaydet(
            veli,
            VeliIcerikGoruntuleme.Tur.DINI_DERS,
            alan_id,
            talebe=talebe,
            sayfa="veli_talebe_dini_ders",
        )


def aidat_goruntulendi(veli: VeliHesap, talebe: Talebe) -> None:
    sayfa_goruntulendi(veli, "veli_talebe_aidat", talebe=talebe)
    _kaydet(
        veli,
        VeliIcerikGoruntuleme.Tur.AIDAT,
        talebe.pk,
        talebe=talebe,
        sayfa="veli_talebe_aidat",
    )


def _kaydet(
    veli: VeliHesap,
    tur: str,
    referans_id: int,
    *,
    talebe: Talebe | None = None,
    sayfa: str = "",
    meta: dict | None = None,
) -> None:
    meta = meta or {}
    obj, created = VeliIcerikGoruntuleme.objects.get_or_create(
        veli=veli,
        talebe=talebe,
        tur=tur,
        referans_id=referans_id,
        defaults={"sayfa": sayfa, "meta": meta},
    )
    if not created:
        obj.sayfa = sayfa or obj.sayfa
        if meta:
            obj.meta = {**obj.meta, **meta}
        obj.save(update_fields=["sayfa", "meta", "son_goruntulenme"])


@dataclass
class IcerikOzet:
    toplam: int = 0
    gorulen: int = 0
    gorulmeyen: int = 0
    oran: float = 0.0


@dataclass
class VeliGoruntulemeOzet:
    veli: VeliHesap
    talebeler: list[Talebe] = field(default_factory=list)
    son_aktivite: datetime | None = None
    hic_giris: bool = True
    duyuru: IcerikOzet = field(default_factory=IcerikOzet)
    ktt: IcerikOzet = field(default_factory=IcerikOzet)
    deneme: IcerikOzet = field(default_factory=IcerikOzet)
    yazili: IcerikOzet = field(default_factory=IcerikOzet)

    @property
    def durum(self) -> str:
        if self.hic_giris:
            return "hic_giris"
        bekleyen = (
            self.duyuru.gorulmeyen
            + self.ktt.gorulmeyen
            + self.deneme.gorulmeyen
        )
        if bekleyen == 0:
            return "tamam"
        return "eksik"

    @property
    def durum_etiketi(self) -> str:
        return {
            "hic_giris": "Henüz giriş yok",
            "tamam": "Güncel",
            "eksik": "Okunmamış içerik var",
        }[self.durum]


def _ozet_hesapla(toplam: int, gorulen: int) -> IcerikOzet:
    gorulen = min(gorulen, toplam) if toplam else gorulen
    gorulmeyen = max(0, toplam - gorulen)
    oran = round((gorulen / toplam) * 100, 1) if toplam else 100.0
    return IcerikOzet(toplam=toplam, gorulen=gorulen, gorulmeyen=gorulmeyen, oran=oran)


def _gorulen_id_set(
    kayitlar: QuerySet[VeliIcerikGoruntuleme],
    tur: str,
    *,
    talebe_id: int | None = None,
) -> set[int]:
    qs = kayitlar.filter(tur=tur)
    if talebe_id is not None:
        qs = qs.filter(talebe_id=talebe_id)
    return set(qs.values_list("referans_id", flat=True))


def veli_goruntuleme_ozeti(veli: VeliHesap) -> VeliGoruntulemeOzet:
    talebeler = list(veli_talebeleri(veli))
    kayitlar = VeliIcerikGoruntuleme.objects.filter(veli=veli)
    son = kayitlar.aggregate(t=Max("son_goruntulenme"))["t"]

    duyuru_toplam = veli_duyurulari().count()
    duyuru_gorulen = kayitlar.filter(tur=VeliIcerikGoruntuleme.Tur.DUYURU).count()

    ktt_toplam = 0
    ktt_gorulen = 0
    deneme_toplam = 0
    deneme_gorulen = 0
    yazili_toplam = 0
    yazili_gorulen = 0

    for talebe in talebeler:
        ktt_ids = set(
            KttSonucu.objects.filter(
                talebe=talebe,
                ktt__veliye_goster=True,
                ktt__aktif=True,
            ).values_list("pk", flat=True)
        )
        deneme_ids = set(
            talebe_deneme_sonuclari(talebe).values_list("pk", flat=True)
        )
        yazili_ids = set(
            talebe_yazili_sonuclari(talebe).values_list("pk", flat=True)
        )

        ktt_toplam += len(ktt_ids)
        deneme_toplam += len(deneme_ids)
        yazili_toplam += len(yazili_ids)

        ktt_gorulen += len(_gorulen_id_set(kayitlar, VeliIcerikGoruntuleme.Tur.KTT, talebe_id=talebe.pk) & ktt_ids)
        deneme_gorulen += len(_gorulen_id_set(kayitlar, VeliIcerikGoruntuleme.Tur.DENEME, talebe_id=talebe.pk) & deneme_ids)
        yazili_gorulen += len(_gorulen_id_set(kayitlar, VeliIcerikGoruntuleme.Tur.YAZILI, talebe_id=talebe.pk) & yazili_ids)

    hic_giris = not kayitlar.filter(tur=VeliIcerikGoruntuleme.Tur.SAYFA).exists()

    return VeliGoruntulemeOzet(
        veli=veli,
        talebeler=talebeler,
        son_aktivite=son,
        hic_giris=hic_giris,
        duyuru=_ozet_hesapla(duyuru_toplam, duyuru_gorulen),
        ktt=_ozet_hesapla(ktt_toplam, ktt_gorulen),
        deneme=_ozet_hesapla(deneme_toplam, deneme_gorulen),
        yazili=_ozet_hesapla(yazili_toplam, yazili_gorulen),
    )


def veli_goruntuleme_panel_listesi() -> list[VeliGoruntulemeOzet]:
    hesaplar = (
        VeliHesap.objects.filter(aktif=True)
        .select_related("user")
        .prefetch_related("talebe_baglantilari__talebe")
        .order_by("ad_soyad")
    )
    ozetler = [veli_goruntuleme_ozeti(v) for v in hesaplar]
    return ozetler


@dataclass
class IcerikSatir:
    baslik: str
    alt: str
    goruldu: bool
    ilk: datetime | None
    son: datetime | None


@dataclass
class VeliGoruntulemeDetay:
    ozet: VeliGoruntulemeOzet
    duyurular: list[IcerikSatir]
    talebe_bloklari: list[dict]
    son_hareketler: list[VeliIcerikGoruntuleme]


def veli_goruntuleme_detay(veli: VeliHesap) -> VeliGoruntulemeDetay:
    ozet = veli_goruntuleme_ozeti(veli)
    kayitlar = VeliIcerikGoruntuleme.objects.filter(veli=veli)

    duyuru_kayit = {
        k.referans_id: k
        for k in kayitlar.filter(tur=VeliIcerikGoruntuleme.Tur.DUYURU)
    }
    duyurular = []
    for duyuru in veli_duyurulari():
        kayit = duyuru_kayit.get(duyuru.pk)
        duyurular.append(
            IcerikSatir(
                baslik=duyuru.baslik,
                alt=duyuru.baslangic.strftime("%d.%m.%Y"),
                goruldu=bool(kayit),
                ilk=kayit.ilk_goruntulenme if kayit else None,
                son=kayit.son_goruntulenme if kayit else None,
            )
        )

    talebe_bloklari = []
    for talebe in ozet.talebeler:
        ktt_kayit = {
            k.referans_id: k
            for k in kayitlar.filter(
                tur=VeliIcerikGoruntuleme.Tur.KTT,
                talebe=talebe,
            )
        }
        deneme_kayit = {
            k.referans_id: k
            for k in kayitlar.filter(
                tur=VeliIcerikGoruntuleme.Tur.DENEME,
                talebe=talebe,
            )
        }

        ktt_satirlar = []
        for sonuc in KttSonucu.objects.filter(
            talebe=talebe,
            ktt__veliye_goster=True,
            ktt__aktif=True,
        ).select_related("ktt", "ktt__ders").order_by("-ktt__sinav_tarihi", "-id"):
            kayit = ktt_kayit.get(sonuc.pk)
            ktt_satirlar.append(
                IcerikSatir(
                    baslik=f"{sonuc.ktt.ad} · {sonuc.ktt.ders.ad if sonuc.ktt.ders else '—'}",
                    alt=sonuc.ktt.sinav_tarihi.strftime("%d.%m.%Y"),
                    goruldu=bool(kayit),
                    ilk=kayit.ilk_goruntulenme if kayit else None,
                    son=kayit.son_goruntulenme if kayit else None,
                )
            )

        deneme_satirlar = []
        for sonuc in talebe_deneme_sonuclari(talebe):
            kayit = deneme_kayit.get(sonuc.pk)
            deneme_satirlar.append(
                IcerikSatir(
                    baslik=sonuc.deneme.ad,
                    alt=sonuc.deneme.sinav_tarihi.strftime("%d.%m.%Y"),
                    goruldu=bool(kayit),
                    ilk=kayit.ilk_goruntulenme if kayit else None,
                    son=kayit.son_goruntulenme if kayit else None,
                )
            )

        talebe_bloklari.append(
            {
                "talebe": talebe,
                "ktt": ktt_satirlar,
                "deneme": deneme_satirlar,
            }
        )

    son_hareketler = list(
        kayitlar.select_related("talebe").order_by("-son_goruntulenme")[:30]
    )

    return VeliGoruntulemeDetay(
        ozet=ozet,
        duyurular=duyurular,
        talebe_bloklari=talebe_bloklari,
        son_hareketler=son_hareketler,
    )


def panel_istatistikleri(ozetler: list[VeliGoruntulemeOzet]) -> dict:
    toplam = len(ozetler)
    hic_giris = sum(1 for o in ozetler if o.durum == "hic_giris")
    eksik = sum(1 for o in ozetler if o.durum == "eksik")
    tamam = sum(1 for o in ozetler if o.durum == "tamam")
    return {
        "toplam_veli": toplam,
        "hic_giris": hic_giris,
        "eksik": eksik,
        "tamam": tamam,
        "simdi": timezone.localtime(),
    }


def sinif_bazli_veli_takip_verisi() -> dict:
    """Aktif sınıflar için veli giriş / okuma durumu — AI raporu kaynağı."""
    from django.utils.timezone import localdate

    from takip.models import SinifSube
    from takip.wave0_models import VeliTalebeBaglantisi

    ozet_map = {o.veli.pk: o for o in veli_goruntuleme_panel_listesi()}

    talebe_veli: dict[int, VeliHesap] = {}
    for bag in VeliTalebeBaglantisi.objects.filter(veli__aktif=True).select_related(
        "veli", "talebe"
    ):
        if bag.talebe_id not in talebe_veli:
            talebe_veli[bag.talebe_id] = bag.veli

    sinif_bloklari: list[dict] = []
    for sinif in SinifSube.objects.filter(aktif=True).order_by("sinif", "sube"):
        ogrenciler = Talebe.objects.filter(
            sinif_sube=sinif,
            durum=Talebe.Durum.AKTIF,
        ).order_by("ad_soyad")

        if not ogrenciler.exists():
            continue

        satirlar: list[dict] = []
        giris_yok: list[str] = []
        eksik: list[str] = []
        guncel: list[str] = []
        veli_yok: list[str] = []

        for talebe in ogrenciler:
            veli = talebe_veli.get(talebe.pk)
            if not veli:
                veli_yok.append(talebe.ad_soyad)
                satirlar.append(
                    {
                        "ogrenci": talebe.ad_soyad,
                        "veli": None,
                        "durum": "veli_yok",
                        "durum_etiket": "Veli hesabı yok",
                        "son_aktivite": None,
                        "duyuru": "—",
                        "ktt": "—",
                        "deneme": "—",
                    }
                )
                continue

            oz = ozet_map.get(veli.pk) or veli_goruntuleme_ozeti(veli)
            etiket = f"{talebe.ad_soyad} (veli: {veli.ad_soyad})"
            if oz.durum == "hic_giris":
                giris_yok.append(etiket)
            elif oz.durum == "eksik":
                eksik.append(etiket)
            else:
                guncel.append(etiket)

            son = None
            if oz.son_aktivite:
                son = timezone.localtime(oz.son_aktivite).strftime("%d.%m.%Y %H:%M")

            satirlar.append(
                {
                    "ogrenci": talebe.ad_soyad,
                    "veli": veli.ad_soyad,
                    "durum": oz.durum,
                    "durum_etiket": oz.durum_etiketi,
                    "son_aktivite": son,
                    "duyuru": f"{oz.duyuru.gorulen}/{oz.duyuru.toplam}",
                    "ktt": f"{oz.ktt.gorulen}/{oz.ktt.toplam}",
                    "deneme": f"{oz.deneme.gorulen}/{oz.deneme.toplam}",
                }
            )

        sinif_bloklari.append(
            {
                "sinif": str(sinif),
                "sinif_id": sinif.pk,
                "toplam": len(satirlar),
                "giris_yok_sayisi": len(giris_yok),
                "eksik_sayisi": len(eksik),
                "guncel_sayisi": len(guncel),
                "veli_yok_sayisi": len(veli_yok),
                "giris_yok": giris_yok,
                "eksik": eksik,
                "guncel": guncel,
                "veli_yok": veli_yok,
                "ogrenciler": satirlar,
            }
        )

    return {
        "siniflar": sinif_bloklari,
        "toplam_sinif": len(sinif_bloklari),
        "tarih": localdate().isoformat(),
    }
