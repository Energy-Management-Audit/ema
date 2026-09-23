"""Review commands backed by the shared use cases."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import typer

from ema.audit.catalogue import CATALOGUE
from ema.audit.sections import Status, set_status, statuses
from ema.audit.workflow import AuditWorkflow
from ema.core.config import workspace_path
from ema.core.errors import EmaError
from ema.core.review import (
    approve_final,
    decide,
    export,
    fields,
    log,
    output_path,
    readiness_hash,
    undo,
)
from ema.core.review.readiness import Workflow
from ema.core.workspace import Workspace

job_review_app = typer.Typer()

# Workflow slices populate these entries through static imports as they land.
WORKFLOWS: dict[str, Workflow] = {"audit": AuditWorkflow()}


def _ws() -> Workspace:
    return Workspace(workspace_path())


def _terminal() -> bool:
    return sys.stdin.isatty()


def _workflow(ws: Workspace, job: str) -> Workflow:
    with ws.connect() as db:
        row = db.execute("SELECT type FROM jobs WHERE id=? AND deleted=0", (job,)).fetchone()
    if row is None:
        raise EmaError("job_missing", "Lucrarea nu există.", job)
    workflow = WORKFLOWS.get(str(row["type"]))
    if workflow is None:
        raise EmaError(
            "workflow_unavailable", "Fluxul de lucru nu este disponibil.", str(row["type"])
        )
    return workflow


def _print(value: Any) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, default=str))


@job_review_app.command("sections")
def sections_command(job: str) -> None:
    names = {section.id: section.title for section in CATALOGUE}
    typer.echo("ID | Stare | Secțiune | Motiv")
    for state in statuses(_ws(), job):
        label = state.status.value + (" (depășit)" if state.stale else "")
        typer.echo(
            f"{state.section_id} | {label} | {names[state.section_id]} | {state.reason or ''}"
        )


@job_review_app.command("section")
def section_command(
    job: str,
    section_id: str,
    to: str,
    reason: str | None = typer.Option(None, "--reason"),
) -> None:
    if to not in ("done", "n/a", "later"):
        raise EmaError("status_invalid", "Starea secțiunii este invalidă.", to)
    if to in ("done", "n/a"):
        if not _terminal():
            raise EmaError(
                "confirmation_requires_terminal", "Confirmarea necesită un terminal.", to
            )
        if not typer.confirm(f"Confirmați {to} pentru {section_id}?", default=False):
            raise typer.Exit(code=2)
    _print(set_status(_ws(), job, section_id, Status(to), "user", reason).payload())


@job_review_app.command("fields")
def field_list(job: str, status: str | None = None) -> None:
    _print([item.model_dump(mode="json") for item in fields(_ws(), job, status=status)])


@job_review_app.command("decide")
def decide_command(
    job: str,
    field_id: str,
    action: str,
    value: Annotated[str | None, typer.Argument()] = None,
    on_revision: int = typer.Option(..., "--on-revision"),
    alternative: str | None = typer.Option(None, "--alternative"),
) -> None:
    if action not in ("accept", "correct", "reject", "choose"):
        raise EmaError("action_invalid", "Decizia este invalidă.", action)
    field = next((item for item in fields(_ws(), job) if item.id == field_id), None)
    parsed: Any = value
    if action == "correct" and field is not None and field.value_type in ("number", "year"):
        try:
            parsed = int(value) if field.value_type == "year" else Decimal(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise EmaError("value_invalid", "Valoarea este invalidă.", str(value)) from exc
    result = decide(
        _ws(), job, field_id, action, on_revision, "user", value=parsed, alternative=alternative
    )  # type: ignore[arg-type]
    _print(result.model_dump(mode="json"))


@job_review_app.command("log")
def log_command(job: str) -> None:
    _print([item.model_dump(mode="json") for item in log(_ws(), job)])


@job_review_app.command("undo")
def undo_command(job: str, decision_id: str) -> None:
    _print(undo(_ws(), job, decision_id, "user").model_dump(mode="json"))


@job_review_app.command("checks")
def checks_command(job: str) -> None:
    ws = _ws()
    _print(_workflow(ws, job).readiness(ws, job).model_dump(mode="json"))


@job_review_app.command("export")
def export_command(
    job: str,
    dest: Annotated[Path, typer.Option("--dest")],
    final: bool = typer.Option(False, "--final"),
) -> None:
    ws = _ws()
    workflow = _workflow(ws, job)
    readiness = workflow.readiness(ws, job)
    _print(readiness.model_dump(mode="json"))
    if final:
        if not readiness.final_ok:
            raise EmaError("not_ready", "Lucrarea nu este pregătită pentru export.", job)
        if not _terminal():
            raise EmaError("approval_requires_terminal", "Aprobarea necesită un terminal.", job)
        output_id = workflow.render(ws, job, "final")
        _print({"rendered_path": str(output_path(ws, job, output_id))})
        if not typer.confirm("Aprobați exportul final?", default=False):
            raise typer.Exit(code=2)
        approve_final(ws, job, output_id, readiness_hash(ws, job, readiness, workflow), "user")
    _print({"path": str(export(ws, job, workflow, final=final, dest=dest, actor="user"))})
