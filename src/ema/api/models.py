"""HTTP shapes for shared use-case results."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as PydanticField

from ema.core.review.models import Readiness


class SessionResult(BaseModel):
    csrf: str


class Health(BaseModel):
    status: Literal["ok"]
    version: str


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Job(BaseModel):
    id: str
    type: Literal["invoices", "piee", "audit", "reporting"]
    client_slug: str
    year: int | None
    state: str
    revision: int


class NewJobResult(BaseModel):
    id: str


class JobStatus(BaseModel):
    id: str
    type: str
    state: str
    revision: int
    runs: list[dict[str, Any]]


class CancelResult(BaseModel):
    cancelled: bool


class DeleteResult(BaseModel):
    deleted: bool


class SlotVersion(BaseModel):
    job_id: str
    slot: str
    version: int
    file_sha: str
    origin: str
    converted_from: str | None


class SectionState(BaseModel):
    section_id: str
    status: Literal["missing", "ready", "drafted", "done", "later", "n/a", "n/a proposed"]
    revision: int
    stale: bool
    reason: str | None
    fingerprint: list[str]
    fact_revisions: dict[str, int | None] | None
    material_inputs: dict[str, Any] | None
    changed_input: str | None
    na_applicable: bool | None


class ExportChecks(BaseModel):
    readiness: Readiness
    readiness_hash: str


class ExportResult(BaseModel):
    output_id: str


class Site(BaseModel):
    id: str
    name: str
    address: str | None = None


class Contact(BaseModel):
    id: str
    name: str
    role: str | None = None


class ClientIn(BaseModel):
    name: str = PydanticField(min_length=1)
    cui: str | None = None


class ClientPatch(BaseModel):
    name: str | None = PydanticField(default=None, min_length=1)
    cui: str | None = None
    caen: str | None = None
    sites: list[Site] | None = None
    contacts: list[Contact] | None = None
    on_revision: int


class Client(BaseModel):
    id: str
    name: str | None = None
    cui: str | None = None
    caen: str | None = None
    sites: list[Site]
    contacts: list[Contact]
    revision: int
    anaf_refreshed_at: str | None = None


class ClientFile(BaseModel):
    sha: str
    name: str
    size_bytes: int
    kind: str
    intake: Literal["stored"]


class FileVersion(BaseModel):
    version: int
    sha: str
    name: str
    size_bytes: int


class AnafState(BaseModel):
    client_id: str
    status: str
    retrieved_at: str | None = None
    source_url: str | None = None


class RunStart(BaseModel):
    run_id: str
    stage: str
    state: Literal["running"]


class Output(BaseModel):
    id: str
    version: int
    kind: Literal["draft", "final"]
    media_type: str
    size_bytes: int
    edited_externally: bool
    name: str
    created_at: str | None
    run_id: str
    stage: str


class PieeImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on_revision: int


class SummaryFigure(BaseModel):
    value: Decimal | None
    unit: str
    field_ids: list[str]
    missing: list[str]


class PieeSummary(BaseModel):
    total_tep: SummaryFigure
    annual_check: Literal["match", "decided", "mismatch", "missing"]
    savings_mwh: SummaryFigure
    investment_thousand_lei: SummaryFigure
    measures_total: int
    measures_complete: int
    measures_without_term: int


class PieeGenerate(BaseModel):
    kind: Literal["draft"]
    on_revision: int


class PrelucrareInput(BaseModel):
    file_id: str
    role: Literal["input"]


class PrelucrareState(BaseModel):
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    authority: Literal["input_for_covered_years", "generated", "none"]


class Measure(BaseModel):
    id: str
    name: str
    origin: str
    savings_mwh: float | None = None
    evidence_ids: list[str]
    missing: list[str]


class CarrierData(BaseModel):
    carrier: str
    annual_mwh: list[float | None]
    evidence_ids: list[str]


class PieeDataView(BaseModel):
    years: list[int]
    carriers: list[CarrierData]
    conflicts: list[str]
    missing: list[str]


class ExtractionSettings(BaseModel):
    ocr: bool
    flag_uncertain: bool
    auto_accept_exact: bool


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="allow")
    theme: Literal["light", "dark"] | None = None
    default_provider: Literal["gemini", "openai"] | None = None
    extraction: ExtractionSettings | None = None
    backup_dir: str | None = None


class ProviderState(BaseModel):
    present: bool
    verified_at: str | None = None
    hint: str | None = None
    source: Literal["environment", "keyring"] | None = None


class BackupState(BaseModel):
    dir: str | None
    last_at: str | None
    last_size: int | None
    last_name: str | None
    due: bool


class BackupResult(BaseModel):
    name: str
    path: str
    created_at: str
    size_bytes: int


class ProviderKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = PydanticField(min_length=1, max_length=512)

    @field_validator("key", mode="before")
    @classmethod
    def valid_key(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value or any(character.isspace() for character in value):
            raise ValueError("invalid provider key")
        return value


class SettingsView(BaseModel):
    theme: Literal["light", "dark"]
    default_provider: Literal["gemini", "openai"] | None = None
    providers: dict[str, ProviderState]
    extraction: ExtractionSettings
    workspace: str
    backup: BackupState


class ProviderTest(BaseModel):
    provider: str
    status: Literal["no_key", "ok", "failed"]
    verified_at: str | None = None


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


class InvoiceRow(BaseModel):
    id: str
    month: str | None = None
    consumption_kwh: float | None = None
    source_evidence_ids: list[str]
    anomalies: list[str]


class InvoiceBatchView(BaseModel):
    batch_id: str
    identity: InvoiceIdentity
    rows: list[InvoiceRow]
    missing_months: list[str]


class ReportingIn(BaseModel):
    years: list[int]
    client_ids: list[str]


class ReportException(BaseModel):
    client_id: str
    year: int | None = None
    code: str
    detail: str


class ReportingRun(BaseModel):
    id: str
    years: list[int]
    client_ids: list[str]
    state: Literal["running", "ready", "failed", "cancelled"]
    exceptions: list[ReportException]
    output_id: str | None = None


class ConflictChoice(BaseModel):
    candidate_id: str
    on_revision: int


class SectionPatch(BaseModel):
    section_id: str
    status: Literal["missing", "ready", "drafted", "done", "later", "n/a"]
    on_revision: int
    reason: str | None = None
    confirm: bool = False


class NaProposal(BaseModel):
    reason: str
    on_revision: int
