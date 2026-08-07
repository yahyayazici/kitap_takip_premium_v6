"""View yetki decorator'ları."""

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from .service import can


def require_permission(modul_kod: str, islem_kod: str = "view"):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if can(request.user, modul_kod, islem_kod):
                return view_func(request, *args, **kwargs)

            messages.error(
                request,
                "Bu işlem için yetkiniz bulunmuyor.",
            )
            if request.user.is_authenticated:
                return redirect("dashboard")
            return HttpResponseForbidden("Yetkiniz yok.")

        return _wrapped

    return decorator
