"""Audit stage commands: section drafting by replay or live, and the job stages."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer

from ema.audit.chapter_five import run_measurements
from ema.audit.draft_stage import draft_section
from ema.audit.measures import run_measures
from ema.audit.measures_form import write_measures_form
from ema.audit.readings import run_readings
from ema.audit.stages import add_document, new_audit, start_audit_stage
from ema.audit.visit import run_visit
from ema.core.config import workspace_path
from ema.core.errors import EmaError
from ema.core.jobs import get_job, recover, subscribe
from ema.core.jobs import status as job_status
from ema.core.workspace import Workspace

audit_app = typer.Typer()


@audit_app.command("visit")
def visit(job: str) -> None:
    ws = Workspace(workspace_path())
    recover(ws)
    typer.echo(json.dumps(asdict(run_visit(ws, job)), ensure_ascii=False))


@audit_app.command("readings")
def readings(
    job: str,
    recording: Path | None = typer.Option(None, "--recording"),  # noqa: B008
) -> None:
    ws = Workspace(workspace_path())
    recover(ws)
    typer.echo(json.dumps(asdict(run_readings(ws, job, recording=recording)), ensure_ascii=False))


@audit_app.command("measurements")
def measurements(job: str) -> None:
    ws = Workspace(workspace_path())
    recover(ws)
    typer.echo(json.dumps(asdict(run_measurements(ws, job)), ensure_ascii=False, default=str))


@audit_app.command("draft")
def draft(
    job: str,
    section: str,
    draft_recording: Path | None = typer.Option(None, "--draft-recording"),  # noqa: B008
    support_recording: Path | None = typer.Option(None, "--support-recording"),  # noqa: B008
) -> None:
    """Draft one chapter 2-3 section: by replay with both recordings, live with neither."""
    ws = Workspace(workspace_path())
    recover(ws)
    result = draft_section(
        ws, job, section, draft_recording=draft_recording, support_recording=support_recording
    )
    typer.echo(json.dumps(asdict(result), ensure_ascii=False, default=str))


@audit_app.command("measures")
def measures(job: str) -> None:
    """Read the uploaded measures form and prepare chapter 6."""
    ws = Workspace(workspace_path())
    recover(ws)
    typer.echo(json.dumps(asdict(run_measures(ws, job)), ensure_ascii=False, default=str))


@audit_app.command("measures-form")
def measures_form(dest: Path) -> None:
    """Write a blank Măsuri propuse workbook."""
    typer.echo(str(write_measures_form(dest)))


@audit_app.command("new")
def new(
    client: str = typer.Option(..., "--client", help="CUI-ul clientului înregistrat."),
    year: int = typer.Option(..., "--year"),
) -> None:
    typer.echo(new_audit(Workspace(workspace_path()), client, year))


@audit_app.command("add")
def add(job: str, sources: list[Path], slot: str | None = typer.Option(None, "--slot")) -> None:
    if slot is not None and len(sources) != 1:
        raise EmaError("invalid_slot", "Un singur fişier poate ocupa locul ales.", slot)
    ws = Workspace(workspace_path())
    for source in sources:
        typer.echo(add_document(ws, job, source, slot))


@audit_app.command("run")
def run(job: str, stage: str) -> None:
    ws = Workspace(workspace_path())
    recover(ws)
    started = start_audit_stage(ws, job, stage, int(str(get_job(ws, job)["revision"])))
    for _ in subscribe(ws, job):
        pass
    typer.echo(json.dumps({"run_id": started, "state": job_status(ws, job).state}))


@audit_app.command("status")
def status(job: str) -> None:
    typer.echo(json.dumps(asdict(job_status(Workspace(workspace_path()), job)), default=str))
