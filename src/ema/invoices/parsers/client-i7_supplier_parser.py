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
    DocumentPage,
    FieldStatus,
    FieldValue,
    InputDocument,
    InvoiceDraft,
    SourceEvidence,
)
from ema.invoices.parsers.energy_summary import add_energy_summary_fields
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.identity_fields import field_issues as issues_for_fields
from ema.invoices.parsers.identity_fields import required_value as required
from ema.invoices.parsers.normalization import parse_romanian_date
from ema.invoices.parsers.CLIENT-I7_identity import (
    document_text,
    electric_client_identity,
    first_match,
    getica_client_identity,
    missing_location_draft,
)
from ema.invoices.parsers.CLIENT-I7_patterns import (
    DATE,
    ELECTRIC_ROW,
    GETICA_ROW,
    GETICA_SPLIT_ROW,
    POD,
)
from ema.invoices.parsers.CLIENT-I7_rows import (
    InvoiceHeader,
    electric_client_level_advance,
    electric_segments,
    price_details,
    price_issues,
)


class GeticaInvoiceParser:
    supplier_name = "GETICA 95 COM S.R.L."
    layout_version = "getica-95-detailed-v1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text(document_text(document))
        return "getica 95 com" in text and "nr. factura" in text

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        invoice_number, number_evidence = first_match(
            document.pages,
            re.compile(r"Nr\. factura:\s*([A-Z0-9]+)\s+([0-9]+)", re.IGNORECASE),
            lambda match: f"{match.group(1).upper()} {match.group(2)}",
            "invoice number",
        )
        invoice_date, date_evidence = first_match(
            document.pages,
            re.compile(rf"Data emitere:\s*({DATE})", re.IGNORECASE),
            lambda match: parse_romanian_date(match.group(1)),
            "invoice date",
        )
        billing_period, period_evidence = first_match(
            document.pages,
            re.compile(rf"Perioada facturare\s*:\s*({DATE})\s*-\s*({DATE})", re.IGNORECASE),
            lambda match: f"{match.group(1)} - {match.group(2)}",
            "billing period",
        )
        client_fields = getica_client_identity(document)
        location_groups: dict[str, list[DocumentPage]] = {}
        for page in document.pages:
            match = POD.search(page.text)
            if match is not None:
                location_groups.setdefault(match.group("value"), []).append(page)
        if not location_groups:
            return [
                missing_location_draft(
                    document,
                    self.supplier_name,
                    invoice_number,
                    invoice_date,
                    billing_period,
                    client_fields,
                )
            ]

        drafts: list[InvoiceDraft] = []
        for pod, pages in location_groups.items():
            page = pages[0]
            pod_match = POD.search(page.text)
            assert pod_match is not None
            details, candidate_count = price_details(
                tuple(pages),
                GETICA_ROW,
                split_pattern=GETICA_SPLIT_ROW,
            )
            fields = {
                INVOICE_NUMBER: required(invoice_number, number_evidence, "invoice number"),
                INVOICE_DATE: required(invoice_date, date_evidence, "invoice date"),
                BILLING_PERIOD: required(billing_period, period_evidence, "billing period"),
                LOCATION_IDENTIFIER: required(
                    pod,
                    (SourceEvidence(page.number, pod_match.group(0), "POD"),),
                    "POD",
                ),
                METER_IDENTIFIER: FieldValue(None, FieldStatus.NOT_PROVIDED),
                CONSUMPTION_PERIOD: FieldValue(
                    billing_period,
                    FieldStatus.EXTRACTED if billing_period else FieldStatus.NOT_PROVIDED,
                    period_evidence,
                ),
                **client_fields,
            }
            add_energy_summary_fields(fields, details)
            issues = issues_for_fields(fields)
            issues.extend(price_issues(details, candidate_count, "GETICA"))
            drafts.append(
                InvoiceDraft(
                    document_id=f"{document.path.stem}:{pod}",
                    source_filename=document.path.name,
                    supplier=self.supplier_name,
                    fields=fields,
                    price_details=details,
                    issues=issues,
                    metadata={
                        "layout": self.layout_version,
                        "page_numbers": [item.number for item in pages],
                        "source_price_row_count": candidate_count,
                        "parsed_price_row_count": len(details),
                    },
                )
            )
        return drafts


