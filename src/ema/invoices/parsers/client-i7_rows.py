from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

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
    EnergyCategory,
    FieldStatus,
    FieldValue,
    InputDocument,
    InvoiceDraft,
    PriceDetail,
    SourceEvidence,
    ValidationIssue,
)
from ema.invoices.parsers.energy_summary import add_energy_summary_fields
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.identity_fields import field_issues as issues_for_fields
from ema.invoices.parsers.identity_fields import required_value as required
from ema.invoices.parsers.normalization import normalize_quantity_and_price
from ema.invoices.parsers.supplier_numbers import parse_supplier_decimal
from ema.invoices.parsers.CLIENT-I7_identity import (
    category_for,
    price_issue,
    reconciles,
)
from ema.invoices.parsers.CLIENT-I7_patterns import (
    CONSUMPTION_PERIOD_PATTERN,
    ELECTRIC_POD,
    METER,
    NUMBER,
    Segment,
)


def electric_segments(document: InputDocument, billing_period: str | None) -> tuple[Segment, ...]:
    segments: list[Segment] = []
    for page in document.pages:
        pod = ELECTRIC_POD.search(page.text)
        if pod is None:
            continue
        meter = METER.search(page.text)
        period = CONSUMPTION_PERIOD_PATTERN.search(page.text)
        meter_value = meter.group("value").lstrip("#") if meter else None
        period_value = (
            f"{period.group('start')} - {period.group('end')}" if period else billing_period
        )
        segments.append(Segment(pod.group("value"), meter_value, period_value, page))
    return tuple(segments)


@dataclass(frozen=True)
class InvoiceHeader:
    number: str | None
    number_evidence: tuple[SourceEvidence, ...]
    issued: date | None
    date_evidence: tuple[SourceEvidence, ...]
    period: str | None
    period_evidence: tuple[SourceEvidence, ...]


def electric_client_level_advance(
    document: InputDocument,
    header: InvoiceHeader,
    client_fields: dict[str, FieldValue],
) -> InvoiceDraft:
    page = document.pages[0]
    lines = [line.strip() for line in page.text.splitlines() if line.strip()]
    quantity: Decimal | None = None
    quantity_snippet = ""
    display_number = re.compile(r"[-−–]?\d{1,3}(?:\.\d{3})*(?:,\d+)?")
    for index, line in enumerate(lines):
        plain = plain_text(line)
        if "avans energie" not in plain and "prezumat energie" not in plain:
            continue
        for candidate in lines[index + 1 : index + 5]:
            values = display_number.findall(candidate)
            if len(values) < 2:
                continue
            quantity = parse_supplier_decimal(values[0])
            quantity_snippet = f"{line} | {candidate}"
            break
        if quantity is not None:
            break
    net_match = re.search(
        r"Factura curent[aă]\s+f[aă]r[aă]\s+TVA:\s*" r"(?P<value>[-−–]?[0-9.]+,[0-9]+)\s+RON",
        page.text,
        re.IGNORECASE,
    )
    net_value = parse_supplier_decimal(net_match.group("value")) if net_match else None
    details: list[PriceDetail] = []
    if quantity not in (None, Decimal(0)) and net_value is not None:
        assert net_match is not None
        unit_price = net_value / quantity
        normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
            quantity,
            unit_price,
            "MWh",
        )
        details.append(
            PriceDetail(
                category=EnergyCategory.ACTIVE_ENERGY,
                description=(
                    "Avans energie electrică; preț derivat din cantitatea și valoarea netă tipărite"
                ),
                source_quantity=quantity,
                source_unit="MWh",
                source_unit_price=unit_price,
                normalized_quantity=normalized_quantity,
                normalized_unit=normalized_unit,
                normalized_unit_price=normalized_price,
                net_value=net_value,
                evidence=SourceEvidence(
                    page.number,
                    f"{quantity_snippet} | {net_match.group(0)}",
                    "client-level advance quantity and net value",
                ),
            )
        )
    fields = {
        INVOICE_NUMBER: required(header.number, header.number_evidence, "invoice number"),
        INVOICE_DATE: required(header.issued, header.date_evidence, "invoice date"),
        BILLING_PERIOD: required(header.period, header.period_evidence, "billing period"),
        LOCATION_IDENTIFIER: FieldValue(None, FieldStatus.NOT_PROVIDED),
        METER_IDENTIFIER: FieldValue(None, FieldStatus.NOT_PROVIDED),
        CONSUMPTION_PERIOD: FieldValue(
            header.period,
            FieldStatus.EXTRACTED if header.period else FieldStatus.NOT_PROVIDED,
            header.period_evidence,
        ),
        **client_fields,
    }
    add_energy_summary_fields(fields, details)
    issues = issues_for_fields(fields)
    if not details:
        issues.append(
            price_issue("Avansul Electric Planners nu are o cantitate și o valoare netă lizibile.")
        )
    return InvoiceDraft(
        document_id=f"{document.path.stem}:client-level:{header.period or 'no-period'}",
        source_filename=document.path.name,
        supplier="ELECTRIC PLANNERS SRL",
        fields=fields,
        price_details=details,
        issues=issues,
        metadata={
            "layout": "electric-planners-client-level-advance-v1",
            "client_level": True,
            "page_numbers": [page.number],
            "source_price_row_count": 1 if details else 0,
            "parsed_price_row_count": len(details),
        },
    )


