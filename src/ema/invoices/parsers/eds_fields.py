from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date

from ema.invoices.configuration.field_catalog import (
    BILLING_PERIOD,
    CLIENT_NAME,
    CLIENT_TAX_ID,
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
from ema.invoices.parsers.eds_prices import NUMBER, invoice_number_grammar, price_detail
from ema.invoices.parsers.eds_text import plain_text, primary_text
from ema.invoices.parsers.energy_summary import (
    add_energy_summary_fields,
)
from ema.invoices.parsers.normalization import (
    parse_romanian_date,
)

SUPPLIER_NAME = "ENERGY DISTRIBUTION SERVICES SRL"

_COMPANY = re.compile(r"^[A-Z0-9][A-Z0-9 .&'’-]+(?:SRL|S\.R\.L\.|SA|S\.A\.)$")
_TAX_ID = re.compile(r"Cod fiscal:\s*(?P<value>RO\s*[0-9]{2,10}|[0-9]{2,10})", re.IGNORECASE)


def client_identity_fields(document: InputDocument) -> dict[str, FieldValue]:
    names: dict[str, tuple[str, SourceEvidence]] = {}
    taxes: dict[str, tuple[str, SourceEvidence]] = {}
    for page in document.pages[:1]:
        names.update(_right_column_names(page))
        for block_text in _right_column_lines(page):
            for match in _TAX_ID.finditer(block_text):
                value = re.sub(r"\s+", "", match.group("value")).upper()
                taxes.setdefault(
                    value,
                    (value, SourceEvidence(page.number, match.group(0), "client tax id")),
                )
        if not names:
            text = primary_text(page.text)
            match = re.search(
                r"ENERGY DISTRIBUTION SERVICES SRL\s+"
                r"(?P<name>[A-Z0-9][A-Z0-9 .&'’-]+(?:SRL|S[.]R[.]L[.]|SA|S[.]A[.]))",
                text,
                re.IGNORECASE,
            )
            if match:
                value = " ".join(match.group("name").split())
                names.setdefault(
                    plain_text(value),
                    (value, SourceEvidence(page.number, match.group("name"), "client name")),
                )
        if not taxes:
            text = primary_text(page.text)
            client_name = next(iter(names.values()), (None, None))[0]
            start = text.find(client_name) if client_name else -1
            client_text = text[start:] if start >= 0 else text
            match = _TAX_ID.search(client_text)
            if match:
                value = re.sub(r"\s+", "", match.group("value")).upper()
                taxes.setdefault(
                    value,
                    (value, SourceEvidence(page.number, match.group(0), "client tax id")),
                )
    return {
        CLIENT_NAME: _candidate_value(names, required=True),
        CLIENT_TAX_ID: _candidate_value(taxes, required=False),
    }


def _right_column_names(page: DocumentPage) -> dict[str, tuple[str, SourceEvidence]]:
    names: dict[str, tuple[str, SourceEvidence]] = {}
    for block in page.blocks:
        if block.x0 < 250:
            continue
        for line in block.text.splitlines():
            value = " ".join(line.split()).strip(" ,;:-")
            if _COMPANY.fullmatch(value) and "energy distribution services" not in plain_text(
                value
            ):
                names.setdefault(
                    plain_text(value),
                    (value, SourceEvidence(page.number, line.strip(), "client name")),
                )
    return names


def _right_column_lines(page: DocumentPage) -> list[str]:
    # pdfplumber supplies positioned words; PyMuPDF supplied text blocks.
    lines: list[tuple[float, str]] = []
    for block in sorted((b for b in page.blocks if b.x0 >= 250), key=lambda b: (b.y0, b.x0)):
        if lines and abs(block.y0 - lines[-1][0]) < 3:
            y, content = lines[-1]
            lines[-1] = (y, f"{content} {block.text}")
        else:
            lines.append((block.y0, block.text))
    return [content for _, content in lines]


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


def issues_for_fields(fields: dict[str, FieldValue]) -> list[ValidationIssue]:
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
        elif field_id == LOCATION_IDENTIFIER:
            code = IssueCode.MISSING_LOCATION_IDENTIFIER
        elif field_id == METER_IDENTIFIER:
            code = IssueCode.MISSING_METER_IDENTIFIER
        elif field_id == CONSUMPTION_PERIOD:
            code = IssueCode.MISSING_CONSUMPTION_PERIOD
        elif field_id == INVOICE_NUMBER:
            code = IssueCode.AMBIGUOUS_INVOICE_NUMBER
        issues.append(
            ValidationIssue(
                field_id=field_id,
                severity=IssueSeverity.ERROR,
                message=value.message or f"{field_id} necesită verificare.",
                code=code,
            )
        )
    return issues


def price_issue(message: str) -> ValidationIssue:
    return ValidationIssue(
        field_id=None,
        severity=IssueSeverity.ERROR,
        message=message,
        code=IssueCode.INVALID_PRICE_RECONCILIATION,
    )


def missing_location_draft(
    document: InputDocument,
    invoice_number: str | None,
    invoice_date: date | None,
    billing_period: str | None,
    client_fields: dict[str, FieldValue],
) -> InvoiceDraft:
    return InvoiceDraft(
        document_id=document.path.stem,
        source_filename=document.path.name,
        supplier=SUPPLIER_NAME,
        fields={
            INVOICE_NUMBER: FieldValue(invoice_number, FieldStatus.EXTRACTED),
            INVOICE_DATE: FieldValue(invoice_date, FieldStatus.EXTRACTED),
            BILLING_PERIOD: FieldValue(billing_period, FieldStatus.EXTRACTED),
            LOCATION_IDENTIFIER: FieldValue(
                None,
                FieldStatus.MISSING,
                message="Factura EDS nu conține un POD pentru locul de consum.",
            ),
            **client_fields,
        },
        issues=[
            ValidationIssue(
                field_id=LOCATION_IDENTIFIER,
                severity=IssueSeverity.ERROR,
                message="Nu a fost găsită secțiunea EDS pentru locul de consum.",
                code=IssueCode.MISSING_LOCATION_IDENTIFIER,
            )
        ],
    )


def first_match[MatchValue](
    pages: tuple[DocumentPage, ...],
    pattern: re.Pattern[str],
    transform: Callable[[re.Match[str]], MatchValue],
    label: str,
) -> tuple[MatchValue | None, tuple[SourceEvidence, ...]]:
    for page in pages:
        match = pattern.search(page.text)
        if match:
            return transform(match), (SourceEvidence(page.number, match.group(0), label),)
    return None, ()


def client_level_green_adjustment(document: InputDocument) -> InvoiceDraft:
    page = document.pages[0]
    text = primary_text(page.text)
    grammar = invoice_number_grammar(document.pages) or "romanian"
    number = re.search(r"SERIA\s+(FEDS)\s+Nr[.]\s*([0-9]+)", text, re.IGNORECASE)
    date_match = re.search(r"Data\s+facturarii:\s*(\d{2}[.]\d{2}[.]\d{4})", text, re.IGNORECASE)
    period = re.search(
        r"Perioada\s+de\s+regularizare:\s*(\d{2}[.]\d{2}[.]\d{4})\s*-\s*(\d{2}[.]\d{2}[.]\d{4})",
        text,
        re.IGNORECASE,
    )
    details: list[PriceDetail] = []
    row_pattern = re.compile(
        rf"^\s*\d+\s+(?P<description>.+?)\s+(?P<unit>MWh|kWh)\s+"
        rf"(?P<quantity>{NUMBER})\s+(?P<price>{NUMBER})\s+(?P<net>{NUMBER})\s+"
        rf"(?P<vat>{NUMBER})\s+(?P<total>{NUMBER})\s*$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        match = row_pattern.match(" ".join(line.split()))
        if match:
            details.append(price_detail(match.groupdict(), page.number, line.strip(), grammar))
    client_fields = client_identity_fields(document)
    invoice_number = f"{number.group(1).upper()} {number.group(2)}" if number else None
    invoice_date = parse_romanian_date(date_match.group(1)) if date_match else None
    consumption_period = f"{period.group(1)} - {period.group(2)}" if period else None
    fields = {
        INVOICE_NUMBER: required_value(invoice_number, (), "invoice number"),
        INVOICE_DATE: required_value(invoice_date, (), "invoice date"),
        BILLING_PERIOD: FieldValue(
            consumption_period,
            FieldStatus.EXTRACTED if consumption_period else FieldStatus.NOT_PROVIDED,
        ),
        LOCATION_IDENTIFIER: FieldValue(None, FieldStatus.NOT_PROVIDED),
        METER_IDENTIFIER: FieldValue(None, FieldStatus.NOT_PROVIDED),
        CONSUMPTION_PERIOD: FieldValue(
            consumption_period,
            FieldStatus.EXTRACTED if consumption_period else FieldStatus.NOT_PROVIDED,
        ),
        **client_fields,
    }
    add_energy_summary_fields(fields, details)
    issues = issues_for_fields(fields)
    if len(details) != 2:
        issues.append(
            price_issue("Regularizarea de certificate verzi nu are exact două linii de preț.")
        )
    return InvoiceDraft(
        document_id=f"{document.path.stem}:client-level:{consumption_period or 'no-period'}",
        source_filename=document.path.name,
        supplier=SUPPLIER_NAME,
        fields=fields,
        price_details=details,
        issues=issues,
        metadata={
            "layout": "feds-green-adjustment-v1",
            "client_level": True,
            "page_numbers": [page.number],
            "source_price_row_count": 2,
            "parsed_price_row_count": len(details),
        },
    )
