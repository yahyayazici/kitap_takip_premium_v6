"""Televizyon yüzeyi — ``ekran.<domain>`` kökü ve cihaz API'si."""

from django.urls import path

from takip import ekran_api_views, ekran_viewer_views

urlpatterns = [
    path("", ekran_viewer_views.viewer, name="ekran_viewer"),
    path("sw.js", ekran_viewer_views.service_worker, name="ekran_service_worker"),
    path("offline/", ekran_viewer_views.offline, name="ekran_offline"),
    path("ekran-qr/", ekran_viewer_views.qr_kodu, name="ekran_qr"),
    path("api/cihaz/kayit/", ekran_api_views.cihaz_kayit, name="ekran_api_kayit"),
    path("api/cihaz/kod/", ekran_api_views.eslestirme_kodu_yenile, name="ekran_api_kod"),
    path("api/cihaz/yoklama/", ekran_api_views.cihaz_yoklama, name="ekran_api_yoklama"),
    path("api/cihaz/yayin/", ekran_api_views.cihaz_yayini, name="ekran_api_yayin"),
    path("api/cihaz/rapor/", ekran_api_views.cihaz_raporu, name="ekran_api_rapor"),
]
