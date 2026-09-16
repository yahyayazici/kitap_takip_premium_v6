from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.static import serve

from takip.bootstrap_views import bootstrap_setup, health_check
from takip.pwa_views import (
    og_share_image,
    push_abone_ol,
    push_abonelik_sil,
    pwa_baslat,
    pwa_icon_180,
    pwa_icon_192,
    pwa_icon_512,
    service_worker,
    web_manifest,
)

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("pwa/baslat/", pwa_baslat, name="pwa_baslat"),
    path("manifest.webmanifest", web_manifest, name="web_manifest"),
    path("sw.js", service_worker, name="service_worker"),
    path("pwa/push/abone-ol/", push_abone_ol, name="push_abone_ol"),
    path("pwa/push/abonelik-sil/", push_abonelik_sil, name="push_abonelik_sil"),
    path("apple-touch-icon.png", pwa_icon_180, name="apple_touch_icon"),
    path("apple-touch-icon-precomposed.png", pwa_icon_180, name="apple_touch_icon_precomposed"),
    path("pwa/icon-180.png", pwa_icon_180, name="pwa_icon_180"),
    path("pwa/icon-192.png", pwa_icon_192, name="pwa_icon_192"),
    path("pwa/icon-512.png", pwa_icon_512, name="pwa_icon_512"),
    path("og.png", og_share_image, name="og_share_image"),
    path("admin/", admin.site.urls),
    path("bootstrap-setup/", bootstrap_setup, name="bootstrap_setup"),
    path("yonetim/", include("takip.yonetim_urls")),
    path("", include("takip.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]