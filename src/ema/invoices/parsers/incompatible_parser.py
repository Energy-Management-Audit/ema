from __future__ import annotations

import unicodedata

from ema.invoices.configuration.user_messages import ISSUE_MESSAGES
from ema.invoices.models import (
    InputDocument,
    InvoiceDraft,
    IssueCode,
    IssueSeverity,
    ValidationIssue,
)
from ema.invoices.parsers.client_identity import extract_client_identity_fields


class MetNaturalGasInvoiceParser:
    supplier_name = "MET ROMANIA ENERGY S.A."
    layout_version = "1"
    document_type = "natural_gas_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        text = _plain_text("\n".join(page.text for page in document.pages))
        return "met romania energy" in text and (
            "gaze naturale" in text or "furnizare gaze" in text
        )

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        return [
            _blocked_draft(
                document,
                self.supplier_name,
                (
                    "A fost recunoscută o factură MET de gaze naturale. Centralizatorul "
                    "actual acceptă numai facturi de energie electrică."
                ),
            )
        ]


class SeeExclusiveRefactoringParser:
    supplier_name = "SEE EXCLUSIVE DEVELOPMENT S.R.L."
    layout_version = "1"
    document_type = "energy_refactoring"

    def recognizes(self, document: InputDocument) -> bool:
        text = _plain_text("\n".join(page.text for page in document.pages))
        supplier_matches = (
            "see exclusive development" in text
            or ("see exclusive" in text and "development srl" in text)
            or "ro20945190" in text
        )
        document_matches = "refactur" in text or "regularizare consum energie" in text
        return supplier_matches and document_matches

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        return [
            _blocked_draft(
                document,
                self.supplier_name,
                (
                    "A fost recunoscut un document de refacturare fără o defalcare sigură "
                    "în kWh și preț unitar. Nu poate fi mapat în centralizatorul actual."
                ),
            )
        ]


class EngieEInvoiceCompanionParser:
    supplier_name = "ENGIE Romania S.A."
    layout_version = "efactura-companion-v1"
    document_type = "invoice_companion"

    def recognizes(self, document: InputDocument) -> bool:
        text = _plain_text("\n".join(page.text for page in document.pages))
        supplier_matches = "engie" in text or "ro13093222" in text
        client_matches = any(
            field.value for field in extract_client_identity_fields(document).values()
        )
        invoice_matches = "efactura" in text or "factura" in text
        is_annex = "anexa" in document.path.name.casefold()
        return supplier_matches and client_matches and invoice_matches and not is_annex

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        return [
            _blocked_draft(
                document,
                self.supplier_name,
                (
                    "Document e-Factura ENGIE recunoscut drept însoțitor al anexei detaliate; "
                    "anexa este sursa exportată pentru POD, contoare și pozițiile de preț."
                ),
            )
        ]


def _blocked_draft(
    document: InputDocument,
    supplier: str,
    message: str,
) -> InvoiceDraft:
    return InvoiceDraft(
        document_id=document.path.stem,
        source_filename=document.path.name,
        supplier=supplier,
        issues=[
            ValidationIssue(
                field_id=None,
                severity=IssueSeverity.ERROR,
                message=message,
                code=IssueCode.INCOMPATIBLE_DOCUMENT_TYPE,
            )
        ],
        metadata={
            "ocr_used": document.used_ocr,
            "document_type": "incompatible",
            "issue_message": ISSUE_MESSAGES[IssueCode.INCOMPATIBLE_DOCUMENT_TYPE],
        },
    )


def _plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(character for character in normalized if not unicodedata.combining(character))
        .casefold()
        .replace("ã", "a")
        .split()
    )
