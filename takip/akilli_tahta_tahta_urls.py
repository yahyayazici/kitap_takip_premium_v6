"""Akıllı tahta hesaplarının ekranı — adresler."""

from django.urls import path

from takip import akilli_tahta_tahta_views as views

app_name = "akilli_tahta_tahta"

urlpatterns = [
    path("", views.ekran, name="ekran"),
    path("durum/", views.durum, name="durum"),
    path("icerik/", views.icerik, name="icerik"),
    path("dosya/<int:pk>/", views.goruntule, name="goruntule"),
]
