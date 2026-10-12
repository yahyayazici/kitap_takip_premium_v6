"""Optik paneline kimlerin girebileceği.

Ana sitede (cinilisarayproje.com) veli ve talebe hesapları da aynı kullanıcı
tablosundadır; bu yüzden giriş yapmış olmak yetmez. `OKUMA_ERISIM` ayarı bir
fonksiyon yoludur (ör. ana sitenin deneme modülü yetkisi). Ayar yoksa yalnız
personel (`is_staff`) girer. Süper kullanıcılar her zaman girer.
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.module_loading import import_string


def erisimi_var(user) -> bool:
    if not (user.is_authenticated and user.is_active):
        return False
    if user.is_superuser:
        return True
    yol = getattr(settings, "OKUMA_ERISIM", None)
    if yol:
        return bool(import_string(yol)(user))
    return user.is_staff


def yetki_yok(request):
    return render(request, "okuma/yetki_yok.html", status=403)


def erisim_gerekli(view):
    @login_required
    @wraps(view)
    def sarici(request, *args, **kwargs):
        if not erisimi_var(request.user):
            return yetki_yok(request)
        return view(request, *args, **kwargs)

    return sarici


def kullanici_yonetimi_acik() -> bool:
    """Ana siteye bağlıyken kullanıcılar ana siteden yönetilir; bu sayfa kapanır."""
    return getattr(settings, "OKUMA_KULLANICI_YONETIMI", True)
