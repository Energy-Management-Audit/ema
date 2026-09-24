from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from ema.invoices.models import (
    DocumentPage,
    EnergyCategory,
    InputDocument,
    PriceDetail,
    SourceEvidence,
)
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.hidroelectrica_patterns import (
    LOCATION_ADDRESS,
    METER_EA,
    NUMBER,
    PERIOD,
    PPC_METER,
    ROW_NO_PERIOD,
    ROW_PERIOD_FIRST,
    ROW_PERIOD_LAST,
    LocationSegment,
    ParsedRow,
)
from ema.invoices.parsers.hidroelectrica_validation import (
    category,
    clean_description,
    display_period,
    is_total_row,
    normalize_meter,
    parse_quantity,
)
from ema.invoices.parsers.normalization import (
    normalize_quantity_and_price,
    parse_romanian_decimal,
)


def segments(
    document: InputDocument,
    pattern: re.Pattern[str],
    group_name: str,
    *,
    fallback_location_pattern: re.Pattern[str] | None = None,
) -> tuple[LocationSegment, ...]:
    starts: list[tuple[int, str, str | None]] = []
    for index, page in enumerate(document.pages):
        match = pattern.search(page.text)
        if match is None and fallback_location_pattern is not None:
            match = fallback_location_pattern.search(page.text)
        if match is None:
            continue
        name_match = LOCATION_ADDRESS.search(page.text)
        starts.append(
            (
                index,
                match.group(group_name).upper(),
                name_match.group("value").strip() if name_match else None,
            )
        )
    segments: list[LocationSegment] = []
    for offset, (start, pod, name) in enumerate(starts):
        end = starts[offset + 1][0] if offset + 1 < len(starts) else len(document.pages)
        segments.append(LocationSegment(pod, name, document.pages[start:end]))
    return tuple(segments)


def price_rows(
    pages: tuple[DocumentPage, ...], billing_period: str | None
) -> tuple[list[ParsedRow], int]:
    rows: list[ParsedRow] = []
    count = 0
    for page in pages:
        page_rows, page_count = page_price_rows(page, billing_period)
        rows.extend(page_rows)
        count += page_count
    return rows, count


def page_price_rows(page: DocumentPage, billing_period: str | None) -> tuple[list[ParsedRow], int]:
    rows: list[ParsedRow] = []
    previous: list[str] = []
    in_price_table = False
    candidates = 0
    for raw_line in page.text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        normalized = plain_text(line)
        if "denumire servicii facturate" in normalized:
            in_price_table = True
            previous.clear()
            continue
        if in_price_table and ends_price_table(normalized):
            break
        if not in_price_table:
            continue
        parsed = parse_price_line(line, page, billing_period, previous)
        if parsed is None:
            remember_line(previous, line)
            continue
        row, count = parsed
        rows.append(row)
        candidates += count
        remember_line(previous, line)
    return rows, candidates


def ends_price_table(normalized: str) -> bool:
    return (
        "detalii masurari" in normalized
        or normalized.startswith("consum de energie electrica")
        or normalized.startswith("temei legal")
    )


def remember_line(previous: list[str], line: str) -> None:
    previous.append(line)
    del previous[:-3]


def parse_price_line(
    line: str,
    page: DocumentPage,
    billing_period: str | None,
    previous: list[str],
) -> tuple[ParsedRow, int] | None:
    match = ROW_PERIOD_FIRST.match(line) or ROW_PERIOD_LAST.match(line)
    period_override: re.Match[str] | None = None
    if match is None:
        period_override = PERIOD.search(line)
        if period_override:
            without_period = line[: period_override.start()] + line[period_override.end() :]
            match = ROW_NO_PERIOD.match(" ".join(without_period.split()))
    if match is None:
        return None
    raw = match.groupdict()
    description = clean_description(raw["description"])
    if not re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", description):
        description = clean_description(" ".join((*previous[-2:], description)))
    if is_total_row(description):
        return None
    period = row_period(period_override, match, raw, billing_period)
    evidence = SourceEvidence(page.number, line, "invoice price row")
    parsed_detail = detail(raw, description, evidence)
    parsed_detail = with_derived_price(line, match, parsed_detail, page.number)
    return ParsedRow(parsed_detail, period), 1


def row_period(
    override: re.Match[str] | None,
    match: re.Match[str],
    raw: dict[str, str | None],
    billing_period: str | None,
) -> str | None:
    if override:
        return display_period(override)
    if raw.get("start") and raw.get("end"):
        return display_period(match)
    return billing_period


def with_derived_price(
    line: str, match: re.Match[str], detail: PriceDetail, page_number: int
) -> PriceDetail:
    unit_match = re.search(r"\b(?:MWh|kWh|kVArh|MVArh|Buc)\b", line, re.IGNORECASE)
    numeric_tail = re.findall(NUMBER, line[unit_match.end() :]) if unit_match else []
    if match.re is not ROW_PERIOD_FIRST or len(numeric_tail) != 2:
        return detail
    net = parse_romanian_decimal(numeric_tail[0])
    quantity = detail.source_quantity
    price = net / quantity if quantity else Decimal(0)
    normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
        quantity, price, detail.source_unit
    )
    return PriceDetail(
        category=detail.category,
        description=f"{detail.description} [preț derivat din cantitate și valoare]",
        source_quantity=quantity,
        source_unit=detail.source_unit,
        source_unit_price=price,
        normalized_quantity=normalized_quantity,
        normalized_unit=normalized_unit,
        normalized_unit_price=normalized_price,
        net_value=net,
        evidence=SourceEvidence(
            page_number,
            line,
            "invoice row; unit price derived from printed quantity and net value",
        ),
    )


