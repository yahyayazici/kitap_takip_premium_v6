"""``optik.cinilisarayproje.com`` için kök URL yapılandırması (deneme okuma ve analiz).

Ana panelin (``config.urls``) adresleri burada tanımlı değildir. Giriş ana
sitenin kullanıcılarıyla yapılır; erişim ``OKUMA_ERISIM`` ile sınırlıdır.
Oturum çerezi host'a özgü olduğundan ana site oturumunu etkilemez.
"""

from django.contrib.auth import views as auth_views
from django.urls import include, path

from takip.bootstrap_views import health_check

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path(
        "giris/",
        auth_views.LoginView.as_view(template_name="okuma/giris.html", next_page="deneme_listesi"),
        name="login",
    ),
    path("cikis/", auth_views.LogoutView.as_view(next_page="login"), name="cikis"),
    path("", include("okuma.urls")),
]
