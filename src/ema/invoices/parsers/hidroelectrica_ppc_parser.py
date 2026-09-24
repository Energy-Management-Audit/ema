"""Page-aware Hidroelectrica and Enel/PPC invoice parsers."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
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
    FieldValue,
    InputDocument,
    InvoiceDraft,
    PriceDetail,
    SourceEvidence,
)
from ema.invoices.parsers.energy_summary import add_energy_summary_fields
from ema.invoices.parsers.hidroelectrica_identity import (
    client_fields,
    field_issues,
    first_match,
    optional,
    required,
    segment_evidence,
)
from ema.invoices.parsers.hidroelectrica_patterns import (
    BILLING_PERIOD_PATTERN,
    HYDRO_FALLBACK_LOCATION,
    HYDRO_LOCATION,
    INVOICE,
    PPC_FALLBACK_LOCATION,
    PPC_LOCATION,
    LocationSegment,
)
from ema.invoices.parsers.hidroelectrica_rows import (
    meter_for_segment,
    price_rows,
)
from ema.invoices.parsers.hidroelectrica_rows import (
    segments as split_segments,
)
from ema.invoices.parsers.hidroelectrica_validation import (
    blocked_draft,
    display_period,
    has_meter_source,
    plain_text,
    price_issue,
    reconciles,
)
from ema.invoices.parsers.normalization import parse_romanian_date


@dataclass(frozen=True)
class ParserConfig:
    supplier: str
    layout: str
    location_pattern: re.Pattern[str]
    fallback_location_pattern: re.Pattern[str] | None
    allow_client_level: bool


@dataclass(frozen=True)
class InvoiceHeader:
    number: str | None
    number_evidence: tuple[SourceEvidence, ...]
    issued: date | None
    period: str | None
    period_evidence: tuple[SourceEvidence, ...]
    client_fields: dict[str, FieldValue]


@dataclass(frozen=True)
class DraftContext:
    config: ParserConfig
    header: InvoiceHeader
    segment: LocationSegment
    period: str | None
    details: list[PriceDetail]
    candidates: int
    parsed_count: int


class HidroelectricaInvoiceParser:
    supplier_name = "SPEEH HIDROELECTRICA S.A."
    layout_version = "hidroelectrica-details-v1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text("\n".join(page.text for page in document.pages))
        return "speeh hidroelectrica sa" in text and "factura fiscala seria fx" in text

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        return parse_document(
            document,
            ParserConfig(
                self.supplier_name,
                self.layout_version,
                HYDRO_LOCATION,
                HYDRO_FALLBACK_LOCATION,
                True,
            ),
        )


class EnelPpcInvoiceParser:
    supplier_name = "ENEL/PPC ENERGIE S.A."
    layout_version = "enel-ppc-details-v1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text("\n".join(page.text for page in document.pages))
        return (
            "adresa loc consum" in text
            and ("cod loc consum" in text or "cod punct de masura" in text)
            and bool(re.search(r"(?:factura fiscala|anexa la factura) seria \d{2}ei", text))
        )

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        return parse_document(
            document,
            ParserConfig(
                self.supplier_name,
                self.layout_version,
                PPC_LOCATION,
                PPC_FALLBACK_LOCATION,
                False,
            ),
        )


def parse_document(document: InputDocument, config: ParserConfig) -> list[InvoiceDraft]:
    header = invoice_header(document)
    segments = invoice_segments(document, config)
    if not segments:
        return [
            blocked_draft(
                document,
                config.supplier,
                header.number,
                header.issued,
                header.period,
                header.client_fields,
            )
        ]
    drafts = [
        period_draft(
            document,
            DraftContext(config, header, segment, period, details, candidates, parsed_count),
        )
        for segment in segments
        for period, details, candidates, parsed_count in segment_periods(segment, header.period)
    ]
    return drafts


def invoice_header(document: InputDocument) -> InvoiceHeader:
    invoice_match, invoice_evidence = first_match(document.pages, INVOICE, "invoice header")
    number = (
        f"{invoice_match.group('series').upper()} {invoice_match.group('number')}"
        if invoice_match
        else None
    )
    issued = parse_romanian_date(invoice_match.group("date")) if invoice_match else None
    billing_match, billing_evidence = first_match(
        document.pages, BILLING_PERIOD_PATTERN, "billing period"
    )
    period = display_period(billing_match) if billing_match else None
    return InvoiceHeader(
        number, invoice_evidence, issued, period, billing_evidence, client_fields(document)
    )


def invoice_segments(document: InputDocument, config: ParserConfig) -> tuple[LocationSegment, ...]:
    segments = split_segments(
        document,
        config.location_pattern,
        "pod",
        fallback_location_pattern=config.fallback_location_pattern,
    )
    if not segments and config.allow_client_level:
        return (LocationSegment(None, None, document.pages),)
    return segments


def segment_periods(
    segment: LocationSegment, billing_period: str | None
) -> list[tuple[str | None, list[PriceDetail], int, int]]:
    parsed_rows, candidates = price_rows(segment.pages, billing_period)
    grouped: dict[str | None, list[PriceDetail]] = defaultdict(list)
    for row in parsed_rows:
        grouped[row.period].append(row.detail)
    if not grouped:
        grouped[billing_period] = []
    return [(period, details, candidates, len(parsed_rows)) for period, details in grouped.items()]


def period_draft(document: InputDocument, context: DraftContext) -> InvoiceDraft:
    segment = context.segment
    config = context.config
    header = context.header
    meter, evidence = meter_for_segment(segment.pages, context.details, context.period)
    if segment.pod is None:
        meter, evidence = None, ()
    fields = draft_fields(header, segment, context.period, meter, evidence, context.details)
    add_energy_summary_fields(fields, context.details)
    issues = field_issues(fields)
    if not context.details:
        issues.append(price_issue("No priced invoice rows were extracted."))
    if context.candidates and not context.details:
        issues.append(price_issue(f"{context.candidates} candidate rows were not parsed."))
    bad = sum(not reconciles(detail) for detail in context.details)
    if bad:
        issues.append(price_issue(f"{bad} price rows do not reconcile."))
    return InvoiceDraft(
        document_id=document_id(document, segment, meter, context.period),
        source_filename=document.path.name,
        supplier=config.supplier,
        fields=fields,
        price_details=context.details,
        issues=issues,
        metadata={
            "layout": config.layout,
            "location_name": segment.name,
            "page_numbers": [page.number for page in segment.pages],
            "source_price_row_count": context.candidates,
            "parsed_price_row_count": context.parsed_count,
            "client_level": segment.pod is None,
        },
    )


def draft_fields(
    header: InvoiceHeader,
    segment: LocationSegment,
    period: str | None,
    meter: str | None,
    meter_evidence: tuple[SourceEvidence, ...],
    details: list[PriceDetail],
) -> dict[str, FieldValue]:
    evidence = tuple(
        SourceEvidence(detail.evidence.page_number, period or "", "price-row consumption period")
        for detail in details[:1]
    )
    return {
        INVOICE_NUMBER: required(header.number, header.number_evidence, "invoice number"),
        INVOICE_DATE: required(header.issued, header.number_evidence, "invoice date"),
        BILLING_PERIOD: optional(header.period, header.period_evidence),
        LOCATION_IDENTIFIER: (
            required(
                segment.pod,
                segment_evidence(segment, "consumption location POD"),
                "consumption location POD",
            )
            if segment.pod is not None
            else optional(None, ())
        ),
        METER_IDENTIFIER: (
            required(meter, meter_evidence, "meter identifier")
            if segment.pod is not None and has_meter_source(segment.pages)
            else optional(None, ())
        ),
        CONSUMPTION_PERIOD: (
            required(period, evidence, "consumption period")
            if segment.pod is not None
            else optional(period, ())
        ),
        **header.client_fields,
    }


def document_id(
    document: InputDocument, segment: LocationSegment, meter: str | None, period: str | None
) -> str:
    period_token = (period or "client-level").replace(" ", "")
    return (
        f"{document.path.stem}:{segment.pod or 'client-level'}:{meter or 'no-meter'}:{period_token}"
    )
