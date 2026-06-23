from __future__ import annotations

from datetime import date
from decimal import Decimal

from check_printing.models import CheckStatus
from check_printing.storage import RegisterEntry
from check_printing.ui import (
    WRITE_MODES,
    _checks_from_manual_rows,
    _drift_mm_to_offset_in,
    _page_labels,
    _selected_entry,
)


def _entry(entry_id: int, check_number: int) -> RegisterEntry:
    return RegisterEntry(
        id=entry_id,
        account_id="sample",
        check_number=check_number,
        check_date=date(2026, 6, 23),
        payee="Payee",
        amount=Decimal("10.00"),
        memo="",
        status=CheckStatus.PRINTED,
        pdf_path=None,
        pdf_hash=None,
        created_at="2026-06-23T00:00:00+00:00",
        printed_at=None,
        notes="",
        cleared_date=None,
    )


def test_checks_from_manual_rows_uses_selected_rows() -> None:
    checks = _checks_from_manual_rows(
        [
            {
                "include": True,
                "check_number": 1001,
                "payee": "Power Co",
                "amount": "123.45",
                "date": "2026-06-23",
                "memo": "Electric",
            },
            {
                "include": False,
                "check_number": 1002,
                "payee": "Water Co",
                "amount": "67.89",
                "date": "2026-06-24",
                "memo": "Water",
            },
        ]
    )

    assert len(checks) == 1
    assert checks[0].check_number == 1001
    assert checks[0].payee == "Power Co"


def test_page_labels_alternate_front_back_per_sheet() -> None:
    assert _page_labels(4) == [
        "Sheet 1 — Front",
        "Sheet 1 — Back",
        "Sheet 2 — Front",
        "Sheet 2 — Back",
    ]


def test_selected_entry_returns_row_by_index() -> None:
    entries = [_entry(1, 1001), _entry(2, 1002)]
    selection = {"selection": {"rows": [1]}}

    assert _selected_entry(entries, selection) is entries[1]


def test_selected_entry_handles_no_selection() -> None:
    entries = [_entry(1, 1001)]

    assert _selected_entry(entries, None) is None
    assert _selected_entry(entries, {"selection": {"rows": []}}) is None
    assert _selected_entry(entries, {"selection": {"rows": [5]}}) is None


def test_write_modes_cover_single_sheet_and_csv() -> None:
    assert WRITE_MODES == ("Single check", "Six-up sheet", "From CSV")


def test_drift_to_offset_cancels_drift() -> None:
    # 2.54 mm of rightward drift -> -0.1 in correction.
    assert _drift_mm_to_offset_in(2.54) == -0.1
    assert _drift_mm_to_offset_in(-2.54) == 0.1
    assert _drift_mm_to_offset_in(0.0) == 0.0
