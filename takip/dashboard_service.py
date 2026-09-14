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
    banner: str = ""
    mark: str = ""
    gorsel_url: str = ""


# Yönetim ekranı + varsayılan katalog
PANEL_KISAYOL_KATALOG: tuple[dict[str, str], ...] = (
    {"key": "kitap", "title": "Kitap Takip", "icon": "book"},
    {"key": "talebeler", "title": "Talebeler", "icon": "users"},
    {"key": "etut", "title": "Etüt Grupları", "icon": "groups"},
    {"key": "gunluk_takip", "title": "Günlük Takip", "icon": "clipboard"},
    {"key": "rehberlik", "title": "Rehberlik", "icon": "chat"},
    {"key": "veli_iletisim", "title": "Veli & Talebe İletişim", "icon": "phone"},
    {"key": "deneme", "title": "Deneme Sonuçları", "icon": "chart"},
    {"key": "ktt", "title": "KTT Takip", "icon": "target"},
    {"key": "gorevler", "title": "Görevler", "icon": "check"},
    {"key": "dosyalar", "title": "Dosyalar", "icon": "folder"},
    {"key": "takvim", "title": "Takvim", "icon": "calendar"},
    {"key": "raporlar", "title": "Raporlar", "icon": "pie"},
    {"key": "ayarlar", "title": "Ayarlar", "icon": "settings"},
    {"key": "veli_duyurular", "title": "Duyurular", "icon": "chat"},
    {"key": "veli_ana", "title": "Ana Sayfa", "icon": "users"},
    {"key": "ogretmen_not", "title": "Not Girişi", "icon": "clipboard"},
    {"key": "ogretmen_program", "title": "Ders Programı", "icon": "calendar"},
    {"key": "ogretmen_degerlendirme", "title": "Değerlendirmeler", "icon": "chart"},
)

ICON_SECENEKLERI: tuple[str, ...] = (
    "book",
    "users",
    "groups",
    "clipboard",
    "chat",
    "phone",
    "chart",
    "target",
    "check",
    "folder",
    "calendar",
    "pie",
    "settings",
)


def panel_kisayol_gorsel_haritasi() -> dict[str, str]:
    from takip.panel_kisayol_models import PanelKisayol, PanelKisayolGorsel

    sonuc: dict[str, str] = {}
    for row in PanelKisayolGorsel.objects.filter(aktif=True).exclude(gorsel=""):
        try:
            sonuc[row.anahtar] = row.gorsel.url
        except ValueError:
            continue
    for row in PanelKisayol.objects.filter(aktif=True).exclude(gorsel=""):
        try:
            sonuc[row.anahtar] = row.gorsel.url
        except ValueError:
            continue
    return sonuc


def _kisayol_url_coz(ayar, *, user: User | None = None, bugun: date | None = None) -> str | None:
    """PanelKisayol kaydından URL üretir."""
    url_ozel = (getattr(ayar, "url_ozel", "") or "").strip()
    if url_ozel:
        return url_ozel

    anahtar = getattr(ayar, "anahtar", "")
    url_name = (getattr(ayar, "url_name", "") or "").strip()

    if anahtar == "gorevler" and user is not None:
        return _gorevler_url(user)

    if not url_name:
        return None
    try:
        return reverse(url_name)
    except Exception:
        return None


def _personel_kisayol_izinli(user: User, anahtar: str) -> bool:
    if anahtar in {"kitap", "talebeler", "dosyalar", "raporlar"}:
        return egitim_modulu_erisimi_var(user)
    if anahtar == "etut":
        return etut_plani_modulu_erisimi_var(user)
    if anahtar == "gunluk_takip":
        return gunluk_takip_modulu_erisimi_var(user)
    if anahtar == "rehberlik":
        return rehberlik_modulu_erisimi_var(user)
    if anahtar == "veli_iletisim":
        return veli_iletisim_modulu_erisimi_var(user)
    if anahtar == "deneme":
        return deneme_modulu_erisimi_var(user)
    if anahtar == "ktt":
        return ktt_modulu_erisimi_var(user)
    if anahtar == "gorevler":
        return bool(_gorevler_url(user))
    if anahtar == "takvim":
        return program_modulu_erisimi_var(user)
    if anahtar == "ayarlar":
        return yonetim_erisimi_var(user)
    # özel / veli anahtarları personelde serbest (url varsa)
    return True


