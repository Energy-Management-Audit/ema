from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

FieldScalar = str | Decimal | date | int | None


class FieldStatus(StrEnum):
    EXTRACTED = "extracted"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    MANUALLY_CORRECTED = "manually_corrected"
    APPROVED = "approved"
    NOT_PROVIDED = "not_provided"


class ClientIdentityStatus(StrEnum):
    RESOLVED = "resolved"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"


class IssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class IssueCode(StrEnum):
    UNSUPPORTED_SUPPLIER = "UNSUPPORTED_SUPPLIER"
    DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"
    INCOMPATIBLE_DOCUMENT_TYPE = "INCOMPATIBLE_DOCUMENT_TYPE"
    MISSING_LOCATION_IDENTIFIER = "MISSING_LOCATION_IDENTIFIER"
    MISSING_METER_IDENTIFIER = "MISSING_METER_IDENTIFIER"
    MISSING_CONSUMPTION_PERIOD = "MISSING_CONSUMPTION_PERIOD"
    AMBIGUOUS_INVOICE_NUMBER = "AMBIGUOUS_INVOICE_NUMBER"
    INVALID_PRICE_RECONCILIATION = "INVALID_PRICE_RECONCILIATION"
    INVOICE_POSITION_COUNT_MISMATCH = "INVOICE_POSITION_COUNT_MISMATCH"
    OCR_RUNTIME_UNAVAILABLE = "OCR_RUNTIME_UNAVAILABLE"
    OCR_TIMEOUT = "OCR_TIMEOUT"
    PDF_READ_FAILED = "PDF_READ_FAILED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    MISSING_CLIENT_IDENTITY = "MISSING_CLIENT_IDENTITY"
    AMBIGUOUS_CLIENT_IDENTITY = "AMBIGUOUS_CLIENT_IDENTITY"
    MULTIPLE_LOCATIONS = "MULTIPLE_LOCATIONS"
    CONFLICTING_INVOICE = "CONFLICTING_INVOICE"


class EnergyCategory(StrEnum):
    ACTIVE_ENERGY = "active_energy"
    ACTIVE_ENERGY_LOSSES = "active_energy_losses"
    REACTIVE_CAPACITIVE = "reactive_capacitive"
    REACTIVE_INDUCTIVE = "reactive_inductive"
    GREEN_CERTIFICATES = "green_certificates"
    OTHER = "other"


@dataclass(frozen=True)
class SourceEvidence:
    page_number: int
    snippet: str
    label: str | None = None


@dataclass(frozen=True)
class FieldValue:
    value: FieldScalar
    status: FieldStatus
    evidence: tuple[SourceEvidence, ...] = ()
    message: str | None = None

    @property
    def requires_review(self) -> bool:
        return self.status in {
            FieldStatus.MISSING,
            FieldStatus.AMBIGUOUS,
            FieldStatus.INVALID,
        }


@dataclass(frozen=True)
class PriceDetail:
    category: EnergyCategory
    description: str
    source_quantity: Decimal
    source_unit: str
    source_unit_price: Decimal
    normalized_quantity: Decimal
    normalized_unit: str
    normalized_unit_price: Decimal
    net_value: Decimal
    evidence: SourceEvidence


@dataclass(frozen=True)
class ValidationIssue:
    field_id: str | None
    severity: IssueSeverity
    message: str
    code: IssueCode | None = None


@dataclass(frozen=True)
class ClientIdentity:
    legal_name: str | None
    tax_id: str | None
    normalized_legal_name: str | None
    normalized_tax_id: str | None
    status: ClientIdentityStatus
    evidence: tuple[SourceEvidence, ...] = ()
    reason: str | None = None

    @property
    def group_key(self) -> str | None:
        if self.status is not ClientIdentityStatus.RESOLVED:
            return None
        if self.normalized_tax_id:
            return f"tax:{self.normalized_tax_id}"
        if self.normalized_legal_name:
            return f"name:{self.normalized_legal_name}"
        return None


def normalize_client_name(value: str | None) -> str | None:
    if value is None:
        return None
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^A-Za-z0-9]+", " ", ascii_value).strip().upper()
    return re.sub(r"\s+", " ", normalized) or None


def normalize_client_tax_id(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    return digits or None


@dataclass
class InvoiceDraft:
    document_id: str
    source_filename: str
    supplier: str | None = None
    fields: dict[str, FieldValue] = field(default_factory=lambda: {})
    price_details: list[PriceDetail] = field(default_factory=lambda: [])
    issues: list[ValidationIssue] = field(default_factory=lambda: [])
    metadata: dict[str, Any] = field(default_factory=lambda: {})

    @property
    def flagged_field_ids(self) -> list[str]:
        return [field_id for field_id, value in self.fields.items() if value.requires_review]

    @property
    def has_blocking_issues(self) -> bool:
        return any(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def is_exportable(self) -> bool:
        return not self.flagged_field_ids and not self.has_blocking_issues

    @property
    def client_identity(self) -> ClientIdentity:
        name = self.fields.get("client_name")
        tax_id = self.fields.get("client_tax_id")
        evidence = tuple(
            dict.fromkeys(
                (
                    *(() if name is None else name.evidence),
                    *(() if tax_id is None else tax_id.evidence),
                )
            )
        )
        if (
            name is None
            or name.value in (None, "")
            or name.status
            in {
                FieldStatus.MISSING,
                FieldStatus.INVALID,
            }
        ):
            return ClientIdentity(
                legal_name=None,
                tax_id=str(tax_id.value) if tax_id and tax_id.value else None,
                normalized_legal_name=None,
                normalized_tax_id=normalize_client_tax_id(
                    str(tax_id.value) if tax_id and tax_id.value else None
                ),
                status=ClientIdentityStatus.MISSING,
                evidence=evidence,
                reason=name.message if name else "Client name was not extracted.",
            )
        if name.status is FieldStatus.AMBIGUOUS or (
            tax_id is not None and tax_id.status in {FieldStatus.AMBIGUOUS, FieldStatus.INVALID}
        ):
            return ClientIdentity(
                legal_name=str(name.value),
                tax_id=str(tax_id.value) if tax_id and tax_id.value else None,
                normalized_legal_name=normalize_client_name(str(name.value)),
                normalized_tax_id=normalize_client_tax_id(
                    str(tax_id.value) if tax_id and tax_id.value else None
                ),
                status=ClientIdentityStatus.AMBIGUOUS,
                evidence=evidence,
                reason=name.message or (tax_id.message if tax_id else None),
            )
        return ClientIdentity(
            legal_name=str(name.value),
            tax_id=str(tax_id.value) if tax_id and tax_id.value else None,
            normalized_legal_name=normalize_client_name(str(name.value)),
            normalized_tax_id=normalize_client_tax_id(
                str(tax_id.value) if tax_id and tax_id.value else None
            ),
            status=ClientIdentityStatus.RESOLVED,
            evidence=evidence,
        )


@dataclass(frozen=True)
class TextBlock:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class DocumentPage:
    number: int
    text: str
    blocks: tuple[TextBlock, ...]
    extraction_method: str = "embedded"


@dataclass(frozen=True)
class InputDocument:
    path: Path
    pages: tuple[DocumentPage, ...]

    @property
    def has_meaningful_text(self) -> bool:
        return any(page.text.strip() for page in self.pages)

    @property
    def used_ocr(self) -> bool:
        return any(page.extraction_method == "ocr" for page in self.pages)
