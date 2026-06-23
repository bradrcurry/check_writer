import csv
from collections.abc import Sequence
from datetime import date as dt_date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import typer

from check_printing.calibration import generate_calibration_pdf
from check_printing.config import DEFAULT_CONFIG_PATH, load_config, save_config
from check_printing.files import sha256_file
from check_printing.micr import MicrFontRegistration
from check_printing.models import AppConfig, Check, CheckStatus
from check_printing.pdf_generator import prepare_checks_pdf, write_checks_pdf
from check_printing.storage import CheckRegister
from check_printing.templates import get_layout

app = typer.Typer(help="Generate print-ready duplex check PDFs.")


@app.command()
def init(
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
) -> None:
    """Create a local sample configuration file."""
    path = Path(config_path)
    if path.exists():
        raise typer.BadParameter(f"{path} already exists")
    save_config(AppConfig(), path)
    typer.echo(f"Created {path}. Review account data before real use.")


@app.command()
def generate(
    payee: str = typer.Option(..., help="Payee name."),
    amount: str = typer.Option(..., help="Check amount."),
    memo: str = typer.Option("", help="Memo text."),
    check_number: Optional[int] = typer.Option(None, help="Override check number."),
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
    output: Optional[str] = typer.Option(None, help="Output PDF path."),
    reprint: bool = typer.Option(
        False,
        "--reprint",
        help="Allow duplicate check number with reprint audit entry.",
    ),
) -> None:
    """Generate a single-check duplex PDF and record it in the local register."""
    config = load_config(Path(config_path))
    register = CheckRegister(config.database_path)
    number = check_number or _next_check_number(register, config.account.account_id)
    check = Check(check_number=number, payee=payee, amount=_parse_amount(amount), memo=memo)
    output_path = Path(output) if output else config.output_dir / f"check-{number}.pdf"
    micr_registration = prepare_checks_pdf([check], config)
    _echo_warnings(micr_registration, config)
    write_checks_pdf([check], config, output_path, micr_registration)
    pdf_hash = sha256_file(output_path)
    register.add_check(
        config.account.account_id,
        check,
        status=CheckStatus.PRINTED,
        pdf_path=output_path,
        pdf_hash=pdf_hash,
        allow_reprint=reprint,
    )
    typer.echo(f"Wrote {output_path}")


@app.command()
def batch(
    csv_path: str,
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
    output: str = typer.Option("outputs/batch-checks.pdf", help="Output PDF path."),
    reprint: bool = typer.Option(
        False,
        "--reprint",
        help="Allow duplicate check numbers with reprint audit entries.",
    ),
) -> None:
    """Generate a duplex PDF from a CSV file and record each check."""
    config = load_config(Path(config_path))
    register = CheckRegister(config.database_path)
    checks = load_checks_csv(Path(csv_path), register, config.account.account_id)
    _ensure_register_numbers_available(register, config.account.account_id, checks, reprint)
    output_path = Path(output)
    micr_registration = prepare_checks_pdf(checks, config)
    _echo_warnings(micr_registration, config)
    write_checks_pdf(checks, config, output_path, micr_registration)
    pdf_hash = sha256_file(output_path)
    for check in checks:
        register.add_check(
            config.account.account_id,
            check,
            status=CheckStatus.PRINTED,
            pdf_path=output_path,
            pdf_hash=pdf_hash,
            allow_reprint=reprint,
        )
    typer.echo(f"Wrote {output_path} with {len(checks)} checks")


@app.command("blank-sheet")
def blank_sheet(
    start_number: Optional[int] = typer.Option(None, help="First check number on the sheet."),
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
    output: str = typer.Option("outputs/blank-checks.pdf", help="Output PDF path."),
    reprint: bool = typer.Option(
        False,
        "--reprint",
        help="Allow duplicate check numbers with reprint audit entries.",
    ),
) -> None:
    """Generate a six-check blank sheet for later handwriting."""
    config = load_config(Path(config_path))
    register = CheckRegister(config.database_path)
    first_number = start_number or _next_check_number(register, config.account.account_id)
    checks = blank_checks(first_number)
    _ensure_register_numbers_available(register, config.account.account_id, checks, reprint)
    output_path = Path(output)
    micr_registration = prepare_checks_pdf(checks, config)
    _echo_warnings(micr_registration, config)
    write_checks_pdf(checks, config, output_path, micr_registration)
    pdf_hash = sha256_file(output_path)
    for check in checks:
        register.add_check(
            config.account.account_id,
            check,
            status=CheckStatus.PRINTED,
            pdf_path=output_path,
            pdf_hash=pdf_hash,
            notes="Printed as blank check stock",
            allow_reprint=reprint,
        )
    typer.echo(f"Wrote {output_path} with blank checks {first_number}-{first_number + 5}")


