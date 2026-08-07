"""Production middleware helpers."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class CanonicalHostMiddleware:
    """onrender.com isteklerini özel domain'e yönlendirir (CANONICAL_HOST tanımlıysa)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonical = getattr(settings, "CANONICAL_HOST", "").strip().lower()
        if canonical:
            host = request.get_host().split(":")[0].lower()
            if host.endswith(".onrender.com") and host != canonical:
                return HttpResponsePermanentRedirect(
                    f"https://{canonical}{request.get_full_path()}"
                )
        return self.get_response(request)
