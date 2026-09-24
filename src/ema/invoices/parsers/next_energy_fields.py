from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime

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
from ema.invoices.parsers.next_energy_patterns import (
    COMPANY_LINE,
    DATE,
    FULL_PERIOD,
    LABELED_CLIENT,
    LOCATION,
    MONTH_PERIOD,
    ROMANIAN_MONTHS,
    SUPPLIER_TAX_ID,
    TAX_ID,
)
from ema.invoices.parsers.next_energy_text import (
    format_period,
    normalize_invoice_number,
    plain_text,
)
from ema.invoices.parsers.normalization import parse_romanian_date


def invoice_number(
    document: InputDocument,
) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    patterns = (
        re.compile(
            r"factura\s+fiscala\s+seria\s+([A-Z]+)\s+nr\.?\s*(\d+)",
            re.IGNORECASE,
        ),
        re.compile(r"factura\s+nr\.?\s*([A-Z]+-?\d+)", re.IGNORECASE),
        re.compile(r"numar\s+factura\s*:\s*([A-Z]+-?\d+)", re.IGNORECASE),
        re.compile(r"([A-Z]+-?\d+)\s+nr\.\s*factura", re.IGNORECASE),
    )
    for page in document.pages:
        texts = (page.text, *(block.text for block in page.blocks))
        for text in texts:
            for pattern in patterns:
                match = pattern.search(text)
                if match is None:
                    continue
                groups = match.groups()
                value = "-".join(groups) if len(groups) == 2 else groups[0]
                return normalize_invoice_number(value), (
                    SourceEvidence(page.number, match.group(0).strip(), "invoice number"),
                )
    return None, ()


def invoice_date(document: InputDocument) -> tuple[date | None, tuple[SourceEvidence, ...]]:
    patterns = (
        re.compile(r"din\s+data\s+de\s+(\d{2}[.\-/]\d{2}[.\-/]\d{4})", re.IGNORECASE),
        re.compile(r"data\s+emitere\s*:?\s*(\d{2}[.\-/]\d{2}[.\-/]\d{4})", re.IGNORECASE),
        re.compile(r"data\s+factura\s*:?\s*(\d{2}[.\-/]\d{2}[.\-/]\d{4})", re.IGNORECASE),
        re.compile(r"data\s+emitere\s*:?\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE),
    )
    for page in document.pages:
        texts = (page.text, *(block.text for block in page.blocks))
        for text in texts:
            for pattern in patterns:
                match = pattern.search(text)
                if match is None:
                    continue
                raw = match.group(1)
                value = (
                    datetime.strptime(raw, "%Y-%m-%d").date()
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw)
                    else parse_romanian_date(raw)
                )
                return value, (SourceEvidence(page.number, match.group(0).strip(), "invoice date"),)
    return None, ()


def billing_period(
    document: InputDocument,
) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    for page in document.pages:
        labeled = re.search(
            rf"perioada\s+(?:de\s+)?facturare\s*:\s*" rf"(?P<start>{DATE})\s*-\s*(?P<end>{DATE})",
            page.text,
            re.IGNORECASE,
        )
        if labeled:
            start = parse_romanian_date(labeled.group("start"))
            end = parse_romanian_date(labeled.group("end"))
            evidence = SourceEvidence(page.number, labeled.group(0).strip(), "billing period")
            return format_period(start, end), (evidence,)

        month = MONTH_PERIOD.search(plain_text(page.text))
        if month:
            year = int(month.group("year"))
            month_number = ROMANIAN_MONTHS[month.group("month").casefold()]
            start = date(year, month_number, 1)
            end = date(year, month_number, monthrange(year, month_number)[1])
            evidence = SourceEvidence(page.number, month.group(0), "billing period")
            return format_period(start, end), (evidence,)

    periods: list[tuple[date, date, SourceEvidence]] = []
    for page in document.pages:
        for text in (page.text, *(block.text for block in page.blocks)):
            for match in FULL_PERIOD.finditer(text):
                start = parse_romanian_date(match.group("start"))
                end = parse_romanian_date(match.group("end"))
                periods.append(
                    (
                        start,
                        end,
                        SourceEvidence(page.number, match.group(0), "billing period"),
                    )
                )
    if not periods:
        return None, ()
    start = min(item[0] for item in periods)
    end = max(item[1] for item in periods)
    evidence = tuple(item[2] for item in periods if item[0] == start or item[1] == end)
    return format_period(start, end), evidence


def location_identifier(
    document: InputDocument,
) -> tuple[str | None, FieldStatus, tuple[SourceEvidence, ...]]:
    found: dict[str, list[SourceEvidence]] = {}
    for page in document.pages:
        for match in LOCATION.finditer(page.text):
            identifier = match.group(0).upper()
            evidence = SourceEvidence(page.number, match.group(0), "consumption location")
            if evidence not in found.setdefault(identifier, []):
                found[identifier].append(evidence)
    if not found:
        return None, FieldStatus.MISSING, ()
    identifier = next(iter(found))
    evidence = tuple(item for values in found.values() for item in values)
    if len(found) > 1:
        return identifier, FieldStatus.AMBIGUOUS, evidence
    return identifier, FieldStatus.EXTRACTED, evidence


def client_identity_fields(document: InputDocument) -> dict[str, FieldValue]:
    names: dict[str, tuple[str, SourceEvidence]] = {}
    taxes: dict[str, tuple[str, SourceEvidence]] = {}
    for page in document.pages:
        texts = (page.text, *(block.text for block in page.blocks))
        for text in texts:
            for match in LABELED_CLIENT.finditer(text):
                add_client_name_candidate(names, match.group("value"), page.number, match.group(0))
            for line in text.splitlines():
                compact_line = " ".join(line.split()).strip(" ,;:-")
                if COMPANY_LINE.fullmatch(compact_line):
                    add_client_name_candidate(names, compact_line, page.number, line.strip())
            for match in TAX_ID.finditer(text):
                value = re.sub(r"\s+", "", match.group(0)).upper()
                if value == SUPPLIER_TAX_ID:
                    continue
                taxes.setdefault(
                    value,
                    (value, SourceEvidence(page.number, match.group(0), "client tax id")),
                )
    return {
        CLIENT_NAME: candidate_value(names, required=True),
        CLIENT_TAX_ID: candidate_value(taxes, required=False),
    }


def add_client_name_candidate(
    candidates: dict[str, tuple[str, SourceEvidence]],
    raw: str,
    page_number: int,
    snippet: str,
) -> None:
    value = " ".join(raw.split()).strip(" ,;:-")
    normalized = plain_text(value)
    if "next energy partners" in normalized:
        return
    candidates.setdefault(
        normalized,
        (value, SourceEvidence(page_number, snippet.strip(), "client name")),
    )


def candidate_value(
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
    if status is FieldStatus.MISSING:
        message = "Factura nu tipărește identificatorul locului de consum (POD)."
    elif status is FieldStatus.AMBIGUOUS:
        message = "Factura conține mai mulți identificatori de loc de consum."
    else:
        message = None
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
