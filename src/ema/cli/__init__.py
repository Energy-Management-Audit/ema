"""Command line interface."""

import json
import socket
from pathlib import Path

import typer
import uvicorn

from ema import __version__
from ema.api import create_app
from ema.cli.review import job_review_app
from ema.core.backup import backup, restore
from ema.core.config import workspace_path
from ema.core.errors import EmaError
from ema.core.intake import ItemOutcome, intake_legacy
from ema.core.jobs import (
    StageContext,
    StageOutcome,
    list_jobs,
    recover,
    run_stage,
    status,
    subscribe,
)
from ema.core.logging import write_event
from ema.core.workspace import Workspace
from ema.invoices import run_batch

_app = typer.Typer(no_args_is_help=True, invoke_without_command=True)
workspace_app = typer.Typer()
job_app = typer.Typer()
invoices_app = typer.Typer()
_app.add_typer(workspace_app, name="workspace")
_app.add_typer(job_app, name="job")
job_app.add_typer(job_review_app)
_app.add_typer(invoices_app, name="invoices")


def _workspace() -> Workspace:
    ws = Workspace(workspace_path())
    recover(ws)
    return ws


@_app.callback()
def root(version: bool = typer.Option(False, "--version", is_eager=True)) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@workspace_app.command("info")
def workspace_info() -> None:
    ws = _workspace()
    typer.echo(json.dumps({"workspace": str(ws.root), "jobs": len(list_jobs(ws))}))


@_app.command("backup")
def backup_command(dest_dir: Path) -> None:
    typer.echo(str(backup(_workspace(), dest_dir)))


@_app.command("restore")
def restore_command(archive: Path, dest_dir: Path) -> None:
    typer.echo(str(restore(archive, dest_dir)))


@job_app.command("list")
def job_list() -> None:
    typer.echo(json.dumps(list_jobs(_workspace()), ensure_ascii=False))


@job_app.command("status")
def job_status(job: str) -> None:
    result = status(_workspace(), job)
    typer.echo(json.dumps(result.__dict__, ensure_ascii=False))


@invoices_app.command("extract")
def invoices_extract(folder: Path, client: str = typer.Option(..., "--client")) -> None:
    if not folder.is_dir():
        raise EmaError("invoice_folder", "Dosarul facturilor nu există.", str(folder))
    sources = sorted(
        path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"
    )
    result = run_batch(_workspace(), client, sources)
    for outcome in result.outcomes:
        reason = f" — {outcome['reason']}" if outcome["reason"] else ""
        detail = outcome["metadata"]["technical_detail"] if outcome["status"] == "failed" else None
        cause = f": {detail}" if detail else ""
        typer.echo(f"{outcome['source_path']}: {outcome['status']}{reason}{cause}")
    if result.omitted:
        typer.echo(f"Omise din Excel ({len(result.omitted)}): {', '.join(result.omitted)}")
    typer.echo(result.client_notice)
    if result.workbook is not None:
        typer.echo(str(result.workbook))


@_app.command("intake")
def intake_command(job: str, collection: str) -> None:
    ws = _workspace()
    results: list[ItemOutcome] = []

    def stage(ctx: StageContext) -> StageOutcome:
        return intake_legacy(ctx, collection, results.append)

    run = run_stage(ws, job, "intake", stage)
    for _ in subscribe(ws, job):
        pass
    current = status(ws, job)
    recorded = next(entry for entry in current.runs if entry["id"] == run)
    if recorded["state"] == "failed":
        raise EmaError("intake_failed", "Prelucrarea fișierului a eșuat.", str(recorded["error"]))
    if recorded["state"] == "cancelled":
        raise EmaError("intake_cancelled", "Prelucrarea fișierului a fost anulată.", collection)
    for item in results:
        typer.echo(
            json.dumps(
                {
                    "slot": item.slot,
                    "version": item.version,
                    "sha": item.file_sha[:12],
                    "kind": item.kind.value,
                    "status": item.status,
                    "words_original": item.original_words,
                    "words_converted": item.converted_words,
                    "shape_words": item.shape_words,
                    "warning": item.warning,
                    "error_code": item.error_code,
                    "detail": item.detail,
                },
                ensure_ascii=False,
            )
        )


@_app.command("serve")
def serve(port: int = typer.Option(0, min=0, max=65535)) -> None:
    ws = _workspace()
    if port == 0:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
    uvicorn.run(create_app(ws, port), host="127.0.0.1", port=port)


def app() -> None:
    try:
        _app()
    except EmaError as exc:
        try:
            with Workspace(workspace_path()).app_log() as handle:
                write_event(handle, "interface_error", code=exc.code, detail=exc.detail)
        except (EmaError, OSError):
            pass
        typer.echo(exc.user_message_ro, err=True)
        raise SystemExit(1) from None
