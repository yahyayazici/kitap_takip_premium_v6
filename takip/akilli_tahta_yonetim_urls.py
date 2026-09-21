"""Akıllı Tahta Dosya Merkezi — yönetici kontrolleri adresleri."""

from django.urls import path

from takip import akilli_tahta_yonetim_views as views

app_name = "akilli_tahta_yonetim"

urlpatterns = [
    path("hesaplar/", views.hesap_listesi, name="hesap_listesi"),
    path("hesaplar/yeni/", views.hesap_olustur, name="hesap_olustur"),
    path("hesaplar/<int:pk>/duzenle/", views.hesap_duzenle, name="hesap_duzenle"),
    path("hesaplar/<int:pk>/sifre/", views.hesap_sifre_degistir, name="hesap_sifre_degistir"),
    path(
        "hesaplar/<int:pk>/oturumlari-sonlandir/",
        views.hesap_oturumlari_sonlandir,
        name="hesap_oturumlari_sonlandir",
    ),
    path("gecmis/", views.islem_gecmisi, name="islem_gecmisi"),
]
