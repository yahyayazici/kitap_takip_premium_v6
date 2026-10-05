"""``ekitap.cinilisarayproje.com`` için kök URL yapılandırması.

Ana panelin (``config.urls``) hiçbir adresi burada tanımlı değildir; yalnızca
e-kitap görüntüleyicisi ve onun yönetim ekranları vardır.
"""

from django.urls import include, path

from takip.bootstrap_views import health_check

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("", include("takip.ekitap_urls")),
]
