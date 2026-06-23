from __future__ import annotations

from decimal import Decimal

import pytest
from check_printing import pdf_generator
from check_printing.models import AccountProfile, AppConfig, Check, DuplexFlip, MicrSettings
from check_printing.pdf_generator import generate_checks_pdf
from check_printing.templates import INCH
from pydantic import ValidationError


def test_pdf_generation_smoke(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "checks.pdf"
    checks = [Check(check_number=1001, payee="Sample Payee", amount=Decimal("10.00"))]

    generate_checks_pdf(checks, AppConfig(output_dir=tmp_path), output)

    assert output.exists()
    assert output.stat().st_size > 1000
    assert b"/MediaBox [ 0 0 612 792 ]" in output.read_bytes()


def test_pdf_generation_rejects_invalid_micr_before_writing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "checks.pdf"
    account = AccountProfile.model_construct(
        routing_number="011000016",
        account_number="000123456789",
    )
    checks = [Check(check_number=1001, payee="Sample Payee", amount=Decimal("10.00"))]

    with pytest.raises(ValueError, match="routing_number"):
        generate_checks_pdf(checks, AppConfig(account=account), output)

    assert not output.exists()


def test_micr_baseline_must_stay_within_clear_band() -> None:
    # Within the 5/8" clear band is accepted.
    MicrSettings(baseline_from_bottom_in=0.1875)
    MicrSettings(baseline_from_bottom_in=0.625)

    # Outside the band is rejected so MICR cannot be placed where scanners
    # will not read it.
    with pytest.raises(ValidationError):
        MicrSettings(baseline_from_bottom_in=0.7)
    with pytest.raises(ValidationError):
        MicrSettings(baseline_from_bottom_in=-0.1)


def test_custom_micr_band_renders(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "checks.pdf"
    checks = [Check(check_number=1001, payee="Sample Payee", amount=Decimal("10.00"))]
    config = AppConfig(
        output_dir=tmp_path,
        micr=MicrSettings(font_size_pt=11.0, baseline_from_bottom_in=0.25, right_margin_in=0.3),
    )

    generate_checks_pdf(checks, config, output)

    assert output.exists()


def test_front_background_stays_above_micr_clear_band(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[float, float]] = []

    def capture_background(*args) -> None:  # type: ignore[no-untyped-def]
        calls.append((float(args[2]), float(args[4])))

    monkeypatch.setattr(pdf_generator, "draw_background", capture_background)

    output = tmp_path / "checks.pdf"
    checks = [Check(check_number=1001, payee="Sample Payee", amount=Decimal("10.00"))]

    generate_checks_pdf(checks, AppConfig(output_dir=tmp_path), output)

    assert calls
    front_y, front_height = calls[0]
    assert front_y >= pdf_generator.CLEAR_BAND_IN * INCH
    assert front_height > 0


def test_too_wide_micr_line_is_rejected_before_writing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "checks.pdf"
    account = AccountProfile(account_number="0" * 80)
    checks = [Check(check_number=1001, payee="Sample Payee", amount=Decimal("10.00"))]

    with pytest.raises(ValueError, match="MICR line is too wide"):
        generate_checks_pdf(checks, AppConfig(account=account), output)

    assert not output.exists()


def test_micr_numeric_settings_are_validated() -> None:
    with pytest.raises(ValidationError):
        MicrSettings(font_size_pt=0)
    with pytest.raises(ValidationError):
        MicrSettings(right_margin_in=-0.01)


def _preview_available() -> bool:
    try:
        import fitz  # noqa: F401
    except ImportError:
        return False
    return True


def _text_line_directions(page) -> set[tuple[float, ...]]:  # type: ignore[no-untyped-def]
    directions: set[tuple[float, ...]] = set()
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            directions.add(tuple(round(value, 2) for value in line["dir"]))
    return directions


def _front_back_dirs(tmp_path, layout: str, flip: DuplexFlip):  # type: ignore[no-untyped-def]
    import fitz

    output = tmp_path / "checks.pdf"
    checks = [Check(check_number=1001, payee="Sample Payee", amount=Decimal("10.00"))]
    generate_checks_pdf(
        checks, AppConfig(output_dir=tmp_path, layout=layout, duplex_flip=flip), output
    )
    with fitz.open(str(output)) as document:
        return _text_line_directions(document[0]), _text_line_directions(document[1])


@pytest.mark.skipif(not _preview_available(), reason="PyMuPDF not installed")
def test_long_edge_back_matches_front_orientation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Long-edge flip mirrors about the vertical edge, leaving "up" unchanged, so
    # the back must use the SAME orientation as the front to read upright.
    front, back = _front_back_dirs(tmp_path, "reliable_6up", DuplexFlip.LONG_EDGE)
    assert front == back


@pytest.mark.skipif(not _preview_available(), reason="PyMuPDF not installed")
def test_short_edge_back_is_opposite_orientation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Short-edge flip inverts "up", so the back must be rotated 180 from the front.
    front, back = _front_back_dirs(tmp_path, "reliable_6up", DuplexFlip.SHORT_EDGE)
    assert all((-a, -b) in back for (a, b) in front)
    assert front != back


@pytest.mark.skipif(not _preview_available(), reason="PyMuPDF not installed")
def test_non_rotated_long_edge_back_matches_front(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # standard_3up is non-rotated; long-edge back must not be upside down.
    front, back = _front_back_dirs(tmp_path, "standard_3up", DuplexFlip.LONG_EDGE)
    assert front == back