@app.command()
def calibration(
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
    output: str = typer.Option("outputs/calibration.pdf", help="Output PDF path."),
) -> None:
    """Generate a two-page calibration PDF."""
    config = load_config(Path(config_path))
    generate_calibration_pdf(
        Path(output),
        config.layout,
        config.layout_templates_path,
        config.duplex_flip.value,
    )
    typer.echo(f"Wrote {output}")


@app.command()
def void(
    check_number: int,
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
    notes: str = typer.Option("", help="Audit notes."),
) -> None:
    """Mark the latest entry for a check number voided."""
    config = load_config(Path(config_path))
    register = CheckRegister(config.database_path)
    register.mark_status(config.account.account_id, check_number, CheckStatus.VOIDED, notes=notes)
    typer.echo(f"Voided check {check_number}")


@app.command("mark-printed")
def mark_printed(
    check_number: int,
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
    notes: str = typer.Option("", help="Audit notes."),
) -> None:
    """Mark the latest entry for a check number printed."""
    config = load_config(Path(config_path))
    register = CheckRegister(config.database_path)
    register.mark_printed(config.account.account_id, check_number, notes=notes)
    typer.echo(f"Marked check {check_number} printed")


@app.command("mark-cleared")
def mark_cleared(
    check_number: int,
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
    cleared_date: Optional[str] = typer.Option(None, help="Cleared date as YYYY-MM-DD."),
    notes: str = typer.Option("", help="Audit notes."),
) -> None:
    """Mark the latest entry for a check number cleared."""
    parsed_date = _parse_date(cleared_date, row_number=0)
    config = load_config(Path(config_path))
    register = CheckRegister(config.database_path)
    register.mark_cleared(
        config.account.account_id,
        check_number,
        cleared_date=parsed_date,
        notes=notes,
    )
    typer.echo(f"Marked check {check_number} cleared on {parsed_date.isoformat()}")


@app.command()
def register(
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
) -> None:
    """Print the local check register."""
    config = load_config(Path(config_path))
    entries = CheckRegister(config.database_path).list_entries()
    for entry in entries:
        typer.echo(
            f"{entry.check_number} {entry.check_date.isoformat()} {entry.status.value:9} "
            f"${entry.amount:>10} {entry.payee}"
        )


@app.command("export-register")
def export_register(
    config_path: str = typer.Option(str(DEFAULT_CONFIG_PATH), help="YAML config path."),
    output: str = typer.Option("outputs/register.csv", help="Output CSV path."),
) -> None:
    """Export the register to CSV."""
    config = load_config(Path(config_path))
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    entries = CheckRegister(config.database_path).list_entries()
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "check_number",
                "date",
                "status",
                "amount",
                "payee",
                "memo",
                "pdf_path",
                "pdf_hash",
                "notes",
                "cleared_date",
            ],
        )
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "check_number": entry.check_number,
                    "date": entry.check_date.isoformat(),
                    "status": entry.status.value,
                    "amount": str(entry.amount),
                    "payee": entry.payee,
                    "memo": entry.memo,
                    "pdf_path": entry.pdf_path or "",
                    "pdf_hash": entry.pdf_hash or "",
                    "notes": entry.notes,
                    "cleared_date": entry.cleared_date.isoformat() if entry.cleared_date else "",
                }
            )
    typer.echo(f"Wrote {output_path}")


def _next_check_number(register: CheckRegister, account_id: str) -> int:
    entries = [
        entry.check_number for entry in register.list_entries() if entry.account_id == account_id
    ]
    return max(entries, default=1000) + 1


