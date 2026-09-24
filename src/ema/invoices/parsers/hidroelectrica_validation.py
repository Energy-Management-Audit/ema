from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal

from ema.invoices.configuration.field_catalog import (
    BILLING_PERIOD,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
)
from ema.invoices.models import (
    DocumentPage,
    EnergyCategory,
    FieldStatus,
    FieldValue,
    InputDocument,
    InvoiceDraft,
    IssueCode,
    IssueSeverity,
    PriceDetail,
    ValidationIssue,
)
from ema.invoices.parsers.hidroelectrica_identity import field_issues, optional, required
from ema.invoices.parsers.hidroelectrica_patterns import (
    METER_EA,
    PPC_METER,
)
from ema.invoices.parsers.normalization import parse_romanian_decimal


def blocked_draft(
    document: InputDocument,
    supplier: str,
    invoice_number: str | None,
    invoice_date: date | None,
    billing_period: str | None,
    client_fields: dict[str, FieldValue],
) -> InvoiceDraft:
    fields = {
        INVOICE_NUMBER: required(invoice_number, (), "invoice number"),
        INVOICE_DATE: required(invoice_date, (), "invoice date"),
        BILLING_PERIOD: optional(billing_period, ()),
        LOCATION_IDENTIFIER: FieldValue(
            None, FieldStatus.MISSING, message="No consumption location was printed."
        ),
        **client_fields,
    }
    return InvoiceDraft(
        document_id=document.path.stem,
        source_filename=document.path.name,
        supplier=supplier,
        fields=fields,
        issues=field_issues(fields),
    )


def display_period(match: re.Match[str]) -> str:
    return f"{four_digit_date(match.group('start'))} - {four_digit_date(match.group('end'))}"


def four_digit_date(value: str) -> str:
    parts = value.split(".")
    if len(parts[2]) == 2:
        parts[2] = f"20{parts[2]}"
    return ".".join(parts)


def clean_description(value: str) -> str:
    cleaned = re.sub(r"^\s*\d+\s+", "", value)
    cleaned = re.sub(r"\s+\d+\s*$", "", cleaned)
    return " ".join(cleaned.split()).strip(" -")


def is_total_row(description: str) -> bool:
    normalized = plain_text(description)
    return normalized.startswith("total de plata") or "total de plata" in normalized


def category(description: str) -> EnergyCategory:
    normalized = plain_text(description)
    checks = (
        (("produsa", "livrata"), EnergyCategory.OTHER),
        (("certificate verzi",), EnergyCategory.GREEN_CERTIFICATES),
        (("reactiv", "capacitiv"), EnergyCategory.REACTIVE_CAPACITIVE),
        (("reactiv", "inductiv"), EnergyCategory.REACTIVE_INDUCTIVE),
        (("pierderi", "energie"), EnergyCategory.ACTIVE_ENERGY_LOSSES),
        (("energie activa",), EnergyCategory.ACTIVE_ENERGY),
    )
    return next(
        (category for words, category in checks if all(word in normalized for word in words)),
        EnergyCategory.OTHER,
    )


def normalize_meter(value: str) -> str:
    return value.lstrip("#").strip()


def has_meter_source(pages: tuple[DocumentPage, ...]) -> bool:
    text = "\n".join(page.text for page in pages)
    return bool(PPC_METER.search(text) or METER_EA.search(text))


def parse_quantity(value: str, unit: str) -> Decimal:
    compact = value.strip()
    if (
        unit.casefold() in {"kwh", "kvarh"}
        and "," not in compact
        and re.fullmatch(r"[-−–]?\d{1,3}(?:[.]\d{3})+", compact)
    ):
        compact = compact.replace(".", "")
    return parse_romanian_decimal(compact)


def reconciles(detail: PriceDetail) -> bool:
    difference = abs(detail.source_quantity * detail.source_unit_price - detail.net_value)
    exponent = detail.source_unit_price.as_tuple().exponent
    assert isinstance(exponent, int)
    tolerance = abs(detail.source_quantity) * Decimal(1).scaleb(exponent) / Decimal(2)
    # Hidroelectrica sometimes prints the contractual unit price with fewer
    # decimals than those used for the printed net amount. Keep the
    # precision-derived tolerance, but also accept at most 0.001% of the
    # source net value. This covers sub-leu display discrepancies without
    # masking materially wrong rows.
    relative_tolerance = abs(detail.net_value) * Decimal("0.00001")
    return difference <= max(tolerance + Decimal("0.05"), relative_tolerance)


def price_issue(message: str) -> ValidationIssue:
    return ValidationIssue(
        None,
        IssueSeverity.ERROR,
        message,
        IssueCode.INVALID_PRICE_RECONCILIATION,
    )


def plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(character for character in normalized if not unicodedata.combining(character))
        .casefold()
        .split()
    )