def dashboard_kisayollari(
    user: User | None = None,
    *,
    bugun: date | None = None,
    hedef: str = "personel",
) -> list[DashboardShortcut]:
    """hedef: personel | yonetim | veli | ogretmen"""
    from takip.panel_kisayol_models import PanelKisayol

    bugun = bugun or timezone.localdate()
    filtre = {"aktif": True}
    if hedef == "yonetim":
        filtre["goster_yonetim"] = True
    elif hedef == "veli":
        filtre["goster_veli"] = True
    elif hedef == "ogretmen":
        filtre["goster_ogretmen"] = True
    else:
        filtre["goster_personel"] = True

    ayarlar = list(PanelKisayol.objects.filter(**filtre).order_by("sira", "id"))
    if not ayarlar:
        if hedef == "personel" and user is not None:
            return _legacy_personel_kisayollari(user, bugun=bugun)
        return []

    sonuc: list[DashboardShortcut] = []
    for ayar in ayarlar:
        if hedef == "personel" and user is not None:
            # Katalog anahtarlarında izin kontrolü; özel URL'lerde geç
            if not (ayar.url_ozel or "").strip():
                if ayar.anahtar in {k["key"] for k in PANEL_KISAYOL_KATALOG}:
                    if not _personel_kisayol_izinli(user, ayar.anahtar):
                        continue

        url = _kisayol_url_coz(ayar, user=user, bugun=bugun)
        if not url:
            continue

        badge = None
        if ayar.anahtar == "gorevler" and user is not None:
            badge = _gorev_badge_sayisi(user, bugun) or None
        elif ayar.anahtar == "vazife" and user is not None:
            from takip.vazife_service import vazife_badge_sayisi

            badge = vazife_badge_sayisi(user, bugun=bugun) or None

        gorsel_url = ""
        if ayar.gorsel:
            try:
                gorsel_url = ayar.gorsel.url
            except ValueError:
                gorsel_url = ""

        sonuc.append(
            DashboardShortcut(
                key=ayar.anahtar,
                title=ayar.baslik,
                subtitle=ayar.alt_baslik,
                url=url,
                icon=ayar.icon or "book",
                badge=badge,
                banner=ayar.baslik.upper(),
                mark=ayar.mark or ayar.baslik[:2].upper(),
                gorsel_url=gorsel_url,
            )
        )
        if len(sonuc) >= 16:
            break
    return sonuc


