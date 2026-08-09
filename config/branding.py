"""Çinili Saray Proje — marka ve modül ayarları."""

from __future__ import annotations

import os

PANEL_NAME = os.environ.get("PANEL_NAME", "Çinili Saray Proje")
PANEL_SHORT = os.environ.get("PANEL_SHORT", "Çinili Saray Proje")
PANEL_MOBILE_SHORT = os.environ.get("PANEL_MOBILE_SHORT", "Çinili Saray")
PANEL_MODULE_LABEL = os.environ.get("PANEL_MODULE_LABEL", "Eğitim Modülü")
PANEL_ORG = os.environ.get("PANEL_ORG", "Çinili Saray Proje")
PANEL_TAGLINE = os.environ.get("PANEL_TAGLINE", "Öğrenmenin En Akıllı Yolu")
PANEL_FOOTER = os.environ.get("PANEL_FOOTER", "Çinili Saray Proje")


def panel_branding_context() -> dict[str, str]:
    return {
        "panel_name": PANEL_NAME,
        "panel_short": PANEL_SHORT,
        "panel_org": PANEL_ORG,
        "panel_tagline": PANEL_TAGLINE,
        "panel_footer": PANEL_FOOTER,
    }


# Modüller: canlıda sadece egitim_kitap açık; diğerleri arka planda hazırlanır.
PANEL_MODULES = {
    "egitim_kitap": {
        "label": "Kitap & Okuma",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "rehberlik": {
        "label": "Rehberlik",
        "enabled": True,
        "nav_group": "Rehberlik",
    },
    "veli_iletisim": {
        "label": "Veli & Talebe İletişim",
        "enabled": True,
        "nav_group": "İletişim",
    },
    "veli_randevu": {
        "label": "Veli Randevu",
        "enabled": True,
        "nav_group": "İletişim",
    },
    "disiplin": {
        "label": "Disiplin Kurulu",
        "enabled": True,
        "nav_group": "Disiplin",
    },
    "disiplin_kurulu": {
        "label": "İstişare ve Disiplin Kurulu",
        "enabled": True,
        "nav_group": "Disiplin",
    },
    "gunluk_takip": {
        "label": "Günlük Takip",
        "enabled": True,
        "nav_group": "Takip",
    },
    "program": {
        "label": "Programlar",
        "enabled": True,
        "nav_group": "Program",
    },
    "dershane_programi": {
        "label": "Dershane Programı",
        "enabled": True,
        "nav_group": "Program",
    },
    "duyuru": {
        "label": "Duyurular",
        "enabled": True,
        "nav_group": "Genel",
    },
    "imam_muezzin": {
        "label": "İmam & Müezzin",
        "enabled": True,
        "nav_group": "Görevler",
    },
    "temizlik": {
        "label": "Temizlik",
        "enabled": True,
        "nav_group": "Görevler",
    },
    "yemekcilik": {
        "label": "Yemekçilik",
        "enabled": True,
        "nav_group": "Görevler",
    },
    "gelisim_dosyasi": {
        "label": "Gelişim Dosyası",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "ktt": {
        "label": "KTT",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "deneme": {
        "label": "Deneme",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "soru_takip": {
        "label": "Soru Takip",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "akademik_mudahale": {
        "label": "Akademik Müdahale",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "etut_plani": {
        "label": "Haftalık Etüt Planı",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "dini_ders_takip": {
        "label": "Dini Ders Takip",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "namaz_yoklama": {
        "label": "Namaz Yoklaması",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "pazar_izin_donus": {
        "label": "Pazar İzin Dönüşü",
        "enabled": True,
        "nav_group": "Disiplin & Takip",
    },
    "yazili_takip": {
        "label": "Yazılı Takip",
        "enabled": True,
        "nav_group": "Eğitim",
    },
    "ogretmen_odeme": {
        "label": "Öğretmen Ödeme",
        "enabled": True,
        "nav_group": "Kurum",
    },
    "mezun": {
        "label": "Mezun Takip Merkezi",
        "enabled": True,
        "nav_group": "Kurum",
    },
    "aidat": {
        "label": "Finans Yönetimi",
        "enabled": True,
        "nav_group": "Kurum",
    },
    "rbac": {
        "label": "Rol & Yetki",
        "enabled": True,
        "nav_group": "Kurum",
    },
    "talebe_panel": {
        "label": "Talebe Paneli",
        "enabled": True,
        "nav_group": "Kurum",
    },
    "ogretmen_not": {
        "label": "Öğretmen Notları",
        "enabled": True,
        "nav_group": "Eğitim",
    },
}
