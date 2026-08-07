"""Ana sayfa dashboard verileri."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from takip.deneme_models import DenemeSinavi
from takip.gunluk_takip_service import yetkili_gunluk_kayitlari
from takip.ktt_models import KttSinav
from takip.models import EtutHocasi, OkumaKaydi, Sinav
from takip.panel_permissions import (
    deneme_modulu_erisimi_var,
    egitim_modulu_erisimi_var,
    etut_plani_modulu_erisimi_var,
    gelisim_dosyasi_erisimi_var,
    gunluk_takip_modulu_erisimi_var,
    imam_muezzin_modulu_erisimi_var,
    ktt_modulu_erisimi_var,
    program_modulu_erisimi_var,
    rehberlik_modulu_erisimi_var,
    veli_iletisim_modulu_erisimi_var,
    temizlik_kat_sorumlusu_mu,
    temizlik_modulu_erisimi_var,
    temizlik_paneli_gorebilir,
    yemekcilik_modulu_erisimi_var,
    yonetim_erisimi_var,
)
from takip.permissions.service import kullanici_birincil_rol_slug
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.models import GorusmeTuru
from takip.rehberlik_service import (
    iletisim_gorebilir,
    rehberlik_gorebilir,
    yetkili_gorusmeler,
)

_AY_KISA = (
    "Oca",
    "Şub",
    "Mar",
    "Nis",
    "May",
    "Haz",
    "Tem",
    "Ağu",
    "Eyl",
    "Eki",
    "Kas",
    "Ara",
)


@dataclass(frozen=True)
class DashboardShortcut:
    key: str
    title: str
    subtitle: str
    url: str
    icon: str
    badge: int | None = None


@dataclass(frozen=True)
class DashboardActivity:
    baslik: str
    meta: str
    zaman: datetime
    zaman_etiketi: str
    bas_harf: str
    ton: str = "blue"


@dataclass(frozen=True)
class DashboardGorusme:
    pk: int
    baslik: str
    ozet: str
    talebe: str
    tur: str
    saat: str
    url: str


@dataclass(frozen=True)
class DashboardEtkinlik:
    tarih: date
    gun_etiketi: str
    baslik: str
    alt: str
    url: str
    ton: str = "blue"


def _kullanici_adi(user: User | None) -> str:
    if not user:
        return "Personel"
    ad = (user.get_full_name() or "").strip()
    return ad or user.username


def _bas_harf(metin: str) -> str:
    metin = (metin or "").strip()
    return metin[:1].upper() if metin else "?"


def _zaman_etiketi(dt: datetime | None) -> str:
    if not dt:
        return ""
    now = timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    delta = now - dt
    saniye = int(delta.total_seconds())
    if saniye < 60:
        return "Az önce"
    if saniye < 3600:
        return f"{saniye // 60} dk önce"
    if delta.days == 0:
        return f"{saniye // 3600} saat önce"
    if delta.days == 1:
        return "Dün"
    return dt.strftime("%d.%m.%Y")


def _tarih_etiketi(tarih: date) -> str:
    return f"{tarih.day} {_AY_KISA[tarih.month - 1]}"


def _saat_etiketi(deger: time | None) -> str:
    if not deger:
        return ""
    return deger.strftime("%H:%M")


def _gorev_badge_sayisi(user: User, bugun: date) -> int:
    sayac = 0
    if imam_muezzin_modulu_erisimi_var(user):
        from takip.imam_muezzin_service import bugunun_atamasi

        if bugunun_atamasi():
            sayac += 1
    if temizlik_modulu_erisimi_var(user):
        from takip.temizlik_service import bugunun_atamalari

        sayac += len(bugunun_atamalari())
    if yemekcilik_modulu_erisimi_var(user):
        from takip.yemekci_service import bugunun_atamalari

        sayac += len(bugunun_atamalari())
    return sayac


def _gorevler_url(user: User) -> str | None:
    if imam_muezzin_modulu_erisimi_var(user):
        return reverse("imam_muezzin_panel")
    if temizlik_modulu_erisimi_var(user):
        return reverse("temizlik_panel")
    if yemekcilik_modulu_erisimi_var(user):
        return reverse("yemekcilik_panel")
    return None


def dashboard_kisayollari(user: User, *, bugun: date | None = None) -> list[DashboardShortcut]:
    bugun = bugun or timezone.localdate()
    adaylar: list[tuple[bool, DashboardShortcut]] = []

    def ekle(
        kosul: bool,
        key: str,
        title: str,
        subtitle: str,
        url_name: str,
        icon: str,
        *,
        url_kwargs: dict | None = None,
        badge: int | None = None,
    ) -> None:
        if not kosul:
            return
        adaylar.append(
            (
                True,
                DashboardShortcut(
                    key=key,
                    title=title,
                    subtitle=subtitle,
                    url=reverse(url_name, kwargs=url_kwargs or {}),
                    icon=icon,
                    badge=badge,
                ),
            )
        )

    ekle(
        egitim_modulu_erisimi_var(user),
        "kitap",
        "Kitap Takip",
        "Zimmet, okuma ve arşiv",
        "kitap_listesi",
        "book",
    )
    ekle(
        egitim_modulu_erisimi_var(user),
        "talebeler",
        "Talebeler",
        "Liste ve profiller",
        "talebe_listesi",
        "users",
    )
    ekle(
        etut_plani_modulu_erisimi_var(user),
        "etut",
        "Etüt Grupları",
        "Grupları yönet",
        "etut_plan_panel",
        "groups",
    )
    ekle(
        gunluk_takip_modulu_erisimi_var(user),
        "gunluk_takip",
        "Günlük Takip",
        "Yoklama ve takip",
        "gunluk_takip_panel",
        "clipboard",
    )
    ekle(
        rehberlik_modulu_erisimi_var(user),
        "rehberlik",
        "Rehberlik",
        "Rehber öğretmeni görüşmeleri",
        "rehberlik_listesi",
        "chat",
    )
    ekle(
        veli_iletisim_modulu_erisimi_var(user),
        "veli_iletisim",
        "Veli & Talebe İletişim",
        "Veli ve öğrenci görüşmeleri",
        "iletisim_listesi",
        "phone",
    )
    ekle(
        deneme_modulu_erisimi_var(user),
        "deneme",
        "Deneme Sonuçları",
        "Deneme analizi",
        "deneme_listesi",
        "chart",
    )
    ekle(
        ktt_modulu_erisimi_var(user),
        "ktt",
        "KTT Takip",
        "Kazanım tarama testleri",
        "ktt_listesi",
        "target",
    )

    gorev_url = _gorevler_url(user)
    if gorev_url:
        adaylar.append(
            (
                True,
                DashboardShortcut(
                    key="gorevler",
                    title="Görevler",
                    subtitle="İmam, temizlik, yemek",
                    url=gorev_url,
                    icon="check",
                    badge=_gorev_badge_sayisi(user, bugun) or None,
                ),
            )
        )

    ekle(
        gelisim_dosyasi_erisimi_var(user),
        "dosyalar",
        "Dosyalar",
        "Gelişim dosyaları",
        "talebe_listesi",
        "folder",
    )
    ekle(
        program_modulu_erisimi_var(user),
        "takvim",
        "Takvim",
        "Kurum programı",
        "program_panel",
        "calendar",
    )
    ekle(
        egitim_modulu_erisimi_var(user),
        "raporlar",
        "Raporlar",
        "Filtre ve PDF çıktı",
        "raporlar",
        "pie",
    )
    ekle(
        yonetim_erisimi_var(user),
        "ayarlar",
        "Ayarlar",
        "Kurum ve modül ayarları",
        "yonetim:dashboard",
        "settings",
    )

    return [item for _, item in adaylar][:12]


def dashboard_son_aktiviteler(user: User, *, limit: int = 6) -> list[DashboardActivity]:
    aktiviteler: list[DashboardActivity] = []

    if rehberlik_gorebilir(user):
        for gorusme in (
            yetkili_gorusmeler(user, alan=GorusmeTuru.Alan.REHBERLIK)
            .select_related("kaydeden", "talebe", "tur")
            .order_by("-olusturulma")[: limit * 2]
        ):
            ad = _kullanici_adi(gorusme.kaydeden)
            aktiviteler.append(
                DashboardActivity(
                    baslik=f"{ad}, rehberlik görüşmesi kaydetti",
                    meta=f"{gorusme.talebe.ad_soyad} · {gorusme.tur.ad}",
                    zaman=gorusme.olusturulma,
                    zaman_etiketi=_zaman_etiketi(gorusme.olusturulma),
                    bas_harf=_bas_harf(ad),
                    ton="violet",
                )
            )

    if iletisim_gorebilir(user):
        for gorusme in (
            yetkili_gorusmeler(user, alan=GorusmeTuru.Alan.ILETISIM)
            .select_related("kaydeden", "talebe", "tur")
            .order_by("-olusturulma")[: limit * 2]
        ):
            ad = _kullanici_adi(gorusme.kaydeden)
            aktiviteler.append(
                DashboardActivity(
                    baslik=f"{ad}, iletişim kaydı girdi",
                    meta=f"{gorusme.talebe.ad_soyad} · {gorusme.tur.ad}",
                    zaman=gorusme.olusturulma,
                    zaman_etiketi=_zaman_etiketi(gorusme.olusturulma),
                    bas_harf=_bas_harf(ad),
                    ton="blue",
                )
            )

    if egitim_modulu_erisimi_var(user):
        talebe_ids = None
        if not user.is_superuser and not tum_talebe_kapsami_var(user):
            talebe_ids = list(
                yetkili_talebeler(user, aktif_only=True).values_list("id", flat=True)
            )

        okuma_qs = (
            OkumaKaydi.objects.select_related(
                "olusturan",
                "zimmet",
                "zimmet__talebe",
                "zimmet__kitap",
            )
            .order_by("-olusturulma")
        )
        if talebe_ids is not None:
            okuma_qs = okuma_qs.filter(zimmet__talebe_id__in=talebe_ids)

        for kayit in okuma_qs[: limit * 2]:
            ad = _kullanici_adi(kayit.olusturan)
            aktiviteler.append(
                DashboardActivity(
                    baslik=f"{ad}, okuma kaydı girdi",
                    meta=(
                        f"{kayit.zimmet.talebe.ad_soyad} · "
                        f"{kayit.zimmet.kitap.ad}"
                    ),
                    zaman=kayit.olusturulma,
                    zaman_etiketi=_zaman_etiketi(kayit.olusturulma),
                    bas_harf=_bas_harf(ad),
                    ton="green",
                )
            )

    if gunluk_takip_modulu_erisimi_var(user):
        for kayit in (
            yetkili_gunluk_kayitlari(user)
            .select_related("talebe", "talebe__etut_hocasi")
            .order_by("-guncellenme")[: limit * 2]
        ):
            hoca = getattr(kayit.talebe, "etut_hocasi", None)
            ad = hoca.ad_soyad if hoca else "Personel"
            aktiviteler.append(
                DashboardActivity(
                    baslik=f"{ad}, günlük yoklama aldı",
                    meta=kayit.talebe.ad_soyad,
                    zaman=kayit.guncellenme,
                    zaman_etiketi=_zaman_etiketi(kayit.guncellenme),
                    bas_harf=_bas_harf(ad),
                    ton="blue",
                )
            )

    aktiviteler.sort(key=lambda item: item.zaman, reverse=True)
    return aktiviteler[:limit]


def dashboard_son_gorusmeler(user: User, *, limit: int = 5) -> list[DashboardGorusme]:
    if not rehberlik_gorebilir(user):
        return []

    sonuc: list[DashboardGorusme] = []
    for gorusme in (
        yetkili_gorusmeler(user, alan=GorusmeTuru.Alan.REHBERLIK)
        .select_related("talebe", "tur")
        .order_by("-tarih", "-saat", "-id")[:limit]
    ):
        sonuc.append(
            DashboardGorusme(
                pk=gorusme.pk,
                baslik=gorusme.tur.ad,
                ozet=gorusme.ozet,
                talebe=gorusme.talebe.ad_soyad,
                tur=gorusme.tur.ad,
                saat=_saat_etiketi(gorusme.saat),
                url=reverse("rehberlik_detay", kwargs={"pk": gorusme.pk}),
            )
        )
    return sonuc


def dashboard_son_iletisim(user: User, *, limit: int = 5) -> list[DashboardGorusme]:
    if not iletisim_gorebilir(user):
        return []

    sonuc: list[DashboardGorusme] = []
    for gorusme in (
        yetkili_gorusmeler(user, alan=GorusmeTuru.Alan.ILETISIM)
        .select_related("talebe", "tur")
        .order_by("-tarih", "-saat", "-id")[:limit]
    ):
        sonuc.append(
            DashboardGorusme(
                pk=gorusme.pk,
                baslik=gorusme.tur.ad,
                ozet=gorusme.ozet,
                talebe=gorusme.talebe.ad_soyad,
                tur=gorusme.tur.ad,
                saat=_saat_etiketi(gorusme.saat),
                url=reverse("iletisim_detay", kwargs={"pk": gorusme.pk}),
            )
        )
    return sonuc


def _etut_hocasi(user: User):
    if not user.is_authenticated:
        return None
    if hasattr(EtutHocasi, "user"):
        hoca = EtutHocasi.objects.filter(user=user).first()
        if hoca:
            return hoca
    if hasattr(EtutHocasi, "kullanici"):
        return EtutHocasi.objects.filter(kullanici=user).first()
    return None


def _yetkili_sinavlar(user: User):
    sinavlar = Sinav.objects.filter(aktif=True)
    if user.is_superuser or tum_talebe_kapsami_var(user):
        return sinavlar

    hoca = _etut_hocasi(user)
    if not hoca:
        return Sinav.objects.none()
    return sinavlar.filter(etut_hocasi=hoca)


def dashboard_yaklasan_etkinlikler(
    user: User,
    *,
    bugun: date | None = None,
    limit: int = 5,
) -> list[DashboardEtkinlik]:
    bugun = bugun or timezone.localdate()
    etkinlikler: list[tuple[date, time | None, DashboardEtkinlik]] = []

    if egitim_modulu_erisimi_var(user):
        for sinav in (
            _yetkili_sinavlar(user)
            .select_related("kitap")
            .filter(sinav_tarihi__gte=bugun)
            .order_by("sinav_tarihi", "id")[:10]
        ):
            etkinlikler.append(
                (
                    sinav.sinav_tarihi,
                    None,
                    DashboardEtkinlik(
                        tarih=sinav.sinav_tarihi,
                        gun_etiketi=_tarih_etiketi(sinav.sinav_tarihi),
                        baslik=sinav.ad,
                        alt=sinav.kitap.ad,
                        url=reverse("sinav_sonuc_paneli"),
                        ton="violet",
                    ),
                )
            )

    if deneme_modulu_erisimi_var(user):
        for deneme in DenemeSinavi.objects.filter(
            sinav_tarihi__gte=bugun,
            durum=DenemeSinavi.Durum.AKTIF,
        ).order_by("sinav_tarihi", "id")[:10]:
            etkinlikler.append(
                (
                    deneme.sinav_tarihi,
                    None,
                    DashboardEtkinlik(
                        tarih=deneme.sinav_tarihi,
                        gun_etiketi=_tarih_etiketi(deneme.sinav_tarihi),
                        baslik=deneme.ad,
                        alt=f"{deneme.sinif_seviyesi}. sınıf",
                        url=reverse("deneme_detay", kwargs={"pk": deneme.pk}),
                        ton="amber",
                    ),
                )
            )

    if ktt_modulu_erisimi_var(user):
        for ktt in (
            KttSinav.objects.select_related("ders")
            .filter(aktif=True, sinav_tarihi__gte=bugun)
            .order_by("sinav_tarihi", "id")[:10]
        ):
            etkinlikler.append(
                (
                    ktt.sinav_tarihi,
                    None,
                    DashboardEtkinlik(
                        tarih=ktt.sinav_tarihi,
                        gun_etiketi=_tarih_etiketi(ktt.sinav_tarihi),
                        baslik=ktt.ad,
                        alt=ktt.ders.ad,
                        url=reverse("ktt_detay", kwargs={"pk": ktt.pk}),
                        ton="teal",
                    ),
                )
            )

    if rehberlik_gorebilir(user):
        for gorusme in (
            yetkili_gorusmeler(user, alan=GorusmeTuru.Alan.REHBERLIK)
            .select_related("talebe", "tur")
            .filter(sonraki_gorusme__gte=bugun)
            .order_by("sonraki_gorusme", "sonraki_gorusme_saat", "id")[:10]
        ):
            etkinlikler.append(
                (
                    gorusme.sonraki_gorusme,
                    gorusme.sonraki_gorusme_saat,
                    DashboardEtkinlik(
                        tarih=gorusme.sonraki_gorusme,
                        gun_etiketi=_tarih_etiketi(gorusme.sonraki_gorusme),
                        baslik=f"{gorusme.talebe.ad_soyad} · {gorusme.tur.ad}",
                        alt="Planlı rehberlik",
                        url=reverse("rehberlik_detay", kwargs={"pk": gorusme.pk}),
                        ton="blue",
                    ),
                )
            )

    if iletisim_gorebilir(user):
        for gorusme in (
            yetkili_gorusmeler(user, alan=GorusmeTuru.Alan.ILETISIM)
            .select_related("talebe", "tur")
            .filter(sonraki_gorusme__gte=bugun)
            .order_by("sonraki_gorusme", "sonraki_gorusme_saat", "id")[:10]
        ):
            etkinlikler.append(
                (
                    gorusme.sonraki_gorusme,
                    gorusme.sonraki_gorusme_saat,
                    DashboardEtkinlik(
                        tarih=gorusme.sonraki_gorusme,
                        gun_etiketi=_tarih_etiketi(gorusme.sonraki_gorusme),
                        baslik=f"{gorusme.talebe.ad_soyad} · {gorusme.tur.ad}",
                        alt="Planlı iletişim",
                        url=reverse("iletisim_detay", kwargs={"pk": gorusme.pk}),
                        ton="teal",
                    ),
                )
            )

    etkinlikler.sort(key=lambda item: (item[0], item[1] or time.min))
    return [item[2] for item in etkinlikler[:limit]]


def bugunku_sinav_sayisi(user: User, bugun: date | None = None) -> int:
    bugun = bugun or timezone.localdate()
    if not egitim_modulu_erisimi_var(user):
        return 0
    return _yetkili_sinavlar(user).filter(sinav_tarihi=bugun).count()


def dashboard_etut_plani_onizleme(user: User):
    if not etut_plani_modulu_erisimi_var(user):
        return None
    from takip.etut_plan_service import dashboard_etut_plani

    return dashboard_etut_plani(user)


@dataclass(frozen=True)
class DashboardGunlukGorev:
    baslik: str
    deger: str
    alt: str = ""
    url: str = ""


def dashboard_gunluk_gorevler(user: User, *, bugun: date | None = None) -> dict[str, object]:
    """Etüt ana ekranı — bugünün imam/müezzin, yemekçi ve (varsa) kat temizliği."""
    bugun = bugun or timezone.localdate()
    rol = kullanici_birincil_rol_slug(user)
    etut_ekrani = rol == "etut_mesul" or etut_plani_modulu_erisimi_var(user)

    sonuc: dict[str, object] = {
        "etut_ekrani": etut_ekrani,
        "imam": None,
        "yemek": [],
        "temizlik": [],
        "temizlik_katlari": [],
        "kat_sorumlusu": temizlik_kat_sorumlusu_mu(user),
    }

    if imam_muezzin_modulu_erisimi_var(user):
        from takip.imam_muezzin_service import bugunun_atamasi

        atama = bugunun_atamasi()
        if atama:
            sonuc["imam"] = DashboardGunlukGorev(
                baslik="Günün imam & müezzini",
                deger=f"İmam: {atama.imam.ad_soyad} · Müezzin: {atama.muezzin.ad_soyad}",
                url=reverse("imam_muezzin_panel"),
            )

    if yemekcilik_modulu_erisimi_var(user):
        from takip.yemekci_service import bugunun_atamalari

        yemek_satirlar = []
        for atama in bugunun_atamalari():
            ogun = getattr(atama.ogun, "ad", "Öğün")
            isim = atama.talebe.ad_soyad
            if atama.yardimci:
                isim = f"{isim} · {atama.yardimci.ad_soyad}"
            yemek_satirlar.append(
                DashboardGunlukGorev(
                    baslik=ogun,
                    deger=isim,
                    url=reverse("yemekcilik_panel"),
                )
            )
        sonuc["yemek"] = yemek_satirlar

    if temizlik_paneli_gorebilir(user):
        from takip.temizlik_service import (
            bugunun_atamalari_kullanici,
            kullanici_kat_sorumluluklari,
        )

        sonuc["temizlik_katlari"] = [
            s.kat.ad for s in kullanici_kat_sorumluluklari(user)
        ]
        temizlik_satirlar = []
        for atama in bugunun_atamalari_kullanici(user):
            kat = atama.alan.kat.ad if atama.alan and atama.alan.kat else "—"
            temizlik_satirlar.append(
                DashboardGunlukGorev(
                    baslik=f"{kat} · {atama.alan.ad}",
                    deger=atama.talebe.ad_soyad,
                    alt=atama.alan.aciklama or "",
                    url=reverse("temizlik_panel"),
                )
            )
        sonuc["temizlik"] = temizlik_satirlar

    return sonuc
