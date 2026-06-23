from __future__ import annotations

from check_printing.calibration import generate_calibration_pdf


def test_calibration_pdf_smoke(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "calibration.pdf"

    generate_calibration_pdf(output)

    assert output.exists()
    assert output.stat().st_size > 1000
