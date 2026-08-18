"""Özelleştirilmiş giriş — veli / talebe / personel yönlendirmesi."""

from django.contrib.auth import views as auth_views
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from takip.ogretmen_service import (
    ogretmen_giris_url_adi,
    ogretmen_paneli_kullanicisi_mi,
)
from takip.rate_limit import (
    basarili_giris_sifirla,
    basarisiz_deneme_kaydet,
    limit_asildi_mi,
)
from takip.talebe_panel_service import kullanici_talebe_mi
from takip.veli_service import kullanici_veli_mi

RATE_LIMIT_MESAJI = (
    "Çok fazla başarısız giriş denemesi yapıldı. "
    "Lütfen birkaç dakika sonra tekrar deneyin."
)


class PanelLoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        kullanici_adi = (request.POST.get("username") or "").strip()

        if limit_asildi_mi(request, kullanici_adi):
            self._rate_limited = True
            form = self.get_form()
            form.is_valid()
            form.add_error(None, RATE_LIMIT_MESAJI)
            return self.form_invalid(form)

        self._rate_limited = False
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        basarili_giris_sifirla(self.request, form.cleaned_data.get("username", ""))
        return super().form_valid(form)

    def form_invalid(self, form):
        if not getattr(self, "_rate_limited", False):
            kullanici_adi = (self.request.POST.get("username") or "").strip()
            basarisiz_deneme_kaydet(self.request, kullanici_adi)
        return super().form_invalid(form)

    def get_success_url(self):
        user = self.request.user
        if kullanici_veli_mi(user):
            return reverse("veli_dashboard")
        if kullanici_talebe_mi(user):
            return reverse("talebe_dashboard")
        if ogretmen_paneli_kullanicisi_mi(user):
            return reverse(ogretmen_giris_url_adi(user))
        return reverse("dashboard")
