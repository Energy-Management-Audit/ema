from __future__ import annotations

import re
from decimal import Decimal

from ema.invoices.models import (
    DocumentPage,
    EnergyCategory,
    PriceDetail,
    SourceEvidence,
)
from ema.invoices.parsers.eds_text import (
    normalized_ocr_text,
    plain_text,
)
from ema.invoices.parsers.normalization import (
    normalize_quantity_and_price,
    parse_english_decimal,
    parse_romanian_decimal,
)

NUMBER = r"[-−–]?[0-9](?:[0-9.,]*[0-9])?"
_ROW_PATTERN = re.compile(
    rf"^\s*(?P<description>.+?)\s+"
    rf"(?P<unit>MWh|kWh|kVArh|MVArh)\s+"
    rf"(?P<quantity>{NUMBER})\s+"
    rf"(?P<price>{NUMBER})\s+"
    rf"(?P<net>{NUMBER})\s+"
    rf"(?P<vat>{NUMBER})\s+"
    rf"(?P<total>{NUMBER})\s*$",
    re.IGNORECASE,
)
_ROW_CANDIDATE = re.compile(r"\b(?:MWh|kWh|kVArh|MVArh)\b", re.IGNORECASE)


def invoice_number_grammar(pages: tuple[DocumentPage, ...]) -> str | None:
    grammars: set[str] = set()
    for page in pages:
        for line in normalized_ocr_text(page.text).splitlines():
            match = _ROW_PATTERN.match(line)
            if match is None:
                continue
            for key in ("quantity", "price", "net", "vat", "total"):
                token = match.group(key)
                if re.search(r",\d{3}\.\d+$|\.\d{1,2}$", token):
                    grammars.add("english")
                if re.search(r"\.\d{3},\d+$|,\d{1,2}$", token):
                    grammars.add("romanian")
    return next(iter(grammars)) if len(grammars) == 1 else None


def price_details(
    pages: tuple[DocumentPage, ...], grammar: str = "romanian"
) -> tuple[list[PriceDetail], int]:
    details: list[PriceDetail] = []
    candidate_count = 0
    for page in pages:
        candidates = [
            line
            for line in normalized_ocr_text(page.text).splitlines()
            if _is_price_candidate(line)
        ]
        candidate_count += len(candidates)
        parsed: list[PriceDetail | None] = []
        active_quantity: Decimal | None = None
        for line in candidates:
            match = _ROW_PATTERN.match(line)
            try:
                detail = (
                    price_detail(match.groupdict(), page.number, line.strip(), grammar)
                    if match is not None
                    else None
                )
            except ValueError:
                detail = None
            parsed.append(detail)
            if (
                detail is not None
                and detail.category is EnergyCategory.ACTIVE_ENERGY
                and detail_reconciles(detail)
            ):
                active_quantity = detail.source_quantity
        for line, detail in zip(candidates, parsed, strict=True):
            if detail is not None and detail_reconciles(detail):
                details.append(detail)
                continue
            recovered = (
                _recover_ocr_price_detail(line, page.number, active_quantity)
                if page.extraction_method == "ocr"
                else None
            )
            if recovered is not None:
                details.append(recovered)
            elif detail is not None:
                details.append(detail)
    return details, candidate_count


def _is_price_candidate(line: str) -> bool:
    unit = _ROW_CANDIDATE.search(line)
    return unit is not None and len(re.findall(NUMBER, line[unit.end() :])) >= 5


def price_detail(
    raw: dict[str, str], page_number: int, snippet: str, grammar: str = "romanian"
) -> PriceDetail:
    parse_number = parse_english_decimal if grammar == "english" else parse_romanian_decimal
    quantity = parse_number(raw["quantity"])
    unit_price = parse_number(raw["price"])
    net_value = parse_number(raw["net"])
    parse_number(raw["vat"])
    parse_number(raw["total"])
    source_unit = raw["unit"]
    normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
        quantity,
        unit_price,
        source_unit,
    )
    description = raw["description"].strip()
    return PriceDetail(
        category=_category_for(description),
        description=description,
        source_quantity=quantity,
        source_unit=source_unit,
        source_unit_price=unit_price,
        normalized_quantity=normalized_quantity,
        normalized_unit=normalized_unit,
        normalized_unit_price=normalized_price,
        net_value=net_value,
        evidence=SourceEvidence(page_number, snippet, "invoice price row"),
    )


def _recover_ocr_price_detail(
    line: str,
    page_number: int,
    active_quantity: Decimal | None,
) -> PriceDetail | None:
    unit_match = re.search(r"\b(MWh|kWh|kVArh|MVArh)\b", line, re.IGNORECASE)
    if unit_match is None:
        return None
    numbers = re.findall(NUMBER, line[unit_match.end() :])
    if len(numbers) < 5:
        return None
    try:
        quantity, price, net = (_parse_ocr_decimal(value) for value in numbers[:3])
    except ValueError:
        return None
    description = line[: unit_match.start()].strip(" _|/\\-'\"")
    unit = unit_match.group(1)
    category = _category_for(description)
    if (
        active_quantity is not None
        and unit.casefold() == "mwh"
        and "pierderi" not in plain_text(description)
    ):
        quantity = active_quantity
    if quantity and abs(quantity * price - net) > Decimal("0.10"):
        price = net / quantity
    normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
        quantity,
        price,
        unit,
    )
    return PriceDetail(
        category=category,
        description=f"{description} [valoare OCR verificată numeric]",
        source_quantity=quantity,
        source_unit=unit,
        source_unit_price=price,
        normalized_quantity=normalized_quantity,
        normalized_unit=normalized_unit,
        normalized_unit_price=normalized_price,
        net_value=net,
        evidence=SourceEvidence(
            page_number,
            line.strip(),
            "OCR invoice price row; corrected by printed quantity/net reconciliation",
        ),
    )


def _parse_ocr_decimal(value: str) -> Decimal:
    try:
        return parse_romanian_decimal(value)
    except ValueError:
        for separator in (",", "."):
            if value.count(separator) <= 1:
                continue
            whole, decimal = value.rsplit(separator, maxsplit=1)
            repaired = f"{whole.replace(separator, '')}.{decimal}"
            return Decimal(repaired)
        raise


def detail_reconciles(detail: PriceDetail) -> bool:
    difference = abs(detail.source_quantity * detail.source_unit_price - detail.net_value)
    # EDS prints unit prices rounded to the displayed decimal places while the
    # net amount is calculated from a more precise contractual price. Accept
    # exactly the uncertainty introduced by that printed rounding, plus one
    # cent for the printed net amount itself.
    exponent = detail.source_unit_price.as_tuple().exponent
    assert isinstance(exponent, int)
    price_step = Decimal(1).scaleb(exponent)
    rounding_tolerance = abs(detail.source_quantity) * price_step / Decimal(2)
    return difference <= rounding_tolerance + Decimal("0.01")


def _category_for(description: str) -> EnergyCategory:
    normalized = plain_text(description)
    if "pierderi" in normalized and "energie" in normalized:
        return EnergyCategory.ACTIVE_ENERGY_LOSSES
    if "reactiv" in normalized and "capacitiv" in normalized:
        return EnergyCategory.REACTIVE_CAPACITIVE
    if "reactiv" in normalized and "inductiv" in normalized:
        return EnergyCategory.REACTIVE_INDUCTIVE
    if "certificate verzi" in normalized:
        return EnergyCategory.GREEN_CERTIFICATES
    if "energie activa" in normalized:
        return EnergyCategory.ACTIVE_ENERGY
    return EnergyCategory.OTHER
