from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from check_printing.micr import (
    MicrFontRegistration,
    format_micr_line,
    register_micr_font,
    validate_micr_inputs,
)
from check_printing.models import AccountProfile, AppConfig, Check
from check_printing.money import amount_to_words
from check_printing.patterns import draw_background
from check_printing.templates import INCH, Layout, get_layout

# ANSI X9 MICR clear band: bottom 5/8" of the check must contain nothing but the
# MICR line (no border, cut marks, or artwork).
CLEAR_BAND_IN = 0.625
# Minimum clearance from the leading (left) edge of the check to printed content.
MICR_LEFT_CLEARANCE_IN = 0.125


def generate_checks_pdf(checks: Sequence[Check], config: AppConfig, output_path: Path) -> Path:
    return write_checks_pdf(checks, config, output_path)


def prepare_checks_pdf(checks: Sequence[Check], config: AppConfig) -> MicrFontRegistration:
    if not checks:
        raise ValueError("At least one check is required")
    validate_micr_inputs(config.account, checks)
    micr_registration = register_micr_font(config.micr_font_path, config.micr.symbol_map)
    layout = get_layout(config.layout, config.layout_templates_path)
    _validate_micr_geometry(checks, config, layout, micr_registration)
    return micr_registration


def write_checks_pdf(
    checks: Sequence[Check],
    config: AppConfig,
    output_path: Path,
    micr_registration: MicrFontRegistration | None = None,
) -> Path:
    layout = get_layout(config.layout, config.layout_templates_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(output_path), pagesize=letter)
    micr_registration = micr_registration or prepare_checks_pdf(checks, config)

    for sheet_checks in _chunks(list(checks), layout.per_page):
        _draw_front_page(canvas, sheet_checks, config, layout, micr_registration)
        canvas.showPage()
        _draw_back_page(canvas, sheet_checks, config, layout)
        canvas.showPage()

    canvas.save()
    return output_path


def _draw_front_page(
    canvas: Canvas,
    checks: Sequence[Check],
    config: AppConfig,
    layout: Layout,
    micr_registration: MicrFontRegistration,
) -> None:
    for index, check in enumerate(checks):
        x, y = layout.front_positions()[index]
        x += config.calibration.front_x_offset_in * INCH
        y += config.calibration.front_y_offset_in * INCH
        _draw_rotated_front_check(
            canvas, x, y, layout, config.account, check, config, micr_registration
        )
    _draw_registration_marks(canvas)


def _draw_back_page(
    canvas: Canvas, checks: Sequence[Check], config: AppConfig, layout: Layout
) -> None:
    for index, check in enumerate(checks):
        x, y = layout.back_positions(config.duplex_flip.value)[index]
        x += config.calibration.back_x_offset_in * INCH
        y += config.calibration.back_y_offset_in * INCH
        _draw_rotated_back_check(canvas, x, y, layout, check, config)
    _draw_registration_marks(canvas)


def _draw_rotated_front_check(
    canvas: Canvas,
    x: float,
    y: float,
    layout: Layout,
    account: AccountProfile,
    check: Check,
    config: AppConfig,
    micr_registration: MicrFontRegistration,
) -> None:
    canvas.saveState()
    if layout.rotated:
        canvas.translate(x, y + layout.slot_height)
        canvas.rotate(-90)
        _draw_front_check(canvas, 0, 0, layout, account, check, config, micr_registration)
    else:
        _draw_front_check(canvas, x, y, layout, account, check, config, micr_registration)
    canvas.restoreState()


def _draw_rotated_back_check(
    canvas: Canvas,
    x: float,
    y: float,
    layout: Layout,
    check: Check,
    config: AppConfig,
) -> None:
    """Draw the back so the endorsement reads upright after the physical flip.

    The required back-content orientation depends on the duplex flip axis:

    - ``long_edge`` (mirror about the vertical edge) leaves a vertical "up"
      vector unchanged, so the back uses the *same* transform as the front.
    - ``short_edge`` (mirror about the horizontal edge) inverts "up", so the
      back is drawn rotated 180 degrees from the front, anchored at the opposite
      corner of the slot.
    """
    short_edge = config.duplex_flip.value == "short_edge"
    canvas.saveState()
    if layout.rotated and short_edge:
        canvas.translate(x + layout.slot_width, y)
        canvas.rotate(90)
        _draw_back_check(canvas, 0, 0, layout, check, config)
    elif layout.rotated:  # long_edge: same transform as the front
        canvas.translate(x, y + layout.slot_height)
        canvas.rotate(-90)
        _draw_back_check(canvas, 0, 0, layout, check, config)
    elif short_edge:  # non-rotated, short edge: 180 from front
        canvas.translate(x + layout.slot_width, y + layout.slot_height)
        canvas.rotate(180)
        _draw_back_check(canvas, 0, 0, layout, check, config)
    else:  # non-rotated, long edge: identical to front
        _draw_back_check(canvas, x, y, layout, check, config)
    canvas.restoreState()


