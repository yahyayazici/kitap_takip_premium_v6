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
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

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


def _static_roots() -> list[Path]:
    roots = [Path(settings.BASE_DIR) / "static"]
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        roots.append(Path(static_root))
    for extra in getattr(settings, "STATICFILES_DIRS", []):
        roots.append(Path(extra))
    return roots


def _path_from_file_uri(uri: str) -> Path:
    """file:///C:/... URI'sini Windows/POSIX dosya yoluna çevirir."""
    parsed = urlparse(uri)
    # url2pathname('/C:/Users/...') → 'C:\\Users\\...' (Windows)
    return Path(url2pathname(unquote(parsed.path)))


def _resolve_static_uri(uri: str) -> Path | None:
    """'/static/...' veya tam URL içindeki static yolu dosya sistemine çevirir."""
    if not uri:
        return None

    raw = unquote(uri.strip())
    if raw.startswith("file:"):
        path = _path_from_file_uri(raw)
        return path if path.is_file() else None

    # Zaten mutlak dosya yolu olabilir
    as_path = Path(raw)
    if as_path.is_file():
        return as_path

    parsed = urlparse(raw)
    path_part = parsed.path if parsed.scheme else raw
    path_part = path_part.replace("\\", "/")

    # file:// URI içindeki /static/ yanlışlıkla yeniden yakalanmasın
    if ":" in path_part and path_part.index(":") < 3:
        return None

    marker = "/static/"
    idx = path_part.find(marker)
    if idx >= 0:
        relative = path_part[idx + len(marker) :]
    elif path_part.startswith("static/"):
        relative = path_part[len("static/") :]
    else:
        return None

    relative = relative.lstrip("/")
    for root in _static_roots():
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def _rewrite_static_urls_to_file(html_string: str) -> str:
    """/static/... yollarını file:// URI yapar — HTTP self-fetch deadlock önler."""

    def _to_file_uri(match: re.Match[str]) -> str:
        uri = match.group(0)
        path = _resolve_static_uri(uri)
        if path is None:
            return uri
        return path.resolve().as_uri()

    return re.sub(
        r"(?<![A-Za-z0-9:])(?:https?://[^\"'\s]+)?/static/[^\s\"')]+",
        _to_file_uri,
        html_string,
    )


def _local_pdf_base_url() -> str:
    return Path(settings.BASE_DIR).resolve().as_uri() + "/"


def _weasyprint_url_fetcher(url: str, timeout=10, ssl_context=None, **kwargs):
    """file:// ve data: kaynaklarına izin ver — http(s) self-fetch engellenir."""
    from weasyprint import default_url_fetcher

    if url.startswith("file:") or url.startswith("data:"):
        return default_url_fetcher(
            url, timeout=timeout, ssl_context=ssl_context, **kwargs
        )
    raise ValueError(f"PDF ağ erişimi engellendi: {url}")


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

    # xhtml2pdf bazı unicode content değerlerini parse edemiyor
    sanitized = re.sub(
        r"\.pdf-karne\s+\.analiz-ton-\w+\s+\.eval-title::before\s*\{[^}]*\}",
        "",
        sanitized,
        flags=re.DOTALL,
    )
    sanitized = re.sub(
        r"\.analiz-ton-\w+\s+\.eval-title::before\s*\{[^}]*\}",
        "",
        sanitized,
        flags=re.DOTALL,
    )

    # xhtml2pdf calc() desteklemez
    sanitized = sanitized.replace("width: calc(100% + 8px);", "width: 100%;")
    sanitized = sanitized.replace("width:calc(100% + 8px);", "width:100%;")

    return _rewrite_static_urls_to_file(sanitized)


def _xhtml2pdf_link_callback(uri: str, rel: str) -> str:
    if uri.startswith("file:"):
        path = _path_from_file_uri(uri)
        return str(path)

    resolved = _resolve_static_uri(uri)
    if resolved is not None:
        return str(resolved)

    path = Path(uri)
    if path.is_file():
        return str(path)

    return uri


def _ensure_xhtml2pdf_windows_tmp_patch() -> None:
    """
    Windows'ta NamedTemporaryFile açıkken aynı yolu yeniden açmak PermissionError verir.
    xhtml2pdf font/görsel için temp kopya oluştururken delete=False + close kullanırız.
    """
    if os.name != "nt":
        return

    from xhtml2pdf import files as xhtml_files

    if getattr(xhtml_files.BaseFile, "_cinili_win_tmp_patched", False):
        return

    def get_named_tmp_file(self):
        data = self.get_data()
        tmp_file = tempfile.NamedTemporaryFile(suffix=self.suffix, delete=False)
        name = tmp_file.name
        try:
            if data:
                tmp_file.write(data)
                tmp_file.flush()
        finally:
            tmp_file.close()

        class _ClosedNamedTmp:
            def __init__(self, path: str) -> None:
                self.name = path

            def close(self) -> None:
                try:
                    Path(self.name).unlink(missing_ok=True)
                except OSError:
                    pass

        wrapper = _ClosedNamedTmp(name)
        xhtml_files.files_tmp.append(wrapper)
        if self.path is None:
            self.path = name
        return wrapper

    xhtml_files.BaseFile.get_named_tmp_file = get_named_tmp_file  # type: ignore[method-assign]
    xhtml_files.BaseFile._cinili_win_tmp_patched = True  # type: ignore[attr-defined]


