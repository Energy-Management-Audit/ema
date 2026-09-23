from __future__ import annotations

import re
from datetime import date

from ema.invoices.configuration.field_catalog import (
    BILLING_PERIOD,
    CONSUMPTION_PERIOD,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
    METER_IDENTIFIER,
)
from ema.invoices.models import (
    FieldStatus,
    FieldValue,
    InputDocument,
    InvoiceDraft,
    IssueCode,
    IssueSeverity,
    SourceEvidence,
    ValidationIssue,
)
from ema.invoices.parsers.client_identity import (
    extract_client_identity_fields,
)
from ema.invoices.parsers.energy_summary import (
    add_energy_summary_fields,
)
from ema.invoices.parsers.engie_layout import (
    EngieLayoutMixin,
    LocationPages,
    meter_identifiers,
)
from ema.invoices.parsers.engie_prices import (
    EngiePriceMixin,
    ocr_sparse_price_details,
)
from ema.invoices.parsers.engie_text import plain_text


class EngieInvoiceParser(EngiePriceMixin, EngieLayoutMixin):
    supplier_name = "ENGIE Romania S.A."
    layout_version = "1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text("\n".join(page.text for page in document.pages))
        return "engie romania" in text and bool(re.search(r"seria\s+eng\s+nr", text))

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        invoice_number, number_evidence = self._invoice_number(document)
        invoice_date, date_evidence = self._invoice_date(document)
        groups = self._location_groups(document)
        if not groups:
            return [self._missing_locations_draft(document, invoice_number, invoice_date)]

        drafts = [
            self._parse_location(
                document,
                group,
                invoice_number,
                number_evidence,
                invoice_date,
                date_evidence,
            )
            for group in groups
        ]
        self._flag_duplicate_identifiers(drafts)
        return drafts

    def _parse_location(
        self,
        document: InputDocument,
        group: LocationPages,
        invoice_number: str | None,
        number_evidence: tuple[SourceEvidence, ...],
        invoice_date: date | None,
        date_evidence: tuple[SourceEvidence, ...],
    ) -> InvoiceDraft:
        details = [detail for page in group.pages for detail in self._price_details(page)]
        if group.ambiguous_locations:
            details = []
        else:
            self._add_unpriced_reactive_readings(group.pages, details)
        period, period_evidence = self._billing_period(group.pages, details)
        meters = () if group.ambiguous_locations else meter_identifiers(group.pages)
        meter_value = " + ".join(meters) if meters else None
        meter_evidence = tuple(
            SourceEvidence(page.number, line.strip(), "meter identifier")
            for page in group.pages
            for line in page.text.splitlines()
            if any(f"#{meter}" in line for meter in meters)
        )
        identifier_evidence = (
            SourceEvidence(
                page_number=group.pages[0].number,
                snippet=f"{group.identifier_label}: {group.identifier}",
                label=group.identifier_label,
            ),
        )
        fields = {
            INVOICE_NUMBER: self._required_value(invoice_number, number_evidence, "invoice number"),
            INVOICE_DATE: self._required_value(invoice_date, date_evidence, "invoice date"),
            BILLING_PERIOD: self._required_value(period, period_evidence, "billing period"),
            LOCATION_IDENTIFIER: self._required_value(
                group.identifier,
                identifier_evidence,
                "consumption-location identifier",
            ),
            METER_IDENTIFIER: FieldValue(
                meter_value,
                FieldStatus.EXTRACTED if meter_value else FieldStatus.NOT_PROVIDED,
                meter_evidence,
            ),
            CONSUMPTION_PERIOD: FieldValue(
                period,
                FieldStatus.EXTRACTED if period else FieldStatus.NOT_PROVIDED,
                period_evidence,
            ),
        }
        if group.ambiguous_locations:
            for field_id in (LOCATION_IDENTIFIER, METER_IDENTIFIER, CONSUMPTION_PERIOD):
                fields[field_id] = FieldValue(
                    None,
                    FieldStatus.AMBIGUOUS,
                    message="mai multe locuri de consum pe aceeași factură",
                )
        add_energy_summary_fields(fields, details)
        fields.update(extract_client_identity_fields(document))
        issues = self._issues_for_fields(fields)
        if group.ambiguous_locations:
            issues.append(
                ValidationIssue(
                    field_id=LOCATION_IDENTIFIER,
                    severity=IssueSeverity.ERROR,
                    message="mai multe locuri de consum pe aceeași factură",
                    code=IssueCode.MULTIPLE_LOCATIONS,
                )
            )
        unparsed_rows = sum(self._unparsed_price_row_count(page) for page in group.pages)
        recovered_ocr_rows = sum(
            len(ocr_sparse_price_details(page))
            for page in group.pages
            if page.extraction_method == "ocr"
        )
        unparsed_rows = max(0, unparsed_rows - recovered_ocr_rows)
        if unparsed_rows:
            issues.append(
                ValidationIssue(
                    field_id=None,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"{unparsed_rows} linii de preț ENGIE nu au putut fi extrase complet."
                    ),
                    code=IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )
        if not details:
            issues.append(
                ValidationIssue(
                    field_id=None,
                    severity=IssueSeverity.ERROR,
                    message="Liniile de preț ENGIE lipsesc.",
                    code=IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )
        return InvoiceDraft(
            document_id=f"{document.path.stem}:{group.identifier}:{meter_value or 'no-meter'}",
            source_filename=document.path.name,
            supplier=self.supplier_name,
            fields=fields,
            price_details=details,
            issues=issues,
            metadata={
                "page_numbers": [page.number for page in group.pages],
                "alternate_location_identifiers": group.alternate_identifiers,
                "meter_identifiers": list(meters),
            },
        )
