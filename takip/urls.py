from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),

    path(
        "giris/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
        ),
        name="login",
    ),

    path("cikis/", auth_views.LogoutView.as_view(), name="logout"),

    path("panel/", views.dashboard, name="dashboard"),

    path("talebeler/", views.talebe_listesi, name="talebe_listesi"),
    path("talebe/<int:talebe_id>/", views.talebe_detay, name="talebe_detay"),

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
]