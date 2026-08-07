"""Canlı ortamda (Render Free) admin şifresi ve temel veri — bootstrap."""

from __future__ import annotations

import os

from django.contrib.auth.models import User
from django.core.management import call_command
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET


def _bootstrap_key_ok(request) -> bool:
    expected_key = os.environ.get("ADMIN_BOOTSTRAP_KEY", "").strip()
    if not expected_key:
        return False
    return request.GET.get("key", "").strip() == expected_key


@require_GET
def bootstrap_admin(request):
    """
    ADMIN_BOOTSTRAP_KEY ve ADMIN_PASSWORD ortam değişkenleri tanımlıysa,
    doğru key ile admin şifresini sıfırlar.

    Örnek:
    /bootstrap-admin/?key=GIZLI_ANAHTAR
    """
    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"

    if not os.environ.get("ADMIN_BOOTSTRAP_KEY", "").strip() or not password:
        return HttpResponseForbidden(
            "ADMIN_BOOTSTRAP_KEY ve ADMIN_PASSWORD ortam değişkenleri tanımlı değil."
        )

    if not _bootstrap_key_ok(request):
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


@require_GET
def bootstrap_setup(request):
    """
    Roller, modüller, dini ders müfredatı ve temel tanımları yükler.

    Örnek:
    /bootstrap-setup/?key=GIZLI_ANAHTAR
    """
    if not os.environ.get("ADMIN_BOOTSTRAP_KEY", "").strip():
        return HttpResponseForbidden("ADMIN_BOOTSTRAP_KEY tanımlı değil.")

    if not _bootstrap_key_ok(request):
        return HttpResponseForbidden("Geçersiz anahtar.")

    call_command("seed_wave0")
    call_command("seed_dini_ders_mufredat")

    return HttpResponse(
        "Tamam — roller, modüller, dini ders müfredatı ve temel tanımlar yüklendi. "
        "Yönetim merkezini yenileyin.",
        content_type="text/plain; charset=utf-8",
    )
