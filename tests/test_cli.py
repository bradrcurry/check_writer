from __future__ import annotations

import csv
from decimal import Decimal

import pytest
import typer
from check_printing.cli import (
    _ensure_register_numbers_available,
    _parse_amount,
    blank_checks,
    export_register,
    load_checks_csv,
)
from check_printing.config import save_config
from check_printing.models import AppConfig, Check
from check_printing.storage import CheckRegister


def test_parse_amount_accepts_decimal_string() -> None:
    assert _parse_amount("123.45") == Decimal("123.45")


def test_parse_amount_rejects_invalid_decimal() -> None:
    with pytest.raises(typer.BadParameter):
        _parse_amount("not-money")


def test_blank_checks_create_six_blank_checks() -> None:
    checks = blank_checks(2000)

    assert [check.check_number for check in checks] == [2000, 2001, 2002, 2003, 2004, 2005]
    assert all(check.is_blank for check in checks)
    assert all(check.payee == "" for check in checks)


def test_load_checks_csv_assigns_missing_check_numbers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    csv_path = tmp_path / "checks.csv"
    csv_path.write_text(
        "payee,amount,memo,date\n"
        "Power Co,123.45,Electric,2026-06-23\n"
        "Water Co,67.89,Water,2026-06-24\n",
        encoding="utf-8",
    )
    register = CheckRegister(tmp_path / "register.sqlite3")

    checks = load_checks_csv(csv_path, register, "acct")

    assert [check.check_number for check in checks] == [1001, 1002]
    assert checks[0].payee == "Power Co"
    assert checks[0].memo == "Electric"


def test_load_checks_csv_rejects_duplicate_numbers_in_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    csv_path = tmp_path / "checks.csv"
    csv_path.write_text(
        "check_number,payee,amount\n1005,Power Co,123.45\n1005,Water Co,67.89\n",
        encoding="utf-8",
    )
    register = CheckRegister(tmp_path / "register.sqlite3")

    with pytest.raises(typer.BadParameter, match="duplicate check_number"):
        load_checks_csv(csv_path, register, "acct")


def test_register_preflight_rejects_existing_numbers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    register = CheckRegister(tmp_path / "register.sqlite3")
    check = Check(check_number=1001, payee="Power Co", amount=Decimal("123.45"))
    register.add_check("acct", check)

    with pytest.raises(typer.BadParameter, match="already exist"):
        _ensure_register_numbers_available(register, "acct", [check], allow_reprint=False)


def test_export_register_writes_valid_csv(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "register.sqlite3"
    config_path = tmp_path / "config.yaml"
    output_path = tmp_path / "register.csv"
    save_config(AppConfig(database_path=db_path), config_path)
    register = CheckRegister(db_path)
    check = Check(check_number=1001, payee='Power, "Co"', amount=Decimal("123.45"), memo="A,B")
    register.add_check("sample", check, pdf_hash="abc123")

    export_register(config_path=str(config_path), output=str(output_path))

    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["payee"] == 'Power, "Co"'
    assert rows[0]["memo"] == "A,B"
    assert rows[0]["pdf_hash"] == "abc123"