def _legacy_personel_kisayollari(user: User, *, bugun: date) -> list[DashboardShortcut]:
    """DB boşsa eski izin tabanlı liste."""
    adaylar: list[DashboardShortcut] = []
    gorseller = panel_kisayol_gorsel_haritasi()

    def ekle(
        kosul: bool,
        key: str,
        title: str,
        subtitle: str,
        url_name: str,
        icon: str,
        *,
        banner: str = "",
        mark: str = "",
        badge: int | None = None,
    ) -> None:
        if not kosul:
            return
        try:
            url = reverse(url_name)
        except Exception:
            return
        adaylar.append(
            DashboardShortcut(
                key=key,
                title=title,
                subtitle=subtitle,
                url=url,
                icon=icon,
                badge=badge,
                banner=banner or title.upper(),
                mark=mark or title[:2].upper(),
                gorsel_url=gorseller.get(key, ""),
            )
        )

    ekle(egitim_modulu_erisimi_var(user), "kitap", "Kitap Takip", "Zimmet, okuma ve arşiv", "kitap_listesi", "book", mark="KT")
    ekle(egitim_modulu_erisimi_var(user), "talebeler", "Talebeler", "Liste ve profiller", "talebe_listesi", "users", mark="TL")
    ekle(etut_plani_modulu_erisimi_var(user), "etut", "Etüt Grupları", "Grupları yönet", "etut_plan_panel", "groups", mark="EG")
    try:
        profil = user.personel_profili
        etut_karne_ok = (
            profil.aktif
            and profil.etut_hocasi_id
            and profil.ana_rol in ("etut_mesul", "sinif_mesul")
        )
    except Exception:
        etut_karne_ok = False
    ekle(
        etut_karne_ok,
        "etut_karne",
        "Haftalık Karneler",
        "Etüt değerlendirme arşivi",
        "etut_haftalik_karneler",
        "clipboard",
        mark="HK",
    )
    ekle(gunluk_takip_modulu_erisimi_var(user), "gunluk_takip", "Günlük Takip", "Yoklama ve takip", "gunluk_takip_panel", "clipboard", mark="GT")
    ekle(rehberlik_modulu_erisimi_var(user), "rehberlik", "Rehberlik", "Rehber öğretmeni görüşmeleri", "rehberlik_listesi", "chat", mark="RH")
    ekle(veli_iletisim_modulu_erisimi_var(user), "veli_iletisim", "Veli & Talebe İletişim", "Veli ve öğrenci görüşmeleri", "iletisim_listesi", "phone", mark="Vİ")
    ekle(deneme_modulu_erisimi_var(user), "deneme", "Deneme Sonuçları", "Deneme analizi", "deneme_listesi", "chart", mark="DN")
    ekle(ktt_modulu_erisimi_var(user), "ktt", "KTT Takip", "Kazanım tarama testleri", "ktt_listesi", "target", mark="KTT")
    gorev_url = _gorevler_url(user)
    if gorev_url:
        adaylar.append(
            DashboardShortcut(
                key="gorevler",
                title="Görevler",
                subtitle="İmam, temizlik, yemek",
                url=gorev_url,
                icon="check",
                badge=_gorev_badge_sayisi(user, bugun) or None,
                banner="GÖREVLER",
                mark="GV",
                gorsel_url=gorseller.get("gorevler", ""),
            )
        )
    ekle(gelisim_dosyasi_erisimi_var(user), "dosyalar", "Dosyalar", "Gelişim dosyaları", "talebe_listesi", "folder", mark="GD")
    ekle(program_modulu_erisimi_var(user), "takvim", "Takvim", "Kurum programı", "program_panel", "calendar", mark="TK")
    from takip.vazife_service import vazife_badge_sayisi

    ekle(
        True,
        "vazife",
        "Vazifelerim",
        "Atanan görevler",
        "vazife_personel",
        "check",
        mark="VZ",
        badge=vazife_badge_sayisi(user, bugun=bugun) or None,
    )
    ekle(egitim_modulu_erisimi_var(user), "raporlar", "Raporlar", "Filtre ve PDF çıktı", "raporlar", "pie", mark="RP")
    ekle(yonetim_erisimi_var(user), "ayarlar", "Ayarlar", "Kurum ve modül ayarları", "yonetim:dashboard", "settings", mark="AY")
    return adaylar[:12]


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
        from takip.temizlik_service import sabit_temizlik_satirlari

        sayac += len(sabit_temizlik_satirlari(user))
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


@dataclass(frozen=True)
class DashboardMetrik:
    key: str
    label: str
    value: str | int
    note: str
    ton: str
    icon: str
    url: str = ""


PANEL_METRIK_KATALOG: tuple[dict[str, str], ...] = (
    {"key": "talebe", "title": "Talebe", "ton": "blue", "icon": "users"},
    {"key": "bugun_okunan", "title": "Bugün okunan", "ton": "green", "icon": "book"},
    {"key": "okuma_kaydi", "title": "Okuma kaydı", "ton": "amber", "icon": "folder"},
    {"key": "sinav", "title": "Sınav", "ton": "violet", "icon": "clipboard"},
    {"key": "aktif_deneme", "title": "Aktif deneme", "ton": "amber", "icon": "chart"},
    {"key": "ktt", "title": "KTT", "ton": "violet", "icon": "target"},
    {"key": "personel", "title": "Personel", "ton": "green", "icon": "users"},
    {"key": "sinif", "title": "Sınıf", "ton": "blue", "icon": "groups"},
    {"key": "sorumlu_sinif", "title": "Sorumlu sınıf", "ton": "blue", "icon": "groups"},
    {"key": "ogretmen_ogrenci", "title": "Toplam öğrenci", "ton": "green", "icon": "users"},
    {"key": "aktif_hafta", "title": "Aktif hafta", "ton": "amber", "icon": "calendar"},
)


