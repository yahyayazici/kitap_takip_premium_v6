"""``ekran.cinilisarayproje.com`` için kök URL yapılandırması.

Bu alan adında kök adres doğrudan televizyon görüntüleyicisidir; yönetim
ekranları ``/yonetim/`` altındadır. Ana panelin (``config.urls``) adresleri
burada tanımlı değildir — iki yüzey birbirine karışmaz.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve

from takip import ekran_viewer_views
from takip.bootstrap_views import health_check
from takip.ekran_viewer_views import VARLIK_SURUMU

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("", include("takip.ekran_viewer_urls")),
    path("yonetim/", include("takip.ekran_urls")),
    path(
        "giris/",
        auth_views.LoginView.as_view(
            template_name="ekran/giris.html",
            # Statik varlık sürümü tek kaynaktan gelir (bkz. ekran_viewer_views).
            extra_context={"varlik_surumu": VARLIK_SURUMU},
        ),
        name="login",
    ),
    path("cikis/", auth_views.LogoutView.as_view(next_page="ekran:viewer"), name="logout"),
]

urlpatterns += [
    re_path(
        r"^ekran-medya/(?P<path>.*)$",
        ekran_viewer_views.ekran_medyasi,
        name="ekran_medyasi",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