class ElectricPlannersInvoiceParser:
    supplier_name = "ELECTRIC PLANNERS SRL"
    layout_version = "electric-planners-detailed-v1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text(document_text(document))
        return "electric planners srl" in text and "seria elec nr" in text

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        invoice_number, number_evidence = first_match(
            document.pages,
            re.compile(r"SERIA\s+(ELEC)\s+Nr\.\s*([0-9]+)", re.IGNORECASE),
            lambda match: f"{match.group(1).upper()} {match.group(2)}",
            "invoice number",
        )
        invoice_date, date_evidence = first_match(
            document.pages,
            re.compile(rf"Data emitere:\s*({DATE})", re.IGNORECASE),
            lambda match: parse_romanian_date(match.group(1)),
            "invoice date",
        )
        billing_period, period_evidence = first_match(
            document.pages,
            re.compile(rf"Perioada de facturare:\s*({DATE})\s*-\s*({DATE})", re.IGNORECASE),
            lambda match: f"{match.group(1)} - {match.group(2)}",
            "billing period",
        )
        client_fields = electric_client_identity(document)
        segments = electric_segments(document, billing_period)
        if not segments:
            return [
                electric_client_level_advance(
                    document,
                    InvoiceHeader(
                        invoice_number,
                        number_evidence,
                        invoice_date,
                        date_evidence,
                        billing_period,
                        period_evidence,
                    ),
                    client_fields,
                )
            ]

        drafts: list[InvoiceDraft] = []
        for segment in segments:
            details, candidate_count = price_details(
                (segment.page,),
                ELECTRIC_ROW,
                recover_invalid_quantity=True,
            )
            meter_status = FieldStatus.EXTRACTED if segment.meter else FieldStatus.NOT_PROVIDED
            period_status = FieldStatus.EXTRACTED if segment.period else FieldStatus.NOT_PROVIDED
            fields = {
                INVOICE_NUMBER: required(invoice_number, number_evidence, "invoice number"),
                INVOICE_DATE: required(invoice_date, date_evidence, "invoice date"),
                BILLING_PERIOD: required(billing_period, period_evidence, "billing period"),
                LOCATION_IDENTIFIER: required(
                    segment.pod,
                    (SourceEvidence(segment.page.number, segment.pod, "POD"),),
                    "POD",
                ),
                METER_IDENTIFIER: FieldValue(
                    segment.meter,
                    meter_status,
                    (
                        (SourceEvidence(segment.page.number, segment.meter, "meter identifier"),)
                        if segment.meter
                        else ()
                    ),
                ),
                CONSUMPTION_PERIOD: FieldValue(
                    segment.period,
                    period_status,
                    (
                        (SourceEvidence(segment.page.number, segment.period, "consumption period"),)
                        if segment.period
                        else ()
                    ),
                ),
                **client_fields,
            }
            add_energy_summary_fields(fields, details)
            issues = issues_for_fields(fields)
            issues.extend(price_issues(details, candidate_count, "Electric Planners"))
            token = segment.meter or f"page-{segment.page.number}"
            drafts.append(
                InvoiceDraft(
                    document_id=(
                        f"{document.path.stem}:{segment.pod}:{token}:"
                        f"{(segment.period or 'no-period').replace(' ', '')}"
                    ),
                    source_filename=document.path.name,
                    supplier=self.supplier_name,
                    fields=fields,
                    price_details=details,
                    issues=issues,
                    metadata={
                        "layout": self.layout_version,
                        "page_numbers": [segment.page.number],
                        "meter_identifier": segment.meter,
                        "source_price_row_count": candidate_count,
                        "parsed_price_row_count": len(details),
                    },
                )
            )
        return drafts