def _draw_front_check(
    canvas: Canvas,
    x: float,
    y: float,
    layout: Layout,
    account: AccountProfile,
    check: Check,
    config: AppConfig,
    micr_registration: MicrFontRegistration,
) -> None:
    width = layout.check_width
    height = layout.check_height
    canvas.saveState()
    _draw_cut_marks(canvas, x, y, width, height, respect_clear_band=True)
    canvas.setStrokeGray(0.10)
    _draw_check_border(canvas, x, y, width, height, respect_clear_band=True)
    _draw_front_background(canvas, x, y, width, height, config)

    canvas.setFillGray(0)
    canvas.setStrokeGray(0)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(x + 12, y + height - 16, account.payor_name)
    canvas.setFont("Helvetica", 6)
    for line_index, line in enumerate(account.payor_address[:2]):
        canvas.drawString(x + 12, y + height - 25 - line_index * 7, line)

    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawCentredString(x + width / 2, y + height - 17, account.bank_name)
    canvas.setFont("Helvetica", 5.5)
    for line_index, line in enumerate(account.bank_address[:2]):
        canvas.drawCentredString(x + width / 2, y + height - 25 - line_index * 6, line)

    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawRightString(x + width - 12, y + height - 18, str(check.check_number))
    canvas.setFont("Helvetica", 6)
    canvas.drawRightString(x + width - 12, y + height - 34, f"Date: {check.date.isoformat()}")

    canvas.setFont("Helvetica", 6.5)
    line_y = y + height - 62
    canvas.drawString(x + 12, line_y, "Pay to the Order of")
    _line(canvas, x + 78, line_y - 1, x + width - 78, line_y - 1)
    if not check.is_blank:
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawString(x + 82, line_y + 2, check.payee)
    _line(canvas, x + width - 70, line_y - 1, x + width - 12, line_y - 1)
    if not check.is_blank:
        canvas.drawRightString(x + width - 14, line_y + 2, f"${check.amount:,.2f}")

    words_y = line_y - 22
    _line(canvas, x + 12, words_y - 1, x + width - 50, words_y - 1)
    if not check.is_blank:
        canvas.setFont("Helvetica", 6)
        canvas.drawString(
            x + 14, words_y + 2, check.written_amount or amount_to_words(check.amount).title()
        )
    canvas.drawString(x + width - 46, words_y + 2, "DOLLARS")

    # Keep the memo/signature line and notices above the MICR clear band so the
    # bottom 5/8" holds only the MICR line (ANSI X9).
    band_top = y + CLEAR_BAND_IN * INCH
    memo_y = band_top + 10
    canvas.setFont("Helvetica", 6)
    canvas.drawString(x + 12, memo_y + 3, "Memo")
    _line(canvas, x + 34, memo_y, x + 120, memo_y)
    if not check.is_blank:
        canvas.drawString(x + 38, memo_y + 3, check.memo[:34])
    _line(canvas, x + width - 132, memo_y, x + width - 12, memo_y)
    canvas.drawString(x + width - 70, memo_y + 3, "Signature")

    if account.void_after_days:
        canvas.setFont("Helvetica-Bold", 5.5)
        canvas.drawCentredString(
            x + width / 2, band_top + 2, f"VOID AFTER {account.void_after_days} DAYS"
        )

    if account.fractional_routing_number:
        canvas.setFont("Helvetica", 5)
        canvas.drawString(x + 12, y + height - 43, account.fractional_routing_number)

    _draw_micr_line(canvas, x, y, width, account, check, config, micr_registration)
    canvas.restoreState()


def _draw_micr_line(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    account: AccountProfile,
    check: Check,
    config: AppConfig,
    micr_registration: MicrFontRegistration,
) -> None:
    """Draw the MICR line inside the ANSI X9 clear band.

    The clear band is the bottom 5/8" of the physical check. The line is placed
    with its baseline a fixed distance above the check bottom edge and ends a
    fixed distance from the right reference edge, rather than being centered, so
    that real E-13B fonts land within the readable band.
    """
    band = config.micr
    canvas.setFont(micr_registration.font_name, band.font_size_pt)
    micr = format_micr_line(
        account.routing_number,
        account.account_number,
        check.check_number,
        symbols=micr_registration.symbols,
        field_order=band.field_order,
    )
    baseline_y = y + band.baseline_from_bottom_in * INCH
    right_x = x + width - band.right_margin_in * INCH
    canvas.drawRightString(right_x, baseline_y, micr)


def _draw_front_background(
    canvas: Canvas, x: float, y: float, width: float, height: float, config: AppConfig
) -> None:
    band_top = y + CLEAR_BAND_IN * INCH
    background_x = x + 8
    background_y = max(y + 32, band_top + 4)
    background_top = y + height - 12
    background_height = background_top - background_y
    if background_height <= 0:
        return
    draw_background(canvas, background_x, background_y, width - 16, background_height, config.pattern)


