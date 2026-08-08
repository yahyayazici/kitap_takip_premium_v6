from django.contrib.auth import views as auth_views
from django.urls import path

from . import etut_plan_views
from . import dini_ders_takip_views
from . import namaz_yoklama_views
from . import ogretmen_odeme_views
from . import mezun_views
from . import aidat_views
from . import finans_views
from . import rehberlik_views
from . import disiplin_views
from . import disiplin_kurul_views
from . import gunluk_takip_views
from . import deneme_views
from . import yazili_takip_views
from . import personel_vazife_views
from . import bildirim_views
from . import akademik_mudahale_views
from . import ktt_views
from . import soru_takip_views
from . import ogretmen_views
from . import talebe_panel_views
from . import veli_views
from . import veli_randevu_views
from . import asistan_views
from . import dershane_program_views
from . import yemekci_views
from . import views
from .auth_views import PanelLoginView

urlpatterns = [
    path("", views.home, name="home"),

    path(
        "giris/",
        PanelLoginView.as_view(),
        name="login",
    ),

    path("cikis/", auth_views.LogoutView.as_view(), name="logout"),

    path("panel/", views.dashboard, name="dashboard"),
    path("panel/yct/", personel_vazife_views.yct_personel, name="yct_personel"),
    path("panel/vazifelerim/", personel_vazife_views.vazife_personel, name="vazife_personel"),
    path("panel/vazifelerim/<int:pk>/durum/",
        personel_vazife_views.vazife_personel_durum,
        name="vazife_personel_durum",
    ),
    path("panel/bildirimler/", bildirim_views.bildirim_merkezi, name="bildirim_merkezi"),
    path("panel/bildirimler/api/", bildirim_views.bildirim_api_liste, name="bildirim_api_liste"),
    path(
        "panel/bildirimler/api/<int:pk>/okundu/",
        bildirim_views.bildirim_api_okundu,
        name="bildirim_api_okundu",
    ),
    path(
        "panel/bildirimler/api/tumunu-okundu/",
        bildirim_views.bildirim_api_tumunu_okundu,
        name="bildirim_api_tumunu_okundu",
    ),
    path(
        "panel/bildirimler/<int:pk>/git/",
        bildirim_views.bildirim_okundu_yonlendir,
        name="bildirim_okundu_yonlendir",
    ),

    path("panel/asistan/chat/", asistan_views.asistan_chat_api, name="asistan_chat_api"),

    path("programlar/", views.program_panel, name="program_panel"),
    path("programlar/<int:pk>/", views.program_detay, name="program_detay"),
    path("programlar/<int:pk>/pdf/", views.program_pdf, name="program_pdf"),
    path("programlar/<int:pk>/excel/", views.program_excel, name="program_excel"),

    path(
        "dershane-programi/",
        dershane_program_views.dershane_program_panel,
        name="dershane_program_panel",
    ),
    path(
        "dershane-programi/atama-surukle/",
        dershane_program_views.dershane_program_atama_surukle,
        name="dershane_program_atama_surukle",
    ),
    path(
        "dershane-programi/goruntule/<str:mod>/",
        dershane_program_views.dershane_program_goruntule,
        name="dershane_program_goruntule",
    ),
    path(
        "dershane-programi/pdf/",
        dershane_program_views.dershane_program_pdf,
        name="dershane_program_pdf",
    ),
    path(
        "dershane-programi/excel/",
        dershane_program_views.dershane_program_excel,
        name="dershane_program_excel",
    ),
    path(
        "dershane-programi/paylas/",
        dershane_program_views.dershane_program_paylas,
        name="dershane_program_paylas",
    ),

    path("imam-muezzin/", views.imam_muezzin_panel, name="imam_muezzin_panel"),
    path(
        "imam-muezzin/<int:pk>/pdf/",
        views.imam_muezzin_pdf,
        name="imam_muezzin_pdf",
    ),

    path("temizlik/", views.temizlik_panel, name="temizlik_panel"),
    path(
        "temizlik/<int:pk>/pdf/",
        views.temizlik_pdf,
        name="temizlik_pdf",
    ),

    path("yemekcilik/", yemekci_views.yemekcilik_panel, name="yemekcilik_panel"),
    path(
        "yemekcilik/pdf/",
        yemekci_views.yemekcilik_pdf,
        name="yemekcilik_pdf",
    ),
    path(
        "yemekcilik/<int:pk>/pdf/",
        yemekci_views.yemekcilik_pdf,
        name="yemekcilik_pdf_eski",
    ),
    path(
        "yemekcilik/api/kayit-ekle/",
        yemekci_views.yemekcilik_api_kayit_ekle,
        name="yemekcilik_api_kayit_ekle",
    ),
    path(
        "yemekcilik/api/kayit-sil/",
        yemekci_views.yemekcilik_api_kayit_sil,
        name="yemekcilik_api_kayit_sil",
    ),
    path(
        "yemekcilik/api/sirala/",
        yemekci_views.yemekcilik_api_sirala,
        name="yemekcilik_api_sirala",
    ),
    path(
        "yemekcilik/api/gorevli/",
        yemekci_views.yemekcilik_api_gorevli,
        name="yemekcilik_api_gorevli",
    ),

    path("talebeler/", views.talebe_listesi, name="talebe_listesi"),
    path(
        "talebeler/rapor/pdf/",
        views.talebe_liste_raporu_pdf,
        name="talebe_liste_raporu_pdf",
    ),
    path(
        "talebeler/rapor/excel/",
        views.talebe_liste_excel,
        name="talebe_liste_excel",
    ),
    path("talebe/<int:talebe_id>/", views.talebe_detay, name="talebe_detay"),
    path(
        "talebe/<int:talebe_id>/profil-karne-pdf/",
        views.talebe_profil_karne_pdf,
        name="talebe_profil_karne_pdf",
    ),

    path("kitaplar/", views.kitap_listesi, name="kitap_listesi"),
    path("kitap-ekle/", views.kitap_ekle, name="kitap_ekle"),

    path("toplu-zimmet/", views.toplu_zimmet, name="toplu_zimmet"),
    path("toplu-gunluk-okuma/", views.toplu_gunluk_okuma, name="toplu_gunluk_okuma"),
    path("toplu-kitap-sinavi/", views.toplu_kitap_sinavi, name="toplu_kitap_sinavi"),

    path("sinav-ekle/", views.sinav_ekle_panel, name="sinav_ekle_panel"),
    path("sinav-sonuclari/", views.sinav_sonuc_paneli, name="sinav_sonuc_paneli"),
    path(
        "sinav-sonuclari/<int:sinav_id>/",
        views.sinav_sonuclari_gir,
        name="sinav_sonuclari_gir",
    ),
    path(
        "sinav-sonuclari/<int:sinav_id>/talebe/<int:talebe_id>/karne-pdf/",
        views.sinav_karne_pdf,
        name="sinav_karne_pdf",
    ),
    path(
        "sinav-sonuclari/<int:sinav_id>/sirali-sonuc-pdf/",
        views.sinav_sirali_sonuc_pdf,
        name="sinav_sirali_sonuc_pdf",
    ),

    path("raporlar/", views.raporlar, name="raporlar"),
    path("raporlar/pdf/", views.okuma_raporu_pdf, name="okuma_raporu_pdf"),

    path("ktt/", ktt_views.ktt_listesi, name="ktt_listesi"),
    path("ktt/rapor/", ktt_views.ktt_rapor, name="ktt_rapor"),
    path("ktt/rapor/analiz/", ktt_views.ktt_rapor_analiz, name="ktt_rapor_analiz"),
    path("ktt/ekle/", ktt_views.ktt_ekle, name="ktt_ekle"),
    path("ktt/<int:pk>/sil/", ktt_views.ktt_sil, name="ktt_sil"),
    path("ktt/<int:pk>/", ktt_views.ktt_detay, name="ktt_detay"),
    path("ktt/<int:pk>/duzenle/", ktt_views.ktt_duzenle, name="ktt_duzenle"),
    path("ktt/<int:pk>/sonuclar/", ktt_views.ktt_sonuc_gir, name="ktt_sonuc_gir"),
    path("ktt/<int:pk>/excel/", ktt_views.ktt_excel_indir, name="ktt_excel_indir"),
    path("ktt/<int:pk>/pdf/", ktt_views.ktt_detay_pdf, name="ktt_detay_pdf"),

    path("denemeler/", deneme_views.deneme_listesi, name="deneme_listesi"),
    path("denemeler/<int:pk>/", deneme_views.deneme_detay, name="deneme_detay"),

    path("yazili-takip/", yazili_takip_views.yazili_kamp_listesi, name="yazili_kamp_listesi"),
    path(
        "yazili-takip/<int:pk>/",
        yazili_takip_views.yazili_kamp_detay,
        name="yazili_kamp_detay",
    ),
    path(
        "yazili-takip/sinav/<int:pk>/sonuclar/",
        yazili_takip_views.yazili_sonuc_gir,
        name="yazili_sonuc_gir",
    ),
    path(
        "yazili-takip/sinav/<int:pk>/sil/",
        yazili_takip_views.yazili_sinav_sil,
        name="yazili_sinav_sil",
    ),
    path(
        "yazili-takip/<int:pk>/pdf/",
        yazili_takip_views.yazili_kamp_pdf,
        name="yazili_kamp_pdf",
    ),
    path(
        "yazili-takip/sinav/<int:pk>/pdf/",
        yazili_takip_views.yazili_sinav_sirali_pdf,
        name="yazili_sinav_sirali_pdf",
    ),
    path(
        "yazili-takip/sinav/<int:pk>/bireysel-pdf/",
        yazili_takip_views.yazili_sinav_bireysel_pdf,
        name="yazili_sinav_bireysel_pdf",
    ),
    path(
        "yazili-takip/sinav/<int:pk>/bireysel-pdf/<int:talebe_id>/",
        yazili_takip_views.yazili_sinav_bireysel_pdf,
        name="yazili_sinav_bireysel_talebe_pdf",
    ),
    path(
        "yazili-takip/sinav/<int:pk>/excel-sablon/",
        yazili_takip_views.yazili_sinav_excel_sablon,
        name="yazili_sinav_excel_sablon",
    ),

    path("soru-takip/", soru_takip_views.soru_takip_panel, name="soru_takip_panel"),
    path(
        "soru-takip/rapor/",
        soru_takip_views.soru_takip_rapor,
        name="soru_takip_rapor",
    ),
    path(
        "soru-takip/excel/",
        soru_takip_views.soru_takip_excel,
        name="soru_takip_excel",
    ),
    path(
        "soru-takip/<int:pk>/",
        soru_takip_views.soru_takip_detay,
        name="soru_takip_detay",
    ),
    path(
        "soru-takip/<int:pk>/sil/",
        soru_takip_views.soru_takip_sil,
        name="soru_takip_sil",
    ),

    path(
        "akademik-mudahale/",
        akademik_mudahale_views.mudahale_listesi,
        name="akademik_mudahale_listesi",
    ),
    path(
        "akademik-mudahale/ekle/",
        akademik_mudahale_views.mudahale_ekle,
        name="akademik_mudahale_ekle",
    ),
    path(
        "akademik-mudahale/rapor/",
        akademik_mudahale_views.mudahale_rapor,
        name="akademik_mudahale_rapor",
    ),
    path(
        "akademik-mudahale/excel/",
        akademik_mudahale_views.mudahale_excel,
        name="akademik_mudahale_excel",
    ),
    path(
        "akademik-mudahale/pdf/",
        akademik_mudahale_views.mudahale_pdf,
        name="akademik_mudahale_pdf",
    ),
    path(
        "akademik-mudahale/<int:pk>/",
        akademik_mudahale_views.mudahale_detay,
        name="akademik_mudahale_detay",
    ),
    path(
        "akademik-mudahale/<int:pk>/duzenle/",
        akademik_mudahale_views.mudahale_duzenle,
        name="akademik_mudahale_duzenle",
    ),
    path(
        "akademik-mudahale/<int:pk>/sil/",
        akademik_mudahale_views.mudahale_sil,
        name="akademik_mudahale_sil",
    ),

    path("etut-plani/", etut_plan_views.etut_plan_panel, name="etut_plan_panel"),
    path(
        "etut-plani/yonetim/",
        etut_plan_views.etut_plan_yonetim,
        name="etut_plan_yonetim",
    ),
    path(
        "etut-plani/olustur/",
        etut_plan_views.etut_plan_olustur,
        name="etut_plan_olustur",
    ),
    path("etut-plani/arsiv/", etut_plan_views.etut_plan_arsiv, name="etut_plan_arsiv"),
    path(
        "etut-plani/pdf/",
        etut_plan_views.etut_plan_pdf,
        name="etut_plan_pdf",
    ),
    path(
        "etut-plani/api/faaliyet-ata/",
        etut_plan_views.etut_plan_faaliyet_ata,
        name="etut_plan_faaliyet_ata",
    ),
    path(
        "etut-plani/api/faaliyet-sil/",
        etut_plan_views.etut_plan_faaliyet_sil,
        name="etut_plan_faaliyet_sil",
    ),
    path(
        "etut-plani/api/durum/",
        etut_plan_views.etut_plan_durum_guncelle,
        name="etut_plan_durum_guncelle",
    ),
    path(
        "etut-plani/api/havuz/",
        etut_plan_views.etut_plan_havuz_ekle,
        name="etut_plan_havuz_ekle",
    ),
    path(
        "etut-plani/api/havuz-sil/",
        etut_plan_views.etut_plan_havuz_sil,
        name="etut_plan_havuz_sil",
    ),
    path(
        "etut-plani/api/havuz-sirala/",
        etut_plan_views.etut_plan_havuz_sirala,
        name="etut_plan_havuz_sirala",
    ),
    path(
        "etut-plani/api/kopyala/",
        etut_plan_views.etut_plan_kopyala,
        name="etut_plan_kopyala",
    ),
    path(
        "etut-plani/api/saat-sirala/",
        etut_plan_views.etut_plan_saat_sirala,
        name="etut_plan_saat_sirala",
    ),
    path(
        "etut-plani/<int:pk>/",
        etut_plan_views.etut_plan_detay,
        name="etut_plan_detay",
    ),

    path("dini-ders/", dini_ders_takip_views.dini_ders_panel, name="dini_ders_panel"),
    path(
        "dini-ders/rapor/",
        dini_ders_takip_views.dini_ders_rapor,
        name="dini_ders_rapor",
    ),
    path(
        "dini-ders/excel/",
        dini_ders_takip_views.dini_ders_excel,
        name="dini_ders_excel",
    ),

    path(
        "namaz-yoklama/",
        namaz_yoklama_views.namaz_yoklama_panel,
        name="namaz_yoklama_panel",
    ),
    path(
        "namaz-yoklama/rapor/",
        namaz_yoklama_views.namaz_yoklama_rapor,
        name="namaz_yoklama_rapor",
    ),

    path(
        "ogretmen-odeme/",
        ogretmen_odeme_views.ogretmen_odeme_listesi,
        name="ogretmen_odeme_listesi",
    ),
    path(
        "ogretmen-odeme/rapor/",
        ogretmen_odeme_views.ogretmen_odeme_rapor,
        name="ogretmen_odeme_rapor",
    ),
    path(
        "ogretmen-odeme/<int:pk>/",
        ogretmen_odeme_views.ogretmen_odeme_detay,
        name="ogretmen_odeme_detay",
    ),
    path(
        "ogretmen-odeme/<int:pk>/pdf/",
        ogretmen_odeme_views.ogretmen_odeme_pdf,
        name="ogretmen_odeme_pdf",
    ),
    path(
        "ogretmen-odeme/<int:pk>/sil/",
        ogretmen_odeme_views.ogretmen_odeme_sil,
        name="ogretmen_odeme_sil",
    ),

    path("mezunlar/", mezun_views.mezun_listesi, name="mezun_listesi"),
    path("mezunlar/ekle/", mezun_views.mezun_ekle, name="mezun_ekle"),
    path("mezunlar/etkinlikler/", mezun_views.mezun_etkinlikler, name="mezun_etkinlikler"),
    path("mezunlar/gorevler/", mezun_views.mezun_gorevler, name="mezun_gorevler"),
    path("mezunlar/gorevler/<int:pk>/", mezun_views.mezun_gorev_detay, name="mezun_gorev_detay"),
    path("mezunlar/istatistik/", mezun_views.mezun_istatistik, name="mezun_istatistik"),
    path("mezunlar/raporlar/", mezun_views.mezun_raporlar, name="mezun_raporlar"),
    path("mezunlar/<int:pk>/", mezun_views.mezun_detay, name="mezun_detay"),

    path("aidat/", finans_views.aidat_listesi_yonlendir, name="aidat_listesi"),
    path("aidat/<int:pk>/", aidat_views.aidat_detay, name="aidat_detay"),

    path("finans/", finans_views.finans_panel, name="finans_panel"),
    path("finans/ogrenci/<int:pk>/", finans_views.finans_ogrenci, name="finans_ogrenci"),
    path("finans/politikalar/", finans_views.finans_politikalar, name="finans_politikalar"),
    path("finans/indirimler/", finans_views.finans_indirimler, name="finans_indirimler"),
    path("finans/raporlar/", finans_views.finans_raporlar, name="finans_raporlar"),
    path("finans/raporlar/pdf/", finans_views.finans_rapor_pdf, name="finans_rapor_pdf"),
    path("finans/raporlar/excel/", finans_views.finans_rapor_excel, name="finans_rapor_excel"),
    path("finans/ayarlar/", finans_views.finans_ayarlar, name="finans_ayarlar"),

    path("rehberlik/", rehberlik_views.rehberlik_listesi, name="rehberlik_listesi"),
    path(
        "rehberlik/<int:pk>/",
        rehberlik_views.rehberlik_detay,
        name="rehberlik_detay",
    ),
    path(
        "rehberlik/<int:pk>/duzenle/",
        rehberlik_views.rehberlik_duzenle,
        name="rehberlik_duzenle",
    ),

    path("iletisim/", rehberlik_views.iletisim_listesi, name="iletisim_listesi"),
    path("randevu/", veli_randevu_views.randevu_panel, name="randevu_panel"),
    path("randevu/raporlar/", veli_randevu_views.randevu_raporlar, name="randevu_raporlar"),
    path("randevu/<int:pk>/", veli_randevu_views.randevu_detay, name="randevu_detay"),
    path(
        "iletisim/<int:pk>/",
        rehberlik_views.iletisim_detay,
        name="iletisim_detay",
    ),
    path(
        "iletisim/<int:pk>/duzenle/",
        rehberlik_views.iletisim_duzenle,
        name="iletisim_duzenle",
    ),

    path("disiplin/", disiplin_views.disiplin_listesi, name="disiplin_listesi"),
    path(
        "disiplin/<int:pk>/",
        disiplin_views.disiplin_detay,
        name="disiplin_detay",
    ),
    path(
        "disiplin/<int:pk>/duzenle/",
        disiplin_views.disiplin_duzenle,
        name="disiplin_duzenle",
    ),

    path(
        "disiplin-kurulu/",
        disiplin_kurul_views.disiplin_kurul_panel,
        name="disiplin_kurul_panel",
    ),
    path(
        "disiplin-kurulu/olustur/",
        disiplin_kurul_views.disiplin_kurul_olustur,
        name="disiplin_kurul_olustur",
    ),
    path(
        "disiplin-kurulu/ayarlar/",
        disiplin_kurul_views.disiplin_kurul_ayarlar,
        name="disiplin_kurul_ayarlar",
    ),
    path(
        "disiplin-kurulu/ayarlar/gundem-pdf/",
        disiplin_kurul_views.disiplin_kurul_gundem_pdf,
        name="disiplin_kurul_gundem_pdf",
    ),
    path(
        "disiplin-kurulu/rapor/",
        disiplin_kurul_views.disiplin_kurul_rapor,
        name="disiplin_kurul_rapor",
    ),
    path(
        "disiplin-kurulu/arsiv/",
        disiplin_kurul_views.disiplin_kurul_arsiv,
        name="disiplin_kurul_arsiv",
    ),
    path(
        "disiplin-kurulu/excel/",
        disiplin_kurul_views.disiplin_kurul_excel,
        name="disiplin_kurul_excel",
    ),
    path(
        "disiplin-kurulu/<int:pk>/",
        disiplin_kurul_views.disiplin_kurul_detay,
        name="disiplin_kurul_detay",
    ),
    path(
        "disiplin-kurulu/<int:pk>/pdf/",
        disiplin_kurul_views.disiplin_kurul_pdf,
        name="disiplin_kurul_pdf",
    ),
    path(
        "disiplin-kurulu/<int:pk>/karar/",
        disiplin_kurul_views.disiplin_kurul_karar_ekle,
        name="disiplin_kurul_karar_ekle",
    ),
    path(
        "disiplin-kurulu/<int:pk>/karar/<int:karar_pk>/durum/",
        disiplin_kurul_views.disiplin_kurul_karar_durum,
        name="disiplin_kurul_karar_durum",
    ),
    path(
        "disiplin-kurulu/<int:pk>/durum/",
        disiplin_kurul_views.disiplin_kurul_durum_ilerlet,
        name="disiplin_kurul_durum_ilerlet",
    ),

    path(
        "gunluk-takip/etut/",
        gunluk_takip_views.gunluk_takip_etut,
        name="gunluk_takip_etut",
    ),
    path(
        "gunluk-takip/",
        gunluk_takip_views.gunluk_takip_panel,
        name="gunluk_takip_panel",
    ),
    path(
        "gunluk-takip/<int:pk>/",
        gunluk_takip_views.gunluk_takip_detay,
        name="gunluk_takip_detay",
    ),
    path(
        "gunluk-takip/<int:pk>/duzenle/",
        gunluk_takip_views.gunluk_takip_duzenle,
        name="gunluk_takip_duzenle",
    ),

    path("veli/", veli_views.veli_dashboard, name="veli_dashboard"),
    path("veli/duyurular/", veli_views.veli_duyurular, name="veli_duyurular"),
    path(
        "veli/talebe/<int:talebe_id>/",
        veli_views.veli_talebe_dashboard,
        name="veli_talebe_dashboard",
    ),
    path(
        "veli/talebe/<int:talebe_id>/profil/",
        veli_views.veli_talebe_profil,
        name="veli_talebe_profil",
    ),
    path(
        "veli/talebe/<int:talebe_id>/sinavlar/",
        veli_views.veli_talebe_sinavlar,
        name="veli_talebe_sinavlar",
    ),
    path(
        "veli/talebe/<int:talebe_id>/degerlendirme-karne-pdf/",
        veli_views.veli_talebe_degerlendirme_karne_pdf,
        name="veli_talebe_degerlendirme_karne_pdf",
    ),
    path(
        "veli/talebe/<int:talebe_id>/dini-ders/",
        veli_views.veli_talebe_dini_ders,
        name="veli_talebe_dini_ders",
    ),
    path(
        "veli/talebe/<int:talebe_id>/soru/",
        veli_views.veli_talebe_soru,
        name="veli_talebe_soru",
    ),
    path(
        "veli/talebe/<int:talebe_id>/ders-notlari/",
        veli_views.veli_talebe_ders_notlari,
        name="veli_talebe_ders_notlari",
    ),
    path(
        "veli/talebe/<int:talebe_id>/yoklama/",
        veli_views.veli_talebe_yoklama,
        name="veli_talebe_yoklama",
    ),
    path(
        "veli/talebe/<int:talebe_id>/namaz/",
        veli_views.veli_talebe_namaz,
        name="veli_talebe_namaz",
    ),
    path(
        "veli/talebe/<int:talebe_id>/akademik-mudahale/",
        veli_views.veli_talebe_mudahale,
        name="veli_talebe_mudahale",
    ),
    path(
        "veli/talebe/<int:talebe_id>/sohbet/",
        veli_views.veli_talebe_sohbet,
        name="veli_talebe_sohbet",
    ),
    path(
        "veli/talebe/<int:talebe_id>/randevu/",
        veli_views.veli_talebe_randevu,
        name="veli_talebe_randevu",
    ),
    path(
        "veli/talebe/<int:talebe_id>/aidat/",
        veli_views.veli_talebe_aidat,
        name="veli_talebe_aidat",
    ),
    path(
        "veli/talebe/<int:talebe_id>/ozet/",
        veli_views.veli_talebe_detay,
        name="veli_talebe_detay",
    ),

    path("talebe/", talebe_panel_views.talebe_dashboard, name="talebe_dashboard"),
    path("talebe/profil/", talebe_panel_views.talebe_profil, name="talebe_profil"),
    path("talebe/gorevler/", talebe_panel_views.talebe_gorevler, name="talebe_gorevler"),
    path("talebe/okuma-soru/", talebe_panel_views.talebe_okuma_soru, name="talebe_okuma_soru"),

    path("ogretmen-panel/", ogretmen_views.ogretmen_dashboard, name="ogretmen_dashboard"),
    path("ogretmen-panel/not/", ogretmen_views.ogretmen_not_girisi, name="ogretmen_not_girisi"),
    path(
        "ogretmen-panel/not/<int:sinif_id>/",
        ogretmen_views.ogretmen_not_girisi,
        name="ogretmen_not_girisi_sinif",
    ),
    path(
        "ogretmen-panel/ders-programi/",
        ogretmen_views.ogretmen_ders_programi,
        name="ogretmen_ders_programi",
    ),
    path(
        "ogretmen-panel/ders-programi/pdf/",
        ogretmen_views.ogretmen_ders_programi_pdf,
        name="ogretmen_ders_programi_pdf",
    ),
    path(
        "ogretmen-panel/degerlendirmeler/",
        ogretmen_views.ogretmen_degerlendirmeler,
        name="ogretmen_degerlendirmeler",
    ),
    path(
        "ogretmen-panel/degerlendirmeler/talebe/<int:talebe_id>/karne-pdf/",
        ogretmen_views.ogretmen_talebe_karne_pdf,
        name="ogretmen_talebe_karne_pdf",
    ),
]