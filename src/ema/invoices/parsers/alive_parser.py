"""ALIVE CAPITAL electricity invoices read through supervised core PDF OCR."""

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
from ema.invoices.parsers.alive_identity import buyer_fields
from ema.invoices.parsers.alive_prices import price_details
from ema.invoices.parsers.alive_text import (
    billing_period,
    invoice_date,
    invoice_number,
    invoice_positions,
    locations,
)
from ema.invoices.parsers.energy_summary import add_energy_summary_fields
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.identity_fields import field_issues, required_value


class AliveInvoiceParser:
    supplier_name = "ALIVE CAPITAL S.A."
    layout_version = "1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text("\n".join(page.text for page in document.pages))
        return "alive capital" in text and ("factura" in text or "invoice" in text)

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        number, number_evidence = invoice_number(document)
        issued, date_evidence = invoice_date(document)
        period, period_evidence = billing_period(document)
        sites = locations(document)
        details = price_details(document)
        printed_count, count_evidence = invoice_positions(document)
        billed_count = sum(detail.evidence.label == "invoice price row" for detail in details)
        if not sites:
            sites = [("", ())]
        drafts: list[InvoiceDraft] = []
        for pod, pod_evidence in sites:
            fields = {
                INVOICE_NUMBER: required_value(number, number_evidence, "invoice number"),
                INVOICE_DATE: required_value(issued, date_evidence, "invoice date"),
                BILLING_PERIOD: required_value(period, period_evidence, "billing period"),
                LOCATION_IDENTIFIER: required_value(
                    pod or None, pod_evidence, "consumption-location identifier (POD)"
                ),
            }
            add_energy_summary_fields(fields, details)
            fields.update(buyer_fields(document))
            issues = field_issues(fields)
            if printed_count is not None and billed_count != printed_count:
                issues.append(
                    ValidationIssue(
                        None,
                        IssueSeverity.ERROR,
                        "Numărul pozițiilor facturate nu corespunde cu totalul tipărit pe factură.",
                        IssueCode.INVOICE_POSITION_COUNT_MISMATCH,
                    )
                )
            if len(sites) > 1:
                issues.append(
                    ValidationIssue(
                        LOCATION_IDENTIFIER,
                        IssueSeverity.ERROR,
                        "Factura ALIVE conține mai multe locuri de consum. "
                        "Liniile comune nu pot fi alocate încă în siguranță pentru fiecare loc.",
                        IssueCode.MISSING_LOCATION_IDENTIFIER,
                    )
                )
            drafts.append(
                InvoiceDraft(
                    document_id=f"{document.path.stem}:{pod}" if pod else document.path.stem,
                    source_filename=document.path.name,
                    supplier=self.supplier_name,
                    fields=fields,
                    price_details=list(details),
                    issues=issues,
                    metadata={
                        "ocr_used": document.used_ocr,
                        "page_numbers": [page.number for page in document.pages],
                        "printed_position_count": printed_count,
                        "parsed_position_count": billed_count,
                        "position_count_evidence": [item.__dict__ for item in count_evidence],
                    },
                )
            )
        return drafts
