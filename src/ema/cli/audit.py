"""Audit section drafting over recorded AI responses."""

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
from ema.audit.visit import run_visit
from ema.core.config import workspace_path
from ema.core.jobs import recover
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
    """Draft one chapter 2-3 section by replay; live AI drafting is not enabled."""
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
