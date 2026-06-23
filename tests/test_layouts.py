from __future__ import annotations

import pytest
from check_printing.templates import INCH, PAGE_HEIGHT, PAGE_WIDTH, get_layout, load_layouts


def test_reliable_layout_positions_are_inside_page() -> None:
    layout = get_layout("reliable_6up")

    assert layout.per_page == 6
    for x, y in layout.front_positions():
        assert x >= 0
        assert y >= 0
        assert x + layout.slot_width <= PAGE_WIDTH
        assert y + layout.slot_height <= PAGE_HEIGHT


def test_back_positions_default_is_long_edge_column_mirror() -> None:
    layout = get_layout("reliable_6up")

    front = layout.front_positions()
    back = layout.back_positions()

    assert back == layout.back_positions("long_edge")
    assert front[0][1] == back[0][1]  # same row band
    assert front[0][0] == back[2][0]  # columns mirrored
    assert front[1][0] == back[1][0]
    assert front[2][0] == back[0][0]


def test_long_edge_flip_mirrors_columns_keeps_rows() -> None:
    layout = get_layout("reliable_6up")
    front = layout.front_positions()
    back = layout.back_positions("long_edge")

    # Front slot i overlays back slot i after a left-edge flip: x mirrors about
    # the page center, y is unchanged.
    page_center = PAGE_WIDTH / 2
    for (fx, fy), (bx, by) in zip(front, back, strict=True):
        assert fy == by
        assert abs((page_center - fx) - (bx + layout.slot_width - page_center)) < 1e-6


def test_short_edge_flip_mirrors_rows_keeps_columns() -> None:
    layout = get_layout("reliable_6up")
    front = layout.front_positions()
    back = layout.back_positions("short_edge")

    page_center = PAGE_HEIGHT / 2
    for (fx, fy), (bx, by) in zip(front, back, strict=True):
        assert fx == bx
        assert abs((page_center - fy) - (by + layout.slot_height - page_center)) < 1e-6


def test_back_positions_rejects_unknown_flip() -> None:
    layout = get_layout("reliable_6up")
    with pytest.raises(ValueError, match="duplex flip"):
        layout.back_positions("diagonal")


def test_builtin_layouts_load_from_yaml() -> None:
    layouts = load_layouts()

    assert set(layouts) == {
        "max_density_6up",
        "reliable_6up",
        "large_6up",
        "standard_3up",
    }
    assert layouts["reliable_6up"].check_width == 5.0 * INCH


def test_new_layouts_fit_inside_page() -> None:
    for name in ("large_6up", "standard_3up"):
        layout = get_layout(name)
        for x, y in layout.front_positions():
            assert x >= 0
            assert y >= 0
            assert x + layout.slot_width <= PAGE_WIDTH + 1e-6
            assert y + layout.slot_height <= PAGE_HEIGHT + 1e-6


def test_standard_3up_is_single_column_non_rotated() -> None:
    layout = get_layout("standard_3up")

    assert layout.per_page == 3
    assert layout.columns == 1
    assert layout.rows == 3
    assert layout.rotated is False
    # Full-size personal check footprint.
    assert layout.check_width == 6.0 * INCH
    assert layout.check_height == 2.75 * INCH


def test_single_column_accepts_both_flips() -> None:
    # A single-column grid aligns correctly under either flip (the mirror is a
    # no-op along the absent axis); orientation is handled in the PDF generator.
    layout = get_layout("standard_3up")

    assert layout.duplex_flip_warning("long_edge") is None
    assert layout.duplex_flip_warning("short_edge") is None


def test_multi_column_has_no_flip_warning() -> None:
    layout = get_layout("reliable_6up")

    assert layout.duplex_flip_warning("long_edge") is None
    assert layout.duplex_flip_warning("short_edge") is None


def test_unknown_flip_warns() -> None:
    layout = get_layout("reliable_6up")

    assert layout.duplex_flip_warning("diagonal") is not None


def test_standard_3up_meets_ansi_dimensions() -> None:
    layout = get_layout("standard_3up")

    assert layout.is_ansi_compliant_size
    assert layout.dimension_warning() is None


def test_compact_6up_layouts_warn_on_dimensions() -> None:
    for name in ("reliable_6up", "max_density_6up", "large_6up"):
        layout = get_layout(name)
        assert not layout.is_ansi_compliant_size
        warning = layout.dimension_warning()
        assert warning is not None
        assert "below bank-spec" in warning


def test_custom_layout_template_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    template_path = tmp_path / "layouts.yaml"
    template_path.write_text(
        """
layouts:
  custom:
    check_width_in: 4.0
    check_height_in: 2.0
    columns: 2
    rows: 2
    rotated: false
""",
        encoding="utf-8",
    )

    layout = get_layout("custom", template_path)

    assert layout.per_page == 4
    assert layout.check_width == 4.0 * INCH
    assert layout.slot_width == layout.check_width


def test_layout_template_requires_layout_mapping(tmp_path) -> None:  # type: ignore[no-untyped-def]
    template_path = tmp_path / "bad.yaml"
    template_path.write_text("not_layouts: {}", encoding="utf-8")

    with pytest.raises(ValueError, match="layouts"):
        load_layouts(template_path)
