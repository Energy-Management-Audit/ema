from __future__ import annotations

from ema.invoices.configuration.field_catalog import (
    BILLING_PERIOD,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
)
from ema.invoices.models import (
    InputDocument,
    InvoiceDraft,
    IssueCode,
    IssueSeverity,
    ValidationIssue,
)
from ema.invoices.parsers.energy_summary import add_energy_summary_fields
from ema.invoices.parsers.next_energy_fields import (
    billing_period,
    client_identity_fields,
    issues_for_fields,
    location_identifier,
    location_value,
    required_value,
)
from ema.invoices.parsers.next_energy_fields import (
    invoice_date as extract_invoice_date,
)
from ema.invoices.parsers.next_energy_fields import (
    invoice_number as extract_invoice_number,
)
from ema.invoices.parsers.next_energy_prices import detail_reconciles, price_details
from ema.invoices.parsers.next_energy_text import document_text, is_efactura, plain_text


class NextEnergyInvoiceParser:
    supplier_name = "NEXT ENERGY PARTNERS S.R.L."
    layout_version = "rvx-efactura-v1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text(document_text(document))
        return "next energy partners" in text and "factura" in text

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        invoice_number, number_evidence = extract_invoice_number(document)
        invoice_date, date_evidence = extract_invoice_date(document)
        period, period_evidence = billing_period(document)
        location, location_status, location_evidence = location_identifier(document)
        details, candidate_count = price_details(document)
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
                    message="Nu au fost găsite liniile de preț NEXT Energy.",
                    code=IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )
        elif candidate_count != len(details):
            issues.append(
                ValidationIssue(
                    field_id=None,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"{candidate_count - len(details)} linii de preț NEXT Energy nu au "
                        "putut fi extrase complet."
                    ),
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
                        f"{invalid_reconciliations} linii NEXT Energy nu reconciliază "
                        "cantitatea, prețul unitar și valoarea netă."
                    ),
                    code=IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )

        identifier = location or "missing-location"
        return [
            InvoiceDraft(
                document_id=f"{document.path.stem}:{identifier}",
                source_filename=document.path.name,
                supplier=self.supplier_name,
                fields=fields,
                price_details=details,
                issues=issues,
                metadata={
                    "layout": "efactura" if is_efactura(document) else "rvx",
                    "source_price_row_count": candidate_count,
                    "parsed_price_row_count": len(details),
                },
            )
        ]
