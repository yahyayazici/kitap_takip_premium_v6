"""PWA — ana ekrana ekleme (manifest + service worker)."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.templatetags.static import static
from django.views.decorators.http import require_GET

from config.branding import (
    PANEL_MOBILE_SHORT,
    PANEL_NAME,
    PANEL_TAGLINE,
)

PWA_THEME_COLOR = "#071b3a"


@require_GET
def web_manifest(request):
    icon_192 = static("images/cinili-saray-pwa-icon-192.png")
    icon_512 = static("images/cinili-saray-pwa-icon.png")
    return JsonResponse(
        {
            "name": PANEL_NAME,
            "short_name": PANEL_MOBILE_SHORT,
            "description": PANEL_TAGLINE,
            "start_url": "/giris/",
            "scope": "/",
            "display": "standalone",
            "orientation": "any",
            "theme_color": PWA_THEME_COLOR,
            "background_color": "#0a1f4a",
            "lang": "tr",
            "icons": [
                {
                    "src": icon_192,
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": icon_512,
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
            ],
        },
        json_dumps_params={"ensure_ascii": False},
        content_type="application/manifest+json",
    )


@require_GET
def service_worker(request):
    sw_path = settings.BASE_DIR / "static" / "sw.js"
    body = sw_path.read_text(encoding="utf-8")
    response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
