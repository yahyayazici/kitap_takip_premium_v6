"""Modül ve işlem kataloğu — yeni modül eklenince buraya kayıt."""

from __future__ import annotations

from dataclasses import dataclass

STANDARD_ACTIONS: tuple[tuple[str, str], ...] = (
    ("view", "Görüntüle"),
    ("create", "Oluştur"),
    ("edit", "Düzenle"),
    ("delete", "Sil"),
    ("export_pdf", "PDF Raporu"),
    ("export_excel", "Excel Aktar"),
)

OGRETMEN_ODEME_ACTIONS: tuple[tuple[str, str], ...] = STANDARD_ACTIONS + (
    ("view_financial", "Finansal Görüntüle"),
)

ILETISIM_ACTIONS: tuple[tuple[str, str], ...] = STANDARD_ACTIONS + (
    ("share", "Paylaş"),
    ("manage_templates", "Şablon Yönet"),
)


@dataclass(frozen=True)
class ModulTanim:
    kod: str
    ad: str
    sira: int
    islemler: tuple[tuple[str, str], ...] = STANDARD_ACTIONS


MODUL_KATALOGU: tuple[ModulTanim, ...] = (
    ModulTanim("asistan", "Panel Asistanı", 5),
    ModulTanim("egitim_kitap", "Kitap & Okuma", 10),
    ModulTanim("gelisim_dosyasi", "Gelişim Dosyası", 15),
    ModulTanim("ktt", "KTT", 18),
    ModulTanim("deneme", "Deneme", 19),
    ModulTanim("soru_takip", "Soru Takip", 20),
    ModulTanim("akademik_mudahale", "Akademik Müdahale", 21),
    ModulTanim("etut_plani", "Haftalık Etüt Planı", 22),
    ModulTanim("dini_ders_takip", "Dini Ders Takip", 23),
    ModulTanim("namaz_yoklama", "Namaz Yoklaması", 24),
    ModulTanim("pazar_izin_donus", "Pazar İzin Dönüşü", 24),
    ModulTanim("ziyaret_arac", "Ziyaret Araç Planlama", 24),
    ModulTanim("yazili_takip", "Yazılı Takip", 25),
    ModulTanim("vazife", "Personel Vazife", 29),
    ModulTanim("yct", "Yıllık Çalışma Takvimi", 30),
    ModulTanim("mezun", "Mezun Takip Merkezi", 32),
    ModulTanim("aidat", "Finans Yönetimi", 33),
    ModulTanim("rehberlik", "Rehberlik", 34),
    ModulTanim("veli_iletisim", "Veli & Talebe İletişim", 35),
    ModulTanim("iletisim_merkezi", "İletişim Merkezi", 36, islemler=ILETISIM_ACTIONS),
    ModulTanim("veli_randevu", "Veli Randevu", 37),
    ModulTanim("disiplin", "Disiplin", 36),
    ModulTanim("disiplin_kurulu", "İstişare ve Disiplin Kurulu", 35),
    ModulTanim("gunluk_takip", "Günlük Takip", 36),
    ModulTanim("ogretmen_odeme", "Öğretmen Ödeme", 26, islemler=OGRETMEN_ODEME_ACTIONS),
    ModulTanim("talebe_panel", "Talebe Paneli", 27),
    ModulTanim("ogretmen_not", "Öğretmen Notları", 28),
    ModulTanim("yonetim", "Kurum Yönetimi", 25),
    ModulTanim("program", "Kurum Akış Programı", 30),
    ModulTanim("dershane_programi", "Dershane Programı", 31),
    ModulTanim("duyuru", "Duyurular", 40),
    ModulTanim("imam_muezzin", "İmam & Müezzin", 50),
    ModulTanim("temizlik", "Temizlik", 60),
    ModulTanim("yemekcilik", "Yemekçilik", 70),
    ModulTanim("raporlar", "Raporlar", 80),
    ModulTanim("rbac", "Rol & Yetki Yönetimi", 900),
    ModulTanim("sistem_ayarlari", "Sistem Ayarları", 910),
)

