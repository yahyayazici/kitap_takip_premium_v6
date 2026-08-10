"""PWA — ana ekrana ekleme (manifest + service worker + ikon servisi)."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from config.branding import (
    PANEL_MOBILE_SHORT,
    PANEL_NAME,
    PANEL_TAGLINE,
)

PWA_THEME_COLOR = "#071b3a"
PWA_VERSION = "v9"
PWA_ID = f"/?pwa={PWA_VERSION}"

_ICON_FILES = {
    180: "app-launcher-v5-180.png",
    192: "app-launcher-v5-192.png",
    512: "app-launcher-v5-512.png",
}


def _no_cache(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


def _icon_bytes(size: int) -> bytes:
    name = _ICON_FILES[size]
    path = settings.BASE_DIR / "static" / "images" / name
    return path.read_bytes()


@require_GET
def web_manifest(request):
    response = JsonResponse(
        {
            "id": PWA_ID,
            "name": PANEL_NAME,
            "short_name": PANEL_MOBILE_SHORT,
            "description": PANEL_TAGLINE,
            "start_url": "/giris/?source=pwa",
            "scope": "/",
            "display": "standalone",
            "orientation": "any",
            "theme_color": PWA_THEME_COLOR,
            "background_color": "#0a1f4a",
            "lang": "tr",
            "icons": [
                {
                    "src": f"/pwa/icon-192.png?{PWA_VERSION}",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": f"/pwa/icon-512.png?{PWA_VERSION}",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
            ],
        },
        json_dumps_params={"ensure_ascii": False},
        content_type="application/manifest+json",
    )
    return _no_cache(response)


@require_GET
def pwa_icon_180(request):
    return _no_cache(HttpResponse(_icon_bytes(180), content_type="image/png"))


@require_GET
def pwa_icon_192(request):
    return _no_cache(HttpResponse(_icon_bytes(192), content_type="image/png"))


@require_GET
def pwa_icon_512(request):
    return _no_cache(HttpResponse(_icon_bytes(512), content_type="image/png"))


@require_GET
def service_worker(request):
    sw_path = settings.BASE_DIR / "static" / "sw.js"
    body = sw_path.read_text(encoding="utf-8")
    response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    return _no_cache(response)


def _panel_giris_hedefi(user) -> str:
    from takip.ogretmen_service import ogretmen_paneli_kullanicisi_mi
    from takip.talebe_panel_service import kullanici_talebe_mi
    from takip.veli_service import kullanici_veli_mi

    if kullanici_veli_mi(user):
        return reverse("veli_dashboard")
    if kullanici_talebe_mi(user):
        return reverse("talebe_dashboard")
    if ogretmen_paneli_kullanicisi_mi(user):
        return reverse("ogretmen_dashboard")
    return reverse("dashboard")


@ensure_csrf_cookie
@require_GET
def pwa_baslat(request):
    """Ana ekran kısayolu — yalnızca GET; oturum varsa panele, yoksa girişe."""
    if request.user.is_authenticated:
        return redirect(_panel_giris_hedefi(request.user))
    return redirect(f"{reverse('login')}?source=pwa")


def csrf_failure(request, reason=""):
    """PWA / mobil geri yüklemede POST tekrarı → girişe yönlendir."""
    if request.method == "POST":
        return redirect(f"{reverse('login')}?source=pwa&csrf=1")
    return redirect(reverse("login"))
