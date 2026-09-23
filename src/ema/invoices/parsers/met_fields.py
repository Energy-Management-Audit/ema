from __future__ import annotations

import re

from ema.invoices.configuration.field_catalog import (
    CLIENT_NAME,
    CLIENT_TAX_ID,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
)
from ema.invoices.models import (
    FieldScalar,
    FieldStatus,
    FieldValue,
    InputDocument,
    IssueCode,
    IssueSeverity,
    SourceEvidence,
    ValidationIssue,
)
from ema.invoices.parsers.met_patterns import (
    COMPANY,
    SUPPLIER_TAX_ID,
    TAX_ID,
)
from ema.invoices.parsers.met_text import plain_text


def client_identity_fields(document: InputDocument) -> dict[str, FieldValue]:
    name_candidates: dict[str, tuple[str, SourceEvidence]] = {}
    tax_candidates: dict[str, tuple[str, SourceEvidence]] = {}
    for page in document.pages:
        for block in page.blocks:
            for match in COMPANY.finditer(block.text):
                value = " ".join(match.group(0).split()).strip(" ,;:-")
                normalized = plain_text(value)
                if "met romania energy" in normalized:
                    continue
                name_candidates.setdefault(
                    normalized,
                    (value, SourceEvidence(page.number, match.group(0), "client name")),
                )
            for match in TAX_ID.finditer(block.text):
                value = re.sub(r"\s+", "", match.group(0)).upper()
                if value == SUPPLIER_TAX_ID:
                    continue
                tax_candidates.setdefault(
                    value,
                    (value, SourceEvidence(page.number, match.group(0), "client tax id")),
                )
    return {
        CLIENT_NAME: _candidate_value(name_candidates, required=True),
        CLIENT_TAX_ID: _candidate_value(tax_candidates, required=False),
    }


def supplier_name(document: InputDocument) -> str | None:
    for page in document.pages:
        for block in page.blocks:
            for match in COMPANY.finditer(block.text):
                value = " ".join(match.group(0).split()).strip(" ,;:-")
                if "met romania energy" in plain_text(value):
                    return value
    return None


def _candidate_value(
    candidates: dict[str, tuple[str, SourceEvidence]],
    *,
    required: bool,
) -> FieldValue:
    values = list(candidates.values())
    if not values:
        return FieldValue(
            None,
            FieldStatus.MISSING if required else FieldStatus.NOT_PROVIDED,
            message="Denumirea clientului nu a putut fi identificată." if required else None,
        )
    value, evidence = values[0]
    if len(values) > 1:
        return FieldValue(
            value,
            FieldStatus.AMBIGUOUS,
            tuple(item[1] for item in values),
            "Au fost găsite mai multe valori posibile pentru identitatea clientului.",
        )
    return FieldValue(value, FieldStatus.EXTRACTED, (evidence,))


def required_value(
    value: FieldScalar,
    evidence: tuple[SourceEvidence, ...],
    label: str,
) -> FieldValue:
    if value is None or value == "":
        return FieldValue(
            None,
            FieldStatus.MISSING,
            evidence,
            f"Lipsește câmpul obligatoriu: {label}.",
        )
    return FieldValue(value, FieldStatus.EXTRACTED, evidence)


def location_value(
    value: str | None,
    status: FieldStatus,
    evidence: tuple[SourceEvidence, ...],
) -> FieldValue:
    message = (
        "Factura nu tipărește identificatorul locului de consum (POD)."
        if status is FieldStatus.MISSING
        else "Factura conține mai mulți identificatori de loc de consum."
        if status is FieldStatus.AMBIGUOUS
        else None
    )
    return FieldValue(value, status, evidence, message)


def issues_for_fields(fields: dict[str, FieldValue]) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            field_id=field_id,
            severity=IssueSeverity.ERROR,
            message=value.message or f"{field_id} necesită verificare.",
            code=(
                IssueCode.AMBIGUOUS_CLIENT_IDENTITY
                if field_id in {CLIENT_NAME, CLIENT_TAX_ID}
                and value.status is FieldStatus.AMBIGUOUS
                else IssueCode.MISSING_CLIENT_IDENTITY
                if field_id == CLIENT_NAME
                else IssueCode.MISSING_LOCATION_IDENTIFIER
                if field_id == LOCATION_IDENTIFIER
                else IssueCode.AMBIGUOUS_INVOICE_NUMBER
                if field_id == INVOICE_NUMBER
                else None
            ),
        )
        for field_id, value in fields.items()
        if value.requires_review
    ]
