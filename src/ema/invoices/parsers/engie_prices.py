from __future__ import annotations

import re
from decimal import Decimal

from ema.invoices.models import (
    DocumentPage,
    EnergyCategory,
    PriceDetail,
    SourceEvidence,
)
from ema.invoices.parsers.engie_patterns import (
    REACTIVE_METER_READING,
    ROW_PATTERN,
)
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.normalization import (
    normalize_quantity_and_price,
    parse_romanian_decimal,
)


class EngiePriceMixin:
    def _price_details(self, page: DocumentPage) -> list[PriceDetail]:
        details: list[PriceDetail] = []
        seen: set[tuple[object, ...]] = set()
        table_started = False
        for line in page.text.splitlines():
            plain_line = plain_text(line)
            if "cantitate energie" in plain_line and "pret unitar" in plain_line:
                table_started = True
                continue
            if re.match(r"^\s*(?:kWh|MWh|kVArh)\s+", line, re.IGNORECASE):
                table_started = True
            if not table_started:
                continue
            detail = _parsed_price_detail(line, page.number)
            if detail is None:
                continue
            key = (
                detail.category,
                plain_text(detail.description),
                detail.source_quantity,
                detail.source_unit_price,
                detail.net_value,
            )
            if key in seen:
                continue
            seen.add(key)
            details.append(detail)
        if page.extraction_method == "ocr":
            existing = {
                (
                    detail.category,
                    plain_text(detail.description),
                    detail.source_quantity,
                    detail.source_unit_price,
                    detail.net_value,
                )
                for detail in details
            }
            for detail in ocr_sparse_price_details(page):
                key = (
                    detail.category,
                    plain_text(detail.description),
                    detail.source_quantity,
                    detail.source_unit_price,
                    detail.net_value,
                )
                if key not in existing:
                    details.append(detail)
                    existing.add(key)
        return details

    @staticmethod
    def _unparsed_price_row_count(page: DocumentPage) -> int:
        count = 0
        table_started = False
        for line in page.text.splitlines():
            plain_line = plain_text(line)
            if "cantitate energie" in plain_line and "pret unitar" in plain_line:
                table_started = True
                continue
            if re.match(r"^\s*(?:kWh|MWh|kVArh)\s+", line, re.IGNORECASE):
                table_started = True
            match = ROW_PATTERN.match(line)
            if not table_started or (match and _row_values_reconcile(match)):
                continue
            if (
                re.match(r"^\s*(?:kWh|MWh|kVArh)\s+", line, re.IGNORECASE)
                and len(re.findall(r"-?[0-9][0-9.]*,[0-9]+", line)) >= 5
            ):
                count += 1
        return count

    def _add_unpriced_reactive_readings(
        self,
        pages: tuple[DocumentPage, ...],
        details: list[PriceDetail],
    ) -> None:
        existing = {detail.category for detail in details}
        for page in pages:
            for line in page.text.splitlines():
                match = REACTIVE_METER_READING.search(plain_text(line))
                if match is None:
                    continue
                category = (
                    EnergyCategory.REACTIVE_INDUCTIVE
                    if match.group("kind").casefold() == "inductiva"
                    else EnergyCategory.REACTIVE_CAPACITIVE
                )
                if category in existing:
                    continue
                quantity = Decimal(match.group("quantity").replace(".", ""))
                details.append(
                    PriceDetail(
                        category=category,
                        description=f"Energie reactiva {match.group('kind')} masurata, nefacturata",
                        source_quantity=quantity,
                        source_unit="kVArh",
                        source_unit_price=Decimal(0),
                        normalized_quantity=quantity,
                        normalized_unit="kVArh",
                        normalized_unit_price=Decimal(0),
                        net_value=Decimal(0),
                        evidence=SourceEvidence(
                            page.number,
                            line.strip(),
                            "meter reading",
                        ),
                    )
                )
                existing.add(category)