def _metrik_deger(
    anahtar: str,
    *,
    user: User | None,
    baglam: dict | None,
) -> tuple[str | int, str] | None:
    """(değer, varsayılan_not) veya None (hesaplanamadı / gizle)."""
    baglam = baglam or {}

    if anahtar == "talebe":
        if "talebe_sayisi" in baglam:
            return baglam["talebe_sayisi"], "Aktif kayıt"
        if user is not None:
            return yetkili_talebeler(user, aktif_only=True).count(), "Aktif kayıt"
        from takip.models import Talebe

        return Talebe.objects.filter(aktif=True).count(), "Aktif kayıt"

    if anahtar == "bugun_okunan":
        return baglam.get("toplam_okunan", 0), "Toplam sayfa"

    if anahtar == "okuma_kaydi":
        deger = baglam.get("bugunku_kayit", 0)
        bekleyen = baglam.get("bekleyen", 0)
        notu = f"{bekleyen} zimmet bekliyor" if bekleyen else "Kayıt tamam"
        return deger, notu

    if anahtar == "sinav":
        deger = baglam.get("bugunku_sinav", 0)
        bekleyen = baglam.get("sinav_bekleyen", 0)
        notu = f"{bekleyen} sonuç bekliyor" if bekleyen else "Bugünkü sınav"
        return deger, notu

    if anahtar == "aktif_deneme":
        from takip.deneme_models import DenemeSinavi

        return (
            DenemeSinavi.objects.filter(durum=DenemeSinavi.Durum.AKTIF).count(),
            "Yayındaki denemeler",
        )

    if anahtar == "ktt":
        return KttSinav.objects.count(), "Kayıtlı tarama"

    if anahtar == "personel":
        from takip.models import PersonelProfili

        return PersonelProfili.objects.filter(aktif=True).count(), "Aktif personel"

    if anahtar == "sinif":
        from takip.models import SinifSube

        return SinifSube.objects.filter(aktif=True).count(), "Tanımlı sınıf"

    if anahtar == "sorumlu_sinif":
        return baglam.get("toplam_sinif", 0), "Sorumlu sınıf"

    if anahtar == "ogretmen_ogrenci":
        return baglam.get("toplam_ogrenci", 0), "Öğrenci"

    if anahtar == "aktif_hafta":
        hn = baglam.get("hafta_no")
        if hn is None:
            return None
        return f"{hn}.", "Hafta"

    return None


def _metrik_url(anahtar: str, *, hedef: str = "personel") -> str:
    """Özet kart → ilgili modül sayfası."""
    harita = {
        "talebe": "talebe_listesi" if hedef != "yonetim" else "yonetim:talebe_listesi",
        "bugun_okunan": "toplu_gunluk_okuma",
        "okuma_kaydi": "toplu_gunluk_okuma",
        "sinav": "sinav_sonuc_paneli",
        "aktif_deneme": "deneme_listesi",
        "ktt": "ktt_listesi",
        "personel": "yonetim:personel_listesi",
        "sinif": "yonetim:sinif_listesi" if hedef == "yonetim" else "talebe_listesi",
        "sorumlu_sinif": "ogretmen_dashboard",
        "ogretmen_ogrenci": "ogretmen_dashboard",
        "aktif_hafta": "ogretmen_not_girisi",
    }
    url_name = harita.get(anahtar)
    if not url_name:
        return ""
    try:
        return reverse(url_name)
    except Exception:
        return ""


def dashboard_metrikleri(
    user: User | None = None,
    *,
    hedef: str = "personel",
    baglam: dict | None = None,
) -> list[DashboardMetrik]:
    from takip.panel_metrik_models import PanelMetrik

    filtre = {"aktif": True}
    if hedef == "yonetim":
        filtre["goster_yonetim"] = True
    elif hedef == "veli":
        filtre["goster_veli"] = True
    elif hedef == "ogretmen":
        filtre["goster_ogretmen"] = True
    else:
        filtre["goster_personel"] = True

    ayarlar = list(PanelMetrik.objects.filter(**filtre).order_by("sira", "id"))
    if not ayarlar and hedef == "personel":
        # DB boşsa eski 4'lü şerit
        ayarlar = [
            type("M", (), {"anahtar": k, "baslik": t, "not_metni": "", "ton": ton, "icon": icon})()
            for k, t, ton, icon in (
                ("talebe", "Talebe", "blue", "users"),
                ("bugun_okunan", "Bugün okunan", "green", "book"),
                ("okuma_kaydi", "Okuma kaydı", "amber", "folder"),
                ("sinav", "Sınav", "violet", "clipboard"),
            )
        ]

    sonuc: list[DashboardMetrik] = []
    for ayar in ayarlar:
        hesap = _metrik_deger(ayar.anahtar, user=user, baglam=baglam)
        if hesap is None:
            continue
        deger, varsayilan_not = hesap
        sonuc.append(
            DashboardMetrik(
                key=ayar.anahtar,
                label=ayar.baslik,
                value=deger,
                note=(ayar.not_metni or "").strip() or varsayilan_not,
                ton=ayar.ton or "blue",
                icon=ayar.icon or "users",
                url=_metrik_url(ayar.anahtar, hedef=hedef),
            )
        )
        if len(sonuc) >= 8:
            break
    return sonuc


