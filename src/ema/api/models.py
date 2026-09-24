"""HTTP shapes for shared use-case results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from ema.core.review.models import Readiness


class SessionResult(BaseModel):
    csrf: str


class Health(BaseModel):
    status: Literal["ok"]
    version: str


class Job(BaseModel):
    id: str
    type: Literal["invoices", "piee", "audit", "reporting"]
    client_slug: str
    year: int | None
    state: str


class NewJobResult(BaseModel):
    id: str


class JobStatus(BaseModel):
    id: str
    type: str
    state: str
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
    status: Literal["missing", "ready", "drafted", "done", "later", "n/a"]
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
