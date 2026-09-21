from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.static import serve

from takip import akilli_tahta_viewer_views, ekran_viewer_views
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
    # Dijital Duyuru Ekranı — ekran.<domain> alt alan adında da /yonetim/
    # altında aynı görünümlere bağlanır (bkz. config.ekran_urls).
    path("ekran/", include("takip.ekran_urls")),
    path("akilli-tahta/", include("takip.akilli_tahta_urls")),
    path("tahta/", include("takip.akilli_tahta_tahta_urls")),
    # Televizyon görüntüleyicisi ana sitede de açılsın: alt alan adı
    # (ekran.<domain>) isteğe bağlı olsun diye. Aynı görünümler, tek fark kök.
    path("tv/", include("takip.ekran_viewer_urls")),
    # Stüdyo ön izlemesi ve televizyon aynı QR ucunu kullanır; adı iki
    # urlconf'ta da "ekran_qr" olduğu için şablon tek {% url %} ile çalışır.
    path("ekran-qr/", ekran_viewer_views.qr_kodu, name="ekran_qr"),
    path("", include("takip.urls")),
]

# Ekran modülünün medyası ayrı kökte durur (kalıcı disk); onu da servis et.
urlpatterns += [
    re_path(
        r"^ekran-medya/(?P<path>.*)$",
        ekran_viewer_views.ekran_medyasi,
        name="ekran_medyasi",
    ),
    path(
        "akilli-tahta-medya/<int:pk>/",
        akilli_tahta_viewer_views.akilli_tahta_medyasi,
        name="akilli_tahta_medyasi",
    ),
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