def _validate_micr_geometry(
    checks: Sequence[Check],
    config: AppConfig,
    layout: Layout,
    micr_registration: MicrFontRegistration,
) -> None:
    band = config.micr
    right_x = layout.check_width - band.right_margin_in * INCH
    left_limit = MICR_LEFT_CLEARANCE_IN * INCH
    for check in checks:
        micr = format_micr_line(
            config.account.routing_number,
            config.account.account_number,
            check.check_number,
            symbols=micr_registration.symbols,
            field_order=band.field_order,
        )
        line_width = pdfmetrics.stringWidth(micr, micr_registration.font_name, band.font_size_pt)
        left_x = right_x - line_width
        if left_x < left_limit:
            raise ValueError(
                f"MICR line is too wide for check {check.check_number}: it extends within "
                f"{left_x / INCH:.3f} in of the left edge (need >= {MICR_LEFT_CLEARANCE_IN} in). "
                "Use a wider check layout or a smaller MICR font."
            )


def _draw_back_check(
    canvas: Canvas, x: float, y: float, layout: Layout, check: Check, config: AppConfig
) -> None:
    width = layout.check_width
    height = layout.check_height
    canvas.saveState()
    _draw_cut_marks(canvas, x, y, width, height, respect_clear_band=False)
    canvas.setStrokeGray(0.10)
    _draw_check_border(canvas, x, y, width, height, respect_clear_band=False)
    draw_background(canvas, x + 8, y + 12, width - 16, height - 24, config.pattern)

    canvas.setFillGray(0)
    canvas.setStrokeGray(0)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(x + 18, y + height - 26, "ENDORSE HERE")
    canvas.setFont("Helvetica", 6)
    for line_index in range(3):
        line_y = y + height - 46 - line_index * 18
        _line(canvas, x + 18, line_y, x + width - 18, line_y)

    restricted_y = y + height * 0.42
    canvas.setFont("Helvetica-Bold", 5.5)
    canvas.drawCentredString(
        x + width / 2, restricted_y + 8, "DO NOT WRITE, STAMP, OR SIGN BELOW THIS LINE"
    )
    _line(canvas, x + 12, restricted_y, x + width - 12, restricted_y)
    canvas.setFont("Helvetica", 5)
    canvas.drawCentredString(x + width / 2, y + 18, f"Processing area - check {check.check_number}")
    canvas.restoreState()


def _draw_check_border(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    respect_clear_band: bool,
) -> None:
    """Draw the check outline, keeping it out of the MICR clear band on the front.

    When ``respect_clear_band`` is set, the bottom edge is raised to the top of
    the 5/8" clear band and the side rules stop there, so the band holds only the
    MICR line (per ANSI X9). Otherwise a full rectangle is drawn.
    """
    if not respect_clear_band:
        canvas.rect(x, y, width, height, stroke=1, fill=0)
        return
    band_top = y + CLEAR_BAND_IN * INCH
    canvas.line(x, band_top, x, y + height)  # left
    canvas.line(x + width, band_top, x + width, y + height)  # right
    canvas.line(x, y + height, x + width, y + height)  # top
    canvas.line(x, band_top, x + width, band_top)  # clear-band tear line


def _draw_cut_marks(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    respect_clear_band: bool,
) -> None:
    canvas.saveState()
    canvas.setStrokeGray(0.35)
    canvas.setLineWidth(0.3)
    mark = 8
    # The bottom corner ticks would intrude into the clear band on the front, so
    # drop their inward (upward) portion there and keep only the outward tick.
    for corner_x in (x, x + width):
        if respect_clear_band:
            canvas.line(corner_x, y - mark, corner_x, y)
        else:
            canvas.line(corner_x, y - mark, corner_x, y + mark)
        canvas.line(corner_x, y + height - mark, corner_x, y + height + mark)
    for corner_y in (y, y + height):
        canvas.line(x - mark, corner_y, x + mark, corner_y)
        canvas.line(x + width - mark, corner_y, x + width + mark, corner_y)
    canvas.restoreState()


def _draw_registration_marks(canvas: Canvas) -> None:
    canvas.saveState()
    canvas.setStrokeGray(0.30)
    canvas.setLineWidth(0.4)
    for x, y in ((0.35 * INCH, 0.35 * INCH), (8.15 * INCH, 10.65 * INCH)):
        canvas.circle(x, y, 5, stroke=1, fill=0)
        canvas.line(x - 8, y, x + 8, y)
        canvas.line(x, y - 8, x, y + 8)
    canvas.restoreState()


def _line(canvas: Canvas, x1: float, y1: float, x2: float, y2: float) -> None:
    canvas.setLineWidth(0.5)
    canvas.line(x1, y1, x2, y2)


T = TypeVar("T")


def _chunks(items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
