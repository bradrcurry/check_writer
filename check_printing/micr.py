from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Display glyphs (Unicode MICR E-13B symbols). These render correctly with
# fonts that map the symbols to the U+2446..U+2449 codepoints, and are used for
# the human-readable Courier fallback (test output only).
TRANSIT = "⑆"
ON_US = "⑈"
DASH = "⑉"
AMOUNT = "⑇"


@dataclass(frozen=True)
class MicrSymbols:
    """Characters used for the four MICR E-13B symbols in a given font.

    Real E-13B fonts (e.g. GnuMICR) do not map the Unicode MICR codepoints;
    they map the symbols onto ASCII ``A B C D``. The exact character set
    therefore depends on which font is registered, so it travels with the
    font registration rather than being a global constant.
    """

    transit: str
    on_us: str
    amount: str
    dash: str


# GnuMICR's ASCII mapping. Verified by RENDERING the glyphs and comparing the
# shapes to the canonical E-13B reference: A=transit, B=amount, C=on-us, D=dash.
# (The font's path-comment labels are misleading; B renders as the amount symbol
# and C as the on-us symbol.) This matches the common ConnectCode/BarcodeResource
# convention.
GNUMICR_SYMBOLS = MicrSymbols(transit="A", on_us="C", amount="B", dash="D")

# Alias: the same A=transit B=amount C=on-us D=dash convention used by GnuMICR
# and most distributable E-13B fonts.
BARCODERESOURCE_SYMBOLS = GNUMICR_SYMBOLS

# Fallback shown with Courier when no MICR font is configured. Not bank-readable;
# uses the Unicode glyphs purely so the line is visibly distinguishable as MICR.
FALLBACK_SYMBOLS = MicrSymbols(transit=TRANSIT, on_us=ON_US, amount=AMOUNT, dash=DASH)


class MicrSymbolMap(StrEnum):
    """Which ASCII->symbol convention a MICR font uses.

    ``auto`` keeps the historical behaviour (Unicode glyphs if present, else the
    GnuMICR A/B/C/D mapping). Set explicitly when using a font whose A/B/C/D
    assignment differs, since on-us and amount are swapped between the two common
    conventions.
    """

    AUTO = "auto"
    GNUMICR = "gnumicr"
    BARCODERESOURCE = "barcoderesource"
    UNICODE = "unicode"


_NAMED_SYMBOL_MAPS = {
    MicrSymbolMap.GNUMICR: GNUMICR_SYMBOLS,
    MicrSymbolMap.BARCODERESOURCE: BARCODERESOURCE_SYMBOLS,
    MicrSymbolMap.UNICODE: FALLBACK_SYMBOLS,
}


class MicrFieldOrder(StrEnum):
    """MICR line arrangement, which differs between personal and business checks.

    E-13B symbol semantics (per ANSI X9.100-160):
    - The transit symbol brackets the routing number on BOTH sides.
    - The on-us symbol is a terminator placed AFTER each on-us value (account,
      and serial), not a bracket on both sides.

    ``personal`` (standard ~6 in personal check): the serial number lives in the
    on-us field after the account number; there is no auxiliary on-us field:
        ``⑆ routing ⑆  account ⑈ serial ⑈``

    ``business`` (longer business check): the serial number is in a separate
    auxiliary on-us field at the far left, bracketed by on-us symbols:
        ``⑈ serial ⑈  ⑆ routing ⑆  account ⑈``

    Confirm the exact layout your bank expects (e.g. via a mobile-deposit scan)
    before relying on either.
    """

    PERSONAL = "personal"
    BUSINESS = "business"


class MicrAccount(Protocol):
    routing_number: str
    account_number: str


class MicrCheck(Protocol):
    check_number: int


def validate_routing_number(routing_number: str) -> bool:
    if len(routing_number) != 9 or not routing_number.isdigit():
        return False
    digits = [int(char) for char in routing_number]
    checksum = (
        3 * (digits[0] + digits[3] + digits[6])
        + 7 * (digits[1] + digits[4] + digits[7])
        + (digits[2] + digits[5] + digits[8])
    )
    return checksum % 10 == 0


def validate_check_number(check_number: int | str) -> bool:
    return str(check_number).isdigit() and int(check_number) > 0


