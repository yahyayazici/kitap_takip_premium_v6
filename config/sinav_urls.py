"""``sinav.cinilisarayproje.com`` için kök URL yapılandırması.

Ana panelin (``config.urls``) hiçbir adresi burada tanımlı değildir.
Okunan sonuçlar bu uygulamanın kendi tablolarında kalır.
"""

from django.urls import include, path

from takip.bootstrap_views import health_check

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("", include("sinav_okuma.urls")),
]
