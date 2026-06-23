from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from check_printing.models import Check, CheckStatus

SCHEMA_VERSION = 1

REQUIRED_CHECK_COLUMNS = {
    "pdf_path": "TEXT",
    "pdf_hash": "TEXT",
    "created_at": "TEXT NOT NULL DEFAULT ''",
    "printed_at": "TEXT",
    "notes": "TEXT NOT NULL DEFAULT ''",
    "cleared_date": "TEXT",
}


@dataclass(frozen=True)
class RegisterEntry:
    id: int
    account_id: str
    check_number: int
    check_date: date
    payee: str
    amount: Decimal
    memo: str
    status: CheckStatus
    pdf_path: str | None
    pdf_hash: str | None
    created_at: str
    printed_at: str | None
    notes: str
    cleared_date: date | None


class CheckRegister:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True) if self.db_path.parent != Path(
            "."
        ) else None
        self._init_db()

    def add_check(
        self,
        account_id: str,
        check: Check,
        *,
        status: CheckStatus = CheckStatus.DRAFT,
        pdf_path: Path | None = None,
        pdf_hash: str | None = None,
        notes: str = "",
        allow_reprint: bool = False,
    ) -> int:
        if self.exists(account_id, check.check_number) and not allow_reprint:
            raise ValueError(
                f"Check number {check.check_number} already exists for account {account_id}"
            )

        entry_status = (
            CheckStatus.REPRINTED
            if allow_reprint and self.exists(account_id, check.check_number)
            else status
        )
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO checks (
                    account_id, check_number, check_date, payee, amount, memo, status,
                    pdf_path, pdf_hash, created_at, printed_at, notes, cleared_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    check.check_number,
                    check.date.isoformat(),
                    check.payee,
                    str(check.amount),
                    check.memo,
                    entry_status.value,
                    str(pdf_path) if pdf_path else None,
                    pdf_hash,
                    _now(),
                    _now()
                    if entry_status in {CheckStatus.PRINTED, CheckStatus.REPRINTED}
                    else None,
                    notes,
                    None,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a row id for inserted check")
            return cursor.lastrowid

    def exists(self, account_id: str, check_number: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM checks WHERE account_id = ? AND check_number = ? LIMIT 1",
                (account_id, check_number),
            ).fetchone()
        return row is not None

    def mark_status(
        self,
        account_id: str,
        check_number: int,
        status: CheckStatus,
        *,
        notes: str = "",
        cleared_date: date | None = None,
    ) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE checks
                SET status = ?, notes = ?, cleared_date = ?
                WHERE id = (
                    SELECT id FROM checks
                    WHERE account_id = ? AND check_number = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                """,
                (
                    status.value,
                    notes,
                    cleared_date.isoformat() if cleared_date else None,
                    account_id,
                    check_number,
                ),
            )
            _ensure_updated(cursor, account_id, check_number)

    def mark_printed(self, account_id: str, check_number: int, *, notes: str = "") -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE checks
                SET status = ?, printed_at = ?, notes = ?
                WHERE id = (
                    SELECT id FROM checks
                    WHERE account_id = ? AND check_number = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                """,
                (CheckStatus.PRINTED.value, _now(), notes, account_id, check_number),
            )
            _ensure_updated(cursor, account_id, check_number)

    def mark_cleared(
        self,
        account_id: str,
        check_number: int,
        *,
        cleared_date: date,
        notes: str = "",
    ) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE checks
                SET status = ?, cleared_date = ?, notes = ?
                WHERE id = (
                    SELECT id FROM checks
                    WHERE account_id = ? AND check_number = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                """,
                (
                    CheckStatus.CLEARED.value,
                    cleared_date.isoformat(),
                    notes,
                    account_id,
                    check_number,
                ),
            )
            _ensure_updated(cursor, account_id, check_number)

    def list_entries(self) -> list[RegisterEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, account_id, check_number, check_date, payee, amount, memo, status,
                       pdf_path, pdf_hash, created_at, printed_at, notes, cleared_date
                FROM checks
                ORDER BY check_number ASC, created_at ASC
                """
            ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    check_number INTEGER NOT NULL,
                    check_date TEXT NOT NULL,
                    payee TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    memo TEXT NOT NULL,
                    status TEXT NOT NULL,
                    pdf_path TEXT,
                    pdf_hash TEXT,
                    created_at TEXT NOT NULL,
                    printed_at TEXT,
                    notes TEXT NOT NULL DEFAULT '',
                    cleared_date TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checks_account_number ON checks(account_id, check_number)"
            )
            _ensure_schema_columns(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _row_to_entry(row: sqlite3.Row) -> RegisterEntry:
    return RegisterEntry(
        id=int(row["id"]),
        account_id=str(row["account_id"]),
        check_number=int(row["check_number"]),
        check_date=date.fromisoformat(str(row["check_date"])),
        payee=str(row["payee"]),
        amount=Decimal(str(row["amount"])),
        memo=str(row["memo"]),
        status=CheckStatus(str(row["status"])),
        pdf_path=str(row["pdf_path"]) if row["pdf_path"] is not None else None,
        pdf_hash=str(row["pdf_hash"]) if row["pdf_hash"] is not None else None,
        created_at=str(row["created_at"]),
        printed_at=str(row["printed_at"]) if row["printed_at"] is not None else None,
        notes=str(row["notes"]),
        cleared_date=date.fromisoformat(str(row["cleared_date"])) if row["cleared_date"] else None,
    )


def _ensure_schema_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(checks)").fetchall()
    }
    for column_name, column_definition in REQUIRED_CHECK_COLUMNS.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE checks ADD COLUMN {column_name} {column_definition}")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_updated(cursor: sqlite3.Cursor, account_id: str, check_number: int) -> None:
    if cursor.rowcount == 0:
        raise ValueError(f"Check number {check_number} does not exist for account {account_id}")