def detail(raw: dict[str, str | None], description: str, evidence: SourceEvidence) -> PriceDetail:
    unit = str(raw["unit"])
    quantity = parse_quantity(str(raw["quantity"]), unit)
    price = parse_romanian_decimal(str(raw["price"]))
    net = parse_romanian_decimal(str(raw["net"]))
    normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
        quantity, price, unit
    )
    return PriceDetail(
        category=category(description),
        description=description,
        source_quantity=quantity,
        source_unit=unit,
        source_unit_price=price,
        normalized_quantity=normalized_quantity,
        normalized_unit=normalized_unit,
        normalized_unit_price=normalized_price,
        net_value=net,
        evidence=evidence,
    )


def meter_for_segment(
    pages: tuple[DocumentPage, ...], details: list[PriceDetail], period: str | None
) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    direct, quantities = direct_meter_data(pages)
    measured = measured_meter_data(pages, period)
    return select_meter(details, direct, quantities, measured)


def direct_meter_data(
    pages: tuple[DocumentPage, ...],
) -> tuple[dict[str, SourceEvidence], dict[str, list[Decimal]]]:
    direct: dict[str, SourceEvidence] = {}
    quantities: dict[str, list[Decimal]] = defaultdict(list)
    for page in pages:
        for match in PPC_METER.finditer(page.text):
            meter = normalize_meter(match.group("value"))
            direct.setdefault(
                meter, SourceEvidence(page.number, match.group(0), "meter identifier")
            )
        sections = re.split(r"Serie\s+contor:\s*([#A-Z0-9./_-]+)", page.text, flags=re.IGNORECASE)
        for index in range(1, len(sections), 2):
            meter = normalize_meter(sections[index])
            if quantity := direct_active_quantity(sections[index + 1]):
                quantities[meter].append(quantity)
    return direct, quantities


def direct_active_quantity(section: str) -> Decimal | None:
    for line in section.splitlines():
        if not re.search(r"Energie\s+activa", line, re.IGNORECASE):
            continue
        unit = re.search(r"\bkWh\b", line, re.IGNORECASE)
        if unit is None:
            return None
        numbers = [
            parse_romanian_decimal(token) for token in re.findall(NUMBER, line[unit.end() :])
        ]
        return abs(numbers[1]) if len(numbers) >= 2 else None
    return None


def measured_meter_data(
    pages: tuple[DocumentPage, ...], period: str | None
) -> dict[str, tuple[SourceEvidence, list[Decimal]]]:
    measured: dict[str, tuple[SourceEvidence, list[Decimal]]] = {}
    for page in pages:
        for line in page.text.splitlines():
            match = METER_EA.search(line)
            if match is None:
                continue
            line_period = PERIOD.search(line)
            if period and line_period and display_period(line_period) != period:
                continue
            meter = normalize_meter(match.group("meter"))
            values = meter_numbers(line[match.end() :])
            measured[meter] = (
                SourceEvidence(page.number, line.strip(), "billed active-energy meter"),
                values,
            )
    return measured


def meter_numbers(value: str) -> list[Decimal]:
    numbers: list[Decimal] = []
    for token in re.findall(NUMBER, value):
        try:
            numbers.append(parse_romanian_decimal(token))
        except ValueError:
            continue
    return numbers


def select_meter(
    details: list[PriceDetail],
    direct: dict[str, SourceEvidence],
    quantities: dict[str, list[Decimal]],
    measured: dict[str, tuple[SourceEvidence, list[Decimal]]],
) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    if len(direct) == 1:
        meter = next(iter(direct))
        return meter, (direct[meter],)
    active = sum(
        (
            abs(detail.source_quantity)
            for detail in details
            if detail.category is EnergyCategory.ACTIVE_ENERGY
        ),
        Decimal(0),
    )
    measured_match = [
        meter
        for meter, (_evidence, values) in measured.items()
        if active and any(abs(value) == active for value in values)
    ]
    direct_match = [meter for meter, values in quantities.items() if active and active in values]
    direct_nonzero = [meter for meter, values in quantities.items() if any(values)]
    measured_nonzero = [
        meter
        for meter, (_evidence, values) in measured.items()
        if any(value != 0 for value in values[1:])
    ]
    options = (
        (measured_match, {key: value[0] for key, value in measured.items()}, False),
        (direct_match, direct, False),
        (direct_nonzero, direct, True),
        (measured_nonzero, {key: value[0] for key, value in measured.items()}, True),
        (list(measured), {key: value[0] for key, value in measured.items()}, False),
    )
    for meters, evidence, combine in options:
        result = meter_result(meters, evidence, combine)
        if result[0] is not None:
            return result
    return None, ()


def meter_result(
    meters: list[str], evidence: dict[str, SourceEvidence], combine: bool
) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    unique = sorted(set(meters))
    if len(unique) == 1:
        return unique[0], (evidence[unique[0]],)
    if len(unique) > 1 and combine:
        return " + ".join(unique), tuple(evidence[meter] for meter in unique)
    return None, ()
