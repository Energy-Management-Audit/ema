from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from ema.invoices.configuration.field_catalog import (
    CLIENT_NAME,
    CONSUMPTION_PERIOD,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
    METER_IDENTIFIER,
)
from ema.invoices.models import (
    DocumentPage,
    FieldScalar,
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
from ema.invoices.parsers.client_identity import (
    extract_client_identity_fields,
)
from ema.invoices.parsers.engie_patterns import DATE_PATTERN
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.normalization import (
    parse_romanian_date,
)


@dataclass(frozen=True)
class LocationPages:
    identifier: str
    identifier_label: str
    pages: tuple[DocumentPage, ...]
    alternate_identifiers: dict[str, str]
    ambiguous_locations: bool = False


class EngieLayoutMixin:
    supplier_name: str

    def _location_groups(self, document: InputDocument) -> tuple[LocationPages, ...]:
        groups: list[LocationPages] = []
        current_pages: list[DocumentPage] = []
        current_identifiers: tuple[str, str, dict[str, str]] | None = None
        current_ambiguous = False
        for original_page in document.pages:
            sections, page_ambiguous = _engie_page_sections(original_page)
            for page in sections:
                if "detalii factura seria" not in plain_text(page.text):
                    continue
                identifiers = _location_identifiers(page.text)
                selected = _select_location_identifier(identifiers)
                if selected:
                    if current_identifiers and current_pages:
                        groups.append(
                            LocationPages(
                                current_identifiers[0],
                                current_identifiers[1],
                                tuple(current_pages),
                                current_identifiers[2],
                                current_ambiguous,
                            )
                        )
                    current_identifiers = (selected[0], selected[1], identifiers)
                    current_pages = [page]
                    current_ambiguous = page_ambiguous
                elif current_identifiers:
                    current_pages.append(page)
                    current_ambiguous |= page_ambiguous
        if current_identifiers and current_pages:
            groups.append(
                LocationPages(
                    current_identifiers[0],
                    current_identifiers[1],
                    tuple(current_pages),
                    current_identifiers[2],
                    current_ambiguous,
                )
            )
        return tuple(groups)

    def _invoice_number(
        self,
        document: InputDocument,
    ) -> tuple[str | None, tuple[SourceEvidence, ...]]:
        pattern = re.compile(r"seria\s+(ENG)\s+nr\.?\s*(\d+)", re.IGNORECASE)
        return _first_match(
            document.pages,
            pattern,
            lambda match: f"{match.group(1)} {match.group(2)}",
        )

    def _invoice_date(
        self,
        document: InputDocument,
    ) -> tuple[date | None, tuple[SourceEvidence, ...]]:
        pattern = re.compile(
            rf"(?:Data facturii:|din data de)\s*({DATE_PATTERN})",
            re.IGNORECASE,
        )
        return _first_match(
            document.pages,
            pattern,
            lambda match: parse_romanian_date(match.group(1)),
        )

    def _billing_period(
        self,
        pages: tuple[DocumentPage, ...],
        details: list[PriceDetail],
    ) -> tuple[str | None, tuple[SourceEvidence, ...]]:
        explicit = re.compile(
            rf"(?:Perioada (?:de facturare|consum))\s*({DATE_PATTERN})\s*-\s*({DATE_PATTERN})",
            re.IGNORECASE,
        )
        value, evidence = _first_match(
            pages,
            explicit,
            lambda match: f"{match.group(1)} - {match.group(2)}",
        )
        if value:
            return value, evidence
        fallback = re.compile(rf"({DATE_PATTERN})\s*-\s*({DATE_PATTERN})")
        ranges: list[tuple[date, date, SourceEvidence]] = []
        for detail in details:
            for match in fallback.finditer(detail.description):
                ranges.append(
                    (
                        parse_romanian_date(match.group(1)),
                        parse_romanian_date(match.group(2)),
                        SourceEvidence(
                            detail.evidence.page_number,
                            detail.description,
                            "price-row billing period",
                        ),
                    )
                )
        if not ranges:
            return None, ()
        start = min(item[0] for item in ranges)
        end = max(item[1] for item in ranges)
        return f"{start:%d.%m.%Y} - {end:%d.%m.%Y}", tuple(item[2] for item in ranges)

    def _required_value(
        self,
        value: FieldScalar,
        evidence: tuple[SourceEvidence, ...],
        label: str,
    ) -> FieldValue:
        if value is None or value == "":
            return FieldValue(
                value=None,
                status=FieldStatus.MISSING,
                evidence=evidence,
                message=f"Lipsește câmpul obligatoriu: {label}.",
            )
        return FieldValue(value=value, status=FieldStatus.EXTRACTED, evidence=evidence)

    def _issues_for_fields(self, fields: dict[str, FieldValue]) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                field_id=field_id,
                severity=IssueSeverity.ERROR,
                message=value.message or f"{field_id} necesită verificare.",
                code=_issue_code_for_field(field_id, value),
            )
            for field_id, value in fields.items()
            if value.requires_review
        ]

    def _missing_locations_draft(
        self,
        document: InputDocument,
        invoice_number: str | None,
        invoice_date: date | None,
    ) -> InvoiceDraft:
        return InvoiceDraft(
            document_id=document.path.stem,
            source_filename=document.path.name,
            supplier=self.supplier_name,
            fields={
                INVOICE_NUMBER: FieldValue(invoice_number, FieldStatus.EXTRACTED),
                INVOICE_DATE: FieldValue(invoice_date, FieldStatus.EXTRACTED),
                LOCATION_IDENTIFIER: FieldValue(None, FieldStatus.MISSING),
                **extract_client_identity_fields(document),
            },
            issues=[
                ValidationIssue(
                    field_id=LOCATION_IDENTIFIER,
                    severity=IssueSeverity.ERROR,
                    message="Nu a fost găsită secțiunea ENGIE pentru locul de consum.",
                    code=IssueCode.MISSING_LOCATION_IDENTIFIER,
                )
            ],
        )

    def _flag_duplicate_identifiers(self, drafts: list[InvoiceDraft]) -> None:
        seen: set[tuple[object, object, object]] = set()
        for draft in drafts:
            identifier = draft.fields[LOCATION_IDENTIFIER].value
            meter = draft.fields.get(METER_IDENTIFIER)
            period = draft.fields.get(CONSUMPTION_PERIOD)
            key = (
                identifier,
                meter.value if meter else None,
                period.value if period else None,
            )
            if key in seen:
                draft.issues.append(
                    ValidationIssue(
                        field_id=LOCATION_IDENTIFIER,
                        severity=IssueSeverity.ERROR,
                        message=f"Cod de loc de consum duplicat: {identifier}",
                        code=IssueCode.MISSING_LOCATION_IDENTIFIER,
                    )
                )
            seen.add(key)