def load_checks_csv(path: Path, register: CheckRegister, account_id: str) -> list[Check]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise typer.BadParameter("CSV must include a header row")
        _validate_csv_headers(reader.fieldnames)
        next_number = _next_check_number(register, account_id)
        checks: list[Check] = []
        seen_numbers: set[int] = set()
        for row_number, row in enumerate(reader, start=2):
            check_number_text = _optional_text(row, "check_number")
            check_number = int(check_number_text) if check_number_text else next_number
            if check_number in seen_numbers:
                raise typer.BadParameter(
                    f"duplicate check_number {check_number} on row {row_number}"
                )
            seen_numbers.add(check_number)
            next_number = max(next_number, check_number + 1)
            checks.append(_check_from_csv_row(row, row_number, check_number))
    if not checks:
        raise typer.BadParameter("CSV did not contain any checks")
    return checks


def _validate_csv_headers(fieldnames: Sequence[str]) -> None:
    normalized = {field.strip() for field in fieldnames}
    missing = {"payee", "amount"} - normalized
    if missing:
        raise typer.BadParameter(f"CSV missing required columns: {', '.join(sorted(missing))}")


def _check_from_csv_row(row: dict[str, str], row_number: int, check_number: int) -> Check:
    payee = _required_text(row, "payee", row_number)
    amount = _parse_amount(_required_text(row, "amount", row_number))
    check_date = _parse_date(_optional_text(row, "date"), row_number)
    return Check(
        check_number=check_number,
        payee=payee,
        amount=amount,
        date=check_date,
        memo=_optional_text(row, "memo") or "",
        written_amount=_optional_text(row, "written_amount"),
    )


def _ensure_register_numbers_available(
    register: CheckRegister, account_id: str, checks: Sequence[Check], allow_reprint: bool
) -> None:
    if allow_reprint:
        return
    existing = [
        str(check.check_number)
        for check in checks
        if register.exists(account_id, check.check_number)
    ]
    if existing:
        raise typer.BadParameter(f"check numbers already exist: {', '.join(existing)}")


def _required_text(row: dict[str, str], key: str, row_number: int) -> str:
    value = _optional_text(row, key)
    if not value:
        raise typer.BadParameter(f"row {row_number} is missing {key}")
    return value


def _optional_text(row: dict[str, str], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_date(value: str | None, row_number: int) -> dt_date:
    if value is None:
        return dt_date.today()
    try:
        return dt_date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"row {row_number} date must use YYYY-MM-DD") from exc


def _parse_amount(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise typer.BadParameter("amount must be a decimal value such as 123.45") from exc


def _echo_micr_warning(registration: MicrFontRegistration) -> None:
    if registration.warning:
        typer.echo(f"WARNING: {registration.warning}", err=True)


def _echo_warnings(registration: MicrFontRegistration, config: AppConfig) -> None:
    _echo_micr_warning(registration)
    try:
        layout = get_layout(config.layout, config.layout_templates_path)
    except Exception:
        return
    for warning in (
        layout.duplex_flip_warning(config.duplex_flip.value),
        layout.dimension_warning(),
    ):
        if warning:
            typer.echo(f"WARNING: {warning}", err=True)


def sample_checks(start: int = 1001) -> list[Check]:
    return [
        Check(
            check_number=start + index,
            payee=f"Sample Payee {index + 1}",
            amount=Decimal("12.34"),
            memo="Sample",
        )
        for index in range(6)
    ]


def blank_checks(start: int, count: int = 6) -> list[Check]:
    return [
        Check(
            check_number=start + index,
            payee="",
            amount=Decimal("0.00"),
            memo="",
            is_blank=True,
        )
        for index in range(count)
    ]


@app.command("sample-pdf")
def sample_pdf(output: str = typer.Option("outputs/sample-checks.pdf")) -> None:
    """Generate an obvious fake six-check sample PDF."""
    config = AppConfig(fake_test_mode=True)
    checks = sample_checks()
    micr_registration = prepare_checks_pdf(checks, config)
    _echo_micr_warning(micr_registration)
    write_checks_pdf(checks, config, Path(output), micr_registration)
    typer.echo(f"Wrote {output}")