# Eski panel_permissions frozenset → modül erişimi eşlemesi
LEGACY_ROL_MODULLER: dict[str, frozenset[str]] = {
    "idareci": frozenset(
        {
            "egitim_kitap",
            "asistan",
            "gelisim_dosyasi",
            "ktt",
            "deneme",
            "soru_takip",
            "akademik_mudahale",
            "etut_plani",
            "dini_ders_takip",
            "namaz_yoklama",
            "pazar_izin_donus",
            "ziyaret_arac",
            "yazili_takip",
            "vazife",
            "yct",
            "mezun",
            "aidat",
            "veli_iletisim",
            "iletisim_merkezi",
            "veli_randevu",
            "disiplin",
            "disiplin_kurulu",
            "gunluk_takip",
            "ogretmen_odeme",
            "talebe_panel",
            "ogretmen_not",
            "yonetim",
            "program",
            "dershane_programi",
            "duyuru",
            "imam_muezzin",
            "temizlik",
            "yemekcilik",
            "raporlar",
            "rbac",
            "sistem_ayarlari",
        }
    ),
    "ic_mesul": frozenset(
        {
            "egitim_kitap",
            "asistan",
            "gelisim_dosyasi",
            "ktt",
            "deneme",
            "soru_takip",
            "akademik_mudahale",
            "etut_plani",
            "dini_ders_takip",
            "namaz_yoklama",
            "pazar_izin_donus",
            "ziyaret_arac",
            "yazili_takip",
            "mezun",
            "aidat",
            "veli_iletisim",
            "iletisim_merkezi",
            "veli_randevu",
            "disiplin",
            "disiplin_kurulu",
            "gunluk_takip",
            "ogretmen_odeme",
            "talebe_panel",
            "ogretmen_not",
            "yonetim",
            "program",
            "dershane_programi",
            "duyuru",
            "imam_muezzin",
            "temizlik",
            "yemekcilik",
            "raporlar",
        }
    ),
    "egitim_mesul": frozenset(
        {
            "egitim_kitap",
            "asistan",
            "gelisim_dosyasi",
            "ktt",
            "deneme",
            "soru_takip",
            "akademik_mudahale",
            "etut_plani",
            "dini_ders_takip",
            "namaz_yoklama",
            "pazar_izin_donus",
            "ziyaret_arac",
            "yazili_takip",
            "mezun",
            "aidat",
            "veli_iletisim",
            "iletisim_merkezi",
            "veli_randevu",
            "disiplin",
            "disiplin_kurulu",
            "gunluk_takip",
            "ogretmen_odeme",
            "talebe_panel",
            "ogretmen_not",
            "yonetim",
            "program",
            "dershane_programi",
            "duyuru",
            "imam_muezzin",
            "temizlik",
            "yemekcilik",
            "raporlar",
        }
    ),
    "etut_mesul": frozenset(
        {
            "egitim_kitap",
            "asistan",
            "gelisim_dosyasi",
            "ktt",
            "deneme",
            "soru_takip",
            "akademik_mudahale",
            "etut_plani",
            "dini_ders_takip",
            "namaz_yoklama",
            "pazar_izin_donus",
            "ziyaret_arac",
            "yazili_takip",
            "aidat",
            "gunluk_takip",
            "veli_iletisim",
            "iletisim_merkezi",
            "veli_randevu",
            "gunluk_takip",
            "ogretmen_odeme",
            "program",
            "dershane_programi",
            "imam_muezzin",
            "temizlik",
            "yemekcilik",
            "raporlar",
        }
    ),
    "rehber_ogretmeni": frozenset(
        {
            "asistan",
            "egitim_kitap",
            "gelisim_dosyasi",
            "rehberlik",
            "veli_iletisim",
            "iletisim_merkezi",
            "veli_randevu",
            "raporlar",
        }
    ),
    "sinif_mesul": frozenset(
        {
            "egitim_kitap",
            "asistan",
            "gelisim_dosyasi",
            "ktt",
            "deneme",
            "soru_takip",
            "akademik_mudahale",
            "etut_plani",
            "dini_ders_takip",
            "namaz_yoklama",
            "pazar_izin_donus",
            "ziyaret_arac",
            "mezun",
            "aidat",
            "veli_iletisim",
            "iletisim_merkezi",
            "veli_randevu",
            "disiplin",
            "disiplin_kurulu",
            "gunluk_takip",
            "ogretmen_odeme",
            "talebe_panel",
            "ogretmen_not",
            "yonetim",
            "program",
            "dershane_programi",
            "imam_muezzin",
            "temizlik",
            "yemekcilik",
            "raporlar",
        }
    ),
    "muhasebeci": frozenset({"raporlar", "ogretmen_odeme", "aidat", "mezun", "asistan"}),
    "nehari_mesul": frozenset(
        {
            "asistan",
            "program",
            "dershane_programi",
            "imam_muezzin",
            "temizlik",
            "yemekcilik",
        }
    ),
    "mahal_sorumlusu": frozenset(
        {
            "asistan",
            "program",
            "dershane_programi",
            "imam_muezzin",
            "temizlik",
            "yemekcilik",
        }
    ),
}

LEGACY_ROL_ETIKETLERI: dict[str, str] = {
    "idareci": "İdareci",
    "ic_mesul": "İç Mesul",
    "egitim_mesul": "Eğitim Mesulü / Kurum İdarecisi",
    "etut_mesul": "Etüt Mesulü",
    "sinif_mesul": "Sınıf Mesulü",
    "rehber_ogretmeni": "Rehber Öğretmeni",
    "muhasebeci": "Muhasebeci",
    "nehari_mesul": "Nehari Mesulü",
    "mahal_sorumlusu": "Mahal Sorumlusu",
}

LEGACY_TUM_TALEBE_ROLLER = frozenset(
    {"idareci", "ic_mesul", "egitim_mesul", "sinif_mesul", "rehber_ogretmeni"}
)

LEGACY_IDARE_ROLLER = frozenset({"idareci", "ic_mesul"})

# Yalnızca idareci / ic_mesul düzenleyebilir; personel görüntüler
ADMIN_ONLY_EDIT_MODULES = frozenset(
    {
        "program",
        "imam_muezzin",
        "temizlik",
        "yemekcilik",
    }
)

# Modül görüntüleme için view işlemi yeterli
DEFAULT_VIEW_ONLY_MODULES = frozenset({"duyuru"})
