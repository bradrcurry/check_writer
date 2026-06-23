from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from check_printing.models import Check, CheckStatus
from check_printing.storage import CheckRegister


def test_register_prevents_duplicate_check_numbers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    register = CheckRegister(tmp_path / "checks.sqlite3")
    check = Check(check_number=1001, payee="Sample", amount=Decimal("1.23"))

    register.add_check("acct", check)

    with pytest.raises(ValueError, match="already exists"):
        register.add_check("acct", check)


def test_register_allows_audited_reprint(tmp_path) -> None:  # type: ignore[no-untyped-def]
    register = CheckRegister(tmp_path / "checks.sqlite3")
    check = Check(check_number=1001, payee="Sample", amount=Decimal("1.23"))

    register.add_check("acct", check)
    register.add_check("acct", check, allow_reprint=True)

    entries = register.list_entries()
    assert len(entries) == 2
    assert entries[-1].status == CheckStatus.REPRINTED


def test_reprint_can_store_audit_note(tmp_path) -> None:  # type: ignore[no-untyped-def]
    register = CheckRegister(tmp_path / "checks.sqlite3")
    check = Check(check_number=1001, payee="Sample", amount=Decimal("1.23"))

    register.add_check("acct", check)
    register.add_check("acct", check, allow_reprint=True, notes="Printer jam")

    entry = register.list_entries()[-1]
    assert entry.status == CheckStatus.REPRINTED
    assert entry.notes == "Printer jam"


def test_register_marks_status(tmp_path) -> None:  # type: ignore[no-untyped-def]
    register = CheckRegister(tmp_path / "checks.sqlite3")
    check = Check(check_number=1001, payee="Sample", amount=Decimal("1.23"))

    register.add_check("acct", check)
    register.mark_status("acct", 1001, CheckStatus.VOIDED, notes="bad stock")

    entry = register.list_entries()[0]
    assert entry.status == CheckStatus.VOIDED
    assert entry.notes == "bad stock"


def test_register_stores_pdf_hash(tmp_path) -> None:  # type: ignore[no-untyped-def]
    register = CheckRegister(tmp_path / "checks.sqlite3")
    check = Check(check_number=1001, payee="Sample", amount=Decimal("1.23"))

    register.add_check("acct", check, pdf_hash="abc123")

    assert register.list_entries()[0].pdf_hash == "abc123"


def test_register_marks_printed_with_timestamp(tmp_path) -> None:  # type: ignore[no-untyped-def]
    register = CheckRegister(tmp_path / "checks.sqlite3")
    check = Check(check_number=1001, payee="Sample", amount=Decimal("1.23"))
    register.add_check("acct", check, status=CheckStatus.DRAFT)

    register.mark_printed("acct", 1001, notes="confirmed")

    entry = register.list_entries()[0]
    assert entry.status == CheckStatus.PRINTED
    assert entry.printed_at is not None
    assert entry.notes == "confirmed"


def test_register_marks_cleared_with_date(tmp_path) -> None:  # type: ignore[no-untyped-def]
    register = CheckRegister(tmp_path / "checks.sqlite3")
    check = Check(check_number=1001, payee="Sample", amount=Decimal("1.23"))
    register.add_check("acct", check, status=CheckStatus.PRINTED)

    register.mark_cleared("acct", 1001, cleared_date=date(2026, 6, 23), notes="bank posted")

    entry = register.list_entries()[0]
    assert entry.status == CheckStatus.CLEARED
    assert entry.cleared_date == date(2026, 6, 23)
    assert entry.notes == "bank posted"


def test_status_update_rejects_missing_check(tmp_path) -> None:  # type: ignore[no-untyped-def]
    register = CheckRegister(tmp_path / "checks.sqlite3")

    with pytest.raises(ValueError, match="does not exist"):
        register.mark_printed("acct", 9999)


def test_register_migrates_older_schema(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "checks.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                check_number INTEGER NOT NULL,
                check_date TEXT NOT NULL,
                payee TEXT NOT NULL,
                amount TEXT NOT NULL,
                memo TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO checks (
                account_id, check_number, check_date, payee, amount, memo, status
            )
            VALUES ('acct', 1001, '2026-06-23', 'Sample', '1.23', '', 'draft')
            """
        )

    register = CheckRegister(db_path)

    entry = register.list_entries()[0]
    assert entry.pdf_hash is None
    assert entry.notes == ""
    assert entry.created_at == ""
