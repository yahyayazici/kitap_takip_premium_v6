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
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger(__name__)

_weasyprint_html = None
_weasyprint_checked = False
_weasyprint_disabled = False
_last_pdf_engine = "none"
_last_pdf_error = ""
_reportlab_fonts_ready = False
_pdf_turkish_font_path: Path | None = None


def _require_weasyprint() -> bool:
    return os.environ.get("PDF_REQUIRE_WEASYPRINT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

_XHTML2PDF_TIMEOUT_S = 25
_WEASYPRINT_MISSING_LIB_MARKERS = (
    "pango",
    "cairo",
    "gobject",
    "harfbuzz",
    "gdk_pixbuf",
    "cannot load library",
    "no library called",
)

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
    path_part = ""
    if raw.startswith("file:"):
        path = _path_from_file_uri(raw)
        if path.is_file():
            return path
        path_part = path.as_posix()
    else:
        as_path = Path(raw)
        if as_path.is_file():
            return as_path
        parsed = urlparse(raw)
        path_part = parsed.path if parsed.scheme else raw
        path_part = path_part.replace("\\", "/")
        if ":" in path_part and path_part.index(":") < 3:
            return None

    relative = ""
    for marker in ("/staticfiles/", "/static/"):
        idx = path_part.find(marker)
        if idx >= 0:
            relative = path_part[idx + len(marker) :]
            break
    if not relative and path_part.startswith("static/"):
        relative = path_part[len("static/") :]
    if not relative:
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
        r"(?<![A-Za-z0-9:])(?:https?://[^\"'\s]+)?/?static/[^\s\"')]+",
        _to_file_uri,
        html_string,
    )


def _local_pdf_base_url() -> str:
    return Path(settings.BASE_DIR).resolve().as_uri() + "/"


def _build_weasyprint_url_fetcher():
    """WeasyPrint 68+ URLFetcher örneği — fonksiyon fetcher `_fail_on_errors` ister."""
    try:
        from weasyprint.urls import URLFetcher
    except ImportError:
        from weasyprint import default_url_fetcher

        def _legacy(url, timeout=10, ssl_context=None, **kwargs):
            resolved = _resolve_static_uri(url)
            if resolved is not None:
                url = resolved.resolve().as_uri()
            elif not (url.startswith("file:") or url.startswith("data:")):
                raise ValueError(f"PDF ağ erişimi engellendi: {url}")
            return default_url_fetcher(
                url, timeout=timeout, ssl_context=ssl_context, **kwargs
            )

        _legacy._fail_on_errors = False  # type: ignore[attr-defined]
        return _legacy

    class LocalStaticFetcher(URLFetcher):
        def __init__(self):
            super().__init__(
                allowed_protocols=("file", "data"),
                allow_redirects=False,
                fail_on_errors=False,
            )

        def fetch(self, url, headers=None):
            resolved = _resolve_static_uri(url)
            if resolved is not None:
                url = resolved.resolve().as_uri()
            elif not (url.startswith("file:") or url.startswith("data:")):
                raise ValueError(f"PDF ağ erişimi engellendi: {url}")
            return super().fetch(url, headers)

    return LocalStaticFetcher()


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
    sanitized = sanitized.replace("width: calc(100% + 20px);", "width: 100%;")
    sanitized = sanitized.replace("width:calc(100% + 20px);", "width:100%;")

    # SVG (gradient/medal/bar) xhtml2pdf'de negatif hücre genişliği veya takılma yapar
    sanitized = re.sub(
        r"<svg\b[^>]*>.*?</svg>",
        "",
        sanitized,
        flags=re.DOTALL | re.IGNORECASE,
    )

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

    if system == "Linux":
        lib_dirs: list[str] = []
        base = Path(getattr(settings, "BASE_DIR", Path.cwd()))
        candidates = [
            base / "vendor" / "pdf-libs" / "usr" / "lib" / "x86_64-linux-gnu",
            base / "vendor" / "pdf-libs" / "usr" / "lib" / "aarch64-linux-gnu",
            Path("/usr/lib/x86_64-linux-gnu"),
            Path("/usr/lib/aarch64-linux-gnu"),
            Path("/usr/local/lib"),
            Path("/usr/lib"),
        ]
        for lib_dir in candidates:
            if not lib_dir.is_dir():
                continue
            if not any(lib_dir.glob("libpango-1.0.so*")) and not any(
                lib_dir.glob("libgobject-2.0.so*")
            ):
                continue
            resolved = str(lib_dir.resolve())
            if resolved not in lib_dirs:
                lib_dirs.append(resolved)

        if lib_dirs:
            current = os.environ.get("LD_LIBRARY_PATH", "")
            merged = lib_dirs + [p for p in current.split(":") if p and p not in lib_dirs]
            os.environ["LD_LIBRARY_PATH"] = ":".join(merged)

        font_conf = base / "vendor" / "pdf-libs" / "etc" / "fonts"
        if font_conf.is_dir() and not os.environ.get("FONTCONFIG_PATH"):
            os.environ["FONTCONFIG_PATH"] = str(font_conf)
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
    global _weasyprint_html, _weasyprint_checked, _weasyprint_disabled

    if _weasyprint_disabled:
        return None

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


