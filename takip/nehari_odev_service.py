"""Nehari günlük pano — ödev işareti ve o günkü akademik kayıtlar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Count, Max

from takip.deneme_models import DenemeSinavi, DenemeSonucu
from takip.dini_ders_takip_models import DiniDersKonuKaydi
from takip.gunluk_takip_models import GunlukTakipKaydi
from takip.ktt_models import KttSinav, KttSonucu
from takip.models import OkumaKaydi, Talebe
from takip.nehari_odev_models import NehariGunlukOdev, NehariOdevIsaret
from takip.ogretmen_not_models import OgretmenSinavNotu
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import kullanici_rol_slugleri
from takip.yazili_takip_models import YaziliSinav, YaziliSonuc


class NehariOdevHata(Exception):
    pass


@dataclass(frozen=True)
class ModulDurum:
    etiket: str
    ton: str


@dataclass(frozen=True)
class NehariSatir:
    talebe_id: int
    ad: str
    sinif: str
    yapildi: bool
    yoklama: ModulDurum
    kitap: ModulDurum
    dini: ModulDurum
    ktt: ModulDurum
    deneme: ModulDurum
    yazili: ModulDurum
    notu: ModulDurum


@dataclass(frozen=True)
class NehariOzet:
    toplam: int
    yapildi: int
    bekleyen: int
    yoklama: int
    kitap: int
    dini: int
    ktt: int
    deneme: int
    yazili: int
    not_girilen: int

    @property
    def oran(self) -> int:
        if not self.toplam:
            return 0
        return round(self.yapildi * 100 / self.toplam)


def nehari_talebeleri(user: User):
    """Nehari mesulün günlük listesi. Kapsam yoksa kurumun aktif talebeleri."""
    aktif = Talebe.objects.filter(durum=Talebe.Durum.AKTIF)
    if not user.is_authenticated:
        return Talebe.objects.none()
    if user.is_superuser or tum_talebe_kapsami_var(user):
        return aktif
    kapsam = yetkili_talebeler(user)
    if kapsam.exists():
        return kapsam
    if "nehari_mesul" in kullanici_rol_slugleri(user):
        return aktif
    return Talebe.objects.none()


def _sayi(deger) -> str:
    if deger is None:
        return ""
    sayi = Decimal(str(deger)).quantize(Decimal("0.01"))
    metin = f"{sayi:.2f}".rstrip("0").rstrip(".")
    return metin.replace(".", ",")


def _sinif_etiket(talebe: Talebe) -> str:
    if talebe.sinif and talebe.sube:
        return f"{talebe.sinif}-{talebe.sube}"
    return talebe.sinif or "Sınıf yok"


def _hedef_uyar(sinif_seviyesi: str, hedef: str, talebe: Talebe) -> bool:
    etiket = _sinif_etiket(talebe)
    parcalar = [p.strip() for p in (hedef or "").replace(";", ",").split(",") if p.strip()]
    if parcalar:
        return etiket in parcalar or (talebe.sinif or "") in parcalar
    return (sinif_seviyesi or "").strip() == (talebe.sinif or "").strip()


def _yoklama_durum(kod: str | None) -> ModulDurum:
    if kod == GunlukTakipKaydi.DevamDurumu.GELDI:
        return ModulDurum("Geldi", "ok")
    if kod == GunlukTakipKaydi.DevamDurumu.GEC:
        return ModulDurum("Geç", "warn")
    if kod == GunlukTakipKaydi.DevamDurumu.GELMEDI:
        return ModulDurum("Gelmedi", "danger")
    return ModulDurum("Kayıt yok", "muted")


def _sinav_etiket(sonuclar: list[str], sinav_var: bool, girilmedi: bool) -> ModulDurum:
    if sonuclar:
        return ModulDurum(" · ".join(sonuclar), "ok")
    if girilmedi:
        return ModulDurum("Girilmedi", "warn")
    if sinav_var:
        return ModulDurum("Katılmadı", "muted")
    return ModulDurum("—", "muted")


def nehari_panosu(
    user: User,
    tarih: date,
    *,
    sinif: str = "",
    q: str = "",
    durum: str = "",
) -> tuple[list[NehariSatir], NehariOzet, str]:
    talebeler = nehari_talebeleri(user).select_related("sinif_sube")
    if sinif:
        if "-" in sinif:
            seviye, _, sube = sinif.partition("-")
            talebeler = talebeler.filter(sinif=seviye, sube=sube)
        else:
            talebeler = talebeler.filter(sinif=sinif)
    if q:
        talebeler = talebeler.filter(ad_soyad__icontains=q.strip())
    talebeler = list(talebeler.order_by("sinif", "sube", "ad_soyad", "id"))
    ids = [t.id for t in talebeler]

    isaret = {
        kayit.talebe_id: kayit.yapildi
        for kayit in NehariOdevIsaret.objects.filter(talebe_id__in=ids, tarih=tarih)
    }
    yoklama = dict(
        GunlukTakipKaydi.objects.filter(talebe_id__in=ids, tarih=tarih).values_list(
            "talebe_id", "devam"
        )
    )
    kitap = {
        satir["zimmet__talebe_id"]: satir["sayfa"]
        for satir in OkumaKaydi.objects.filter(zimmet__talebe_id__in=ids, tarih=tarih)
        .values("zimmet__talebe_id")
        .annotate(sayfa=Max("son_sayfa"))
    }
    dini = {
        satir["talebe_id"]: satir["adet"]
        for satir in DiniDersKonuKaydi.objects.filter(
            talebe_id__in=ids,
            tamamlandi=True,
            tamamlanma_tarihi=tarih,
        )
        .values("talebe_id")
        .annotate(adet=Count("id"))
    }

    ktt_sinavlari = list(
        KttSinav.objects.filter(sinav_tarihi=tarih, aktif=True).prefetch_related(
            "haric_talebeler"
        )
    )
    ktt_haric = {
        sinav.id: {t.id for t in sinav.haric_talebeler.all()}
        for sinav in ktt_sinavlari
    }
    ktt_sonuc: dict[int, list[str]] = {}
    for sonuc in KttSonucu.objects.filter(
        talebe_id__in=ids, ktt__sinav_tarihi=tarih, ktt__aktif=True
    ).select_related("ktt__ders"):
        ktt_sonuc.setdefault(sonuc.talebe_id, []).append(
            f"{sonuc.ktt.ders.ad} {_sayi(sonuc.net)} net"
        )

    denemeler = list(DenemeSinavi.objects.filter(sinav_tarihi=tarih).exclude(durum="arsiv"))
    deneme_sonuc: dict[int, list[str]] = {}
    for sonuc in DenemeSonucu.objects.filter(
        talebe_id__in=ids, deneme__sinav_tarihi=tarih
    ).select_related("deneme"):
        deneme_sonuc.setdefault(sonuc.talebe_id, []).append(
            f"{sonuc.deneme.ad} {_sayi(sonuc.puan)} puan"
        )

    yazililar = list(
        YaziliSinav.objects.filter(sinav_tarihi=tarih)
        .exclude(durum=YaziliSinav.Durum.TASLAK)
        .select_related("kamp")
    )
    yazili_sonuc: dict[int, list[str]] = {}
    for sonuc in YaziliSonuc.objects.filter(
        talebe_id__in=ids, sinav__sinav_tarihi=tarih
    ).select_related("sinav"):
        yazili_sonuc.setdefault(sonuc.talebe_id, []).append(
            f"{sonuc.sinav.ders_ad} {_sayi(sonuc.puan)}"
        )

    hafta = tarih - timedelta(days=tarih.weekday())
    notlu = set(
        OgretmenSinavNotu.objects.filter(
            talebe_id__in=ids, hafta_baslangic=hafta
        ).values_list("talebe_id", flat=True)
    )

    satirlar: list[NehariSatir] = []
    for talebe in talebeler:
        yapildi = bool(isaret.get(talebe.id))
        if durum == "yapildi" and not yapildi:
            continue
        if durum == "bekleyen" and yapildi:
            continue

        sayfa = kitap.get(talebe.id)
        dini_adet = dini.get(talebe.id, 0)
        ktt_uyar = [s for s in ktt_sinavlari if _hedef_uyar(s.sinif_seviyesi, s.hedef_siniflar, talebe)]
        ktt_sonuc_var = bool(ktt_sonuc.get(talebe.id))
        ktt_girilmedi = (
            not ktt_sonuc_var
            and any(talebe.id not in ktt_haric.get(s.id, set()) for s in ktt_uyar)
        )

        deneme_uyar = [s for s in denemeler if (s.sinif_seviyesi or "").strip() == (talebe.sinif or "").strip()]
        yazili_uyar = [
            s
            for s in yazililar
            if _hedef_uyar(s.kamp.sinif_seviyesi if s.kamp_id else "", s.hedef_siniflar, talebe)
        ]

        satirlar.append(
            NehariSatir(
                talebe_id=talebe.id,
                ad=talebe.ad_soyad,
                sinif=_sinif_etiket(talebe),
                yapildi=yapildi,
                yoklama=_yoklama_durum(yoklama.get(talebe.id)),
                kitap=ModulDurum(f"s. {sayfa}", "ok") if sayfa is not None else ModulDurum("Kayıt yok", "muted"),
                dini=ModulDurum(f"{dini_adet} konu", "ok") if dini_adet else ModulDurum("Kayıt yok", "muted"),
                ktt=_sinav_etiket(
                    ktt_sonuc.get(talebe.id, []),
                    bool(ktt_uyar),
                    ktt_girilmedi,
                ),
                deneme=_sinav_etiket(
                    deneme_sonuc.get(talebe.id, []),
                    bool(deneme_uyar),
                    bool(deneme_uyar) and not deneme_sonuc.get(talebe.id),
                ),
                yazili=_sinav_etiket(
                    yazili_sonuc.get(talebe.id, []),
                    bool(yazili_uyar),
                    bool(yazili_uyar) and not yazili_sonuc.get(talebe.id),
                ),
                notu=ModulDurum("Bu hafta girildi", "ok") if talebe.id in notlu else ModulDurum("Bu hafta yok", "warn"),
            )
        )

    ozet = NehariOzet(
        toplam=len(satirlar),
        yapildi=sum(1 for s in satirlar if s.yapildi),
        bekleyen=sum(1 for s in satirlar if not s.yapildi),
        yoklama=sum(1 for s in satirlar if s.yoklama.etiket != "Kayıt yok"),
        kitap=sum(1 for s in satirlar if s.kitap.ton == "ok"),
        dini=sum(1 for s in satirlar if s.dini.ton == "ok"),
        ktt=sum(1 for s in satirlar if s.ktt.ton == "ok"),
        deneme=sum(1 for s in satirlar if s.deneme.ton == "ok"),
        yazili=sum(1 for s in satirlar if s.yazili.ton == "ok"),
        not_girilen=sum(1 for s in satirlar if s.notu.ton == "ok"),
    )
    metin_kaydi = NehariGunlukOdev.objects.filter(tarih=tarih).only("metin").first()
    return satirlar, ozet, (metin_kaydi.metin if metin_kaydi else "")


def sinif_secenekleri(user: User) -> list[str]:
    etiketler = set()
    for sinif, sube in nehari_talebeleri(user).values_list("sinif", "sube").distinct():
        if sinif and sube:
            etiketler.add(f"{sinif}-{sube}")
        elif sinif:
            etiketler.add(sinif)
    return sorted(etiketler)


def metin_kaydet(user: User, tarih: date, metin: str) -> NehariGunlukOdev:
    temiz = " ".join((metin or "").split())
    if not temiz:
        raise NehariOdevHata("Günün ödevini yazın.")
    if len(temiz) > 300:
        raise NehariOdevHata("Ödev metni 300 karakteri geçemez.")
    kayit, _ = NehariGunlukOdev.objects.update_or_create(
        tarih=tarih,
        defaults={"metin": temiz, "guncelleyen": user},
    )
    return kayit


def isaret_kaydet(user: User, tarih: date, talebe_id: int, yapildi: bool) -> NehariOdevIsaret:
    if not nehari_talebeleri(user).filter(pk=talebe_id).exists():
        raise NehariOdevHata("Bu talebe listenizde yok.")
    kayit, _ = NehariOdevIsaret.objects.update_or_create(
        talebe_id=talebe_id,
        tarih=tarih,
        defaults={"yapildi": yapildi, "isaretleyen": user},
    )
    return kayit
