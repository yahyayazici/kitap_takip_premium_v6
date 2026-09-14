"""Production middleware helpers."""

from __future__ import annotations

import time

from django.conf import settings
from django.http import HttpResponsePermanentRedirect

_SESSION_SLIDE_SECONDS = 6 * 60 * 60


class SlideSessionMiddleware:
    """Oturumu her tıklamada yazmak yerine birkaç saatte bir kaydır."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        session = getattr(request, "session", None)
        if not session or not session.session_key:
            return response
        last = int(session.get("_slide_at") or 0)
        now = int(time.time())
        if now - last >= _SESSION_SLIDE_SECONDS:
            session["_slide_at"] = now
        return response


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
