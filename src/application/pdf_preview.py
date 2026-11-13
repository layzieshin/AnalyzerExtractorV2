from __future__ import annotations

import json
import math
import multiprocessing
import tempfile
import threading
import time
from pathlib import Path

from .errors import PdfPreviewError
from .models import ReportPdfPage


MAX_ZOOM = 3.0
MAX_PAGES = 1000
MAX_DIMENSION = 3000
MAX_PIXELS = 6_000_000
MAX_IMAGE_BYTES = MAX_PIXELS * 3 + 64
MAX_PDF_BYTES = 128 * 1024 * 1024
RENDER_TIMEOUT_S = 8.0
_RENDER_LOCK = threading.Lock()


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    if not path.is_file() or stat.st_size > MAX_PDF_BYTES:
        raise PdfPreviewError("Die PDF fehlt oder ist fuer die Vorschau zu gross (max. 128 MB).")
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _bounded_scale(width: float, height: float, zoom: float) -> float:
    if not all(math.isfinite(value) and value > 0 for value in (width, height)):
        raise PdfPreviewError("Die PDF-Seite hat ungueltige Abmessungen.")
    # Leave room for MuPDF's outward rounding before allocating the pixmap.
    return min(zoom, (MAX_DIMENSION - 2) / width, (MAX_DIMENSION - 2) / height,
               math.sqrt((MAX_PIXELS - 2 * MAX_DIMENSION * 2) / (width * height)))


def _render_pdf_worker(pdf_path: str, page_index: int, zoom: float, output_dir: str) -> None:
    """Spawn target. MuPDF is used only on this child process's main thread.

    No document, page, pixmap, or Tk object crosses the process boundary. The
    parent waits for exit before reading bounded files, so a partial IPC send
    cannot defeat its timeout. Every request gets a fresh process and temp dir.
    """
    folder = Path(output_dir)
    try:
        import fitz

        with fitz.open(pdf_path) as document:
            if not document.is_pdf or document.needs_pass or document.is_repaired:
                raise PdfPreviewError("Die PDF ist beschaedigt oder geschuetzt und kann nicht angezeigt werden.")
            count = document.page_count
            if count == 0:
                raise PdfPreviewError("Die PDF enthaelt keine Seiten.")
            if count > MAX_PAGES:
                raise PdfPreviewError(f"Die PDF hat zu viele Seiten fuer die Vorschau (max. {MAX_PAGES}).")
            if page_index >= count:
                raise PdfPreviewError("Die angeforderte PDF-Seite ist nicht vorhanden.")
            page = document.load_page(page_index)
            scale = _bounded_scale(float(page.rect.width), float(page.rect.height), zoom)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
            width, height = pixmap.width, pixmap.height
            if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION and width * height <= MAX_PIXELS):
                raise PdfPreviewError("Die PDF-Seite ueberschreitet die sichere Vorschaugroesse.")
            image = pixmap.tobytes("ppm")
            if len(image) > MAX_IMAGE_BYTES:
                raise PdfPreviewError("Die PDF-Seite ueberschreitet die sichere Vorschaugroesse.")
            (folder / "page.ppm").write_bytes(image)
            result = {"page_index": page_index, "page_count": count, "zoom": scale, "width": width, "height": height}
    except Exception as exc:
        message = str(exc) if isinstance(exc, PdfPreviewError) else "Die PDF ist unlesbar oder beschaedigt."
        result = {"error": message}
    (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")


def _stop_process(process: object) -> None:
    if process.is_alive():
        process.terminate()
        process.join(timeout=0.5)
    if process.is_alive():
        process.kill()
        process.join(timeout=0.5)


def render_pdf_page(report_id: str, pdf_path: str, *, page_index: int, zoom: float) -> ReportPdfPage:
    """Internal bounded renderer; callers must first resolve a report's source.

    One application-wide render slot prevents unbounded process creation. The
    eight-second budget includes waiting for that slot and the child lifetime;
    termination/kill cleanup adds at most one second. No application worker
    thread calls MuPDF, including while the extraction parser is running.
    """
    if isinstance(page_index, bool) or not isinstance(page_index, int) or not 0 <= page_index < MAX_PAGES:
        raise PdfPreviewError("Die angeforderte PDF-Seite ist ungueltig.")
    try:
        requested_zoom = float(zoom)
    except (ValueError, TypeError, OverflowError) as exc:
        raise PdfPreviewError("Der PDF-Zoom ist ungueltig.") from exc
    if not math.isfinite(requested_zoom) or requested_zoom <= 0:
        raise PdfPreviewError("Der PDF-Zoom ist ungueltig.")
    # The view owns the manual zoom floor. Automatic fit scales may be smaller;
    # finite positive scales still pass through the same image/resource caps.
    requested_zoom = min(MAX_ZOOM, requested_zoom)
    path = Path(pdf_path)
    deadline = time.monotonic() + RENDER_TIMEOUT_S
    acquired = _RENDER_LOCK.acquire(timeout=RENDER_TIMEOUT_S)
    if not acquired:
        raise PdfPreviewError("Die PDF-Vorschau hat das Zeitlimit ueberschritten. Bitte erneut versuchen.")
    process = None
    started = False
    try:
        identity = _file_identity(path)
        with tempfile.TemporaryDirectory(prefix="arev2-pdf-preview-") as temporary:
            try:
                process = multiprocessing.get_context("spawn").Process(
                    target=_render_pdf_worker,
                    args=(str(path), page_index, requested_zoom, temporary),
                    daemon=True,
                )
                process.start()
                started = True
                process.join(timeout=max(0.0, deadline - time.monotonic()))
                if process.is_alive():
                    raise PdfPreviewError("Die PDF-Vorschau hat das Zeitlimit ueberschritten. Bitte erneut versuchen.")
                if process.exitcode != 0:
                    raise PdfPreviewError("Die PDF-Vorschau wurde unerwartet beendet.")
                folder = Path(temporary)
                result_path = folder / "result.json"
                if result_path.stat().st_size > 4096:
                    raise ValueError("oversized_metadata")
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if result.get("error"):
                    raise PdfPreviewError(str(result["error"]))
                width, height, count = result["width"], result["height"], result["page_count"]
                scale = result["zoom"]
                if not (type(width) is int and type(height) is int and type(count) is int
                        and 0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION
                        and width * height <= MAX_PIXELS and page_index < count <= MAX_PAGES
                        and result["page_index"] == page_index and math.isfinite(scale) and 0 < scale <= MAX_ZOOM):
                    raise ValueError("invalid_preview_metadata")
                image_path = folder / "page.ppm"
                if image_path.stat().st_size > MAX_IMAGE_BYTES:
                    raise ValueError("oversized_image")
                image = image_path.read_bytes()
                header = f"P6\n{width} {height}\n255\n".encode("ascii")
                if not image.startswith(header) or len(image) != len(header) + width * height * 3:
                    raise ValueError("invalid_preview_image")
                if _file_identity(path) != identity:
                    raise PdfPreviewError("Die PDF wurde waehrend des Ladens geaendert. Bitte aktualisieren.")
                return ReportPdfPage(report_id, page_index, count, float(scale), width, height, image)
            finally:
                if process is not None:
                    if started:
                        _stop_process(process)
                    if not started or not process.is_alive():
                        process.close()
    except PdfPreviewError:
        raise
    except Exception as exc:
        raise PdfPreviewError("Die PDF-Vorschau konnte nicht geladen werden. Die Quelle fehlt oder ist unlesbar.") from exc
    finally:
        _RENDER_LOCK.release()
