"""Özelleştirilmiş giriş — veli / talebe / personel yönlendirmesi."""

from django.contrib.auth import views as auth_views
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from takip.ogretmen_service import ogretmen_paneli_kullanicisi_mi
from takip.talebe_panel_service import kullanici_talebe_mi
from takip.veli_service import kullanici_veli_mi


class PanelLoginView(auth_views.LoginView):
    template_name = "registration/login.html"

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        user = self.request.user
        if kullanici_veli_mi(user):
            return reverse("veli_dashboard")
        if kullanici_talebe_mi(user):
            return reverse("talebe_dashboard")
        if ogretmen_paneli_kullanicisi_mi(user):
            return reverse("ogretmen_dashboard")
        return reverse("dashboard")
