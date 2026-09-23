from __future__ import annotations

import re
from decimal import Decimal

from ema.invoices.models import (
    EnergyCategory,
    InputDocument,
    PriceDetail,
    SourceEvidence,
)
from ema.invoices.parsers.met_patterns import NUMBER, PRICE_UNITS, VAT
from ema.invoices.parsers.met_text import plain_text
from ema.invoices.parsers.normalization import (
    normalize_quantity_and_price,
    parse_romanian_decimal,
)


def price_details(document: InputDocument) -> tuple[list[PriceDetail], int, int]:
    details: list[PriceDetail] = []
    candidate_count = 0
    unparsed_count = 0
    for page in document.pages:
        tokens = [
            token.strip()
            for block in page.blocks
            if "RON" in block.text.upper()
            and any(unit in block.text.upper() for unit in PRICE_UNITS)
            for token in block.text.splitlines()
            if token.strip()
        ]
        raw_rows: list[dict[str, str]] = []
        previous_end = 0
        for ron_index, token in enumerate(tokens):
            if token.upper() != "RON" or ron_index < 2 or ron_index + 4 >= len(tokens):
                continue
            quantity, net, unit, price = tokens[ron_index + 1 : ron_index + 5]
            if (
                unit.upper() not in PRICE_UNITS
                or NUMBER.fullmatch(quantity) is None
                or NUMBER.fullmatch(net) is None
                or NUMBER.fullmatch(price) is None
            ):
                continue

            candidate_count += 1
            segment = tokens[previous_end : ron_index - 1]
            vat_positions = [index for index, value in enumerate(segment) if VAT.fullmatch(value)]
            if not vat_positions:
                unparsed_count += 1
                previous_end = ron_index + 5
                continue
            vat_index = vat_positions[-1]
            continuation = segment[:vat_index]
            if continuation and raw_rows:
                raw_rows[-1]["description"] = _join_description(
                    [raw_rows[-1]["description"], *continuation]
                )
            description_tokens = segment[vat_index + 1 :]
            if not description_tokens:
                unparsed_count += 1
                previous_end = ron_index + 5
                continue
            raw_rows.append(
                {
                    "description": _join_description(description_tokens),
                    "quantity": quantity,
                    "net": net,
                    "unit": unit,
                    "price": price,
                }
            )
            previous_end = ron_index + 5

        for row in raw_rows:
            details.append(_price_detail(row, page.number))
    return details, candidate_count, unparsed_count


def _price_detail(raw: dict[str, str], page_number: int) -> PriceDetail:
    quantity = parse_romanian_decimal(raw["quantity"], decimal_dot=True)
    source_price = parse_romanian_decimal(raw["price"], decimal_dot=True)
    net_value = parse_romanian_decimal(raw["net"], decimal_dot=True)
    source_unit = raw["unit"].upper()
    description = raw["description"]
    category = _category_for(description)
    normalization_unit = source_unit
    if (
        category
        in {
            EnergyCategory.REACTIVE_CAPACITIVE,
            EnergyCategory.REACTIVE_INDUCTIVE,
        }
        and source_unit == "MAH"
    ):
        normalization_unit = "MVArh"
    normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
        quantity,
        source_price,
        normalization_unit,
    )
    snippet = (
        f"{description} | {quantity} {source_unit} | "
        f"{source_price} RON/{source_unit} | {net_value} RON"
    )
    return PriceDetail(
        category=category,
        description=description,
        source_quantity=quantity,
        source_unit=source_unit,
        source_unit_price=source_price,
        normalized_quantity=normalized_quantity,
        normalized_unit=normalized_unit,
        normalized_unit_price=normalized_price,
        net_value=net_value,
        evidence=SourceEvidence(page_number, snippet, "invoice price row"),
    )


def detail_reconciles(detail: PriceDetail) -> bool:
    price_text = format(detail.source_unit_price, "f")
    precision = len(price_text.partition(".")[2])
    rounding_tolerance = abs(detail.source_quantity) * (
        Decimal("0.5") * (Decimal(10) ** -precision)
    )
    difference = abs(detail.source_quantity * detail.source_unit_price - detail.net_value)
    return difference <= rounding_tolerance + Decimal("0.02")


def _category_for(description: str) -> EnergyCategory:
    normalized = plain_text(description)
    if "energie reactiva capacitiva" in normalized:
        return EnergyCategory.REACTIVE_CAPACITIVE
    if "energie reactiva inductiva" in normalized:
        return EnergyCategory.REACTIVE_INDUCTIVE
    if "certificate verzi" in normalized or "regularizare cv" in normalized:
        return EnergyCategory.GREEN_CERTIFICATES
    if (
        "pret de baza energie electrica" in normalized
        or "componenta achizitie furnizare" in normalized
    ):
        return EnergyCategory.ACTIVE_ENERGY
    return EnergyCategory.OTHER


def _join_description(tokens: list[str]) -> str:
    value = " ".join(" ".join(token.split()) for token in tokens).strip()
    return re.sub(r"(?<!\d)8\s+5%", "85%", value)
