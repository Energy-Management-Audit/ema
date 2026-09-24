"""Common field and evidence rules for supplier invoice parsers."""

from __future__ import annotations

import re
from collections.abc import Callable

from ema.invoices.configuration.field_catalog import (
    CLIENT_NAME,
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


def first_match[T](
    document: InputDocument,
    pattern: re.Pattern[str],
    convert: Callable[[re.Match[str]], T],
    label: str | None = None,
) -> tuple[T | None, tuple[SourceEvidence, ...]]:
    for page in document.pages:
        if match := pattern.search(page.text):
            return convert(match), (SourceEvidence(page.number, match.group(0), label),)
    return None, ()


def required_value(
    value: FieldScalar, evidence: tuple[SourceEvidence, ...], label: str
) -> FieldValue:
    if value is None or value == "":
        return FieldValue(
            None, FieldStatus.MISSING, evidence, f"Lipsește câmpul obligatoriu: {label}."
        )
    return FieldValue(value, FieldStatus.EXTRACTED, evidence)


def field_issues(fields: dict[str, FieldValue]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for key, field in fields.items():
        if not field.requires_review:
            continue
        code = (
            IssueCode.AMBIGUOUS_CLIENT_IDENTITY
            if key == CLIENT_NAME and field.status is FieldStatus.AMBIGUOUS
            else IssueCode.MISSING_CLIENT_IDENTITY
            if key == CLIENT_NAME
            else IssueCode.MISSING_LOCATION_IDENTIFIER
            if key == LOCATION_IDENTIFIER
            else IssueCode.AMBIGUOUS_INVOICE_NUMBER
            if key == INVOICE_NUMBER
            else None
        )
        issues.append(
            ValidationIssue(
                key, IssueSeverity.ERROR, field.message or f"{key} necesită verificare.", code
            )
        )
    return issues
