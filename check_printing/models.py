from __future__ import annotations

from datetime import date as dt_date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from check_printing.micr import MicrFieldOrder, MicrSymbolMap


class CheckStatus(StrEnum):
    DRAFT = "draft"
    PRINTED = "printed"
    VOIDED = "voided"
    REPRINTED = "reprinted"
    CLEARED = "cleared"


class BackgroundStyle(StrEnum):
    GUILLOCHE = "guilloche"
    DIAGONAL = "diagonal"
    CROSSHATCH = "crosshatch"
    NONE = "none"


class AccountProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: str = "sample"
    payor_name: str = "Sample Payor"
    payor_address: list[str] = Field(
        default_factory=lambda: ["123 Example St", "Anytown, NY 10001"]
    )
    bank_name: str = "Example Bank"
    bank_address: list[str] = Field(default_factory=lambda: ["100 Bank Ave", "Anytown, NY 10001"])
    routing_number: str = "011000015"
    account_number: str = "000123456789"
    fractional_routing_number: str | None = None
    void_after_days: int | None = 90

    @field_validator("routing_number")
    @classmethod
    def routing_number_must_be_digits(cls, value: str) -> str:
        if len(value) != 9 or not value.isdigit():
            raise ValueError("routing_number must be exactly 9 digits")
        return value


class Check(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_number: int
    payee: str
    amount: Decimal
    date: dt_date = Field(default_factory=dt_date.today)
    memo: str = ""
    written_amount: str | None = None
    is_blank: bool = False

    @field_validator("check_number")
    @classmethod
    def check_number_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("check_number must be positive")
        return value

    @field_validator("amount")
    @classmethod
    def amount_must_be_non_negative(cls, value: Decimal) -> Decimal:
        if value < Decimal("0"):
            raise ValueError("amount cannot be negative")
        return value.quantize(Decimal("0.01"))


class Calibration(BaseModel):
    model_config = ConfigDict(frozen=True)

    front_x_offset_in: float = 0.0
    front_y_offset_in: float = 0.0
    back_x_offset_in: float = 0.0
    back_y_offset_in: float = 0.0


class DuplexFlip(StrEnum):
    LONG_EDGE = "long_edge"
    SHORT_EDGE = "short_edge"


class MicrSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    # E-13B is a fixed 8 CPI (0.125 in/char) font. With GnuMICR-compatible
    # metrics, 12pt renders at ~8.0 CPI; adjust for fonts with different metrics.
    font_size_pt: float = 12.0
    # ANSI X9 clear band is the bottom 5/8". Baseline default ~3/16" above the
    # check bottom edge keeps the glyphs inside the readable band.
    baseline_from_bottom_in: float = 0.1875
    right_margin_in: float = 0.25
    # Personal checks carry the serial in the on-us field after the account;
    # business checks use a separate auxiliary on-us field. See MicrFieldOrder.
    field_order: MicrFieldOrder = MicrFieldOrder.PERSONAL
    # Which ASCII->symbol convention the MICR font uses. 'auto' suits GnuMICR and
    # Unicode-mapped fonts; set explicitly for fonts that swap on-us/amount.
    symbol_map: MicrSymbolMap = MicrSymbolMap.AUTO

    @field_validator("baseline_from_bottom_in")
    @classmethod
    def baseline_within_clear_band(cls, value: float) -> float:
        if not 0.0 <= value <= 0.625:
            raise ValueError("baseline_from_bottom_in must be within the 0.625in clear band")
        return value

    @field_validator("font_size_pt")
    @classmethod
    def font_size_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("font_size_pt must be positive")
        return value

    @field_validator("right_margin_in")
    @classmethod
    def right_margin_must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("right_margin_in cannot be negative")
        return value


class PatternSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    style: BackgroundStyle = BackgroundStyle.GUILLOCHE
    intensity: float = 0.08
    microtext: str = "AUTHORIZED DOCUMENT"

    @field_validator("intensity")
    @classmethod
    def intensity_must_be_light(cls, value: float) -> float:
        if not 0.0 <= value <= 0.20:
            raise ValueError("intensity must be between 0.0 and 0.20")
        return value


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    account: AccountProfile = Field(default_factory=AccountProfile)
    micr_font_path: Path | None = None
    micr: MicrSettings = Field(default_factory=MicrSettings)
    layout: str = "reliable_6up"
    layout_templates_path: Path | None = None
    routing_directory_path: Path | None = None
    duplex_flip: DuplexFlip = DuplexFlip.LONG_EDGE
    output_dir: Path = Path("outputs")
    database_path: Path = Path("check_register.sqlite3")
    fake_test_mode: bool = True
    calibration: Calibration = Field(default_factory=Calibration)
    pattern: PatternSettings = Field(default_factory=PatternSettings)