def _prepare_html_for_xhtml2pdf(html_string: str) -> str:
    """
    xhtml2pdf için HTML hazırlar.
    PdfTurkish.ttf @font-face ile gömülür — Türkçe karakterler (İ, ı, ş, ğ) düzgün çıkar.
    """
    font_path = _pdf_turkish_font_file()
    prepared = _sanitize_html_for_xhtml2pdf(html_string)

    # xhtml2pdf Poppins @font-face + numeric font-weight bozar → PdfTurkish kullan
    prepared = re.sub(
        r"@font-face\s*\{[^}]*font-family:\s*[\"']Poppins[\"'][^}]*\}",
        "",
        prepared,
        flags=re.DOTALL | re.IGNORECASE,
    )
    prepared = prepared.replace('"Poppins"', "PdfTurkish")
    prepared = prepared.replace("'Poppins'", "PdfTurkish")
    prepared = prepared.replace("Poppins,", "PdfTurkish,")
    prepared = prepared.replace('"DejaVu Sans", Arial, sans-serif', "PdfTurkish, sans-serif")
    prepared = prepared.replace('"DejaVu Sans"', "PdfTurkish")

    register_reportlab_turkish_fonts()

    if font_path.is_file():
        font_src = font_path.resolve().as_uri()
        font_css = f"""
/* xhtml2pdf Türkçe font */
@font-face {{
    font-family: PdfTurkish;
    src: url("{font_src}");
}}
body, table, td, th, div, p, span, small, section, h1, h2, h3 {{
    font-family: PdfTurkish, Arial, sans-serif;
}}
"""
    else:
        logger.error("PDF Türkçe font dosyası bulunamadı: %s", font_path)
        prepared = prepared.replace("PdfTurkish", "Vera")
        font_css = """
body, table, td, th, div, p, span, small, section, h1, h2, h3 {
    font-family: Vera, Arial, sans-serif;
}
"""

    if "<style>" in prepared:
        prepared = prepared.replace("<style>", f"<style>{font_css}", 1)
    else:
        prepared = prepared.replace(
            "</head>",
            f"<style>{font_css}</style></head>",
            1,
        )
    return prepared


def _configure_weasyprint_library_path() -> None:
    """WeasyPrint native kütüphaneleri (Pango/GLib) için arama yollarını ayarlar."""
    system = platform.system()

    if system == "Darwin":
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
        return

    if system != "Windows":
        return

    candidates: list[Path] = []
    existing = os.environ.get("WEASYPRINT_DLL_DIRECTORIES", "")
    if existing:
        candidates.extend(Path(p) for p in existing.split(os.pathsep) if p.strip())

    candidates.extend(
        [
            Path(r"C:\msys64\mingw64\bin"),
            Path(r"C:\msys64\ucrt64\bin"),
            Path(os.environ.get("MSYS2_PATH", "")) / "mingw64" / "bin",
            Path(r"C:\Program Files\GTK3-Runtime Win64\bin"),
        ]
    )

    dll_dirs: list[str] = []
    for path in candidates:
        if not path or not path.is_dir():
            continue
        # GLib/Pango var mı?
        if not any(path.glob("libgobject-2.0-0.dll")) and not any(
            path.glob("*gobject-2.0-0*.dll")
        ):
            continue
        resolved = str(path.resolve())
        if resolved not in dll_dirs:
            dll_dirs.append(resolved)

    if not dll_dirs:
        return

    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = os.pathsep.join(dll_dirs)

    # Python 3.8+ Windows DLL araması
    for dll_dir in dll_dirs:
        try:
            os.add_dll_directory(dll_dir)
        except (OSError, AttributeError):
            pass
        path_env = os.environ.get("PATH", "")
        if dll_dir.lower() not in path_env.lower().split(os.pathsep):
            os.environ["PATH"] = dll_dir + os.pathsep + path_env


