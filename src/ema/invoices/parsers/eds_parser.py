from __future__ import annotations

import re

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
from ema.invoices.parsers.eds_fields import (
    client_identity_fields,
    client_level_green_adjustment,
    first_match,
    issues_for_fields,
    missing_location_draft,
    price_issue,
    required_value,
)
from ema.invoices.parsers.eds_layout import (
    DATE,
    consumption_segments,
    segment_document_id,
)
from ema.invoices.parsers.eds_prices import (
    detail_reconciles,
    invoice_number_grammar,
    price_details,
)
from ema.invoices.parsers.eds_text import plain_text
from ema.invoices.parsers.energy_summary import (
    add_energy_summary_fields,
)
from ema.invoices.parsers.normalization import (
    parse_romanian_date,
)


class EdsInvoiceParser:
    supplier_name = "ENERGY DISTRIBUTION SERVICES SRL"
    layout_version = "feds-detailed-v1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text("\n".join(page.text for page in document.pages))
        return (
            "energy distribution services srl" in text
            and "seria feds nr" in text
            and (
                "factura energie electrica" in text
                or "factura regularizare certificate verzi" in text
            )
        )

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        if "factura regularizare certificate verzi" in plain_text(document.pages[0].text):
            return [client_level_green_adjustment(document)]
        invoice_number, number_evidence = first_match(
            document.pages,
            re.compile(r"SERIA\s+(FEDS)\s+Nr\.\s*([0-9]+)", re.IGNORECASE),
            lambda match: f"{match.group(1).upper()} {match.group(2)}",
            "invoice number",
        )
        invoice_date, date_evidence = first_match(
            document.pages,
            re.compile(rf"Data emitere:\s*({DATE})", re.IGNORECASE),
            lambda match: parse_romanian_date(match.group(1)),
            "invoice date",
        )
        billing_period, billing_period_evidence = first_match(
            document.pages,
            re.compile(
                rf"Perioada de facturare:\s*({DATE})\s*-\s*({DATE})",
                re.IGNORECASE,
            ),
            lambda match: f"{match.group(1)} - {match.group(2)}",
            "billing period",
        )
        client_fields = client_identity_fields(document)
        grammar = invoice_number_grammar(document.pages)
        segments = consumption_segments(document, billing_period)
        if not segments:
            return [
                missing_location_draft(
                    document,
                    invoice_number,
                    invoice_date,
                    billing_period,
                    client_fields,
                )
            ]

        drafts: list[InvoiceDraft] = []
        for segment in segments:
            details, candidate_count = (
                price_details(segment.pages, grammar) if grammar is not None else ([], 0)
            )
            if segment.ambiguous_locations:
                details = []
                candidate_count = 0
            location_evidence = tuple(
                SourceEvidence(page.number, segment.identifier, "consumption location POD")
                for page in segment.pages
            )
            meter_evidence = tuple(
                SourceEvidence(page.number, segment.meter_source_value or "", "meter identifier")
                for page in segment.pages
                if segment.meter_identifier
            )
            segment_period_evidence = tuple(
                SourceEvidence(
                    page.number,
                    segment.consumption_period or "",
                    "segment consumption period",
                )
                for page in segment.pages
                if segment.consumption_period
            )
            fields = {
                INVOICE_NUMBER: required_value(
                    invoice_number,
                    number_evidence,
                    "invoice number",
                ),
                INVOICE_DATE: required_value(invoice_date, date_evidence, "invoice date"),
                BILLING_PERIOD: required_value(
                    billing_period,
                    billing_period_evidence,
                    "billing period",
                ),
                LOCATION_IDENTIFIER: required_value(
                    segment.identifier,
                    location_evidence,
                    "consumption location POD",
                ),
                METER_IDENTIFIER: required_value(
                    segment.meter_identifier,
                    meter_evidence,
                    "meter identifier",
                ),
                CONSUMPTION_PERIOD: required_value(
                    segment.consumption_period,
                    segment_period_evidence,
                    "segment consumption period",
                ),
                **client_fields,
            }
            add_energy_summary_fields(fields, details)
            issues = issues_for_fields(fields)
            if grammar is None:
                issues.append(
                    price_issue("Separatoarele numerice sunt ambigue sau contradictorii.")
                )
            _mark_ambiguous_location(fields, issues, segment.ambiguous_locations)
            if not details:
                issues.append(price_issue("Nu au fost găsite liniile de preț EDS."))
            elif candidate_count != len(details):
                issues.append(
                    price_issue(
                        f"{candidate_count - len(details)} linii de preț EDS nu au putut fi "
                        "extrase complet."
                    )
                )
            invalid_reconciliations = sum(not detail_reconciles(detail) for detail in details)
            if invalid_reconciliations:
                issues.append(
                    price_issue(
                        f"{invalid_reconciliations} linii EDS nu reconciliază cantitatea, "
                        "prețul unitar și valoarea netă."
                    )
                )
            drafts.append(
                InvoiceDraft(
                    document_id=segment_document_id(document, segment),
                    source_filename=document.path.name,
                    supplier=self.supplier_name,
                    fields=fields,
                    price_details=details,
                    issues=issues,
                    metadata={
                        "layout": self.layout_version,
                        "location_name": None if segment.ambiguous_locations else segment.name,
                        "meter_identifier": (
                            None if segment.ambiguous_locations else segment.meter_identifier
                        ),
                        "meter_source_value": (
                            None if segment.ambiguous_locations else segment.meter_source_value
                        ),
                        "consumption_period": (
                            None if segment.ambiguous_locations else segment.consumption_period
                        ),
                        "page_numbers": [page.number for page in segment.pages],
                        "source_price_row_count": candidate_count,
                        "parsed_price_row_count": len(details),
                    },
                )
            )
        return drafts


def _mark_ambiguous_location(
    fields: dict[str, FieldValue], issues: list[ValidationIssue], ambiguous: bool
) -> None:
    if not ambiguous:
        return
    reason = "mai multe locuri de consum pe aceeași factură"
    for field_id in (LOCATION_IDENTIFIER, METER_IDENTIFIER, CONSUMPTION_PERIOD):
        fields[field_id] = FieldValue(None, FieldStatus.AMBIGUOUS, message=reason)
    issues.append(
        ValidationIssue(
            field_id=LOCATION_IDENTIFIER,
            severity=IssueSeverity.ERROR,
            message=reason,
            code=IssueCode.MULTIPLE_LOCATIONS,
        )
    )
