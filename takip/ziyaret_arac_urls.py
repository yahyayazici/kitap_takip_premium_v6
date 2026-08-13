"""Ziyaret Araç Planlama — URL'ler."""

from django.urls import path

from takip import ziyaret_arac_views as views

urlpatterns = [
    path("", views.ziyaret_arac_listesi, name="ziyaret_arac_listesi"),
    path("yeni/", views.ziyaret_arac_olustur, name="ziyaret_arac_olustur"),
    path("<int:pk>/", views.ziyaret_arac_detay, name="ziyaret_arac_detay"),
    path("<int:pk>/duzenle/", views.ziyaret_arac_duzenle, name="ziyaret_arac_duzenle"),
    path("<int:pk>/etut/", views.ziyaret_arac_etut, name="ziyaret_arac_etut"),
    path("<int:pk>/planlama/", views.ziyaret_arac_planlama, name="ziyaret_arac_planlama"),
    path("<int:pk>/onizleme/", views.ziyaret_arac_onizleme, name="ziyaret_arac_onizleme"),
    path("<int:pk>/hazir/", views.ziyaret_arac_hazir, name="ziyaret_arac_hazir"),
    path("<int:pk>/talebe-ekle/", views.ziyaret_arac_talebe_ekle, name="ziyaret_arac_talebe_ekle"),
    path(
        "<int:pk>/talebe-cikar/<int:talebe_id>/",
        views.ziyaret_arac_talebe_cikar,
        name="ziyaret_arac_talebe_cikar",
    ),
    path("<int:pk>/pdf/", views.ziyaret_arac_pdf_genel, name="ziyaret_arac_pdf_genel"),
    path(
        "<int:pk>/pdf/arac/<int:arac_id>/",
        views.ziyaret_arac_pdf_arac,
        name="ziyaret_arac_pdf_arac",
    ),
    path(
        "<int:pk>/pdf/tum-araclar/",
        views.ziyaret_arac_pdf_tum_araclar,
        name="ziyaret_arac_pdf_tum_araclar",
    ),
    path("<int:pk>/api/ata/", views.ziyaret_arac_api_ata, name="ziyaret_arac_api_ata"),
    path("<int:pk>/api/cikar/", views.ziyaret_arac_api_cikar, name="ziyaret_arac_api_cikar"),
    path(
        "<int:pk>/api/otomatik/",
        views.ziyaret_arac_api_otomatik,
        name="ziyaret_arac_api_otomatik",
    ),
    path(
        "<int:pk>/api/geri-al/",
        views.ziyaret_arac_api_geri_al,
        name="ziyaret_arac_api_geri_al",
    ),
    path(
        "<int:pk>/api/sabitle/",
        views.ziyaret_arac_api_sabitle,
        name="ziyaret_arac_api_sabitle",
    ),
    path(
        "<int:pk>/api/arac/",
        views.ziyaret_arac_arac_kaydet,
        name="ziyaret_arac_arac_kaydet",
    ),
    path(
        "<int:pk>/api/arac/<int:arac_id>/sil/",
        views.ziyaret_arac_arac_sil,
        name="ziyaret_arac_arac_sil",
    ),
    path(
        "<int:pk>/api/talebe-ara/",
        views.ziyaret_arac_talebe_ara,
        name="ziyaret_arac_talebe_ara",
    ),
]
