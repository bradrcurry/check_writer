from __future__ import annotations

from decimal import Decimal

import pytest
from check_printing.models import AppConfig, Check
from check_printing.pdf_generator import generate_checks_pdf
from check_printing.preview import preview_available, render_pdf_to_pngs


def _sample_pdf(tmp_path):  # type: ignore[no-untyped-def]
    output = tmp_path / "checks.pdf"
    checks = [Check(check_number=1001, payee="Sample Payee", amount=Decimal("10.00"))]
    generate_checks_pdf(checks, AppConfig(output_dir=tmp_path), output)
    return output


@pytest.mark.skipif(not preview_available(), reason="PyMuPDF not installed")
def test_render_pdf_to_pngs_returns_one_image_per_page(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = _sample_pdf(tmp_path)

    images = render_pdf_to_pngs(output)

    # One check -> one duplex sheet -> front + back pages.
    assert len(images) == 2
    assert all(image.startswith(b"\x89PNG\r\n") for image in images)


@pytest.mark.skipif(not preview_available(), reason="PyMuPDF not installed")
def test_render_pdf_respects_max_pages(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = _sample_pdf(tmp_path)

    images = render_pdf_to_pngs(output, max_pages=1)

    assert len(images) == 1


@pytest.mark.skipif(not preview_available(), reason="PyMuPDF not installed")
def test_render_pdf_rejects_bad_dpi(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = _sample_pdf(tmp_path)

    with pytest.raises(ValueError, match="dpi"):
        render_pdf_to_pngs(output, dpi=0)
