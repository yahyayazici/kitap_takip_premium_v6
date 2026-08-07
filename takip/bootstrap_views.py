"""Canlı ortamda (Render Free) admin şifresi — tek seferlik bootstrap."""

from __future__ import annotations

import os

from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET


@require_GET
def bootstrap_admin(request):
    """
    ADMIN_BOOTSTRAP_KEY ve ADMIN_PASSWORD ortam değişkenleri tanımlıysa,
    doğru key ile admin şifresini sıfırlar.

    Örnek:
    /bootstrap-admin/?key=GIZLI_ANAHTAR
    """
    expected_key = os.environ.get("ADMIN_BOOTSTRAP_KEY", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"

    if not expected_key or not password:
        return HttpResponseForbidden(
            "ADMIN_BOOTSTRAP_KEY ve ADMIN_PASSWORD ortam değişkenleri tanımlı değil."
        )

    if request.GET.get("key", "").strip() != expected_key:
        return HttpResponseForbidden("Geçersiz anahtar.")

    user, created = User.objects.get_or_create(username=username)
    user.is_active = True
    user.is_staff = True
    user.is_superuser = True
    user.set_password(password)
    user.save()

    action = "oluşturuldu" if created else "güncellendi"
    return HttpResponse(
        f"Tamam — '{username}' kullanıcısı {action}. "
        f"Şimdi /giris/ sayfasından giriş yapabilirsiniz.",
        content_type="text/plain; charset=utf-8",
    )
