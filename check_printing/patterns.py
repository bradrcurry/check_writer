from __future__ import annotations

import math
from itertools import pairwise

from reportlab.pdfgen.canvas import Canvas

from check_printing.models import BackgroundStyle, PatternSettings


def gray_from_intensity(intensity: float) -> float:
    return max(0.80, min(0.98, 1.0 - intensity))


def draw_background(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    settings: PatternSettings,
) -> None:
    if settings.style == BackgroundStyle.NONE:
        return
    canvas.saveState()
    canvas.setStrokeGray(gray_from_intensity(settings.intensity))
    canvas.setFillGray(gray_from_intensity(settings.intensity))
    if settings.style == BackgroundStyle.DIAGONAL:
        _draw_diagonal(canvas, x, y, width, height, spacing=10)
    elif settings.style == BackgroundStyle.CROSSHATCH:
        _draw_diagonal(canvas, x, y, width, height, spacing=12)
        _draw_diagonal(canvas, x, y, width, height, spacing=12, reverse=True)
    else:
        _draw_guilloche(canvas, x, y, width, height)
    _draw_microtext(canvas, x, y, width, height, settings.microtext)
    canvas.restoreState()


def _draw_diagonal(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    spacing: float,
    reverse: bool = False,
) -> None:
    canvas.setLineWidth(0.25)
    start = -height
    end = width + height
    current = start
    while current <= end:
        if reverse:
            canvas.line(x + current, y, x + current - height, y + height)
        else:
            canvas.line(x + current, y, x + current + height, y + height)
        current += spacing


def _draw_guilloche(canvas: Canvas, x: float, y: float, width: float, height: float) -> None:
    canvas.setLineWidth(0.3)
    center_y = y + height * 0.55
    amplitude = height * 0.12
    step = 5.0
    for phase in (0.0, math.pi / 2, math.pi):
        points: list[tuple[float, float]] = []
        current_x = x + 12
        while current_x <= x + width - 12:
            relative = (current_x - x) / width
            wave_y = center_y + math.sin(relative * math.tau * 3 + phase) * amplitude
            points.append((current_x, wave_y))
            current_x += step
        for start, end in pairwise(points):
            canvas.line(start[0], start[1], end[0], end[1])


def _draw_microtext(
    canvas: Canvas, x: float, y: float, width: float, height: float, text: str
) -> None:
    canvas.setFont("Helvetica", 3.2)
    repeated = (text + " ") * 30
    canvas.drawString(x + 6, y + height - 7, repeated[:120])
    canvas.drawString(x + 6, y + 5, repeated[:120])
