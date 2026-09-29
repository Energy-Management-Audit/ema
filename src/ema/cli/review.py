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
from ema.core.config import workspace_path
from ema.core.errors import EmaError
from ema.core.review import (
    decide,
    export,
    export_final,
    fields,
    log,
    output_path,
    undo,
)
from ema.core.review.models import Readiness
from ema.core.review.readiness import FinalOutput, final_checks
from ema.core.workspace import Workspace
from ema.workflows_registry import workflow_for as _workflow

job_review_app = typer.Typer()


def _ws() -> Workspace:
    return Workspace(workspace_path())


def _terminal() -> bool:
    return sys.stdin.isatty()


def _print(value: Any) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, default=str))


@job_review_app.command("sections")
def sections_command(job: str) -> None:
    names = {section.id: section.title for section in CATALOGUE}
    typer.echo("ID | Stare | Secţiune | Motiv")
    for state in statuses(_ws(), job):
        label = state.status.value + (" (depăşit)" if state.stale else "")
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
        raise EmaError("status_invalid", "Starea secţiunii este invalidă.", to)
    if to in ("done", "n/a"):
        if not _terminal():
            raise EmaError(
                "confirmation_requires_terminal", "Confirmarea necesită un terminal.", to
            )
        if not typer.confirm(f"Confirmaţi {to} pentru {section_id}?", default=False):
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
    checks = final_checks(ws, job, workflow) if final else None
    readiness = (
        Readiness.model_validate(checks["readiness"]) if checks else workflow.readiness(ws, job)
    )
    _print(readiness.model_dump(mode="json"))
    if checks is not None:
        if not readiness.final_ok:
            raise EmaError("not_ready", "Lucrarea nu este pregătită pentru export.", job)
        if not _terminal():
            raise EmaError("approval_requires_terminal", "Aprobarea necesită un terminal.", job)
        final_output = FinalOutput.model_validate(checks["final"]) if checks["final"] else None
        output_id = final_output.output_id if final_output else None
        if output_id is None:
            raise EmaError("output_missing", "Documentul final lipseşte.", job)
        _print({"rendered_path": str(output_path(ws, job, output_id))})
        if not typer.confirm("Aprobaţi exportul final?", default=False):
            raise typer.Exit(code=2)
        result = export_final(
            ws,
            job,
            output_id,
            str(checks["readiness_hash"]),
            dest,
            workflow=workflow,
        )
        _print(result.model_dump(mode="json"))
        return
    _print({"path": str(export(ws, job, workflow, final=False, dest=dest, actor="user"))})
