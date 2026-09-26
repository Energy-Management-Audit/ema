"""Structured outputs of the MCP tools; paths are absolute strings."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ema.core.review.models import Decision, Field


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceInfo(_Output):
    workspace: str
    jobs: int
    import_roots: list[str]


class JobSummary(_Output):
    id: str
    type: str
    client_slug: str
    year: int | None
    state: str
    revision: int


class JobList(_Output):
    jobs: list[JobSummary]


class RunView(_Output):
    id: str
    stage: str
    state: str
    publication: str | None
    outcome: str | None
    error: str | None


class JobStatusView(_Output):
    id: str
    type: str
    state: str
    revision: int
    runs: list[RunView]


class FieldList(_Output):
    fields: list[Field]


class DecisionList(_Output):
    decisions: list[Decision]


class SectionView(_Output):
    section_id: str
    title: str
    status: str
    revision: int
    stale: bool
    reason: str | None


class SectionList(_Output):
    sections: list[SectionView]


class ReviewItem(_Output):
    code: str
    location: str
    detail: str


class AuditDraft(_Output):
    job: str
    run: str
    section: str
    draft_status: Literal["drafted", "missing"]
    section_status: str
    coverage: float
    cited_sentences: int
    total_sentences: int
    review: list[ReviewItem]
    draft_path: str
    review_path: str


class PieeDraft(_Output):
    job: str
    run: str
    draft: str
    workbook: str
