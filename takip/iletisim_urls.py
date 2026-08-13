"""İletişim Merkezi — URL'ler."""

from django.urls import path

from takip import iletisim_views as views

urlpatterns = [
    path("", views.iletisim_merkezi, name="iletisim_merkezi"),
    path("yeni/", views.iletisim_yeni_mesaj, name="iletisim_yeni_mesaj"),
    path("hazirla/<slug:modul>/<int:kaynak_id>/", views.iletisim_hazirla, name="iletisim_hazirla"),
    path("paket/<int:pk>/", views.iletisim_paket_onizleme, name="iletisim_paket_onizleme"),
    path("paket/<int:pk>/share-bridge/", views.iletisim_share_bridge, name="iletisim_share_bridge"),
    path("p/ek/<path:token>/", views.iletisim_ek_public_indir, name="iletisim_ek_public"),
    path("ek/<int:pk>/indir/", views.iletisim_ek_indir, name="iletisim_ek_indir"),
    path("api/paket/<int:pk>/", views.iletisim_api_paket, name="iletisim_api_paket"),
    path("api/paket/<int:pk>/mesaj/", views.iletisim_api_mesaj_guncelle, name="iletisim_api_mesaj_guncelle"),
    path("api/paket/<int:pk>/taslak/", views.iletisim_api_taslak, name="iletisim_api_taslak"),
    path("api/paket/<int:pk>/olay/", views.iletisim_api_olay, name="iletisim_api_olay"),
]
