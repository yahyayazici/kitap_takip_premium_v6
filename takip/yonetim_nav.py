"""Yönetim merkezi — gruplu üst menü tanımları."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class YonetimNavItem:
    label: str
    url_name: str
    active_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class YonetimNavGroup:
    name: str
    items: tuple[YonetimNavItem, ...]

    @property
    def is_dropdown(self) -> bool:
        return len(self.items) > 1


YONETIM_NAV_GROUPS: tuple[YonetimNavGroup, ...] = (
    YonetimNavGroup(
        name="Genel Bakış",
        items=(
            YonetimNavItem(
                label="İdareci Özeti",
                url_name="yonetim:idareci_panel",
                active_names=("idareci_panel",),
            ),
            YonetimNavItem(
                label="Genel Bakış",
                url_name="yonetim:dashboard",
                active_names=("dashboard",),
            ),
            YonetimNavItem(
                label="Vazifeler",
                url_name="yonetim:vazife_listesi",
                active_names=("vazife_listesi", "vazife_ekle", "vazife_duzenle", "vazife_durum"),
            ),
            YonetimNavItem(
                label="Toplantılar",
                url_name="yonetim:personel_toplanti_listesi",
                active_names=(
                    "personel_toplanti_listesi",
                    "personel_toplanti_ekle",
                    "personel_toplanti_detay",
                    "personel_toplanti_pdf",
                    "personel_toplanti_arsiv",
                ),
            ),
            YonetimNavItem(
                label="YÇT",
                url_name="yonetim:yct_takvim",
                active_names=("yct_takvim", "yct_ekle", "yct_sil"),
            ),
            YonetimNavItem(
                label="Hızlı Ekle",
                url_name="yonetim:hizli_kayit",
                active_names=("hizli_kayit",),
            ),
            YonetimNavItem(
                label="Sınıf ve Şubeler",
                url_name="yonetim:sinif_listesi",
                active_names=("sinif_listesi", "sinif_ekle", "sinif_duzenle"),
            ),
        ),
    ),
    YonetimNavGroup(
        name="Kurum",
        items=(
            YonetimNavItem(
                label="Personeller",
                url_name="yonetim:personel_listesi",
                active_names=("personel_listesi", "personel_ekle", "personel_duzenle"),
            ),
            YonetimNavItem(
                label="Öğretmenler",
                url_name="yonetim:ogretmen_odeme_profil_listesi",
                active_names=(
                    "ogretmen_odeme_profil_listesi",
                    "ogretmen_odeme_profil_duzenle",
                ),
            ),
            YonetimNavItem(
                label="Branşlar",
                url_name="yonetim:brans_listesi",
                active_names=("brans_listesi", "brans_ekle", "brans_duzenle"),
            ),
            YonetimNavItem(
                label="Dersler",
                url_name="yonetim:ders_listesi",
                active_names=("ders_listesi", "ders_ekle", "ders_duzenle"),
            ),
            YonetimNavItem(
                label="Talebeler",
                url_name="yonetim:talebe_listesi",
                active_names=(
                    "talebe_listesi",
                    "talebe_ekle",
                    "talebe_duzenle",
                    "talebe_excel_yukle",
                    "talebe_excel_sablon_indir",
                    "talebe_liste_raporu_pdf",
                ),
            ),
            YonetimNavItem(
                label="Roller",
                url_name="yonetim:rol_listesi",
                active_names=("rol_listesi", "rol_ekle", "rol_duzenle"),
            ),
            YonetimNavItem(
                label="Talebe Hesapları",
                url_name="yonetim:talebe_hesap_listesi",
                active_names=(
                    "talebe_hesap_listesi",
                    "talebe_hesap_ekle",
                    "talebe_hesap_duzenle",
                ),
            ),
            YonetimNavItem(
                label="Mezuniyet",
                url_name="yonetim:mezuniyet_islemi",
                active_names=(
                    "mezuniyet_islemi",
                    "mezun_profil_duzenle",
                ),
            ),
        ),
    ),
    YonetimNavGroup(
        name="Finans",
        items=(
            YonetimNavItem(
                label="Aidat",
                url_name="finans_panel",
                active_names=(
                    "finans_panel",
                    "finans_ogrenci",
                    "finans_politikalar",
                    "finans_indirimler",
                    "finans_raporlar",
                    "finans_ayarlar",
                    "aidat_listesi",
                    "aidat_detay",
                    "aidat_tanim_listesi",
                    "aidat_tanim_ekle",
                    "aidat_tanim_duzenle",
                ),
            ),
            YonetimNavItem(
                label="Öğretmen Ödeme",
                url_name="ogretmen_odeme_listesi",
                active_names=(
                    "ogretmen_odeme_listesi",
                    "ogretmen_odeme_detay",
                    "ogretmen_odeme_rapor",
                    "ogretmen_odeme_pdf",
                    "ogretmen_odeme_sil",
                    "ogretmen_odeme_profil_listesi",
                    "ogretmen_odeme_profil_duzenle",
                ),
            ),
        ),
    ),
    YonetimNavGroup(
        name="İletişim",
        items=(
            YonetimNavItem(
                label="Duyurular",
                url_name="yonetim:duyuru_listesi",
                active_names=("duyuru_listesi", "duyuru_ekle", "duyuru_duzenle"),
            ),
            YonetimNavItem(
                label="Kısayollar",
                url_name="yonetim:kisayol_gorsel_listesi",
                active_names=("kisayol_gorsel_listesi",),
            ),
            YonetimNavItem(
                label="Özet Kartları",
                url_name="yonetim:metrik_listesi",
                active_names=("metrik_listesi",),
            ),
            YonetimNavItem(
                label="Sohbet Mevzuu",
                url_name="yonetim:sohbet_mevzuu_listesi",
                active_names=(
                    "sohbet_mevzuu_listesi",
                    "sohbet_mevzuu_ekle",
                    "sohbet_mevzuu_duzenle",
                ),
            ),
            YonetimNavItem(
                label="Cuma Durumu",
                url_name="yonetim:cuma_durum_listesi",
                active_names=(
                    "cuma_durum_listesi",
                    "cuma_durum_ekle",
                    "cuma_durum_duzenle",
                ),
            ),
            YonetimNavItem(
                label="Veli Hesapları",
                url_name="yonetim:veli_hesap_listesi",
                active_names=(
                    "veli_hesap_listesi",
                    "veli_hesap_ekle",
                    "veli_hesap_duzenle",
                ),
            ),
            YonetimNavItem(
                label="Veli Randevu Ayarları",
                url_name="yonetim:randevu_personel_listesi",
                active_names=("randevu_personel_listesi", "randevu_personel_ayar"),
            ),
            YonetimNavItem(
                label="Veli Görüntüleme",
                url_name="yonetim:veli_goruntuleme_paneli",
                active_names=(
                    "veli_goruntuleme_paneli",
                    "veli_goruntuleme_detay",
                ),
            ),
        ),
    ),
    YonetimNavGroup(
        name="Program",
        items=(
            YonetimNavItem(
                label="Programlar",
                url_name="yonetim:program_listesi",
                active_names=(
                    "program_listesi",
                    "program_ekle",
                    "program_duzenle",
                    "program_pdf",
                ),
            ),
            YonetimNavItem(
                label="Program Türleri",
                url_name="yonetim:program_tur_listesi",
                active_names=(
                    "program_tur_listesi",
                    "program_tur_ekle",
                    "program_tur_duzenle",
                ),
            ),
            YonetimNavItem(
                label="İmam / Müezzin",
                url_name="yonetim:imam_listesi",
                active_names=("imam_listesi", "imam_ekle", "imam_duzenle", "imam_gorev_panel", "imam_onizleme", "imam_pdf"),
            ),
            YonetimNavItem(
                label="Temizlik",
                url_name="yonetim:temizlik_listesi",
                active_names=(
                    "temizlik_listesi",
                    "temizlik_ekle",
                    "temizlik_gorev_panel",
                    "temizlik_duzenle",
                    "temizlik_pdf",
                    "temizlik_alan_listesi",
                    "temizlik_alan_ekle",
                    "temizlik_alan_duzenle",
                ),
            ),
            YonetimNavItem(
                label="Yemekçilik",
                url_name="yemekcilik_panel",
                active_names=(
                    "yemekcilik_panel",
                    "yemekcilik_pdf",
                    "yemekci_listesi",
                    "yemekci_ekle",
                    "yemekci_duzenle",
                    "yemekci_pdf",
                    "yemek_ogun_listesi",
                    "yemek_ogun_ekle",
                    "yemek_ogun_duzenle",
                ),
            ),
        ),
    ),
    YonetimNavGroup(
        name="Eğitim",
        items=(
            YonetimNavItem(
                label="KTT",
                url_name="yonetim:ktt_listesi",
                active_names=("ktt_listesi", "ktt_sil", "ktt_veli_toggle"),
            ),
            YonetimNavItem(
                label="Denemeler",
                url_name="yonetim:deneme_listesi",
                active_names=(
                    "deneme_listesi",
                    "deneme_ekle",
                    "deneme_detay",
                    "deneme_onizleme",
                    "deneme_rapor",
                ),
            ),
            YonetimNavItem(
                label="Yazılı Takip",
                url_name="yonetim:yazili_kamp_listesi",
                active_names=(
                    "yazili_kamp_listesi",
                    "yazili_kamp_ekle",
                    "yazili_kamp_duzenle",
                    "yazili_kamp_detay",
                    "yazili_kamp_sil",
                    "yazili_sinav_ekle",
                    "yazili_sinav_detay",
                    "yazili_sinav_duzenle",
                    "yazili_sinav_sil",
                ),
            ),
            YonetimNavItem(
                label="Müdahale Türleri",
                url_name="yonetim:mudahale_turu_listesi",
                active_names=(
                    "mudahale_turu_listesi",
                    "mudahale_turu_ekle",
                    "mudahale_turu_duzenle",
                    "mudahale_turu_sil",
                ),
            ),
            YonetimNavItem(
                label="Sınav Başvuruları",
                url_name="yonetim:sinav_basvuru_listesi",
                active_names=(
                    "sinav_basvuru_listesi",
                    "sinav_basvuru_detay",
                    "sinav_basvuru_sil",
                    "sinav_basvuru_excel",
                    "sinav_basvuru_toplu_mesaj",
                ),
            ),
            YonetimNavItem(
                label="Başvuru Mesaj Anları",
                url_name="yonetim:sinav_basvuru_mesaj_an_listesi",
                active_names=(
                    "sinav_basvuru_mesaj_an_listesi",
                    "sinav_basvuru_mesaj_an_duzenle",
                    "sinav_basvuru_mesaj_an_toggle",
                ),
            ),
            YonetimNavItem(
                label="Dini Ders",
                url_name="yonetim:dini_ders_alan_listesi",
                active_names=(
                    "dini_ders_alan_listesi",
                    "dini_ders_alan_ekle",
                    "dini_ders_alan_duzenle",
                    "dini_ders_seviye_listesi",
                    "dini_ders_seviye_duzenle",
                    "dini_ders_konu_listesi",
                    "dini_ders_konu_ekle",
                    "dini_ders_konu_duzenle",
                ),
            ),
            YonetimNavItem(
                label="Kitaplar",
                url_name="kitap_listesi",
                active_names=("kitap_listesi", "kitap_ekle"),
            ),
            YonetimNavItem(
                label="Okuma Raporları",
                url_name="raporlar",
                active_names=("raporlar", "okuma_raporu_pdf"),
            ),
            YonetimNavItem(
                label="Sınav Sonuçları",
                url_name="sinav_sonuc_paneli",
                active_names=(
                    "sinav_sonuc_paneli",
                    "sinav_sonuclari_gir",
                    "sinav_ekle_panel",
                ),
            ),
            YonetimNavItem(
                label="Haftalık Not Takibi",
                url_name="yonetim:ogretmen_degerlendirme_rapor",
                active_names=(
                    "ogretmen_degerlendirme_rapor",
                    "ogretmen_degerlendirme_karne_pdf",
                ),
            ),
        ),
    ),
)


def yonetim_nav_item_active(item: YonetimNavItem, resolver_match) -> bool:
    if resolver_match is None:
        return False

    url_name = resolver_match.url_name or ""
    view_name = resolver_match.view_name or ""

    if view_name == item.url_name:
        return True

    if url_name in item.active_names:
        return True

    return False


def yonetim_nav_group_active(group: YonetimNavGroup, resolver_match) -> bool:
    return any(yonetim_nav_item_active(item, resolver_match) for item in group.items)


def yonetim_nav_groups() -> tuple[YonetimNavGroup, ...]:
    return YONETIM_NAV_GROUPS
