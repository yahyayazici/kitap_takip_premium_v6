from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from takip.bootstrap_views import bootstrap_admin, bootstrap_setup, health_check
from takip.pwa_views import service_worker, web_manifest

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("manifest.webmanifest", web_manifest, name="web_manifest"),
    path("sw.js", service_worker, name="service_worker"),
    path("admin/", admin.site.urls),
    path("bootstrap-admin/", bootstrap_admin, name="bootstrap_admin"),
    path("bootstrap-setup/", bootstrap_setup, name="bootstrap_setup"),
    path("yonetim/", include("takip.yonetim_urls")),
    path("", include("takip.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)