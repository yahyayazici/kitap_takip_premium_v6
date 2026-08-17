from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import etut_plan_views
from . import etut_karne_views
from . import dini_ders_takip_views
from . import namaz_yoklama_views
from . import pazar_izin_donus_views
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
from . import cuma_durum_views
from . import bildirim_views
from . import akademik_mudahale_views
from . import ktt_views
from . import ss_deneme_views
from . import ktt_akilli_views
from . import olcme_views
from . import soru_takip_views
from . import ogretmen_views
from . import talebe_panel_views
from . import konu_destek_views
from . import veli_views
from . import veli_randevu_views
from . import asistan_views
from . import ai_views
from . import dershane_program_views
from . import yemekci_views
from . import sinav_basvuru_views
from . import ziyaret_arac_views
from . import views
from .auth_views import PanelLoginView

urlpatterns = [
    path("", views.home, name="home"),

    path(
        "giris/",
        PanelLoginView.as_view(),
        name="login",
    ),

    path(
        "sinav-basvuru/",
        sinav_basvuru_views.sinav_basvuru_form,
        name="sinav_basvuru_form",
    ),
    path(
        "sinav-basvuru/tesekkur/",
        sinav_basvuru_views.sinav_basvuru_tesekkur,
        name="sinav_basvuru_tesekkur",
    ),

    path("cikis/", auth_views.LogoutView.as_view(), name="logout"),

    path("panel/", views.dashboard, name="dashboard"),
    path("panel/yct/", personel_vazife_views.yct_personel, name="yct_personel"),
    path("panel/vazifelerim/", personel_vazife_views.vazife_personel, name="vazife_personel"),
    path("panel/cuma-durum/", cuma_durum_views.cuma_durum_panel, name="cuma_durum_panel"),
    path(
        "panel/cuma-durum/api/",
        cuma_durum_views.cuma_durum_api_havuz,
        name="cuma_durum_api_havuz",
    ),
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
    path("panel/ai/analiz/", ai_views.ai_analiz_api, name="ai_analiz_api"),
    path("panel/ai/analiz/html/", ai_views.ai_analiz_html, name="ai_analiz_html"),

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
    path("kitap/<int:pk>/sil/", views.kitap_sil, name="kitap_sil"),

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

    path("olcme/", olcme_views.olcme_hub, name="olcme_hub"),
    path("olcme/sinavlar/", olcme_views.olcme_sinav_listesi, name="olcme_sinav_listesi"),
    path("olcme/sinav/yeni/", olcme_views.olcme_sinav_wizard_yeni, name="olcme_sinav_wizard_yeni"),
    path("olcme/sinav/<int:pk>/duzenle/", olcme_views.olcme_sinav_wizard, name="olcme_sinav_wizard"),
    path("olcme/sinav/<int:pk>/", olcme_views.olcme_sinav_detay, name="olcme_sinav_detay"),
    path("olcme/sinav/<int:pk>/sil/", olcme_views.olcme_sinav_sil, name="olcme_sinav_sil"),
    path("olcme/sinav/<int:pk>/zimmet/", olcme_views.olcme_sinav_zimmet, name="olcme_sinav_zimmet"),
    path("olcme/sinav/<int:pk>/sablondan/", olcme_views.olcme_sinav_sablondan, name="olcme_sinav_sablondan"),
    path("olcme/sinav/<int:pk>/sablon-kaydet/", olcme_views.olcme_sinav_sablon_kaydet, name="olcme_sinav_sablon_kaydet"),
    path("olcme/sinav/<int:pk>/sonuc/", olcme_views.olcme_sinav_sonuc_soru, name="olcme_sinav_sonuc_soru"),
    path("olcme/sinav/<int:pk>/sonuc-toplu/", olcme_views.olcme_sinav_sonuc_toplu, name="olcme_sinav_sonuc_toplu"),
    path("olcme/sinav/<int:pk>/durum/", olcme_views.olcme_sinav_durum, name="olcme_sinav_durum"),
    path(
        "olcme/sinav/<int:pk>/veli-toggle/",
        olcme_views.olcme_sinav_veli_toggle,
        name="olcme_sinav_veli_toggle",
    ),
    path("olcme/sinav/<int:pk>/analiz-excel/", olcme_views.olcme_sinav_analiz_excel, name="olcme_sinav_analiz_excel"),
    path("olcme/sinav/<int:pk>/sonuc-csv/", olcme_views.olcme_sinav_sonuc_csv, name="olcme_sinav_sonuc_csv"),
    path("olcme/sinav/<int:pk>/optik-pdf/", olcme_views.olcme_optik_form_pdf, name="olcme_optik_form_pdf"),
    path("olcme/raporlar/", olcme_views.olcme_rapor_sec, name="olcme_rapor_sec"),
    path("olcme/konu-analiz/", olcme_views.olcme_konu_analiz_sec, name="olcme_konu_analiz_sec"),
    path("olcme/sinav/<int:pk>/konu-analiz/", olcme_views.olcme_konu_analiz, name="olcme_konu_analiz"),
    path(
        "olcme/sinav/<int:pk>/etut-aktar/",
        olcme_views.olcme_sinav_etut_aktar,
        name="olcme_sinav_etut_aktar",
    ),
    path("olcme/konu-havuzu/", olcme_views.olcme_konu_havuzu, name="olcme_konu_havuzu"),
    path("olcme/api/konu/", olcme_views.olcme_konu_ara_api, name="olcme_konu_ara_api"),
    path("olcme/api/kazanim/", olcme_views.olcme_kazanim_ara_api, name="olcme_kazanim_ara_api"),
    path("olcme/sablonlar/", olcme_views.olcme_sablon_listesi, name="olcme_sablon_listesi"),
    path("olcme/optik/", olcme_views.olcme_optik_sec, name="olcme_optik_sec"),
    path("olcme/optik-oku/", olcme_views.olcme_optik_oku_sec, name="olcme_optik_oku_sec"),
    path("olcme/sinav/<int:pk>/optik/", olcme_views.olcme_optik_form, name="olcme_optik_form"),
    path("olcme/sinav/<int:pk>/optik-oku/", olcme_views.olcme_optik_oku, name="olcme_optik_oku"),
    path("olcme/sinav/<int:pk>/optik-mobil/", olcme_views.olcme_optik_mobil, name="olcme_optik_mobil"),
    path("olcme/sinav/<int:pk>/optik-foto/", olcme_views.olcme_optik_foto, name="olcme_optik_foto"),
    path("ktt/", ktt_views.ktt_listesi, name="ktt_listesi"),
    path("ktt/akilli/", ktt_akilli_views.ktt_akilli_ozet, name="ktt_akilli_ozet"),
    path("ktt/konu-oneri/", ktt_akilli_views.ktt_konu_oneri, name="ktt_konu_oneri"),
    path(
        "ktt/mudahale/<int:eksik_id>/calisildi/",
        ktt_akilli_views.ktt_mudahale_calisildi,
        name="ktt_mudahale_calisildi",
    ),
    path(
        "ktt/eslestirme/<int:pk>/onayla/",
        ktt_akilli_views.ktt_eslestirme_onayla,
        name="ktt_eslestirme_onayla",
    ),
    path("ktt/rapor/", ktt_views.ktt_rapor, name="ktt_rapor"),
    path("ktt/rapor/analiz/", ktt_views.ktt_rapor_analiz, name="ktt_rapor_analiz"),
    path("ktt/ekle/", ktt_views.ktt_ekle, name="ktt_ekle"),
    path("ktt/<int:pk>/sil/", ktt_views.ktt_sil, name="ktt_sil"),
    path("ktt/<int:pk>/", ktt_views.ktt_detay, name="ktt_detay"),
    path("ktt/<int:pk>/duzenle/", ktt_views.ktt_duzenle, name="ktt_duzenle"),
    path("ktt/<int:pk>/sonuclar/", ktt_views.ktt_sonuc_gir, name="ktt_sonuc_gir"),
    path("ktt/<int:pk>/katilmayan-cikar/", ktt_views.ktt_katilmayan_cikar, name="ktt_katilmayan_cikar"),
    path("ktt/<int:pk>/excel/", ktt_views.ktt_excel_indir, name="ktt_excel_indir"),
    path("ktt/<int:pk>/pdf/", ktt_views.ktt_detay_pdf, name="ktt_detay_pdf"),

    path("ss-deneme/", ss_deneme_views.ss_deneme_listesi, name="ss_deneme_listesi"),
    path("ss-deneme/<int:pk>/", ss_deneme_views.ss_deneme_detay, name="ss_deneme_detay"),
    path("ss-deneme/<int:pk>/sil/", ss_deneme_views.ss_deneme_sil, name="ss_deneme_sil"),
    path("ss-deneme/<int:pk>/sonuclar/", ss_deneme_views.ss_deneme_sonuc_gir, name="ss_deneme_sonuc_gir"),
    path("ss-deneme/<int:pk>/pdf/", ss_deneme_views.ss_deneme_detay_pdf, name="ss_deneme_detay_pdf"),
    path("ss-deneme/<int:pk>/bireysel.pdf", ss_deneme_views.ss_deneme_bireysel_pdf, name="ss_deneme_bireysel_pdf"),
    path(
        "ss-deneme/<int:pk>/bireysel/<int:talebe_id>.pdf",
        ss_deneme_views.ss_deneme_bireysel_pdf,
        name="ss_deneme_bireysel_talebe_pdf",
    ),

    path("denemeler/", deneme_views.deneme_listesi, name="deneme_listesi"),
    path("denemeler/<int:pk>/", deneme_views.deneme_detay, name="deneme_detay"),
    path("denemeler/<int:pk>/excel/", deneme_views.deneme_excel_indir, name="deneme_excel_indir"),
    path("denemeler/<int:pk>/pdf/", deneme_views.deneme_detay_pdf, name="deneme_detay_pdf"),

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

    path(
        "etut-panel/haftalik-karneler/",
        etut_karne_views.etut_haftalik_karneler,
        name="etut_haftalik_karneler",
    ),
    path(
        "etut-panel/haftalik-karneler/talebe/<int:talebe_id>/pdf/",
        etut_karne_views.etut_talebe_haftalik_karne_pdf,
        name="etut_talebe_haftalik_karne_pdf",
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
        "pazar-izin-donus/",
        pazar_izin_donus_views.pazar_izin_donus_panel,
        name="pazar_izin_donus_panel",
    ),
    path(
        "pazar-izin-donus/rapor/",
        pazar_izin_donus_views.pazar_izin_donus_rapor,
        name="pazar_izin_donus_rapor",
    ),

    path("ziyaret-arac/", include("takip.ziyaret_arac_urls")),
    path("iletisim/", include("takip.iletisim_urls")),

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
    path("talebe/konu-destek/", konu_destek_views.talebe_konu_destek, name="talebe_konu_destek"),
    path(
        "talebe/konu-destek/<int:konu_id>/",
        konu_destek_views.talebe_konu_destek_detay,
        name="talebe_konu_destek_detay",
    ),
    path(
        "talebe/konu-destek/<int:konu_id>/video/<int:sira>/",
        konu_destek_views.talebe_konu_video,
        name="talebe_konu_video",
    ),
    path(
        "talebe/konu-destek/video-heartbeat/",
        konu_destek_views.talebe_konu_video_heartbeat,
        name="talebe_konu_video_heartbeat",
    ),
    path(
        "talebe/konu-destek/<int:konu_id>/test/",
        konu_destek_views.talebe_konu_test,
        name="talebe_konu_test",
    ),
    path(
        "konu-destek/rapor/",
        konu_destek_views.etut_konu_destek_rapor,
        name="etut_konu_destek_rapor",
    ),

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