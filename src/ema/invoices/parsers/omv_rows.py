"""OMV Petrom annex and ANAF line recognition."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ema.invoices.models import DocumentPage, EnergyCategory, PriceDetail, SourceEvidence
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.normalization import (
    normalize_quantity_and_price,
    parse_romanian_date,
    parse_romanian_decimal,
)

NUMBER = r"[-−–]?[0-9][0-9.,]*"
DATE = r"\d{2}[.\-/]\d{2}[.\-/]\d{4}"
PERIOD = re.compile(rf"(?P<start>{DATE})\s*-\s*(?P<end>{DATE})")
ANNEX_ROW = re.compile(
    rf"^\s*\d+\s+(?P<description>.+?)\s+(?P<start>{DATE})\s*-\s*(?P<end>{DATE})\s+"
    rf"(?P<quantity>{NUMBER})\s+(?P<unit>MWh|kWh|kVArh|KVH|MAH|MVH)\s+"
    rf"(?P<price>{NUMBER})\s+(?P<net>{NUMBER})\s+(?P<vat>{NUMBER})\s*$",
    re.I,
)
UNPRICED_ROW = re.compile(
    rf"^\s*\d+\s+(?P<description>.+?)\s+(?P<start>{DATE})\s*-\s*(?P<end>{DATE})\s+"
    rf"(?P<quantity>{NUMBER})\s+(?P<unit>MWh|kWh|kVArh|KVH|MAH|MVH)\s+"
    rf"(?P<net>{NUMBER})\s+(?P<vat>{NUMBER})\s*$",
    re.I,
)
ANAF_NUMBERS = re.compile(
    rf"^\s*(?P<quantity>{NUMBER})\s+-\s+-\s+(?P<price>{NUMBER})\s+"
    rf"[0-9]+(?:[.,][0-9]+)?%\s+(?P<net>{NUMBER})\s*$"
)
SITE = re.compile(r"\bRS\d{6,}\b", re.I)


@dataclass
class LocationRows:
    identifier: str
    evidence: list[SourceEvidence] = field(default_factory=list[SourceEvidence])
    details: list[PriceDetail] = field(default_factory=list[PriceDetail])
    periods: list[tuple[date, date, SourceEvidence]] = field(
        default_factory=list[tuple[date, date, SourceEvidence]]
    )
    unparsed: int = 0


def category(description: str) -> EnergyCategory:
    value = plain_text(description)
    if "pierderi" in value and "energie" in value:
        return EnergyCategory.ACTIVE_ENERGY_LOSSES
    if "energie reactiva capacitiva" in value:
        return EnergyCategory.REACTIVE_CAPACITIVE
    if "energie reactiva inductiva" in value:
        return EnergyCategory.REACTIVE_INDUCTIVE
    if "certificate verzi" in value:
        return EnergyCategory.GREEN_CERTIFICATES
    return (
        EnergyCategory.ACTIVE_ENERGY
        if value in {"energie activa", "energie activa mt"}
        else EnergyCategory.OTHER
    )


def price_detail(
    row: re.Match[str],
    evidence: SourceEvidence,
    *,
    description: str | None = None,
    unit: str | None = None,
) -> PriceDetail:
    quantity = parse_romanian_decimal(row["quantity"])
    net = parse_romanian_decimal(row["net"])
    raw_price = row.groupdict().get("price")
    price = (
        parse_romanian_decimal(raw_price)
        if raw_price is not None
        else net / quantity
        if quantity
        else Decimal(0)
    )
    source_unit = unit or row.groupdict().get("unit") or ""
    label = description or row.groupdict().get("description") or ""
    kind = category(label)
    normalization_unit = (
        "MVArh"
        if kind in {EnergyCategory.REACTIVE_CAPACITIVE, EnergyCategory.REACTIVE_INDUCTIVE}
        and source_unit.casefold() in {"mah", "mvh"}
        else source_unit
    )
    normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
        quantity, price, normalization_unit
    )
    return PriceDetail(
        kind,
        label,
        quantity,
        source_unit,
        price,
        normalized_quantity,
        normalized_unit,
        normalized_price,
        net,
        evidence,
    )


def representative_period(
    periods: list[tuple[date, date, SourceEvidence]],
) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    if not periods:
        return None, ()
    start, end = Counter((a, b) for a, b, _ in periods).most_common(1)[0][0]
    evidence = tuple(item[2] for item in periods if item[:2] == (start, end))
    return f"{start:%d.%m.%Y} - {end:%d.%m.%Y}", evidence


def annex_rows(
    page: DocumentPage,
) -> tuple[list[PriceDetail], list[tuple[date, date, SourceEvidence]], int]:
    details: list[PriceDetail] = []
    periods: list[tuple[date, date, SourceEvidence]] = []
    unparsed = 0
    lines = page.text.splitlines()
    in_table = False
    for index, line in enumerate(lines):
        if "denumire servicii facturate" in plain_text(line):
            in_table = True
            continue
        if not in_table or not re.match(r"^\s*\d+\s+", line):
            continue
        # PDFium/pdfplumber put the period's end date on the following visual line.
        end = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if re.fullmatch(DATE, end) and re.search(rf"{DATE}\s*-", line):
            rebuilt = re.sub(rf"({DATE}\s*-\s*)", rf"\g<1>{end} ", line, count=1)
        else:
            rebuilt = line
        row = ANNEX_ROW.match(rebuilt) or UNPRICED_ROW.match(rebuilt)
        if row is None:
            if PERIOD.search(rebuilt) and re.search(
                r"\b(?:MWH|KWH|KVARH|MAH|MVH)\b", rebuilt, re.I
            ):
                unparsed += 1
            continue
        description = plain_text(row["description"])
        if description.startswith("total") or description == "energie reactiva total":
            continue
        evidence = SourceEvidence(page.number, " ".join(rebuilt.split()), "invoice price row")
        details.append(price_detail(row, evidence))
        periods.append(
            (parse_romanian_date(row["start"]), parse_romanian_date(row["end"]), evidence)
        )
    return details, periods, unparsed


def anaf_rows(page: DocumentPage) -> dict[str, LocationRows]:
    # In PDFium the ANAF columns are interleaved in text order, but each article
    # still ends at its RS site and period line. Read those bounded groups.
    locations: dict[str, LocationRows] = {}
    lines = page.text.splitlines()
    previous = 0
    number_line = re.compile(
        rf"\b(?P<unit>MWH|KWH|MAH|KVARH)\s+(?P<quantity>{NUMBER})\s+-\s+"
        rf"[0-9]+(?:[.,][0-9]+)?%\s+(?P<net>{NUMBER})\b",
        re.I,
    )
    price_line = re.compile(rf"\bPCE\s+(?P<price>{NUMBER})\b", re.I)
    for index, line in enumerate(lines):
        site = SITE.search(line)
        period = PERIOD.search(line)
        if site is None or period is None:
            continue
        segment = lines[previous : index + 1]
        previous = index + 1
        identifier = site.group(0).upper()
        location = locations.setdefault(identifier, LocationRows(identifier))
        proof = SourceEvidence(page.number, site.group(0), "consumption location")
        if proof not in location.evidence:
            location.evidence.append(proof)
        numbers = [(part, match) for part in segment if (match := number_line.search(part))]
        prices = [(part, match) for part in segment if (match := price_line.search(part))]
        headings = [
            i for i, part in enumerate(segment) if "cod articol furnizor" in plain_text(part)
        ]
        if len(numbers) != 1 or len(prices) != 1 or not headings:
            location.unparsed += 1
            continue
        heading = headings[0]
        choices = [part.strip() for part in segment[max(0, heading - 3) : heading] if part.strip()]
        description = next(
            (part for part in reversed(choices) if not re.match(r"^(?:\d|FURNIZOR|Nr\.)", part)), ""
        )
        if not description:
            location.unparsed += 1
            continue
        numeric_line, numeric = numbers[0]
        _, price = prices[0]
        row_text = f"{numeric['quantity']} - - {price['price']} 19,00% {numeric['net']}"
        row = ANAF_NUMBERS.match(row_text)
        assert row is not None
        evidence = SourceEvidence(
            page.number, f"{description} | {numeric_line}", "invoice price row"
        )
        location.details.append(
            price_detail(row, evidence, description=description, unit=numeric["unit"])
        )
        location.periods.append(
            (
                parse_romanian_date(period["start"]),
                parse_romanian_date(period["end"]),
                SourceEvidence(page.number, period.group(0), "billing period"),
            )
        )
    return locations
