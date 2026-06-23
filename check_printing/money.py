from __future__ import annotations

from decimal import Decimal

ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
SCALES = ("", "thousand", "million", "billion")


def amount_to_words(amount: Decimal) -> str:
    normalized = amount.quantize(Decimal("0.01"))
    if normalized < 0:
        raise ValueError("amount cannot be negative")

    dollars = int(normalized)
    cents = int((normalized - dollars) * 100)
    dollar_words = _integer_to_words(dollars)
    dollar_unit = "dollar" if dollars == 1 else "dollars"
    cent_unit = "cent" if cents == 1 else "cents"
    return f"{dollar_words} {dollar_unit} and {cents:02d}/100 {cent_unit}"


def _integer_to_words(value: int) -> str:
    if value == 0:
        return "zero"
    if value < 0:
        raise ValueError("value cannot be negative")

    parts: list[str] = []
    scale_index = 0
    while value:
        value, chunk = divmod(value, 1000)
        if chunk:
            scale = SCALES[scale_index]
            chunk_words = _chunk_to_words(chunk)
            parts.append(f"{chunk_words} {scale}".strip())
        scale_index += 1
        if scale_index >= len(SCALES) and value:
            raise ValueError("value is too large")
    return " ".join(reversed(parts))


def _chunk_to_words(value: int) -> str:
    words: list[str] = []
    hundreds, remainder = divmod(value, 100)
    if hundreds:
        words.extend((ONES[hundreds], "hundred"))
    if remainder >= 20:
        tens, ones = divmod(remainder, 10)
        words.append(TENS[tens] if ones == 0 else f"{TENS[tens]}-{ONES[ones]}")
    elif remainder:
        words.append(ONES[remainder])
    return " ".join(words)
