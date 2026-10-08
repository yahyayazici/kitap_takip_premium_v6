from django.urls import path

from sinav_okuma import views

app_name = "sinav_okuma"

urlpatterns = [
    path("", views.sinav_listesi, name="sinav_listesi"),
    path("giris/", views.giris, name="giris"),
    path("cikis/", views.cikis, name="cikis"),
    path("formlar/", views.form_listesi, name="form_listesi"),
    path("formlar/ekle/", views.form_kaydet, name="form_ekle"),
    path("formlar/<int:pk>/", views.form_kaydet, name="form_kaydet"),
    path("sinavlar/<int:pk>/", views.sinav_detay, name="sinav_detay"),
    path("sinavlar/<int:pk>/oku/", views.sinav_oku, name="sinav_oku"),
    path("sinavlar/<int:pk>/sil/", views.sinav_sil, name="sinav_sil"),
]
