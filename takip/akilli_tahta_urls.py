"""Akıllı Tahta Dosya Merkezi — etüt hocası / yönetici paneli adresleri."""

from django.urls import path

from takip import akilli_tahta_views as views

app_name = "akilli_tahta"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("yukle/", views.yukle, name="yukle"),
    path("<int:pk>/duzenle/", views.duzenle, name="duzenle"),
    path("<int:pk>/yayindan-kaldir/", views.yayindan_kaldir, name="yayindan_kaldir"),
    path("<int:pk>/arsivle/", views.arsivle, name="arsivle"),
    path("<int:pk>/yayina-al/", views.yayina_al, name="yayina_al"),
]
