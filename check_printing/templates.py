from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, cast

import yaml
from reportlab.lib.pagesizes import letter

INCH = 72.0
PAGE_WIDTH = cast(float, letter[0])
PAGE_HEIGHT = cast(float, letter[1])
DEFAULT_TEMPLATE_RESOURCE = "layout_templates.yaml"

# ANSI X9 / common check-stock dimension limits (inches). Checks outside these
# ranges are below bank-spec size; see README compliance notes.
MIN_CHECK_WIDTH_IN = 6.0
MAX_CHECK_WIDTH_IN = 8.75
MIN_CHECK_HEIGHT_IN = 2.75
MAX_CHECK_HEIGHT_IN = 3.66


@dataclass(frozen=True)
class Layout:
    name: str
    check_width: float
    check_height: float
    columns: int = 3
    rows: int = 2
    rotated: bool = True

    @property
    def per_page(self) -> int:
        return self.columns * self.rows

    @property
    def occupied_width(self) -> float:
        return self.columns * self.slot_width

    @property
    def occupied_height(self) -> float:
        return self.rows * self.slot_height

    @property
    def slot_width(self) -> float:
        return self.check_height if self.rotated else self.check_width

    @property
    def slot_height(self) -> float:
        return self.check_width if self.rotated else self.check_height

    @property
    def origin_x(self) -> float:
        return (PAGE_WIDTH - self.occupied_width) / 2

    @property
    def origin_y(self) -> float:
        return (PAGE_HEIGHT - self.occupied_height) / 2

    def front_positions(self) -> list[tuple[float, float]]:
        positions: list[tuple[float, float]] = []
        for row in range(self.rows):
            for col in range(self.columns):
                x = self.origin_x + col * self.slot_width
                y = PAGE_HEIGHT - self.origin_y - (row + 1) * self.slot_height
                positions.append((x, y))
        return positions

    @property
    def check_width_in(self) -> float:
        return self.check_width / INCH

    @property
    def check_height_in(self) -> float:
        return self.check_height / INCH

    @property
    def is_ansi_compliant_size(self) -> bool:
        return self.dimension_warning() is None

    def dimension_warning(self) -> str | None:
        """Warn if the check size falls outside ANSI/common bank-stock limits."""
        problems: list[str] = []
        if not MIN_CHECK_WIDTH_IN <= self.check_width_in <= MAX_CHECK_WIDTH_IN:
            problems.append(
                f"width {self.check_width_in:.3f} in is outside the "
                f"{MIN_CHECK_WIDTH_IN}-{MAX_CHECK_WIDTH_IN} in range"
            )
        if not MIN_CHECK_HEIGHT_IN <= self.check_height_in <= MAX_CHECK_HEIGHT_IN:
            problems.append(
                f"height {self.check_height_in:.3f} in is outside the "
                f"{MIN_CHECK_HEIGHT_IN}-{MAX_CHECK_HEIGHT_IN} in range"
            )
        if not problems:
            return None
        return (
            f"Layout {self.name!r} is below bank-spec check size ({'; '.join(problems)}). "
            "Use it for drafts or handwriting practice; for bank-accepted checks use an "
            "ANSI-size layout such as 'standard_3up'."
        )

    def duplex_flip_warning(self, flip: str) -> str | None:
        """Return a warning if the flip/grid combination needs attention.

        Both flips align correctly for a single-row or single-column grid (the
        mirror is simply a no-op along the absent axis), and back-content
        orientation is handled per flip axis in the PDF generator, so no warning
        is needed in those cases. Reserved for future grid-specific guidance.
        """
        if flip not in ("long_edge", "short_edge"):
            return f"Unknown duplex flip {flip!r}; use 'long_edge' or 'short_edge'."
        return None

    def back_positions(self, flip: str = "long_edge") -> list[tuple[float, float]]:
        """Slot positions for the back page so each back overlays its front.

        ``long_edge`` flips the sheet about its vertical edge (mirror columns);
        ``short_edge`` flips about its horizontal edge (mirror rows). This must
        match the printer/driver duplex setting or backs land on wrong checks.
        """
        if flip not in ("long_edge", "short_edge"):
            raise ValueError(f"Unknown duplex flip {flip!r}; use 'long_edge' or 'short_edge'")
        positions: list[tuple[float, float]] = []
        for row in range(self.rows):
            back_row = self.rows - 1 - row if flip == "short_edge" else row
            for col in range(self.columns):
                back_col = self.columns - 1 - col if flip == "long_edge" else col
                x = self.origin_x + back_col * self.slot_width
                y = PAGE_HEIGHT - self.origin_y - (back_row + 1) * self.slot_height
                positions.append((x, y))
        return positions


def get_layout(name: str, templates_path: Path | None = None) -> Layout:
    layouts = load_layouts(templates_path)
    try:
        return layouts[name]
    except KeyError as exc:
        choices = ", ".join(sorted(layouts))
        raise ValueError(f"Unknown layout {name!r}. Choose one of: {choices}") from exc


def load_layouts(templates_path: Path | None = None) -> dict[str, Layout]:
    data = _load_template_data(templates_path)
    raw_layouts = data.get("layouts")
    if not isinstance(raw_layouts, dict):
        raise ValueError("Layout template file must contain a 'layouts' mapping")

    layouts: dict[str, Layout] = {}
    for name, raw_layout in raw_layouts.items():
        if not isinstance(name, str) or not isinstance(raw_layout, dict):
            raise ValueError("Each layout template must be a mapping keyed by layout name")
        layouts[name] = _layout_from_mapping(name, raw_layout)
    return layouts


def _load_template_data(templates_path: Path | None) -> dict[str, Any]:
    if templates_path is None:
        text = (
            resources.files("check_printing")
            .joinpath(DEFAULT_TEMPLATE_RESOURCE)
            .read_text(encoding="utf-8")
        )
    else:
        text = templates_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("Layout template file must contain a YAML mapping")
    return data


def _layout_from_mapping(name: str, raw_layout: dict[str, Any]) -> Layout:
    try:
        check_width_in = float(raw_layout["check_width_in"])
        check_height_in = float(raw_layout["check_height_in"])
        columns = int(raw_layout["columns"])
        rows = int(raw_layout["rows"])
    except KeyError as exc:
        raise ValueError(f"Layout {name!r} is missing required field {exc.args[0]!r}") from exc

    return Layout(
        name=name,
        check_width=check_width_in * INCH,
        check_height=check_height_in * INCH,
        columns=columns,
        rows=rows,
        rotated=bool(raw_layout.get("rotated", True)),
    )
