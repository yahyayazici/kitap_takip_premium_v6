"""Canlı ortamda (Render Free) temel veri — bootstrap.

Admin şifresi sıfırlama artık HTTP üzerinden yapılamaz (eski
/bootstrap-admin/ endpoint'i kaldırıldı — anahtarı ele geçiren herkes
admin hesabını devralabiliyordu). Admin şifresi gerekirse Render Shell
üzerinden `python manage.py reset_admin --password ...` çalıştırın.
"""

from __future__ import annotations

import io
import logging
import os

from django.core.management import call_command
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def health_check(request):
    if request.GET.get("diag") != "pdf":
        return HttpResponse("ok", content_type="text/plain")

    from takip.pdf_utils import last_pdf_error, pdf_engine_status, probe_weasyprint

    ok, msg = probe_weasyprint()
    lines = [
        f"engine={pdf_engine_status()}",
        f"weasyprint={'ok' if ok else 'fail'}",
        f"detail={msg}",
    ]
    err = last_pdf_error()
    if err:
        lines.append(f"last_error={err}")
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")


def _bootstrap_key_ok(request) -> bool:
    expected_key = os.environ.get("ADMIN_BOOTSTRAP_KEY", "").strip()
    if not expected_key:
        return False
    return request.GET.get("key", "").strip() == expected_key


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

    out = io.StringIO()
    try:
        call_command("seed_wave0", stdout=out)
    except Exception:
        # Ayrıntılı hata (traceback) sunucu logunda kalır; HTTP yanıtına
        # asla stack trace/iç bilgi sızdırılmaz (bilgi sızıntısı riski).
        logger.exception("bootstrap_setup: seed_wave0 çalıştırılamadı")
        return HttpResponse(
            "Bootstrap-setup başarısız (seed_wave0). Ayrıntı için sunucu "
            "loglarına bakın.\n\n"
            f"{out.getvalue()}\n"
            "İpucu: Render → Environment → RUN_SEED_WAVE0=true ekleyip "
            "Manual Deploy yapın; seed build aşamasında çalışır (zaman aşımı olmaz).",
            content_type="text/plain; charset=utf-8",
            status=500,
        )

    return HttpResponse(
        "Tamam — roller, modüller, dini ders müfredatı ve temel tanımlar yüklendi.\n\n"
        f"{out.getvalue()}\n"
        "Yönetim merkezini yenileyin.",
        content_type="text/plain; charset=utf-8",
    )
