from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from check_printing.templates import INCH, PAGE_HEIGHT, PAGE_WIDTH, Layout, get_layout


def generate_calibration_pdf(
    output_path: Path,
    layout_name: str = "reliable_6up",
    layout_templates_path: Path | None = None,
    duplex_flip: str = "long_edge",
) -> Path:
    layout = get_layout(layout_name, layout_templates_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(output_path), pagesize=letter)

    canvas.setTitle("Check Printing Calibration")
    _draw_grid(canvas)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(
        0.5 * INCH, PAGE_HEIGHT - 0.35 * INCH, "Calibration Page - Print at Actual Size / 100%"
    )
    canvas.setFont("Helvetica", 8)
    canvas.drawString(
        0.5 * INCH,
        PAGE_HEIGHT - 0.52 * INCH,
        "Measure ruler drift and update config.local.yaml offsets in inches.",
    )

    for slot, (x, y) in enumerate(layout.front_positions(), start=1):
        canvas.setLineWidth(0.8)
        canvas.rect(x, y, layout.slot_width, layout.slot_height, stroke=1, fill=0)
        canvas.setFont("Helvetica", 6)
        canvas.drawString(
            x + 8,
            y + layout.slot_height - 12,
            f"{layout.name}: {layout.check_width / INCH:.3f} x {layout.check_height / INCH:.3f} in",
        )
        _draw_slot_marker(canvas, x, y, layout, f"FRONT {slot}")

    canvas.showPage()
    _draw_grid(canvas)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(
        0.5 * INCH,
        PAGE_HEIGHT - 0.35 * INCH,
        f"Duplex Back Alignment Page ({duplex_flip})",
    )
    canvas.setFont("Helvetica", 8)
    canvas.drawString(
        0.5 * INCH,
        PAGE_HEIGHT - 0.52 * INCH,
        "Print duplex, hold to light: each FRONT n must align with BACK n. If not, switch flip mode.",
    )
    for slot, (x, y) in enumerate(layout.back_positions(duplex_flip), start=1):
        canvas.rect(x, y, layout.slot_width, layout.slot_height, stroke=1, fill=0)
        _draw_slot_marker(canvas, x, y, layout, f"BACK {slot}")

    canvas.save()
    return output_path


def _draw_grid(canvas: Canvas) -> None:
    canvas.saveState()
    canvas.setStrokeGray(0.85)
    canvas.setLineWidth(0.25)
    step = 0.25 * INCH
    current = 0.0
    while current <= PAGE_WIDTH:
        canvas.line(current, 0, current, PAGE_HEIGHT)
        current += step
    current = 0.0
    while current <= PAGE_HEIGHT:
        canvas.line(0, current, PAGE_WIDTH, current)
        current += step

    canvas.setStrokeGray(0.35)
    canvas.setLineWidth(0.6)
    for inch in range(9):
        x = inch * INCH
        canvas.line(x, 0, x, 0.25 * INCH)
        canvas.drawString(x + 2, 0.08 * INCH, str(inch))
    for inch in range(12):
        y = inch * INCH
        canvas.line(0, y, 0.25 * INCH, y)
        canvas.drawString(0.08 * INCH, y + 2, str(inch))
    canvas.restoreState()


def _draw_slot_marker(canvas: Canvas, x: float, y: float, layout: Layout, label: str) -> None:
    """Center crosshair plus a label anchored to the lower-left corner.

    The corner anchor is asymmetric, so a mismatched duplex flip makes front and
    back labels land in opposite corners instead of overlapping.
    """
    center_x = x + layout.slot_width / 2
    center_y = y + layout.slot_height / 2
    canvas.saveState()
    canvas.setStrokeGray(0.15)
    canvas.circle(center_x, center_y, 7, stroke=1, fill=0)
    canvas.line(center_x - 12, center_y, center_x + 12, center_y)
    canvas.line(center_x, center_y - 12, center_x, center_y + 12)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(x + 6, y + 6, label)
    canvas.restoreState()
