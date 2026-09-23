from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

from ema.invoices.configuration.field_catalog import (
    BILLING_PERIOD,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
)
from ema.invoices.models import (
    FieldStatus,
    InputDocument,
    InvoiceDraft,
    IssueCode,
    IssueSeverity,
    SourceEvidence,
    ValidationIssue,
)
from ema.invoices.parsers.energy_summary import (
    add_energy_summary_fields,
)
from ema.invoices.parsers.met_fields import (
    client_identity_fields,
    issues_for_fields,
    location_value,
    required_value,
    supplier_name,
)
from ema.invoices.parsers.met_patterns import (
    FULL_PERIOD,
    INVOICE_NUMBER_PATTERN,
    ISO_DATE,
    MONTH_PERIOD,
    POD,
)
from ema.invoices.parsers.met_price import (
    detail_reconciles,
    price_details,
)
from ema.invoices.parsers.met_text import document_text, plain_text


class MetElectricityInvoiceParser:
    supplier_name = "MET ROMANIA ENERGY"
    layout_version = "ro-efactura-electricity-v1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text(document_text(document))
        return (
            "met romania energy" in text
            and "ro efactura" in text
            and (
                "pret de baza energie electrica" in text
                or "certificate verzi" in text
                or "regularizare cv" in text
            )
            and "gaze naturale" not in text
            and "furnizare gaze" not in text
        )

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        invoice_number, number_evidence = _invoice_number(document)
        invoice_date, date_evidence = _invoice_date(document)
        period, period_evidence = _billing_period(document)
        location, location_status, location_evidence = _location_identifier(document)
        details, candidate_count, unparsed_count = price_details(document)
        supplier = supplier_name(document) or self.supplier_name

        fields = {
            INVOICE_NUMBER: required_value(
                invoice_number,
                number_evidence,
                "invoice number",
            ),
            INVOICE_DATE: required_value(invoice_date, date_evidence, "invoice date"),
            BILLING_PERIOD: required_value(period, period_evidence, "billing period"),
            LOCATION_IDENTIFIER: location_value(
                location,
                location_status,
                location_evidence,
            ),
        }
        add_energy_summary_fields(fields, details)
        fields.update(client_identity_fields(document))
        issues = issues_for_fields(fields)

        if not details:
            issues.append(
                ValidationIssue(
                    field_id=None,
                    severity=IssueSeverity.ERROR,
                    message="Nu au fost găsite liniile de preț MET energie electrică.",
                    code=IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )
        if unparsed_count:
            issues.append(
                ValidationIssue(
                    field_id=None,
                    severity=IssueSeverity.ERROR,
                    message=(f"{unparsed_count} linii de preț MET nu au putut fi extrase complet."),
                    code=IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )
        invalid_reconciliations = sum(not detail_reconciles(detail) for detail in details)
        if invalid_reconciliations:
            issues.append(
                ValidationIssue(
                    field_id=None,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"{invalid_reconciliations} linii MET nu reconciliază cantitatea, "
                        "prețul unitar afișat și valoarea netă în limita rotunjirii sursei."
                    ),
                    code=IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )

        identifier = location or "missing-location"
        return [
            InvoiceDraft(
                document_id=f"{document.path.stem}:{identifier}",
                source_filename=document.path.name,
                supplier=supplier,
                fields=fields,
                price_details=details,
                issues=issues,
                metadata={
                    "source_price_row_count": candidate_count,
                    "parsed_price_row_count": len(details),
                },
            )
        ]


def _invoice_number(
    document: InputDocument,
) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    for page in document.pages:
        for block in page.blocks:
            match = INVOICE_NUMBER_PATTERN.search(block.text)
            if match:
                value = " ".join(match.group(0).upper().split())
                return value, (SourceEvidence(page.number, match.group(0), "invoice number"),)
    return None, ()


def _invoice_date(
    document: InputDocument,
) -> tuple[date | None, tuple[SourceEvidence, ...]]:
    for page in document.pages:
        for block in page.blocks:
            if "data emitere" not in plain_text(block.text):
                continue
            match = ISO_DATE.search(block.text)
            if match:
                return datetime.strptime(match.group(0), "%Y-%m-%d").date(), (
                    SourceEvidence(page.number, block.text.strip(), "invoice date"),
                )
    return None, ()


def _billing_period(
    document: InputDocument,
) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    for page in document.pages:
        for block in page.blocks:
            if "perioada" not in plain_text(block.text):
                continue
            match = FULL_PERIOD.search(block.text)
            if match:
                start = datetime.strptime(match.group("start"), "%Y-%m-%d").date()
                end = datetime.strptime(match.group("end"), "%Y-%m-%d").date()
                evidence = SourceEvidence(page.number, block.text.strip(), "billing period")
                return _format_period(start, end), (evidence,)

            month_match = MONTH_PERIOD.search(block.text)
            if month_match:
                start_year, start_month = map(int, month_match.group("start").split("-"))
                end_year, end_month = map(int, month_match.group("end").split("-"))
                start = date(start_year, start_month, 1)
                end = date(end_year, end_month, monthrange(end_year, end_month)[1])
                evidence = SourceEvidence(page.number, block.text.strip(), "billing period")
                return _format_period(start, end), (evidence,)
    return None, ()


def _location_identifier(
    document: InputDocument,
) -> tuple[str | None, FieldStatus, tuple[SourceEvidence, ...]]:
    found: dict[str, list[SourceEvidence]] = {}
    for page in document.pages:
        for block in page.blocks:
            for match in POD.finditer(block.text):
                value = match.group(1).upper()
                evidence = SourceEvidence(page.number, match.group(0), "consumption location")
                if evidence not in found.setdefault(value, []):
                    found[value].append(evidence)
    if not found:
        return None, FieldStatus.MISSING, ()
    value = next(iter(found))
    evidence = tuple(item for items in found.values() for item in items)
    if len(found) > 1:
        return value, FieldStatus.AMBIGUOUS, evidence
    return value, FieldStatus.EXTRACTED, evidence


def _format_period(start: date, end: date) -> str:
    return f"{start:%d.%m.%Y} - {end:%d.%m.%Y}"
