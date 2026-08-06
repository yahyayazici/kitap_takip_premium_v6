from django.urls import path

from . import yonetim_views

app_name = "yonetim"

urlpatterns = [
    path("", yonetim_views.dashboard, name="dashboard"),

    path(
        "siniflar/",
        yonetim_views.sinif_listesi,
        name="sinif_listesi",
    ),
    path(
        "siniflar/ekle/",
        yonetim_views.sinif_ekle,
        name="sinif_ekle",
    ),
    path(
        "siniflar/<int:pk>/duzenle/",
        yonetim_views.sinif_duzenle,
        name="sinif_duzenle",
    ),

    path(
        "personeller/",
        yonetim_views.personel_listesi,
        name="personel_listesi",
    ),
    path(
        "personeller/ekle/",
        yonetim_views.personel_ekle,
        name="personel_ekle",
    ),
    path(
        "personeller/<int:pk>/duzenle/",
        yonetim_views.personel_duzenle,
        name="personel_duzenle",
    ),

    path(
        "talebeler/",
        yonetim_views.talebe_listesi,
        name="talebe_listesi",
    ),
    path(
        "talebeler/ekle/",
        yonetim_views.talebe_ekle,
        name="talebe_ekle",
    ),
    path(
        "talebeler/<int:pk>/duzenle/",
        yonetim_views.talebe_duzenle,
        name="talebe_duzenle",
    ),
]
