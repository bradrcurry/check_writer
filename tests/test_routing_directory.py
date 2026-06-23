from __future__ import annotations

from check_printing.routing_directory import (
    load_routing_directory,
    lookup_routing_number,
    search_bank_name,
)


def test_loads_fedach_fixed_width_directory(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "fedach.txt"
    line = (
        "011000015"
        "O"
        "011000015"
        "1"
        "010126"
        "000000000"
        f"{'EXAMPLE BANK':<36}"
        f"{'100 BANK AVE':<36}"
        f"{'ANYTOWN':<20}"
        "NY"
        "10001"
        "0000"
        "212"
        "555"
        "0100"
        "1"
        "1"
        "     "
    )
    path.write_text(line + "\n", encoding="utf-8")

    entries = load_routing_directory(path)

    assert len(entries) == 1
    assert entries[0].routing_number == "011000015"
    assert entries[0].customer_name == "EXAMPLE BANK"
    assert entries[0].bank_address_lines == ["100 BANK AVE", "ANYTOWN, NY 10001-0000"]
    assert entries[0].phone == "(212) 555-0100"


def test_loads_csv_directory_and_searches(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "routing.csv"
    path.write_text(
        "\n".join(
            [
                "routing_number,bank_name,address,city,state,zip,phone",
                "011000015,Example Bank,100 Bank Ave,Anytown,NY,10001,212-555-0100",
                "021000021,Other Bank,200 Wire St,New York,NY,10005,212-555-0200",
            ]
        ),
        encoding="utf-8",
    )

    entries = load_routing_directory(path)

    assert lookup_routing_number(entries, "011000015")[0].customer_name == "Example Bank"
    assert [entry.routing_number for entry in search_bank_name(entries, "example")] == [
        "011000015"
    ]
    assert search_bank_name(entries, "missing") == []


def test_routing_lookup_normalizes_punctuation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "routing.csv"
    path.write_text(
        "Routing Number,Institution Name,City,State\n011000015,Example National Bank,Anytown,NY\n",
        encoding="utf-8",
    )
    entries = load_routing_directory(path)

    assert lookup_routing_number(entries, "011-000-015")
    assert search_bank_name(entries, "example bank")
