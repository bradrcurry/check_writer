from __future__ import annotations

from pathlib import Path

import pytest
from check_printing.micr import (
    GNUMICR_SYMBOLS,
    MicrFieldOrder,
    MicrSymbolMap,
    format_micr_line,
    register_micr_font,
    validate_micr_inputs,
    validate_routing_number,
)
from check_printing.models import AccountProfile, Check
from reportlab.pdfbase.ttfonts import TTFont

GNUMICR_TTF = Path("local_fonts/gnumicr/GnuMICR.ttf")


def test_routing_checksum_validates_sample_number() -> None:
    assert validate_routing_number("011000015")
    assert not validate_routing_number("011000016")


def test_format_micr_line_rejects_bad_routing_number() -> None:
    with pytest.raises(ValueError, match="routing_number"):
        format_micr_line("123", "000123456789", 1001)


def test_format_micr_line_contains_symbols_and_fields() -> None:
    line = format_micr_line("011000015", "000123456789", 1001)

    assert "011000015" in line
    assert "000123456789" in line
    assert "1001" in line


def test_gnumicr_symbol_mapping_matches_rendered_glyphs() -> None:
    # Verified by rendering the font: A=transit, B=amount, C=on-us, D=dash.
    assert GNUMICR_SYMBOLS.transit == "A"
    assert GNUMICR_SYMBOLS.amount == "B"
    assert GNUMICR_SYMBOLS.on_us == "C"
    assert GNUMICR_SYMBOLS.dash == "D"


def test_personal_check_layout_symbols_and_order() -> None:
    # Personal check (default): transit-bracketed routing, then the account
    # (terminated by on-us) followed by the serial. The serial ends the line
    # with NO trailing symbol.
    t, o = GNUMICR_SYMBOLS.transit, GNUMICR_SYMBOLS.on_us
    line = format_micr_line("011000015", "000123456789", 1001, symbols=GNUMICR_SYMBOLS)

    assert line == f"{t}011000015{t} 000123456789{o} 1001"
    # routing first, then account, then serial.
    assert line.index("011000015") < line.index("000123456789") < line.index("1001")
    # No trailing on-us after the check number on a personal check.
    assert not line.rstrip().endswith(o)
    # The serial is NOT bracketed by on-us on its left (that is the business form).
    assert f"{o}1001{o}" not in line


def test_business_check_layout_uses_auxiliary_on_us_field() -> None:
    t, o = GNUMICR_SYMBOLS.transit, GNUMICR_SYMBOLS.on_us
    line = format_micr_line(
        "011000015",
        "000123456789",
        1001,
        symbols=GNUMICR_SYMBOLS,
        field_order=MicrFieldOrder.BUSINESS,
    )

    # Serial first in the auxiliary on-us field, bracketed by on-us symbols.
    assert line == f"{o}1001{o} {t}011000015{t} 000123456789{o}"
    assert line.index("1001") < line.index("011000015") < line.index("000123456789")


def test_transit_symbol_brackets_routing_on_both_sides() -> None:
    t = GNUMICR_SYMBOLS.transit
    line = format_micr_line("011000015", "000123456789", 1001, symbols=GNUMICR_SYMBOLS)

    assert f"{t}011000015{t}" in line  # transit on both sides of routing


def test_on_us_symbol_terminates_account_not_brackets_it() -> None:
    o = GNUMICR_SYMBOLS.on_us
    line = format_micr_line("011000015", "000123456789", 1001, symbols=GNUMICR_SYMBOLS)

    # On-us follows the account number; there is no on-us before it.
    assert f"000123456789{o}" in line
    assert f"{o}000123456789" not in line


def test_amount_field_is_rightmost_when_present() -> None:
    a = GNUMICR_SYMBOLS.amount
    line = format_micr_line(
        "011000015", "000123456789", 1001, amount_cents=12345, symbols=GNUMICR_SYMBOLS
    )

    # Amount field (bank of first deposit) is the rightmost field on a real check.
    assert line.endswith(f"{a}0000012345{a}")
    assert line.index("1001") < line.index("0000012345")


def test_validate_micr_inputs_rejects_bad_routing_number() -> None:
    account = AccountProfile.model_construct(
        routing_number="011000016",
        account_number="000123456789",
    )
    check = Check(check_number=1001, payee="Sample", amount="10.00")

    with pytest.raises(ValueError, match="routing_number"):
        validate_micr_inputs(account, [check])


def test_register_micr_font_warns_when_missing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    registration = register_micr_font(tmp_path / "missing.ttf")

    assert registration.font_name == "Courier"
    assert registration.warning is not None


@pytest.mark.skipif(not GNUMICR_TTF.exists(), reason="GnuMICR font not available")
def test_gnumicr_registration_uses_ascii_symbols() -> None:
    registration = register_micr_font(GNUMICR_TTF)

    assert registration.warning is None
    assert registration.symbols == GNUMICR_SYMBOLS
    assert (registration.symbols.transit, registration.symbols.on_us) == ("A", "C")


@pytest.mark.skipif(not GNUMICR_TTF.exists(), reason="GnuMICR font not available")
def test_explicit_gnumicr_symbol_map() -> None:
    registration = register_micr_font(GNUMICR_TTF, MicrSymbolMap.GNUMICR)

    assert registration.symbols == GNUMICR_SYMBOLS


@pytest.mark.skipif(not GNUMICR_TTF.exists(), reason="GnuMICR font not available")
def test_barcoderesource_map_matches_gnumicr_convention() -> None:
    # GnuMICR uses the same A=transit B=amount C=on-us D=dash convention.
    registration = register_micr_font(GNUMICR_TTF, MicrSymbolMap.BARCODERESOURCE)

    assert registration.symbols.on_us == "C"
    assert registration.symbols.amount == "B"
    assert registration.symbols == GNUMICR_SYMBOLS


@pytest.mark.skipif(not GNUMICR_TTF.exists(), reason="GnuMICR font not available")
def test_micr_symbols_have_glyphs_in_registered_font() -> None:
    """Regression guard: every emitted symbol must exist in the real font."""
    registration = register_micr_font(GNUMICR_TTF)
    mapped = set(TTFont("probe", str(GNUMICR_TTF)).face.charToGlyph)

    symbols = registration.symbols
    for char in (symbols.transit, symbols.on_us, symbols.amount, symbols.dash):
        assert ord(char) in mapped, f"symbol {char!r} missing from GnuMICR font"


@pytest.mark.skipif(not GNUMICR_TTF.exists(), reason="GnuMICR font not available")
def test_gnumicr_pitch_is_near_8_cpi_at_default_size() -> None:
    """E-13B is a fixed 8 CPI font; the default size must render close to that."""
    from check_printing.models import MicrSettings
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_name = "MICR-pitch-probe"
    pdfmetrics.registerFont(TTFont(font_name, str(GNUMICR_TTF)))
    size = MicrSettings().font_size_pt
    width_in = pdfmetrics.stringWidth("0123456789", font_name, size) / 72.0
    cpi = 10 / width_in

    assert abs(cpi - 8.0) < 0.25, f"MICR pitch {cpi:.2f} CPI is too far from 8 CPI"


@pytest.mark.skipif(not GNUMICR_TTF.exists(), reason="GnuMICR font not available")
def test_format_micr_line_uses_font_specific_symbols() -> None:
    registration = register_micr_font(GNUMICR_TTF)
    line = format_micr_line(
        "011000015", "000123456789", 1001, symbols=registration.symbols
    )

    assert "A011000015A" in line  # transit symbol wraps the routing number
    assert "⑆" not in line  # the unreadable Unicode glyph is not emitted
