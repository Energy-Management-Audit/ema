from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
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
    SourceEvidence,
    ValidationIssue,
)
from ema.invoices.parsers.client_identity import extract_client_identity_fields


def reconciles(detail: PriceDetail) -> bool:
    difference = abs(detail.source_quantity * detail.source_unit_price - detail.net_value)
    exponent = detail.source_unit_price.as_tuple().exponent
    assert isinstance(exponent, int)
    printed_price_uncertainty = (
        abs(detail.source_quantity) * Decimal(1).scaleb(exponent) / Decimal(2)
    )
    relative_tolerance = abs(detail.net_value) * Decimal("0.00001")
    return difference <= max(
        Decimal("0.05"),
        printed_price_uncertainty,
        relative_tolerance,
    )


def category_for(description: str) -> EnergyCategory:
    normalized = plain_text(description)
    if "certificate verzi" in normalized:
        return EnergyCategory.GREEN_CERTIFICATES
    if "reactiv" in normalized and "capacitiv" in normalized:
        return EnergyCategory.REACTIVE_CAPACITIVE
    if "reactiv" in normalized and "inductiv" in normalized:
        return EnergyCategory.REACTIVE_INDUCTIVE
    if "pierderi" in normalized and "energie activa" in normalized:
        return EnergyCategory.ACTIVE_ENERGY_LOSSES
    if (
        "pret de baza energie electrica" in normalized
        or "consum prezumat energie electrica" in normalized
        or "prezumat energie activa" in normalized
        or normalized.startswith("energie activa")
        or "storno energie activa" in normalized
        or "avans energie activa" in normalized
        or "avans energie cons" in normalized
    ):
        return EnergyCategory.ACTIVE_ENERGY
    return EnergyCategory.OTHER


def getica_client_identity(document: InputDocument) -> dict[str, FieldValue]:
    return extract_client_identity_fields(document)


def electric_client_identity(document: InputDocument) -> dict[str, FieldValue]:
    return extract_client_identity_fields(document)


def missing_location_draft(
    document: InputDocument,
    supplier: str,
    invoice_number: str | None,
    invoice_date: date | None,
    billing_period: str | None,
    client_fields: dict[str, FieldValue],
) -> InvoiceDraft:
    return InvoiceDraft(
        document_id=document.path.stem,
        source_filename=document.path.name,
        supplier=supplier,
        fields={
            INVOICE_NUMBER: FieldValue(invoice_number, FieldStatus.EXTRACTED),
            INVOICE_DATE: FieldValue(invoice_date, FieldStatus.EXTRACTED),
            BILLING_PERIOD: FieldValue(billing_period, FieldStatus.EXTRACTED),
            LOCATION_IDENTIFIER: FieldValue(None, FieldStatus.MISSING),
            **client_fields,
        },
        issues=[
            ValidationIssue(
                LOCATION_IDENTIFIER,
                IssueSeverity.ERROR,
                f"Factura {supplier} nu conține un POD pentru locul de consum.",
                IssueCode.MISSING_LOCATION_IDENTIFIER,
            )
        ],
    )


def first_match[T](
    pages: tuple[DocumentPage, ...],
    pattern: re.Pattern[str],
    transform: Callable[[re.Match[str]], T],
    label: str,
) -> tuple[T | None, tuple[SourceEvidence, ...]]:
    for page in pages:
        match = pattern.search(page.text)
        if match:
            return transform(match), (SourceEvidence(page.number, match.group(0), label),)
    return None, ()


def price_issue(message: str) -> ValidationIssue:
    return ValidationIssue(
        None,
        IssueSeverity.ERROR,
        message,
        IssueCode.INVALID_PRICE_RECONCILIATION,
    )


def document_text(document: InputDocument) -> str:
    return "\n".join(page.text for page in document.pages)


def plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(character for character in normalized if not unicodedata.combining(character))
        .casefold()
        .split()
    )
