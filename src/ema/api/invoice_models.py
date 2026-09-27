"""HTTP shapes for invoice batch review."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class InvoiceIdentityInput(BaseModel):
    client_id: str
    on_revision: int
    confirm: bool


class InvoiceCandidate(BaseModel):
    client_id: str
    cui: str | None = None
    pod: str | None = None


class InvoiceIdentity(BaseModel):
    batch_id: str
    candidate: InvoiceCandidate | None = None
    confirmed: bool
    evidence_ids: list[str]
    revision: int
    name: str | None = None
    reasons: IdentityReasons
    pod_fill: list[PodFill]
    memory: list[dict[str, str]]
    files_total: int
    client_cui: str | None = None


class IdentityReasons(BaseModel):
    printed: int
    pods: list[str]
    other_client: int


class PodFill(BaseModel):
    pod: str
    files: list[str]
    source_count: int


class InvoiceSource(BaseModel):
    page: int
    snippet: str


class InvoiceOutlier(BaseModel):
    ratio: Decimal
    neighbours_mean_kwh: Decimal


class InvoiceRow(BaseModel):
    id: str
    month: str | None = None
    consumption_kwh: Decimal | None = None
    source_evidence_ids: list[str]
    anomalies: list[str]
    file_name: str
    slot: str
    supplier: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    status: str
    issues: list[str]
    price_lei_kwh: Decimal | None = None
    value_lei: Decimal | None = None
    sources: dict[str, InvoiceSource]
    outlier: InvoiceOutlier | None = None


class InvoiceFile(BaseModel):
    slot: str
    file_name: str
    status: str
    reason: str | None = None


class InvoiceTotals(BaseModel):
    months: int
    consumption_kwh: Decimal
    value_lei: Decimal
    price_avg_lei_kwh: Decimal | None


class InvoiceUploadAdded(BaseModel):
    slot: str
    file_name: str
    sha: str


class InvoiceUploadRejected(BaseModel):
    file_name: str
    code: str
    reason: str


class InvoiceUpload(BaseModel):
    added: list[InvoiceUploadAdded]
    rejected: list[InvoiceUploadRejected]


class InvoiceBatchView(BaseModel):
    batch_id: str
    identity: InvoiceIdentity
    rows: list[InvoiceRow]
    missing_months: list[str]
    files: list[InvoiceFile]
    totals: InvoiceTotals
    year: int | None = None
    read_ended_at: str | None = None
