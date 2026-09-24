from __future__ import annotations

import re

from ema.invoices.configuration.field_catalog import (
    CLIENT_NAME,
    CLIENT_TAX_ID,
)
from ema.invoices.models import (
    DocumentPage,
    FieldScalar,
    FieldStatus,
    FieldValue,
    InputDocument,
    IssueCode,
    IssueSeverity,
    SourceEvidence,
    ValidationIssue,
)
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.hidroelectrica_patterns import (
    CLIENT_NAME_PATTERN,
    CLIENT_TAX,
    LocationSegment,
)


def client_fields(document: InputDocument) -> dict[str, FieldValue]:
    text = "\n".join(page.text for page in document.pages[:2])
    name_matches = list(CLIENT_NAME_PATTERN.finditer(text))
    names: dict[str, tuple[str, SourceEvidence]] = {}
    for match in name_matches:
        value = " ".join(match.group("value").split()).strip(" ,;:-")
        legal_name = re.search(
            r"(?P<name>.+?\b(?:S[.]?A[.]?|S[.]?R[.]?L[.]?))\b",
            value,
            re.IGNORECASE,
        )
        if legal_name:
            value = legal_name.group("name").strip()
        if (
            value
            and re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", value)
            and not re.fullmatch(r"C\d+", value, re.IGNORECASE)
        ):
            names.setdefault(
                plain_text(value),
                (value, SourceEvidence(1, match.group(0), "client name")),
            )
    taxes: dict[str, tuple[str, SourceEvidence]] = {}
    for match in CLIENT_TAX.finditer(text):
        value = re.sub(r"\s+", "", match.group("value")).upper()
        if value == "RO13267213":
            continue
        taxes.setdefault(value, (value, SourceEvidence(1, match.group(0), "client tax id")))
    return {
        CLIENT_NAME: candidate(names, required=True),
        CLIENT_TAX_ID: candidate(taxes, required=False),
    }


def candidate(candidates: dict[str, tuple[str, SourceEvidence]], *, required: bool) -> FieldValue:
    values = list(candidates.values())
    if not values:
        return FieldValue(
            None,
            FieldStatus.MISSING if required else FieldStatus.NOT_PROVIDED,
            message="Client identity was not printed." if required else None,
        )
    value, evidence = values[0]
    if len(values) > 1:
        return FieldValue(
            value,
            FieldStatus.AMBIGUOUS,
            tuple(item[1] for item in values),
            "Multiple client identity candidates were printed.",
        )
    return FieldValue(value, FieldStatus.EXTRACTED, (evidence,))


def first_match(
    pages: tuple[DocumentPage, ...], pattern: re.Pattern[str], label: str
) -> tuple[re.Match[str] | None, tuple[SourceEvidence, ...]]:
    for page in pages:
        match = pattern.search(page.text)
        if match:
            return match, (SourceEvidence(page.number, match.group(0), label),)
    return None, ()


def required(value: FieldScalar, evidence: tuple[SourceEvidence, ...], label: str) -> FieldValue:
    if value in (None, ""):
        return FieldValue(None, FieldStatus.MISSING, evidence, f"Missing required {label}.")
    return FieldValue(value, FieldStatus.EXTRACTED, evidence)


def optional(value: FieldScalar, evidence: tuple[SourceEvidence, ...]) -> FieldValue:
    return FieldValue(
        value,
        FieldStatus.EXTRACTED if value not in (None, "") else FieldStatus.NOT_PROVIDED,
        evidence,
    )


def segment_evidence(segment: LocationSegment, label: str) -> tuple[SourceEvidence, ...]:
    if not segment.pod:
        return ()
    return tuple(SourceEvidence(page.number, segment.pod, label) for page in segment.pages[:1])


def field_issues(fields: dict[str, FieldValue]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for field_id, value in fields.items():
        if not value.requires_review:
            continue
        code = None
        if field_id in {CLIENT_NAME, CLIENT_TAX_ID}:
            code = (
                IssueCode.AMBIGUOUS_CLIENT_IDENTITY
                if value.status is FieldStatus.AMBIGUOUS
                else IssueCode.MISSING_CLIENT_IDENTITY
            )
        issues.append(
            ValidationIssue(
                field_id, IssueSeverity.ERROR, value.message or "Review required.", code
            )
        )
    return issues
