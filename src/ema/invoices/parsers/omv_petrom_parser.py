"""OMV Petrom annex and ANAF electricity invoice layouts."""

from __future__ import annotations

import re
from datetime import date

from ema.invoices.configuration.field_catalog import (
    BILLING_PERIOD,
    CLIENT_TAX_ID,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
)
from ema.invoices.models import (
    EnergyCategory,
    FieldStatus,
    FieldValue,
    InputDocument,
    InvoiceDraft,
    IssueCode,
    IssueSeverity,
    SourceEvidence,
    ValidationIssue,
)
from ema.invoices.parsers.client_identity import extract_client_identity_fields
from ema.invoices.parsers.energy_summary import add_energy_summary_fields
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.identity_fields import field_issues, first_match, required_value
from ema.invoices.parsers.normalization import parse_romanian_date
from ema.invoices.parsers.omv_rows import LocationRows, anaf_rows, annex_rows, representative_period

DATE = r"\d{2}[.\-/]\d{2}[.\-/]\d{4}"
ANNEX_META = re.compile(
    rf"anexa\s+factura\s+fiscala\s+nr\.?\s*(?P<number>\d+)\s+"
    rf"din\s+data\s+de\s+(?P<date>{DATE})",
    re.I,
)
POD = re.compile(r"\bPOD\s*\)?\s*:\s*([A-Z0-9-]{6,})", re.I)
ANAF_NUMBER = re.compile(r"numar\s+factura\s*:\s*(\d+)", re.I)
ANAF_DATE = re.compile(rf"data\s+factura\s*:\s*({DATE})", re.I)


class OmvPetromInvoiceParser:
    supplier_name = "OMV PETROM S.A."
    layout_version = "annex-anaf-v1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = plain_text("\n".join(page.text for page in document.pages))
        return (
            "anexa factura fiscala" in text
            and "denumire servicii facturate" in text
            and "omvpetrom" in text
        ) or (
            "omv petrom sa" in text
            and "numar factura" in text
            and "cod articol furnizor" in text
            and "total pozitii factura" in text
        )

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        if ANNEX_META.search("\n".join(page.text for page in document.pages)):
            return self._annex(document)
        return self._anaf(document)

    def _annex(self, document: InputDocument) -> list[InvoiceDraft]:
        metadata, meta_evidence = first_match(
            document,
            ANNEX_META,
            lambda m: (m["number"], parse_romanian_date(m["date"])),
            "invoice metadata",
        )
        number, issued = metadata if metadata else (None, None)
        pod, pod_evidence = first_match(document, POD, lambda m: m[1].upper())
        location = LocationRows(pod or "", list(pod_evidence))
        for page in document.pages:
            details, periods, unparsed = annex_rows(page)
            location.details.extend(details)
            location.periods.extend(periods)
            location.unparsed += unparsed
        return [self._draft(document, number, meta_evidence, issued, meta_evidence, location)]

    def _anaf(self, document: InputDocument) -> list[InvoiceDraft]:
        number, number_evidence = first_match(document, ANAF_NUMBER, lambda m: m[1])
        issued, date_evidence = first_match(
            document, ANAF_DATE, lambda m: parse_romanian_date(m[1])
        )
        locations: dict[str, LocationRows] = {}
        for page in document.pages:
            for identifier, found in anaf_rows(page).items():
                location = locations.setdefault(identifier, LocationRows(identifier))
                location.evidence.extend(found.evidence)
                location.details.extend(found.details)
                location.periods.extend(found.periods)
                location.unparsed += found.unparsed
        if not locations:
            locations[""] = LocationRows("")
        return [
            self._draft(document, number, number_evidence, issued, date_evidence, location)
            for location in locations.values()
        ]

    def _draft(
        self,
        document: InputDocument,
        number: str | None,
        number_evidence: tuple[SourceEvidence, ...],
        issued: date | None,
        date_evidence: tuple[SourceEvidence, ...],
        location: LocationRows,
    ) -> InvoiceDraft:
        period, period_evidence = representative_period(location.periods)
        fields = {
            INVOICE_NUMBER: required_value(number, number_evidence, "invoice number"),
            INVOICE_DATE: required_value(issued, date_evidence, "invoice date"),
            BILLING_PERIOD: required_value(period, period_evidence, "billing period"),
            LOCATION_IDENTIFIER: required_value(
                location.identifier or None,
                tuple(location.evidence),
                "consumption-location identifier",
            ),
        }
        add_energy_summary_fields(fields, location.details)
        fields.update(extract_client_identity_fields(document))
        if "cumparator" in plain_text(document.pages[0].text[:250]):
            for page in document.pages[:1]:
                for line in page.text.splitlines():
                    taxes = re.findall(r"Cod fiscal:\s*(RO\d{2,10})", line, re.I)
                    if len(taxes) == 2:
                        fields[CLIENT_TAX_ID] = FieldValue(
                            taxes[-1].upper(),
                            FieldStatus.EXTRACTED,
                            (SourceEvidence(page.number, line.strip(), "client tax id"),),
                        )
                        break
        issues = field_issues(fields)
        if not location.details:
            issues.append(
                ValidationIssue(
                    None,
                    IssueSeverity.ERROR,
                    "Nu au fost găsite liniile de preț OMV Petrom.",
                    IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )
        if not any(detail.category is EnergyCategory.ACTIVE_ENERGY for detail in location.details):
            issues.append(
                ValidationIssue(
                    None,
                    IssueSeverity.ERROR,
                    "Linia principală de energie activă OMV Petrom lipsește.",
                    IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )
        if location.unparsed:
            issues.append(
                ValidationIssue(
                    None,
                    IssueSeverity.ERROR,
                    f"{location.unparsed} linii de preț OMV Petrom nu au putut fi extrase complet.",
                    IssueCode.INVALID_PRICE_RECONCILIATION,
                )
            )
        return InvoiceDraft(
            document_id=f"{document.path.stem}:{location.identifier or 'missing-location'}",
            source_filename=document.path.name,
            supplier=self.supplier_name,
            fields=fields,
            price_details=location.details,
            issues=issues,
            metadata={
                "page_numbers": sorted({detail.evidence.page_number for detail in location.details})
            },
        )