def ocr_sparse_price_details(page: DocumentPage) -> list[PriceDetail]:
    marker = "[OCR sparse-layout alternatives]"
    if marker not in page.text:
        return []
    sparse_text = page.text.split(marker, 1)[1].split("[OCR horizontal-strip alternatives]", 1)[0]
    lines = [line.strip() for line in sparse_text.splitlines() if line.strip()]
    numeric = re.compile(r"^[-−–]?[0-9][0-9.]*,[0-9]+$")
    details: list[PriceDetail] = []
    table_started = False
    index = 0
    while index < len(lines):
        plain = plain_text(lines[index])
        if plain in {"explicatii", "cantitate energie"}:
            table_started = True
            index += 1
            continue
        if not table_started or not re.fullmatch(r"(?:kWh|MWh|kVArh)", lines[index], re.IGNORECASE):
            index += 1
            continue
        source_unit = lines[index]
        description_lines: list[str] = []
        cursor = index + 1
        while cursor < len(lines) and not numeric.fullmatch(lines[cursor]):
            if re.fullmatch(r"(?:kWh|MWh|kVArh)", lines[cursor], re.IGNORECASE):
                break
            description_lines.append(lines[cursor])
            cursor += 1
        values: list[str] = []
        while cursor < len(lines) and numeric.fullmatch(lines[cursor]):
            values.append(lines[cursor])
            cursor += 1
        financials = _sparse_financial_values(values)
        if financials is None or not description_lines:
            index += 1
            continue
        quantity, price, net = financials
        normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
            quantity,
            price,
            source_unit,
        )
        description = " ".join(description_lines)
        details.append(
            PriceDetail(
                category=_category_for(description),
                description=description,
                source_quantity=quantity,
                source_unit=source_unit,
                source_unit_price=price,
                normalized_quantity=normalized_quantity,
                normalized_unit=normalized_unit,
                normalized_unit_price=normalized_price,
                net_value=net,
                evidence=SourceEvidence(
                    page.number,
                    " | ".join((source_unit, description, *values)),
                    "OCR sparse-layout invoice price row",
                ),
            )
        )
        index = cursor
    return details


def _row_values_reconcile(match: re.Match[str]) -> bool:
    return (
        _reconcile_financial_values(
            parse_romanian_decimal(match.group("quantity")),
            parse_romanian_decimal(match.group("price")),
            parse_romanian_decimal(match.group("net")),
            parse_romanian_decimal(match.group("vat")),
            parse_romanian_decimal(match.group("total")),
        )
        is not None
    )


def _sparse_financial_values(values: list[str]) -> tuple[Decimal, Decimal, Decimal] | None:
    parsed = [parse_romanian_decimal(value) for value in values]
    for width in (5, 4):
        for start in range(0, len(parsed) - width + 1):
            quantity, price, net, vat = parsed[start : start + 4]
            total = parsed[start + 4] if width == 5 else net + vat
            reconciled = _reconcile_financial_values(quantity, price, net, vat, total)
            if reconciled is not None:
                return reconciled[0], price, reconciled[1]
    return None


def _reconcile_financial_values(
    quantity: Decimal,
    price: Decimal,
    net: Decimal,
    vat: Decimal,
    total: Decimal,
) -> tuple[Decimal, Decimal] | None:
    if quantity == 0 and price == 0:
        return quantity, net

    calculated = quantity * price
    base_tolerance = _net_tolerance(quantity, price)
    for candidate in (net, total - vat):
        tolerance = max(base_tolerance, abs(candidate) * Decimal("0.0001"))
        if abs(calculated - candidate) <= tolerance:
            return quantity, candidate
        if abs(-calculated - candidate) <= tolerance:
            return -quantity, candidate
    return None


def _net_tolerance(quantity: Decimal, price: Decimal) -> Decimal:
    exponent = price.as_tuple().exponent
    assert isinstance(exponent, int)
    price_step = Decimal(1).scaleb(exponent)
    return max(Decimal("0.02"), abs(quantity) * price_step / 2 + Decimal("0.01"))


def _category_for(description: str) -> EnergyCategory:
    normalized = plain_text(description)
    if "pierderi energie activa" in normalized:
        return EnergyCategory.ACTIVE_ENERGY_LOSSES
    if "energie reactiva capacitiva" in normalized:
        return EnergyCategory.REACTIVE_CAPACITIVE
    if "energie reactiva inductiva" in normalized:
        return EnergyCategory.REACTIVE_INDUCTIVE
    if "certificate verzi" in normalized:
        return EnergyCategory.GREEN_CERTIFICATES
    if "energie activa" in normalized:
        return EnergyCategory.ACTIVE_ENERGY
    return EnergyCategory.OTHER


def _parsed_price_detail(line: str, page_number: int) -> PriceDetail | None:
    match = ROW_PATTERN.match(line)
    if not match:
        return None
    description = match.group("description").strip()
    if plain_text(description).startswith(("total", "acciza")):
        return None
    source_unit = (match.group("unit") or "").strip()
    source_quantity = parse_romanian_decimal(match.group("quantity"))
    source_price = parse_romanian_decimal(match.group("price"))
    net_value = parse_romanian_decimal(match.group("net"))
    vat_value = parse_romanian_decimal(match.group("vat"))
    total_value = parse_romanian_decimal(match.group("total"))
    reconciled = _reconcile_financial_values(
        source_quantity, source_price, net_value, vat_value, total_value
    )
    if reconciled is None:
        return None
    source_quantity, net_value = reconciled
    normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
        source_quantity, source_price, source_unit
    )
    return PriceDetail(
        category=_category_for(description),
        description=description,
        source_quantity=source_quantity,
        source_unit=source_unit,
        source_unit_price=source_price,
        normalized_quantity=normalized_quantity,
        normalized_unit=normalized_unit,
        normalized_unit_price=normalized_price,
        net_value=net_value,
        evidence=SourceEvidence(page_number, line.strip(), "invoice price row"),
    )
