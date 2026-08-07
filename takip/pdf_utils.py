"""
PDF üretim yardımcıları.

Sınav karneleri: HTML şablon → WeasyPrint (birincil) → xhtml2pdf (yedek)
Okuma raporu: HTML şablon → WeasyPrint (birincil) → xhtml2pdf (yedek)
"""

from __future__ import annotations

import logging
import os
import platform
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger(__name__)

_weasyprint_html = None
_weasyprint_checked = False
_reportlab_fonts_ready = False
_pdf_turkish_font_path: Path | None = None

_XHTML2PDF_UNSUPPORTED_AT_RULES = (
    "@bottom-left",
    "@bottom-right",
    "@bottom-center",
    "@top-left",
    "@top-right",
    "@top-center",
)


def _pdf_turkish_font_file() -> Path:
    global _pdf_turkish_font_path

    if _pdf_turkish_font_path is None:
        _pdf_turkish_font_path = (
            Path(settings.BASE_DIR) / "static" / "fonts" / "PdfTurkish.ttf"
        )

    return _pdf_turkish_font_path


def _sanitize_html_for_xhtml2pdf(html_string: str) -> str:
    """xhtml2pdf'in desteklemediği WeasyPrint @page margin box kurallarını temizler."""
    sanitized = html_string

    for rule in _XHTML2PDF_UNSUPPORTED_AT_RULES:
        sanitized = re.sub(
            rf"{re.escape(rule)}\s*\{{[^}}]*\}}",
            "",
            sanitized,
            flags=re.DOTALL,
        )

    return sanitized


def _xhtml2pdf_link_callback(uri: str, rel: str) -> str:
    if uri.startswith("file:"):
        return unquote(urlparse(uri).path)

    path = Path(uri)
    if path.is_file():
        return str(path)

    return uri


def _prepare_html_for_xhtml2pdf(html_string: str) -> str:
    """
    xhtml2pdf için HTML hazırlar.
    PdfTurkish.ttf @font-face ile gömülür — Türkçe karakterler (İ, ı, ş, ğ) düzgün çıkar.
    """
    font_path = _pdf_turkish_font_file()

    if not font_path.is_file():
        logger.error("PDF Türkçe font dosyası bulunamadı: %s", font_path)
        register_reportlab_turkish_fonts()
    else:
        font_uri = font_path.resolve().as_uri()
        font_css = f"""
/* xhtml2pdf Türkçe font */
@font-face {{
    font-family: "PdfTurkish";
    src: url("{font_uri}");
}}
body, table, td, th, div, p, span, small, section {{
    font-family: PdfTurkish, sans-serif;
}}
"""
        prepared = _sanitize_html_for_xhtml2pdf(html_string)
        prepared = prepared.replace(
            '"DejaVu Sans", Arial, sans-serif',
            "PdfTurkish, sans-serif",
        )
        prepared = prepared.replace('"DejaVu Sans"', "PdfTurkish")

        if "<style>" in prepared:
            prepared = prepared.replace("<style>", f"<style>{font_css}", 1)
        else:
            prepared = prepared.replace(
                "</head>",
                f"<style>{font_css}</style></head>",
                1,
            )

        return prepared

    prepared = _sanitize_html_for_xhtml2pdf(html_string)
    prepared = prepared.replace('"DejaVu Sans"', "Vera")
    if "<style>" in prepared:
        prepared = prepared.replace(
            "<style>",
            '<style>body{font-family:Vera,sans-serif;}',
            1,
        )
    return prepared


def _configure_weasyprint_library_path() -> None:
    """macOS Homebrew: GLib/Pango kütüphanelerinin bulunması için library path ayarlar."""
    if platform.system() != "Darwin":
        return

    for prefix in ("/opt/homebrew", "/usr/local"):
        lib_dir = Path(prefix) / "lib"
        if not lib_dir.is_dir():
            continue

        current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        lib_str = str(lib_dir)
        if lib_str not in current.split(":"):
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
                f"{lib_str}:{current}" if current else lib_str
            )
        break


def get_weasyprint_html():
    """WeasyPrint HTML sınıfını lazy-load eder; yoksa None döner."""
    global _weasyprint_html, _weasyprint_checked

    if _weasyprint_checked:
        return _weasyprint_html

    _weasyprint_checked = True

    _configure_weasyprint_library_path()

    try:
        from weasyprint import HTML

        _weasyprint_html = HTML
        logger.info("WeasyPrint kullanılabilir.")
    except (ImportError, OSError) as exc:
        logger.warning("WeasyPrint kullanılamıyor: %s", exc)
        _weasyprint_html = None

    return _weasyprint_html


def html_to_pdf(html_string: str, base_url: str = "/") -> bytes | None:
    """
    HTML metninden PDF üretir.
    Önce WeasyPrint, başarısız olursa xhtml2pdf dener.
    """
    html_cls = get_weasyprint_html()

    if html_cls is not None:
        try:
            return html_cls(
                string=html_string,
                base_url=base_url,
            ).write_pdf()
        except Exception:
            logger.exception("WeasyPrint PDF üretimi başarısız.")

    try:
        from xhtml2pdf import pisa
    except ImportError:
        logger.error("xhtml2pdf yüklü değil; HTML tabanlı PDF üretilemedi.")
        return None

    buffer = BytesIO()
    try:
        result = pisa.CreatePDF(
            _prepare_html_for_xhtml2pdf(html_string),
            dest=buffer,
            encoding="utf-8",
            link_callback=_xhtml2pdf_link_callback,
        )
    except Exception:
        logger.exception("xhtml2pdf PDF üretimi başarısız.")
        return None

    if result.err:
        logger.error("xhtml2pdf hata kodu: %s", result.err)
        return None

    return buffer.getvalue()


def pdf_engine_status() -> str:
    """Kullanılabilir PDF motorunu döndürür (log/diagnostic için)."""
    if get_weasyprint_html() is not None:
        return "weasyprint"

    try:
        import xhtml2pdf  # noqa: F401
    except ImportError:
        return "none"

    return "xhtml2pdf"


def make_pdf_response(pdf_bytes: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def pdf_error_response(message: str, status: int = 500) -> HttpResponse:
    logger.error("PDF istemciye hata döndürüldü: %s", message)
    return HttpResponse(
        message,
        status=status,
        content_type="text/plain; charset=utf-8",
    )


def register_reportlab_turkish_fonts() -> tuple[str, str]:
    """
    ReportLab için Türkçe destekli font kaydeder.
    Önce PdfTurkish.ttf, yoksa reportlab Vera fontları.
    """
    global _reportlab_fonts_ready

    regular = "PdfTurkish"
    bold = "PdfTurkish-Bold"

    if _reportlab_fonts_ready:
        return regular, bold

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    turkish_font = _pdf_turkish_font_file()

    if turkish_font.is_file():
        pdfmetrics.registerFont(TTFont(regular, str(turkish_font)))
        pdfmetrics.registerFont(TTFont(bold, str(turkish_font)))
    else:
        import reportlab

        fonts_dir = Path(reportlab.__file__).resolve().parent / "fonts"
        regular = "Vera"
        bold = "Vera-Bold"
        pdfmetrics.registerFont(TTFont(regular, str(fonts_dir / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont(bold, str(fonts_dir / "VeraBd.ttf")))

    _reportlab_fonts_ready = True
    return regular, bold