def dashboard_etut_plani_onizleme(user: User):
    if not etut_plani_modulu_erisimi_var(user):
        return None
    from takip.etut_plan_service import dashboard_etut_plani

    return dashboard_etut_plani(user)


def dashboard_dershane_onizleme(user: User) -> list[dict]:
    """Haftalık dershane programı özeti — hocanın etüt grubu."""
    from takip.etut_plan_service import dershane_hafta_onizleme
    from takip.panel_permissions import dershane_program_modulu_erisimi_var
    from takip.user_helpers import etut_hocasi_for_user

    if not dershane_program_modulu_erisimi_var(user):
        return []
    hoca = etut_hocasi_for_user(user)
    if not hoca:
        return []
    return dershane_hafta_onizleme(user, hoca)


def dashboard_namaz_gelmedi(user: User, *, bugun: date | None = None) -> dict | None:
    """Etüt hocasının talebelerinden bugün namaza gelmeyenler (vakit vakit)."""
    from takip.namaz_yoklama_service import etut_gelmedi_bildirimleri, gelmedi_ozetleri
    from takip.panel_permissions import namaz_yoklama_modulu_erisimi_var
    from takip.user_helpers import etut_hocasi_for_user

    if not namaz_yoklama_modulu_erisimi_var(user):
        return None
    if not etut_hocasi_for_user(user) and not tum_talebe_kapsami_var(user):
        return None

    bugun = bugun or timezone.localdate()
    # Tam yetkili idareci için de etüt filtresi: kendi etüdü yoksa tüm gelmeyen özeti
    hoca = etut_hocasi_for_user(user)
    sadece_etudum = bool(hoca)
    ozetler = gelmedi_ozetleri(user, bugun, sadece_etudum=sadece_etudum)
    if hoca:
        bildirimler = etut_gelmedi_bildirimleri(user, bugun)
    else:
        bildirimler = []
        for ozet in ozetler:
            if not ozet["gelmeyenler"]:
                continue
            bildirimler.append(
                {
                    "vakit": ozet["vakit"],
                    "baslik": ozet["vakit_label"],
                    "etiket": f"{ozet['vakit_label']} Namazına Gelmedi",
                    "talebeler": [k.talebe for k in ozet["gelmeyenler"]],
                }
            )
    return {
        "bildirimler": bildirimler,
        "ozetler": ozetler,
        "toplam": sum(int(o.get("sayi") or 0) for o in ozetler),
        "url": reverse("namaz_yoklama_panel") + ("?etudum=1" if hoca else ""),
    }


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
            imam_url = reverse("imam_muezzin_panel")
            sonuc["imam"] = [
                DashboardGunlukGorev(
                    baslik="İmam",
                    deger=atama.imam.ad_soyad,
                    url=imam_url,
                ),
                DashboardGunlukGorev(
                    baslik="Müezzin",
                    deger=atama.muezzin.ad_soyad,
                    url=imam_url,
                ),
            ]

    if yemekcilik_modulu_erisimi_var(user):
        from takip.yemekci_service import bugunun_atamalari

        yemek_satirlar = []
        for kart in bugunun_atamalari():
            talebe = kart.get("talebe") or {}
            yemek_satirlar.append(
                DashboardGunlukGorev(
                    baslik=kart.get("etiket") or f"{kart.get('sinif')}. Sınıf",
                    deger=talebe.get("ad") or "—",
                    alt=talebe.get("sinif_label") or "",
                    url=reverse("yemekcilik_panel"),
                )
            )
        sonuc["yemek"] = yemek_satirlar

    if temizlik_paneli_gorebilir(user):
        from takip.temizlik_service import (
            kullanici_kat_sorumluluklari,
            sabit_temizlik_satirlari,
        )

        sonuc["temizlik_katlari"] = [
            s.kat.ad for s in kullanici_kat_sorumluluklari(user)
        ]
        temizlik_satirlar = []
        for satir in sabit_temizlik_satirlari(user)[:12]:
            kat = satir["kat"].ad if satir.get("kat") else "—"
            temizlik_satirlar.append(
                DashboardGunlukGorev(
                    baslik=f"{kat} · {satir['alan'].ad}",
                    deger=", ".join(satir["temizlikciler"]) or "—",
                    alt=satir["alan"].aciklama or "",
                    url=reverse("temizlik_panel"),
                )
            )
        sonuc["temizlik"] = temizlik_satirlar

    return sonuc
