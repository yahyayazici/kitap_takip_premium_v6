"""Çinili Saray Panel — rol tanımları, menü ve yetki kontrolü."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.contrib.auth.models import User

from config.branding import PANEL_MODULES

from .permissions.registry import (
    LEGACY_IDARE_ROLLER,
    LEGACY_ROL_ETIKETLERI,
    LEGACY_TUM_TALEBE_ROLLER,
)
from .permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler, yonetim_kapsami_var
from .permissions.service import can, kullanici_birincil_rol_slug, modul_erisimi_var

# ---------------------------------------------------------------------------
# Roller (geriye dönük)
# ---------------------------------------------------------------------------

ROL_IDARECI = "idareci"
ROL_IC_MESUL = "ic_mesul"
ROL_EGITIM_MESUL = "egitim_mesul"
ROL_ETUT_MESUL = "etut_mesul"
ROL_SINIF_MESUL = "sinif_mesul"
ROL_REHBER_OGRETMENI = "rehber_ogretmeni"
ROL_MUHASEBECI = "muhasebeci"
ROL_NEHARI_MESUL = "nehari_mesul"
ROL_MAHAL_SORUMLU = "mahal_sorumlusu"

PERSONEL_ROLLER: tuple[tuple[str, str], ...] = (
    (ROL_IDARECI, "İdareci"),
    (ROL_IC_MESUL, "İç Mesul"),
    (ROL_EGITIM_MESUL, "Eğitim Mesulü"),
    (ROL_ETUT_MESUL, "Etüt Mesulü"),
    (ROL_SINIF_MESUL, "Sınıf Mesulü"),
    (ROL_REHBER_OGRETMENI, "Rehber Öğretmeni"),
    (ROL_MUHASEBECI, "Muhasebeci"),
    (ROL_NEHARI_MESUL, "Nehari Mesulü"),
    (ROL_MAHAL_SORUMLU, "Mahal Sorumlusu"),
)

ROL_ETIKETLERI = LEGACY_ROL_ETIKETLERI
IDARE_ROLLER = LEGACY_IDARE_ROLLER
TUM_TALEBE_ROLLER = LEGACY_TUM_TALEBE_ROLLER
EGITIM_MODULU_ROLLER = frozenset(
    {
        ROL_IDARECI,
        ROL_IC_MESUL,
        ROL_EGITIM_MESUL,
        ROL_ETUT_MESUL,
        ROL_SINIF_MESUL,
    }
)
REHBERLIK_MODULU_ROLLER = frozenset({ROL_REHBER_OGRETMENI})
DISIPLIN_KURUL_ROLLER = frozenset(
    {
        ROL_IDARECI,
        ROL_IC_MESUL,
        ROL_EGITIM_MESUL,
        ROL_SINIF_MESUL,
    }
)
TUM_PERSONEL_ROLLER = frozenset(dict(PERSONEL_ROLLER))
PROGRAM_MODULU_ROLLER = frozenset(
    {
        ROL_IDARECI,
        ROL_IC_MESUL,
        ROL_EGITIM_MESUL,
        ROL_ETUT_MESUL,
        ROL_SINIF_MESUL,
        ROL_NEHARI_MESUL,
    }
)
GOREV_MODULU_ROLLER = PROGRAM_MODULU_ROLLER
TEMIZLIK_MODULU_ROLLER = frozenset(
    {
        ROL_IDARECI,
        ROL_IC_MESUL,
        ROL_EGITIM_MESUL,
        ROL_ETUT_MESUL,
        ROL_SINIF_MESUL,
        ROL_NEHARI_MESUL,
        ROL_MAHAL_SORUMLU,
    }
)
YEMEKCI_MODULU_ROLLER = TEMIZLIK_MODULU_ROLLER


@dataclass(frozen=True)
class PanelNavItem:
    key: str
    label: str
    url_name: str
    roller: frozenset[str]
    active_names: tuple[str, ...] = ()
    nav_group: str = "Eğitim"


PANEL_NAV_ITEMS: tuple[PanelNavItem, ...] = (
    PanelNavItem(
        key="dashboard",
        label="Ana Sayfa",
        url_name="dashboard",
        roller=TUM_PERSONEL_ROLLER,
        active_names=("dashboard",),
        nav_group="Genel",
    ),
    PanelNavItem(
        key="yct",
        label="YÇT",
        url_name="yct_personel",
        roller=TUM_PERSONEL_ROLLER,
        active_names=("yct_personel",),
        nav_group="Genel",
    ),
    PanelNavItem(
        key="vazife",
        label="Vazifelerim",
        url_name="vazife_personel",
        roller=TUM_PERSONEL_ROLLER,
        active_names=("vazife_personel", "vazife_personel_durum"),
        nav_group="Genel",
    ),
    PanelNavItem(
        key="cuma_durum",
        label="Cuma Durumu",
        url_name="cuma_durum_panel",
        roller=TUM_PERSONEL_ROLLER,
        active_names=("cuma_durum_panel",),
        nav_group="Genel",
    ),
    PanelNavItem(
        key="program",
        label="Programlar",
        url_name="program_panel",
        roller=PROGRAM_MODULU_ROLLER,
        active_names=(
            "program_panel",
            "program_detay",
            "program_pdf",
            "program_excel",
        ),
        nav_group="Program",
    ),
    PanelNavItem(
        key="dershane_programi",
        label="Dershane Programı",
        url_name="dershane_program_panel",
        roller=PROGRAM_MODULU_ROLLER,
        active_names=(
            "dershane_program_panel",
            "dershane_program_goruntule",
            "dershane_program_pdf",
            "dershane_program_excel",
        ),
        nav_group="Program",
    ),
    PanelNavItem(
        key="ziyaret_arac",
        label="Ziyaret Araç Planı",
        url_name="ziyaret_arac_listesi",
        roller=PROGRAM_MODULU_ROLLER,
        active_names=(
            "ziyaret_arac_listesi",
            "ziyaret_arac_olustur",
            "ziyaret_arac_duzenle",
            "ziyaret_arac_detay",
            "ziyaret_arac_etut",
            "ziyaret_arac_planlama",
            "ziyaret_arac_onizleme",
            "ziyaret_arac_pdf_genel",
            "ziyaret_arac_pdf_program",
            "ziyaret_arac_pdf_arac",
            "ziyaret_arac_pdf_tum_araclar",
        ),
        nav_group="Program",
    ),
    PanelNavItem(
        key="imam_muezzin",
        label="İmam / Müezzin",
        url_name="imam_muezzin_panel",
        roller=GOREV_MODULU_ROLLER,
        active_names=("imam_muezzin_panel", "imam_muezzin_pdf"),
        nav_group="Görevler",
    ),
    PanelNavItem(
        key="temizlik",
        label="Temizlik",
        url_name="temizlik_panel",
        roller=TEMIZLIK_MODULU_ROLLER,
        active_names=("temizlik_panel", "temizlik_pdf"),
        nav_group="Görevler",
    ),
    PanelNavItem(
        key="yemekcilik",
        label="Yemekçilik",
        url_name="yemekcilik_panel",
        roller=YEMEKCI_MODULU_ROLLER,
        active_names=("yemekcilik_panel", "yemekcilik_pdf"),
        nav_group="Görevler",
    ),
    PanelNavItem(
        key="talebeler",
        label="Talebeler",
        url_name="talebe_listesi",
        roller=EGITIM_MODULU_ROLLER,
        active_names=("talebe_listesi", "talebe_detay", "talebe_liste_excel", "talebe_liste_raporu_pdf"),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="kitap_ekle",
        label="Kitap Ekle",
        url_name="kitap_ekle",
        roller=EGITIM_MODULU_ROLLER,
        active_names=("kitap_ekle", "kitap_listesi"),
        nav_group="Kitaplar",
    ),
    PanelNavItem(
        key="zimmetler",
        label="Zimmetleme",
        url_name="toplu_zimmet",
        roller=EGITIM_MODULU_ROLLER,
        active_names=("toplu_zimmet",),
        nav_group="Kitaplar",
    ),
    PanelNavItem(
        key="okuma",
        label="Günlük Adet Gir",
        url_name="toplu_gunluk_okuma",
        roller=EGITIM_MODULU_ROLLER,
        active_names=("toplu_gunluk_okuma",),
        nav_group="Kitaplar",
    ),
    PanelNavItem(
        key="sinav_olustur",
        label="Sınav Oluştur",
        url_name="sinav_ekle_panel",
        roller=EGITIM_MODULU_ROLLER,
        active_names=("sinav_ekle_panel",),
        nav_group="Kitaplar",
    ),
    PanelNavItem(
        key="sinav_sonuc",
        label="Sonuç Gir",
        url_name="sinav_sonuc_paneli",
        roller=EGITIM_MODULU_ROLLER,
        active_names=("sinav_sonuc_paneli", "sinav_sonuclari_gir"),
        nav_group="Kitaplar",
    ),
    PanelNavItem(
        key="raporlar",
        label="Okuma Raporları",
        url_name="raporlar",
        roller=EGITIM_MODULU_ROLLER,
        active_names=("raporlar", "okuma_raporu_pdf"),
        nav_group="Kitaplar",
    ),
    PanelNavItem(
        key="olcme",
        label="Ölçme ve Değerlendirme",
        url_name="olcme_hub",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "olcme_hub",
            "olcme_sinav_listesi",
            "olcme_sinav_wizard_yeni",
            "olcme_sinav_wizard",
            "olcme_sinav_detay",
            "olcme_sinav_zimmet",
            "olcme_sablon_listesi",
        ),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="olcme_optik",
        label="Optik",
        url_name="olcme_optik_sec",
        roller=frozenset({ROL_IDARECI, ROL_IC_MESUL}),
        active_names=(
            "olcme_optik_sec",
            "olcme_optik_form",
            "olcme_optik_foto",
            "olcme_optik_form_pdf",
            "olcme_optik_oku",
            "olcme_optik_mobil",
            "olcme_optik_oku_sec",
        ),
        nav_group="Optik",
    ),
    PanelNavItem(
        key="ktt",
        label="KTT",
        url_name="ktt_listesi",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "ktt_listesi",
            "ktt_rapor",
            "ktt_ekle",
            "ktt_detay",
            "ktt_duzenle",
            "ktt_sonuc_gir",
            "ktt_akilli_ozet",
        ),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="deneme",
        label="Deneme",
        url_name="deneme_listesi",
        roller=EGITIM_MODULU_ROLLER,
        active_names=("deneme_listesi", "deneme_detay"),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="soru_takip",
        label="Soru Takip",
        url_name="soru_takip_panel",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "soru_takip_panel",
            "soru_takip_detay",
            "soru_takip_rapor",
        ),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="akademik_mudahale",
        label="Akademik Takip",
        url_name="akademik_mudahale_listesi",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "akademik_mudahale_listesi",
            "akademik_mudahale_ekle",
            "akademik_mudahale_detay",
            "akademik_mudahale_duzenle",
            "akademik_mudahale_rapor",
        ),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="etut_plani",
        label="Haftalık Etüt Planı",
        url_name="etut_plan_panel",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "etut_plan_panel",
            "etut_plan_detay",
            "etut_plan_arsiv",
            "etut_plan_olustur",
            "etut_plan_yonetim",
            "etut_plan_pdf",
            "etut_plan_faaliyet_ata",
            "etut_plan_faaliyet_sil",
            "etut_plan_durum_guncelle",
            "etut_plan_havuz_ekle",
            "etut_plan_havuz_sil",
            "etut_plan_havuz_sirala",
            "etut_plan_kopyala",
            "etut_plan_saat_sirala",
        ),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="etut_haftalik_karne",
        label="Haftalık Karneler",
        url_name="etut_haftalik_karneler",
        roller=frozenset({ROL_ETUT_MESUL, ROL_SINIF_MESUL}),
        active_names=(
            "etut_haftalik_karneler",
            "etut_talebe_haftalik_karne_pdf",
        ),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="dini_ders_takip",
        label="Dini Ders Takip",
        url_name="dini_ders_panel",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "dini_ders_panel",
            "dini_ders_rapor",
        ),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="namaz_yoklama",
        label="Namaz Yoklaması",
        url_name="namaz_yoklama_panel",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "namaz_yoklama_panel",
            "namaz_yoklama_rapor",
        ),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="pazar_izin_donus",
        label="Pazar İzin Dönüşü",
        url_name="pazar_izin_donus_panel",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "pazar_izin_donus_panel",
            "pazar_izin_donus_rapor",
        ),
        nav_group="Disiplin & Takip",
    ),
    PanelNavItem(
        key="rehberlik",
        label="Rehberlik",
        url_name="rehberlik_listesi",
        roller=REHBERLIK_MODULU_ROLLER,
        active_names=(
            "rehberlik_listesi",
            "rehberlik_detay",
            "rehberlik_duzenle",
        ),
        nav_group="İletişim",
    ),
    PanelNavItem(
        key="veli_randevu",
        label="Veli Randevuları",
        url_name="randevu_panel",
        roller=EGITIM_MODULU_ROLLER,
        active_names=("randevu_panel", "randevu_detay", "randevu_raporlar"),
        nav_group="İletişim",
    ),
    PanelNavItem(
        key="iletisim_merkezi",
        label="İletişim Merkezi",
        url_name="iletisim_merkezi",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "iletisim_merkezi",
            "iletisim_yeni_mesaj",
            "iletisim_hazirla",
            "iletisim_paket_onizleme",
            "iletisim_ek_indir",
        ),
        nav_group="İletişim",
    ),
    PanelNavItem(
        key="veli_iletisim",
        label="Veli & Talebe İletişim",
        url_name="iletisim_listesi",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "iletisim_listesi",
            "iletisim_detay",
            "iletisim_duzenle",
        ),
        nav_group="İletişim",
    ),
    PanelNavItem(
        key="disiplin",
        label="Disiplin Kurulu",
        url_name="disiplin_kurul_panel",
        roller=DISIPLIN_KURUL_ROLLER,
        active_names=(
            "disiplin_kurul_panel",
            "disiplin_kurul_detay",
            "disiplin_kurul_olustur",
            "disiplin_kurul_ayarlar",
            "disiplin_kurul_gundem_pdf",
            "disiplin_kurul_rapor",
            "disiplin_kurul_arsiv",
            "disiplin_kurul_pdf",
            "disiplin_listesi",
            "disiplin_detay",
            "disiplin_duzenle",
        ),
        nav_group="Disiplin & Takip",
    ),
    PanelNavItem(
        key="gunluk_takip",
        label="Günlük Takip",
        url_name="gunluk_takip_panel",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "gunluk_takip_panel",
            "gunluk_takip_etut",
            "gunluk_takip_detay",
            "gunluk_takip_duzenle",
        ),
        nav_group="Disiplin & Takip",
    ),
    PanelNavItem(
        key="mezun",
        label="Mezun Takip Merkezi",
        url_name="mezun_listesi",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "mezun_listesi",
            "mezun_detay",
            "mezun_ekle",
            "mezun_etkinlikler",
            "mezun_gorevler",
            "mezun_gorev_detay",
            "mezun_istatistik",
            "mezun_raporlar",
        ),
        nav_group="Kurum",
    ),
    PanelNavItem(
        key="aidat",
        label="Finans Yönetimi",
        url_name="finans_panel",
        roller=TUM_PERSONEL_ROLLER,
        active_names=(
            "finans_panel",
            "finans_ogrenci",
            "finans_politikalar",
            "finans_indirimler",
            "finans_raporlar",
            "finans_ayarlar",
            "aidat_listesi",
            "aidat_detay",
        ),
        nav_group="Kurum",
    ),
    PanelNavItem(
        key="yazili_takip",
        label="Yazılı Takip",
        url_name="yazili_kamp_listesi",
        roller=EGITIM_MODULU_ROLLER,
        active_names=(
            "yazili_kamp_listesi",
            "yazili_kamp_detay",
            "yazili_sonuc_gir",
            "yazili_sinav_sil",
            "yazili_kamp_pdf",
            "yazili_sinav_sirali_pdf",
            "yazili_sinav_bireysel_pdf",
            "yazili_sinav_bireysel_talebe_pdf",
            "yazili_sinav_excel_sablon",
        ),
        nav_group="Eğitim",
    ),
    PanelNavItem(
        key="ogretmen_odeme",
        label="Öğretmen Ödeme",
        url_name="ogretmen_odeme_listesi",
        roller=TUM_PERSONEL_ROLLER,
        active_names=(
            "ogretmen_odeme_listesi",
            "ogretmen_odeme_detay",
            "ogretmen_odeme_rapor",
            "ogretmen_odeme_pdf",
        ),
        nav_group="Kurum",
    ),
    PanelNavItem(
        key="yonetim",
        label="Yönetim",
        url_name="yonetim:dashboard",
        roller=IDARE_ROLLER,
        active_names=(),
        nav_group="Kurum",
    ),
)

NAV_GROUP_ORDER: tuple[str, ...] = (
    "Genel",
    "Program",
    "Görevler",
    "Kitaplar",
    "Eğitim",
    "Optik",
    "İletişim",
    "Disiplin & Takip",
    "Kurum",
)


@dataclass(frozen=True)
class PanelNavGroup:
    name: str
    items: tuple[PanelNavItem, ...]

    @property
    def is_dropdown(self) -> bool:
        if self.name == "Genel":
            return len(self.items) > 1
        return len(self.items) >= 1


def _personel_profili(user: User):
    if not user.is_authenticated:
        return None

    try:
        return user.personel_profili
    except Exception:
        return None


def kullanici_rolu(user: User) -> str | None:
    return kullanici_birincil_rol_slug(user)


def rol_etiketi(user: User) -> str:
    rol = kullanici_rolu(user)
    if not rol:
        return "Personel"

    return ROL_ETIKETLERI.get(rol, "Personel")


def rol_yetkili_mi(user: User, roller: Iterable[str]) -> bool:
    rol = kullanici_rolu(user)
    if rol is None:
        return False

    return rol in roller


def yonetim_erisimi_var(user: User) -> bool:
    return yonetim_kapsami_var(user)


def tum_talebe_erisimi_var(user: User) -> bool:
    return tum_talebe_kapsami_var(user)


def program_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("program", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "program")


def dershane_program_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("dershane_programi", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "dershane_programi")


def imam_muezzin_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("imam_muezzin", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "imam_muezzin")


def gorev_modulu_erisimi_var(user: User) -> bool:
    return imam_muezzin_modulu_erisimi_var(user)


def temizlik_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("temizlik", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "temizlik")


def temizlik_kat_sorumlusu_mu(user: User) -> bool:
    from takip.temizlik_service import temizlik_kat_sorumlusu_mu as _kat_sorumlu

    return _kat_sorumlu(user)


def temizlik_paneli_gorebilir(user: User) -> bool:
    """Etüt hocası yalnızca kat veya mahal zimmeti varsa temizlik panelini görür."""
    if not temizlik_modulu_erisimi_var(user):
        return False
    if user.is_superuser or yonetim_erisimi_var(user):
        return True
    rol = kullanici_birincil_rol_slug(user)
    if rol == ROL_ETUT_MESUL:
        from takip.temizlik_service import temizlik_zimmeti_var

        return temizlik_zimmeti_var(user)
    return True


def yemekcilik_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("yemekcilik", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "yemekcilik")


def egitim_modulu_erisimi_var(user: User) -> bool:
    return modul_erisimi_var(user, "egitim_kitap")


def gelisim_dosyasi_erisimi_var(user: User) -> bool:
    return modul_erisimi_var(user, "gelisim_dosyasi")


def ktt_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("ktt", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "ktt")


def olcme_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("olcme", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "olcme")


def deneme_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("deneme", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "deneme")


def soru_takip_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("soru_takip", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "soru_takip")


def akademik_mudahale_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("akademik_mudahale", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "akademik_mudahale")


def etut_plani_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("etut_plani", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "etut_plani")


def dini_ders_takip_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("dini_ders_takip", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "dini_ders_takip")


def namaz_yoklama_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("namaz_yoklama", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "namaz_yoklama")


def pazar_izin_donus_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("pazar_izin_donus", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "pazar_izin_donus")


def ziyaret_arac_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("ziyaret_arac", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "ziyaret_arac")


def ogretmen_odeme_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("ogretmen_odeme", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "ogretmen_odeme")


def mezun_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("mezun", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "mezun")


def aidat_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("aidat", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "aidat")


def rehberlik_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("rehberlik", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "rehberlik")


def iletisim_merkezi_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("iletisim_merkezi", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "iletisim_merkezi")


def veli_iletisim_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("veli_iletisim", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "veli_iletisim")


def veli_randevu_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("veli_randevu", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "veli_randevu")


def disiplin_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("disiplin", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "disiplin") or modul_erisimi_var(user, "disiplin_kurulu")


def gunluk_takip_modulu_erisimi_var(user: User) -> bool:
    if not PANEL_MODULES.get("gunluk_takip", {}).get("enabled", False):
        return False

    return modul_erisimi_var(user, "gunluk_takip")


def panel_nav_items(user: User) -> list[PanelNavItem]:
    rol = kullanici_rolu(user)
    if rol is None:
        return []

    items: list[PanelNavItem] = []
    for item in PANEL_NAV_ITEMS:
        if item.key == "program" and not PANEL_MODULES.get(
            "program", {}
        ).get("enabled", False):
            continue
        if item.key == "dershane_programi" and not dershane_program_modulu_erisimi_var(
            user
        ):
            continue
        if item.key == "imam_muezzin" and not PANEL_MODULES.get(
            "imam_muezzin", {}
        ).get("enabled", False):
            continue
        if item.key == "temizlik" and not PANEL_MODULES.get(
            "temizlik", {}
        ).get("enabled", False):
            continue
        if item.key == "yemekcilik" and not PANEL_MODULES.get(
            "yemekcilik", {}
        ).get("enabled", False):
            continue
        if item.key == "olcme" and not olcme_modulu_erisimi_var(user):
            continue
        if item.key == "olcme_optik" and not olcme_modulu_erisimi_var(user):
            continue
        if item.key == "ktt" and not ktt_modulu_erisimi_var(user):
            continue
        if item.key == "deneme" and not deneme_modulu_erisimi_var(user):
            continue
        if item.key == "soru_takip" and not soru_takip_modulu_erisimi_var(user):
            continue
        if item.key == "akademik_mudahale" and not akademik_mudahale_modulu_erisimi_var(
            user
        ):
            continue
        if item.key == "etut_plani" and not etut_plani_modulu_erisimi_var(user):
            continue
        if item.key == "dini_ders_takip" and not dini_ders_takip_modulu_erisimi_var(
            user
        ):
            continue
        if item.key == "namaz_yoklama" and not namaz_yoklama_modulu_erisimi_var(user):
            continue
        if item.key == "pazar_izin_donus" and not pazar_izin_donus_modulu_erisimi_var(
            user
        ):
            continue
        if item.key == "ziyaret_arac" and not ziyaret_arac_modulu_erisimi_var(user):
            continue
        if item.key == "ogretmen_odeme" and not ogretmen_odeme_modulu_erisimi_var(user):
            continue
        if item.key == "mezun" and not mezun_modulu_erisimi_var(user):
            continue
        if item.key == "aidat" and not aidat_modulu_erisimi_var(user):
            continue
        if item.key == "rehberlik" and not rehberlik_modulu_erisimi_var(user):
            continue
        if item.key == "iletisim_merkezi" and not iletisim_merkezi_modulu_erisimi_var(user):
            continue
        if item.key == "veli_iletisim" and not veli_iletisim_modulu_erisimi_var(user):
            continue
        if item.key == "veli_randevu" and not veli_randevu_modulu_erisimi_var(user):
            continue
        if item.key == "temizlik" and not temizlik_paneli_gorebilir(user):
            continue
        if item.key == "disiplin" and not disiplin_modulu_erisimi_var(user):
            continue
        if item.key == "gunluk_takip" and not gunluk_takip_modulu_erisimi_var(user):
            continue
        if item.key == "yonetim" and not yonetim_erisimi_var(user):
            continue
        if rol in item.roller or user.is_superuser:
            items.append(item)

    return items


def panel_nav_groups(user: User) -> list[PanelNavGroup]:
    by_group: dict[str, list[PanelNavItem]] = {}
    for item in panel_nav_items(user):
        by_group.setdefault(item.nav_group, []).append(item)

    groups: list[PanelNavGroup] = []
    for name in NAV_GROUP_ORDER:
        items = by_group.get(name)
        if items:
            groups.append(PanelNavGroup(name=name, items=tuple(items)))

    return groups


def nav_aktif_mi(item: PanelNavItem, url_name: str | None) -> bool:
    if not url_name:
        return False

    if url_name == item.url_name:
        return True

    return url_name in item.active_names