def get_weasyprint_html():
    """WeasyPrint HTML sınıfını lazy-load eder; yoksa None döner."""
    global _weasyprint_html, _weasyprint_checked

    if _weasyprint_checked:
        return _weasyprint_html

    _weasyprint_checked = True

    _configure_weasyprint_library_path()

    try:
        from weasyprint import HTML

        # Windows'ta DLL eksikse import geçer ama ilk kullanımda patlar;
        # gerçek yazımda yakalanır ve xhtml2pdf'e düşülür.
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

    base_url HTTP olsa bile yerel dosya tabanı kullanılır; aksi halde Render'da
    worker kendini bekleyerek (static fetch) kilitlenebilir.
    """
    del base_url  # bilinçli: ağ self-fetch engeli
    global _weasyprint_html
    html_cls = get_weasyprint_html()
    local_html = _rewrite_static_urls_to_file(html_string)
    local_base = _local_pdf_base_url()

    if html_cls is not None:
        try:
            try:
                document = html_cls(
                    string=local_html,
                    base_url=local_base,
                    url_fetcher=_weasyprint_url_fetcher,
                )
            except TypeError:
                document = html_cls(string=local_html, base_url=local_base)
            return document.write_pdf()
        except Exception as exc:
            logger.warning("WeasyPrint PDF üretimi başarısız, xhtml2pdf deneniyor: %s", exc)
            _weasyprint_html = None

    try:
        from xhtml2pdf import pisa
    except ImportError:
        logger.error("xhtml2pdf yüklü değil; HTML tabanlı PDF üretilemedi.")
        return None

    _ensure_xhtml2pdf_windows_tmp_patch()

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


def _safe_download_filename(
    filename: str, *, default: str = "dosya.pdf"
) -> tuple[str, str]:
    """Tarayıcı/uyumluluk için ASCII dosya adı + UTF-8 encoded ad."""
    from urllib.parse import quote

    raw = (filename or default).strip() or default
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-") or default
    if not ascii_name.lower().endswith(".pdf") and raw.lower().endswith(".pdf"):
        ascii_name += ".pdf"
    return ascii_name, quote(raw)


def make_pdf_response(pdf_bytes: bytes, filename: str) -> HttpResponse:
    ascii_name, utf8_name = _safe_download_filename(filename)
    # octet-stream: tarayıcı PDF panelinde açmak yerine indirmeyi zorlar
    response = HttpResponse(pdf_bytes, content_type="application/octet-stream")
    response["Content-Disposition"] = (
        f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response


# —— Sayfa boyutu tercihi (A4/A3 × dikey/yatay) ——

PDF_SAYFA_VARSAYILAN = "a4_portrait"

PDF_SAYFA_SECENEKLERI: tuple[tuple[str, str, str], ...] = (
    ("a4_portrait", "A4 dikey", "A4 portrait"),
    ("a4_landscape", "A4 yatay", "A4 landscape"),
    ("a3_portrait", "A3 dikey", "A3 portrait"),
    ("a3_landscape", "A3 yatay", "A3 landscape"),
)

_PDF_SAYFA_MAP = {kod: (etiket, css) for kod, etiket, css in PDF_SAYFA_SECENEKLERI}


def coz_pdf_sayfa(kaynak=None, *, default: str = PDF_SAYFA_VARSAYILAN) -> dict:
    """
    Request veya kod'dan PDF sayfa boyutunu çözer.
    Tercih yoksa A4 dikey.
    Query: ?sayfa=a4_portrait|a4_landscape|a3_portrait|a3_landscape
    Eski parametreler: format/boyut=a4|a3 + orientation=portrait|landscape
    """
    kod = default
    if kaynak is None:
        pass
    elif isinstance(kaynak, str):
        kod = (kaynak or "").strip().lower() or default
    else:
        # HttpRequest
        get = getattr(kaynak, "GET", None)
        if get is not None:
            ham = (get.get("sayfa") or get.get("pdf_sayfa") or "").strip().lower()
            if ham:
                kod = ham
            else:
                # Geriye uyum: boyut=a4|a3 + orientation=portrait|landscape
                # Not: format=pdf gibi export bayraklarını boyut sanma
                boyut = (get.get("boyut") or "").strip().lower()
                yon = (get.get("orientation") or get.get("yon") or "").strip().lower()
                if boyut in {"a4", "a3"} or yon in {"portrait", "landscape", "dikey", "yatay"}:
                    if boyut not in {"a4", "a3"}:
                        boyut = "a4"
                    if yon in {"landscape", "yatay"}:
                        yon = "landscape"
                    else:
                        yon = "portrait"
                    kod = f"{boyut}_{yon}"

    if kod not in _PDF_SAYFA_MAP:
        # a4-portrait / a4 dikey gibi varyantlar
        kod = (
            kod.replace("-", "_")
            .replace(" ", "_")
            .replace("dikey", "portrait")
            .replace("yatay", "landscape")
        )
    if kod not in _PDF_SAYFA_MAP:
        kod = default if default in _PDF_SAYFA_MAP else PDF_SAYFA_VARSAYILAN

    etiket, size_css = _PDF_SAYFA_MAP[kod]
    return {
        "kod": kod,
        "etiket": etiket,
        "size_css": size_css,
        "secenekler": [
            {"kod": k, "etiket": e, "secili": k == kod}
            for k, e, _ in PDF_SAYFA_SECENEKLERI
        ],
    }


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