def _run_with_timeout(fn, timeout_s: float, *args, **kwargs):
    """PDF motorunu sınırlı sürede çalıştır; takılırsa TimeoutError."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdf-engine")
    fut = pool.submit(fn, *args, **kwargs)
    try:
        result = fut.result(timeout=timeout_s)
    except FuturesTimeoutError as exc:
        pool.shutdown(wait=False, cancel_futures=True)
        raise TimeoutError(f"PDF motoru {timeout_s:.0f}s aştı") from exc
    pool.shutdown(wait=False, cancel_futures=True)
    return result


def _weasyprint_write(html_cls, local_html: str, local_base: str) -> bytes:
    document = html_cls(
        string=local_html,
        base_url=local_base,
        url_fetcher=_build_weasyprint_url_fetcher(),
    )
    return document.write_pdf()


def _xhtml2pdf_write(html_string: str) -> bytes:
    from xhtml2pdf import pisa

    _ensure_xhtml2pdf_windows_tmp_patch()
    buffer = BytesIO()
    result = pisa.CreatePDF(
        _prepare_html_for_xhtml2pdf(html_string),
        dest=buffer,
        encoding="utf-8",
        link_callback=_xhtml2pdf_link_callback,
    )
    if result.err:
        raise RuntimeError(f"xhtml2pdf hata kodu: {result.err}")
    return buffer.getvalue()


def _is_weasyprint_native_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _WEASYPRINT_MISSING_LIB_MARKERS)


def html_to_pdf(html_string: str, base_url: str = "/") -> bytes | None:
    """
    HTML metninden PDF üretir.
    Önce WeasyPrint, başarısız olursa xhtml2pdf dener.

    WeasyPrint (Cairo/Pango) istek iş parçacığında çalışır; ayrı thread
    zaman aşımı native kütüphaneyi kilitler ve tasarımı yedek motora düşürür.

    base_url HTTP olsa bile yerel dosya tabanı kullanılır; aksi halde Render'da
    worker kendini bekleyerek (static fetch) kilitlenebilir.
    """
    global _weasyprint_disabled, _last_pdf_engine, _last_pdf_error
    del base_url  # bilinçli: ağ self-fetch engeli
    html_cls = get_weasyprint_html()
    local_html = _rewrite_static_urls_to_file(html_string)
    local_base = _local_pdf_base_url()
    _last_pdf_error = ""

    if html_cls is not None:
        try:
            pdf_bytes = _weasyprint_write(html_cls, local_html, local_base)
            _last_pdf_engine = "weasyprint"
            return pdf_bytes
        except Exception as exc:
            _last_pdf_error = f"{type(exc).__name__}: {exc}"
            if _is_weasyprint_native_error(exc):
                _weasyprint_disabled = True
                logger.exception(
                    "WeasyPrint native kütüphane yok (Pango/Cairo), xhtml2pdf deneniyor"
                )
            else:
                logger.exception("WeasyPrint PDF üretimi başarısız, xhtml2pdf deneniyor")
            if _require_weasyprint():
                _last_pdf_engine = "none"
                return None

    try:
        pdf_bytes = _run_with_timeout(
            _xhtml2pdf_write,
            _XHTML2PDF_TIMEOUT_S,
            html_string,
        )
        _last_pdf_engine = "xhtml2pdf"
        return pdf_bytes
    except ImportError:
        logger.error("xhtml2pdf yüklü değil; HTML tabanlı PDF üretilemedi.")
        _last_pdf_engine = "none"
        return None
    except Exception:
        logger.exception("xhtml2pdf PDF üretimi başarısız.")
        _last_pdf_engine = "none"
        return None


def pdf_engine_status() -> str:
    """Kullanılabilir PDF motorunu döndürür (log/diagnostic için)."""
    if not _weasyprint_disabled and get_weasyprint_html() is not None:
        return "weasyprint"

    try:
        import xhtml2pdf  # noqa: F401
    except ImportError:
        return "none"

    return "xhtml2pdf"


def last_pdf_engine() -> str:
    """Son html_to_pdf çağrısının gerçekten kullandığı motor."""
    return _last_pdf_engine


def last_pdf_error() -> str:
    return _last_pdf_error


def probe_weasyprint() -> tuple[bool, str]:
    """WeasyPrint'in gerçekten PDF üretebildiğini dener (Pango/Cairo dahil)."""
    html_cls = get_weasyprint_html()
    if html_cls is None:
        return False, "WeasyPrint import edilemedi"
    try:
        html_cls(string="<html><body><p>ok</p></body></html>").write_pdf()
        return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


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
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    response["X-PDF-Engine"] = last_pdf_engine() or pdf_engine_status()
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
    extra = last_pdf_error()
    if extra:
        message = f"{message}\n{extra}"
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
