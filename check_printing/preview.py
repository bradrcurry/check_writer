"""Render generated check PDFs to images for in-app preview.

Kept independent of Streamlit so it can be unit-tested, and tolerant of a
missing optional dependency (PyMuPDF) so the core package and CLI never require
it. Preview shows the exact PDF that will print, not a separate HTML mockup.
"""

from __future__ import annotations

from pathlib import Path

PREVIEW_UNAVAILABLE_MESSAGE = (
    "PDF preview requires PyMuPDF. Install the UI extra: pip install 'check-printing[ui]'."
)


def preview_available() -> bool:
    try:
        import fitz  # noqa: F401  (PyMuPDF)
    except ImportError:
        return False
    return True


def render_pdf_to_pngs(pdf_path: Path, *, dpi: int = 150, max_pages: int | None = None) -> list[bytes]:
    """Render each page of ``pdf_path`` to PNG bytes.

    Raises ``RuntimeError`` if PyMuPDF is not installed so callers can show a
    friendly message instead of crashing.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - exercised via preview_available()
        raise RuntimeError(PREVIEW_UNAVAILABLE_MESSAGE) from exc

    if dpi <= 0:
        raise ValueError("dpi must be positive")

    images: list[bytes] = []
    with fitz.open(str(pdf_path)) as document:
        page_count = len(document)
        limit = page_count if max_pages is None else min(max_pages, page_count)
        for page_index in range(limit):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(dpi=dpi)
            images.append(pixmap.tobytes("png"))
    return images