def price_details(
    pages: tuple[DocumentPage, ...],
    pattern: re.Pattern[str],
    *,
    split_pattern: re.Pattern[str] | None = None,
    recover_invalid_quantity: bool = False,
) -> tuple[list[PriceDetail], int]:
    details: list[PriceDetail] = []
    candidate_count = 0
    for page in pages:
        previous_lines: list[str] = []
        for line in page.text.splitlines():
            unit = re.search(r"\b(?:MWh|kWh|kVArh|MVArh)\b", line, re.IGNORECASE)
            if unit is None or len(re.findall(NUMBER, line[unit.end() :])) < 4:
                if line.strip():
                    previous_lines.append(line.strip())
                continue
            candidate_count += 1
            match = pattern.match(" ".join(line.split()))
            description_override: str | None = None
            if match is None and split_pattern is not None:
                match = split_pattern.match(" ".join(line.split()))
                if match is not None:
                    description_override = nearest_getica_description(previous_lines)
            if match is None:
                previous_lines.append(line.strip())
                continue
            raw = match.groupdict()
            quantity = parse_us_decimal(raw["quantity"])
            price = parse_us_decimal(raw["price"])
            net = parse_us_decimal(raw["net"])
            source_unit = raw["unit"]
            normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
                quantity,
                price,
                source_unit,
            )
            description = description_override or raw["description"].strip()
            detail = PriceDetail(
                category=category_for(description),
                description=description,
                source_quantity=quantity,
                source_unit=source_unit,
                source_unit_price=price,
                normalized_quantity=normalized_quantity,
                normalized_unit=normalized_unit,
                normalized_unit_price=normalized_price,
                net_value=net,
                evidence=SourceEvidence(page.number, line.strip(), "invoice price row"),
            )
            if recover_invalid_quantity and not reconciles(detail):
                detail = recover_quantity_from_printed_net(detail)
            details.append(detail)
            previous_lines.append(line.strip())
    return details, candidate_count


def nearest_getica_description(previous_lines: list[str]) -> str:
    ignored = ("nr. crt", "denumirea produselor", "u.m.", "cantitate")
    candidates = list(reversed(previous_lines[-5:]))
    for line in candidates:
        plain = plain_text(line)
        if any(token in plain for token in ("energie", "certificate", "acciza", "tarif")):
            return line
    for line in candidates:
        plain = plain_text(line)
        if any(token in plain for token in ignored):
            continue
        return line
    return "Linie tarifară GETICA"


def parse_us_decimal(value: str) -> Decimal:
    return parse_supplier_decimal(value.replace(",", "").rstrip("."))


def recover_quantity_from_printed_net(detail: PriceDetail) -> PriceDetail:
    if detail.source_unit_price == 0:
        return detail
    precision = Decimal("0.001") if detail.source_unit.casefold() == "mwh" else Decimal("1")
    recovered_quantity = (detail.net_value / detail.source_unit_price).quantize(precision)
    normalized_quantity, normalized_unit, normalized_price = normalize_quantity_and_price(
        recovered_quantity,
        detail.source_unit_price,
        detail.source_unit,
    )
    return PriceDetail(
        category=detail.category,
        description=f"{detail.description} [cantitate recuperată prin reconciliere]",
        source_quantity=recovered_quantity,
        source_unit=detail.source_unit,
        source_unit_price=detail.source_unit_price,
        normalized_quantity=normalized_quantity,
        normalized_unit=normalized_unit,
        normalized_unit_price=normalized_price,
        net_value=detail.net_value,
        evidence=SourceEvidence(
            detail.evidence.page_number,
            detail.evidence.snippet,
            "invoice row; quantity recovered from printed unit price and net value",
        ),
    )


def price_issues(
    details: list[PriceDetail],
    candidate_count: int,
    supplier: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not details:
        issues.append(price_issue(f"Nu au fost găsite liniile de preț {supplier}."))
    if candidate_count != len(details):
        issues.append(
            price_issue(
                f"{candidate_count - len(details)} linii de preț {supplier} nu au putut fi "
                "extrase complet."
            )
        )
    invalid = sum(not reconciles(detail) for detail in details)
    if invalid:
        issues.append(
            price_issue(
                f"{invalid} linii {supplier} nu reconciliază cantitatea, prețul unitar și "
                "valoarea netă."
            )
        )
    return issues
