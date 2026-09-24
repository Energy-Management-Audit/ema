from __future__ import annotations

import re
from decimal import Decimal

from ema.invoices.models import EnergyCategory, InputDocument, PriceDetail, SourceEvidence
from ema.invoices.parsers.next_energy_patterns import (
    NUMBER,
    TEXT_PRICE_ROW,
    TEXT_ROW_CANDIDATE,
)
from ema.invoices.parsers.next_energy_text import is_efactura, plain_text
from ema.invoices.parsers.normalization import normalize_quantity_and_price
from ema.invoices.parsers.supplier_numbers import parse_supplier_decimal


def price_details(document: InputDocument) -> tuple[list[PriceDetail], int]:
    if is_efactura(document):
        return efactura_price_details(document)
    details: list[PriceDetail] = []
    candidates = 0
    for page in document.pages:
        for line in page.text.splitlines():
            if is_text_row_candidate(line):
                candidates += 1
            match = TEXT_PRICE_ROW.match(line)
            if match:
                details.append(price_detail(match.groupdict(), page.number, line.strip()))
    return details, candidates


def efactura_price_details(document: InputDocument) -> tuple[list[PriceDetail], int]:
    details: list[PriceDetail] = []
    candidates = 0
    for page in document.pages:
        for block in page.blocks:
            tokens = [line.strip() for line in block.text.splitlines() if line.strip()]
            for unit_index, token in enumerate(tokens):
                if token.casefold() not in {"mwh", "kwh", "kvarh", "mvarh"}:
                    continue
                raw: dict[str, str] | None = None
                snippet_start = 0
                snippet_end = 0
                if (
                    unit_index >= 6
                    and unit_index + 1 < len(tokens)
                    and tokens[unit_index - 4].upper() == "RON"
                    and tokens[unit_index - 5].isdigit()
                ):
                    raw = {
                        "description": tokens[unit_index - 6],
                        "quantity": tokens[unit_index - 2],
                        "net": tokens[unit_index - 1],
                        "unit": token,
                        "price": tokens[unit_index + 1],
                    }
                    snippet_start, snippet_end = unit_index - 6, unit_index + 2
                elif (
                    unit_index >= 4
                    and unit_index + 4 < len(tokens)
                    and tokens[unit_index - 3].upper() == "RON"
                    and tokens[unit_index + 4].isdigit()
                ):
                    raw = {
                        "description": tokens[unit_index + 3],
                        "quantity": tokens[unit_index - 1],
                        "net": tokens[unit_index + 2],
                        "unit": token,
                        "price": tokens[unit_index - 4],
                    }
                    snippet_start, snippet_end = unit_index - 4, unit_index + 5
                if raw is None:
                    continue
                candidates += 1
                if not all(
                    re.fullmatch(NUMBER, raw[field]) for field in ("quantity", "net", "price")
                ):
                    continue
                snippet = " | ".join(tokens[snippet_start:snippet_end])
                details.append(price_detail(raw, page.number, snippet))
    return details, candidates


def price_detail(raw: dict[str, str], page_number: int, snippet: str) -> PriceDetail:
    quantity = parse_supplier_decimal(raw["quantity"])
    price = parse_supplier_decimal(raw["price"])
    net = parse_supplier_decimal(raw["net"])
    source_unit = raw["unit"]
    normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
        quantity,
        price,
        source_unit,
    )
    description = raw["description"].strip()
    return PriceDetail(
        category=category_for(description),
        description=description,
        source_quantity=quantity,
        source_unit=source_unit,
        source_unit_price=price,
        normalized_quantity=normalized_quantity,
        normalized_unit=normalized_unit,
        normalized_unit_price=normalized_price,
        net_value=net,
        evidence=SourceEvidence(page_number, snippet, "invoice price row"),
    )


def detail_reconciles(detail: PriceDetail) -> bool:
    difference = abs(detail.source_quantity * detail.source_unit_price - detail.net_value)
    return difference <= Decimal("0.10")


def is_text_row_candidate(line: str) -> bool:
    match = TEXT_ROW_CANDIDATE.match(line)
    if match is None:
        return False
    unit = re.search(r"\b(?:MWh|kWh|kVArh|MVArh)\b", line, re.IGNORECASE)
    assert unit is not None
    return len(re.findall(NUMBER, line[unit.end() :])) >= 4


def category_for(description: str) -> EnergyCategory:
    normalized = plain_text(description)
    if "pierderi" in normalized and "energie" in normalized:
        return EnergyCategory.ACTIVE_ENERGY_LOSSES
    if "energie reactiva capacitiva" in normalized:
        return EnergyCategory.REACTIVE_CAPACITIVE
    if "energie reactiva inductiva" in normalized:
        return EnergyCategory.REACTIVE_INDUCTIVE
    if "certificate verzi" in normalized:
        return EnergyCategory.GREEN_CERTIFICATES
    if any(
        marker in normalized
        for marker in ("energie activa", "avans energie electrica", "avans vanzare")
    ):
        return EnergyCategory.ACTIVE_ENERGY
    return EnergyCategory.OTHER