def _issue_code_for_field(field_id: str, value: FieldValue) -> IssueCode | None:
    if field_id == CLIENT_NAME:
        return (
            IssueCode.AMBIGUOUS_CLIENT_IDENTITY
            if value.status is FieldStatus.AMBIGUOUS
            else IssueCode.MISSING_CLIENT_IDENTITY
        )
    if field_id == LOCATION_IDENTIFIER:
        return IssueCode.MISSING_LOCATION_IDENTIFIER
    if field_id == INVOICE_NUMBER:
        return IssueCode.AMBIGUOUS_INVOICE_NUMBER
    return None


def _first_match[MatchValue](
    pages: tuple[DocumentPage, ...],
    pattern: re.Pattern[str],
    transform: Callable[[re.Match[str]], MatchValue],
) -> tuple[MatchValue | None, tuple[SourceEvidence, ...]]:
    for page in pages:
        match = pattern.search(page.text)
        if match:
            return transform(match), (
                SourceEvidence(page.number, match.group(0), "invoice metadata"),
            )
    return None, ()


def _engie_page_sections(page: DocumentPage) -> tuple[tuple[DocumentPage, ...], bool]:
    markers = list(re.finditer(r"Detalii factura seria", page.text, re.IGNORECASE))
    if len(markers) < 2:
        repeated_identifiers = any(
            len(set(re.findall(pattern, page.text, re.IGNORECASE))) > 1
            for pattern in (
                r"Cod tehnic:[ \t]*;?['\"]?([A-Z0-9][A-Z0-9._/-]*)",
                r"Cod loc consum distribuitor:[ \t]*;?['\"]?([A-Z0-9][A-Z0-9._/-]*)",
                r"Cod autocitire:[ \t]*;?['\"]?([A-Z0-9][A-Z0-9._/-]*)",
            )
        )
        return (page,), repeated_identifiers
    boundaries = [0, *(marker.start() for marker in markers[1:]), len(page.text)]
    sections = tuple(
        DocumentPage(page.number, page.text[start:end], page.blocks, page.extraction_method)
        for start, end in pairwise(boundaries)
    )
    if any(
        _select_location_identifier(_location_identifiers(section.text)) is None
        or not re.search(r"\b(?:kWh|MWh|kVArh)\b", section.text, re.IGNORECASE)
        for section in sections
    ):
        return (page,), True
    return sections, False


def _location_identifiers(text: str) -> dict[str, str]:
    patterns = {
        "Cod autocitire": r"Cod autocitire:[ \t]*;?['\"]?([A-Z0-9][A-Z0-9._/-]*)",
        "Cod loc consum distribuitor": (
            r"Cod loc consum distribuitor:[ \t]*;?['\"]?([A-Z0-9][A-Z0-9._/-]*)"
        ),
        "Cod tehnic": r"Cod tehnic:[ \t]*;?['\"]?([A-Z0-9][A-Z0-9._/-]*)",
    }
    identifiers: dict[str, str] = {}
    for label, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            identifiers[label] = match.group(1)
    return identifiers


def _select_location_identifier(identifiers: dict[str, str]) -> tuple[str, str] | None:
    for label in ("Cod tehnic", "Cod loc consum distribuitor", "Cod autocitire"):
        if value := identifiers.get(label):
            return value, label
    return None


def meter_identifiers(pages: tuple[DocumentPage, ...]) -> tuple[str, ...]:
    meters: dict[str, None] = {}
    pattern = re.compile(
        r"Energie\s+(?:Activa|Reactiva)[^\r\n]*?#(?P<value>[A-Z0-9./_-]+)",
        re.IGNORECASE,
    )
    for page in pages:
        for match in pattern.finditer(page.text):
            meters.setdefault(match.group("value"), None)
    return tuple(meters)
