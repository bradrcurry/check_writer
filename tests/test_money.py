from __future__ import annotations

from decimal import Decimal

import pytest
from check_printing.money import amount_to_words


def test_amount_to_words_formats_dollars_and_cents() -> None:
    assert (
        amount_to_words(Decimal("1234.05"))
        == "one thousand two hundred thirty-four dollars and 05/100 cents"
    )


def test_amount_to_words_uses_singular_units() -> None:
    assert amount_to_words(Decimal("1.01")) == "one dollar and 01/100 cent"


def test_amount_to_words_rejects_negative_amount() -> None:
    with pytest.raises(ValueError, match="negative"):
        amount_to_words(Decimal("-1.00"))
