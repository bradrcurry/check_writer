from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

FED_SEARCH_URL = "https://www.frbservices.org/resources/routing-number-directory"


@dataclass(frozen=True)
class RoutingDirectoryEntry:
    routing_number: str
    customer_name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone: str = ""

    @property
    def label(self) -> str:
        location = ", ".join(part for part in (self.city, self.state) if part)
        return f"{self.routing_number} | {self.customer_name} | {location}".strip(" |")

    @property
    def bank_address_lines(self) -> list[str]:
        line1 = self.address.strip()
        city_state_zip = " ".join(
            part
            for part in (
                ", ".join(item for item in (self.city, self.state) if item),
                self.zip_code,
            )
            if part
        )
        return [line for line in (line1, city_state_zip) if line]


def load_routing_directory(path: Path) -> list[RoutingDirectoryEntry]:
    if not path.exists():
        raise ValueError(f"Routing directory file not found: {path}")
    entries = _load_csv(path) if path.suffix.lower() == ".csv" else _load_fedach_fixed_width(path)
    if not entries:
        raise ValueError(f"No routing directory entries found in {path}")
    return entries


def lookup_routing_number(
    entries: list[RoutingDirectoryEntry], routing_number: str
) -> list[RoutingDirectoryEntry]:
    normalized = "".join(char for char in routing_number if char.isdigit())
    if len(normalized) != 9:
        return []
    return [entry for entry in entries if entry.routing_number == normalized]


def search_bank_name(
    entries: list[RoutingDirectoryEntry], query: str, *, limit: int = 50
) -> list[RoutingDirectoryEntry]:
    normalized_query = _normalize(query)
    if not normalized_query:
        return []
    query_tokens = normalized_query.split()
    matches = [
        entry
        for entry in entries
        if all(token in _normalize(entry.customer_name) for token in query_tokens)
    ]
    return sorted(matches, key=lambda entry: (entry.customer_name, entry.routing_number))[:limit]


def _load_fedach_fixed_width(path: Path) -> list[RoutingDirectoryEntry]:
    entries: list[RoutingDirectoryEntry] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if len(line) < 150:
            continue
        routing_number = line[0:9].strip()
        if not routing_number.isdigit():
            continue
        entries.append(
            RoutingDirectoryEntry(
                routing_number=routing_number,
                customer_name=line[35:71].strip(),
                address=line[71:107].strip(),
                city=line[107:127].strip(),
                state=line[127:129].strip(),
                zip_code=_zip(line[129:134].strip(), line[134:138].strip()),
                phone=_phone(line[138:141].strip(), line[141:144].strip(), line[144:148].strip()),
            )
        )
    return entries


def _load_csv(path: Path) -> list[RoutingDirectoryEntry]:
    entries: list[RoutingDirectoryEntry] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized = {_normalize_header(key): value.strip() for key, value in row.items() if key}
            routing_number = _first(
                normalized, "routingnumber", "routingtransitnumber", "aba", "rtn"
            )
            if len(routing_number) != 9 or not routing_number.isdigit():
                continue
            entries.append(
                RoutingDirectoryEntry(
                    routing_number=routing_number,
                    customer_name=_first(
                        normalized,
                        "customername",
                        "institutionname",
                        "bankname",
                        "name",
                    ),
                    address=_first(normalized, "address", "streetaddress"),
                    city=_first(normalized, "city"),
                    state=_first(normalized, "state", "statecode"),
                    zip_code=_first(normalized, "zipcode", "zip", "postalcode"),
                    phone=_first(normalized, "phone", "telephone"),
                )
            )
    return entries


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if row.get(key):
            return row[key]
    return ""


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _zip(zip_code: str, extension: str) -> str:
    if zip_code and extension:
        return f"{zip_code}-{extension}"
    return zip_code


def _phone(area: str, prefix: str, suffix: str) -> str:
    if area and prefix and suffix:
        return f"({area}) {prefix}-{suffix}"
    return ""
