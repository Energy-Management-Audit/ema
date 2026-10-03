"""The stdio MCP server: agent tools over the same use cases as the CLI (R14 applies)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field as Describe

from ema import __version__
from ema.audit.catalogue import CATALOGUE
from ema.audit.chapter_five import run_measurements
from ema.audit.draft_stage import draft_section
from ema.audit.measures import run_measures
from ema.audit.readings import run_readings
from ema.audit.sections import statuses
from ema.audit.visit import run_visit
from ema.core.config import workspace_path
from ema.core.jobs import get_job, list_jobs, recover
from ema.core.jobs import status as read_status
from ema.core.logging import write_event
from ema.core.review import decide, fields, log
from ema.core.review.models import Decision, Readiness
from ema.core.workspace import Workspace
from ema.mcp.boundary import call, input_file, optional_file, resolve_roots
from ema.mcp.models import (
    AuditDraft,
    AuditMeasurements,
    AuditReadings,
    AuditVisit,
    DecisionList,
    FieldList,
    JobList,
    JobStatusView,
    JobSummary,
    PieeDraft,
    RunView,
    SectionList,
    SectionView,
    WorkspaceInfo,
)
from ema.piee.workflow import GenerateRequest
from ema.workflows_registry import generate_draft
from ema.workflows_registry import workflow_for as _workflow

INSTRUCTIONS = (
    "Ema prepares energy-audit paperwork. Through these tools an agent can generate a PIEE draft, "
    "review fields and draft audit sections from recorded facts. Exporting a final document, "
    "marking a section done or n/a, undoing decisions and deleting are a human's actions in the "
    "Ema app and are not available here. Input files must be inside one of the folders listed by "
    "workspace_info."
)

READ = ToolAnnotations(readOnlyHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
FieldStatus = Literal[
    "pending",
    "uncertain",
    "accepted",
    "corrected",
    "rejected",
    "conflict",
    "missing",
    "needs_confirmation",
]


def _in_job[T](ws: Workspace, job: str, fn: Callable[[], T]) -> T:
    """The review use cases do not check the job; an agent is told when it does not exist."""
    get_job(ws, job)
    return fn()


def build_server(ws: Workspace, import_roots: tuple[Path, ...]) -> FastMCP:  # noqa: C901
    server = FastMCP("ema", instructions=INSTRUCTIONS, log_level="WARNING")
    # FastMCP 1.30 takes no version argument; without this the low-level server reports mcp's.
    server._mcp_server.version = __version__  # pyright: ignore[reportPrivateUsage]

    @server.tool(
        description="Workspace folder, number of jobs and the folders input files must be in.",
        annotations=READ,
    )
    async def workspace_info() -> WorkspaceInfo:
        jobs = await call(ws, "workspace_info", lambda: list_jobs(ws))
        return WorkspaceInfo(
            workspace=str(ws.root),
            jobs=len(jobs),
            import_roots=[str(root) for root in import_roots],
        )

    @server.tool(description="List the jobs in the workspace.", annotations=READ)
    async def job_list() -> JobList:
        jobs = await call(ws, "job_list", lambda: list_jobs(ws))
        return JobList(jobs=[JobSummary.model_validate(job) for job in jobs])

    @server.tool(description="A job's state, revision and stage runs.", annotations=READ)
    async def job_status(job: str) -> JobStatusView:
        current = await call(ws, "job_status", lambda: read_status(ws, job))
        runs = [
            RunView.model_validate({key: run[key] for key in RunView.model_fields})
            for run in current.runs
        ]
        return JobStatusView(
            id=current.id,
            type=current.type,
            state=current.state,
            revision=current.revision,
            runs=runs,
        )

    @server.tool(
        description=(
            "A job's review fields with their values, evidence ids and revisions; "
            "optionally filtered by status."
        ),
        annotations=READ,
    )
    async def job_fields(job: str, status: FieldStatus | None = None) -> FieldList:
        found = await call(
            ws, "job_fields", lambda: _in_job(ws, job, lambda: fields(ws, job, status=status))
        )
        return FieldList(fields=found)

    @server.tool(
        description=(
            "Record a review decision on one field (accept, correct, reject, choose) "
            "at the field's current revision."
        ),
        annotations=WRITE,
    )
    async def job_decide(
        job: str,
        field_id: str,
        action: Literal["accept", "correct", "reject", "choose"],
        on_revision: int,
        value: Any = None,
        alternative: str | None = None,
    ) -> Decision:
        return await call(
            ws,
            "job_decide",
            lambda: _in_job(
                ws,
                job,
                lambda: decide(
                    ws,
                    job,
                    field_id,
                    action,
                    on_revision,
                    "agent",
                    value=value,
                    alternative=alternative,
                ),
            ),
        )

    @server.tool(description="The job's decision log (Jurnal).", annotations=READ)
    async def job_log(job: str) -> DecisionList:
        decisions = await call(ws, "job_log", lambda: _in_job(ws, job, lambda: log(ws, job)))
        return DecisionList(decisions=decisions)

    @server.tool(
        description="Readiness of the job: what blocks a draft or a final export.",
        annotations=READ,
    )
    async def job_checks(job: str) -> Readiness:
        return await call(ws, "job_checks", lambda: _workflow(ws, job).readiness(ws, job))

    @server.tool(description="Status of every audit section.", annotations=READ)
    async def audit_sections(job: str) -> SectionList:
        states = await call(ws, "audit_sections", lambda: statuses(ws, job))
        titles = {section.id: section.title for section in CATALOGUE}
        return SectionList(
            sections=[
                SectionView(
                    section_id=state.section_id,
                    title=titles[state.section_id],
                    status=state.status.value,
                    revision=state.revision,
                    stale=state.stale,
                    reason=state.reason,
                )
                for state in states
            ]
        )

    @server.tool(
        description=(
            "Draft one audit section of chapter 2 or 3 from recorded facts, using recorded AI "
            "responses, or the live model when none are given and the live-AI switch is on."
        ),
        annotations=WRITE,
    )
    async def audit_draft_section(
        job: str,
        section: str,
        draft_recording: str | None = None,
        support_recording: str | None = None,
    ) -> AuditDraft:
        result = await call(
            ws,
            "audit_draft_section",
            lambda: draft_section(
                ws,
                job,
                section,
                draft_recording=optional_file(import_roots, draft_recording),
                support_recording=optional_file(import_roots, support_recording),
            ),
        )
        return AuditDraft.model_validate(
            {
                **asdict(result),
                "draft_path": str(result.draft_path),
                "review_path": str(result.review_path),
            }
        )

    @server.tool(description="Register grouped meter and thermal visit photos.", annotations=WRITE)
    async def audit_visit(job: str) -> AuditVisit:
        result = await call(ws, "audit_visit", lambda: run_visit(ws, job))
        return AuditVisit.model_validate(asdict(result))

    @server.tool(
        description="Read visit photos from a recording; live vision is disabled.",
        annotations=WRITE,
    )
    async def audit_readings(job: str, recording: str | None = None) -> AuditReadings:
        result = await call(
            ws,
            "audit_readings",
            lambda: run_readings(ws, job, recording=optional_file(import_roots, recording)),
        )
        return AuditReadings.model_validate(asdict(result))

    @server.tool(
        description="Compose chapter-five measurements from confirmed readings.", annotations=WRITE
    )
    async def audit_measurements(job: str) -> AuditMeasurements:
        result = await call(ws, "audit_measurements", lambda: run_measurements(ws, job))
        return AuditMeasurements.model_validate(
            {**asdict(result), "plan_path": str(result.plan_path)}
        )

    @server.tool(
        description="Read the audit measures form and prepare chapter 6.", annotations=WRITE
    )
    async def audit_measures(job: str) -> dict[str, str | int]:
        result = await call(ws, "audit_measures", lambda: run_measures(ws, job))
        return {
            "job": result.job,
            "run": result.run,
            "measures": result.measures,
            "payback_missing": result.payback_missing,
            "factor_version": result.factor_version,
            "missing_narratives": result.missing_narratives,
            "plan_path": str(result.plan_path),
        }

    @server.tool(
        description=(
            "Create a PIEE job from an Anexa 2-3 (and optional Necesar info, Prelucrare date, "
            "previous PIEE) and generate its draft. Never produces a final."
        ),
        annotations=WRITE,
    )
    async def piee_generate(
        client: str,
        year: Annotated[int, Describe(description="Data year N; the job is for year N+1.")],
        anexa: str,
        necesar: str | None = None,
        prelucrare: str | None = None,
        previous_piee: str | None = None,
    ) -> PieeDraft:
        result = await call(
            ws,
            "piee_generate",
            lambda: generate_draft(
                ws,
                GenerateRequest(
                    client,
                    year,
                    input_file(import_roots, anexa),
                    optional_file(import_roots, necesar),
                    optional_file(import_roots, prelucrare),
                    optional_file(import_roots, previous_piee),
                ),
            ),
        )
        return PieeDraft(
            job=result.job, run=result.run, draft=str(result.draft), workbook=str(result.workbook)
        )

    return server


def serve(import_roots: list[Path]) -> None:
    ws = Workspace(workspace_path())
    recover(ws)
    (ws.root / "imports").mkdir(exist_ok=True)
    roots = resolve_roots(ws, import_roots)
    with ws.app_log() as handle:
        write_event(handle, "mcp_started", version=__version__, import_roots=len(roots))
    build_server(ws, roots).run("stdio")