def format_micr_line(
    routing_number: str,
    account_number: str,
    check_number: int | str,
    *,
    amount_cents: int | None = None,
    symbols: MicrSymbols = FALLBACK_SYMBOLS,
    field_order: MicrFieldOrder = MicrFieldOrder.PERSONAL,
) -> str:
    if not validate_routing_number(routing_number):
        raise ValueError("routing_number must be 9 digits with a valid ABA checksum")
    if not validate_check_number(check_number):
        raise ValueError("check_number must be numeric")
    if not account_number:
        raise ValueError("account_number is required")

    # Transit symbol brackets the routing number on both sides; the on-us symbol
    # terminates each on-us value (placed after it), it does not bracket.
    transit_field = f"{symbols.transit}{routing_number}{symbols.transit}"

    if field_order == MicrFieldOrder.PERSONAL:
        # Personal check: routing, then the on-us field holding the account number
        # (terminated by an on-us symbol) followed by the serial number. The
        # serial ends the line with NO trailing symbol; the account's on-us
        # serves as the separator before it.
        #     ⑆ routing ⑆  account ⑈ serial
        line = f"{transit_field} {account_number}{symbols.on_us} {check_number}"
    else:
        # Business check: serial in the auxiliary on-us field, bracketed by on-us
        # symbols on both sides, then routing, then account (on-us terminated).
        #     ⑈ serial ⑈  ⑆ routing ⑆  account ⑈
        aux_serial = f"{symbols.on_us}{check_number}{symbols.on_us}"
        line = f"{aux_serial} {transit_field} {account_number}{symbols.on_us}"

    if amount_cents is not None:
        if amount_cents < 0:
            raise ValueError("amount_cents cannot be negative")
        line = f"{line} {symbols.amount}{amount_cents:010d}{symbols.amount}"
    return line


def validate_micr_inputs(account: MicrAccount, checks: Sequence[MicrCheck]) -> None:
    if not validate_routing_number(account.routing_number):
        raise ValueError("routing_number must be 9 digits with a valid ABA checksum")
    if not account.account_number.strip():
        raise ValueError("account_number is required")
    for check in checks:
        if not validate_check_number(check.check_number):
            raise ValueError(f"check_number must be numeric and positive: {check.check_number}")


@dataclass(frozen=True)
class MicrFontRegistration:
    font_name: str
    symbols: MicrSymbols
    warning: str | None


def register_micr_font(
    font_path: Path | None,
    symbol_map: MicrSymbolMap = MicrSymbolMap.AUTO,
) -> MicrFontRegistration:
    if font_path is None:
        return MicrFontRegistration(
            font_name="Courier",
            symbols=FALLBACK_SYMBOLS,
            warning="No MICR font configured; using Courier fallback for test output only.",
        )
    if not font_path.exists():
        return MicrFontRegistration(
            font_name="Courier",
            symbols=FALLBACK_SYMBOLS,
            warning=f"MICR font not found at {font_path}; using Courier fallback for test output only.",
        )

    font_name = "MICR-E13B"
    font = TTFont(font_name, str(font_path))
    pdfmetrics.registerFont(font)
    symbols = _resolve_symbols(font, font_path, symbol_map)
    return MicrFontRegistration(font_name=font_name, symbols=symbols, warning=None)


def _resolve_symbols(
    font: TTFont, font_path: Path, symbol_map: MicrSymbolMap
) -> MicrSymbols:
    """Choose the ASCII->symbol mapping for a font.

    An explicit ``symbol_map`` is honoured (after checking the font can render
    those characters); ``auto`` falls back to Unicode glyphs if present, else the
    GnuMICR A/B/C/D mapping.
    """
    mapped = set(font.face.charToGlyph)
    if symbol_map != MicrSymbolMap.AUTO:
        symbols = _NAMED_SYMBOL_MAPS[symbol_map]
        missing = [c for c in (symbols.transit, symbols.on_us, symbols.amount, symbols.dash)
                   if ord(c) not in mapped]
        if missing:
            raise ValueError(
                f"MICR font {font_path} is missing glyphs for the {symbol_map.value} "
                f"symbol mapping (characters {missing!r})."
            )
        return symbols
    if all(ord(char) in mapped for char in (TRANSIT, ON_US, AMOUNT, DASH)):
        return FALLBACK_SYMBOLS
    if all(ord(char) in mapped for char in ("A", "B", "C", "D")):
        return GNUMICR_SYMBOLS
    raise ValueError(
        f"MICR font {font_path} does not contain the four E-13B symbols on either the "
        "Unicode (U+2446..U+2449) or ASCII (A B C D) code points; cannot render a readable MICR line."
    )
