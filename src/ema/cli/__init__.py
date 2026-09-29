"""Command line interface."""

import json
import secrets
import socket
import sys
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

import typer
import uvicorn

from ema import __version__
from ema.api import create_app
from ema.api.mock import seed as seed_mock
from ema.cli.audit import audit_app
from ema.cli.desktop import run_desktop
from ema.cli.install_check import check_install as run_install_check
from ema.cli.office_worker import office_worker
from ema.cli.piee import piee_app
from ema.cli.review import job_review_app
from ema.cli.server import uvicorn_config
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
from ema.core.keyring_backend import install_keyring
from ema.core.logging import write_event
from ema.core.workspace import Workspace
from ema.invoices import (
    batch_client,
    confirm_client,
    run_batch,
)
from ema.invoices import (
    export as export_invoices,
)
from ema.invoices import (
    readiness as invoice_readiness,
)
from ema.mcp.server import serve as serve_mcp
from ema.reporting import collect_annexes
from ema.reporting.runs import generate_from_sources

_app = typer.Typer(no_args_is_help=True, invoke_without_command=True)
workspace_app = typer.Typer()
job_app = typer.Typer()
invoices_app = typer.Typer()
reporting_app = typer.Typer()
_app.add_typer(workspace_app, name="workspace")
_app.add_typer(job_app, name="job")
job_app.add_typer(job_review_app)
_app.add_typer(invoices_app, name="invoices")
_app.add_typer(piee_app, name="piee")
_app.add_typer(reporting_app, name="reporting")
_app.add_typer(audit_app, name="audit")
_app.command("office-worker", hidden=True)(office_worker)


@reporting_app.command("generate")
def reporting_generate(
    sources: list[Path],
    years: str = typer.Option(..., "--years"),
    out: Path = typer.Option(..., "--out"),  # noqa: B008
) -> None:
    """Build a report from annex files or folders."""
    try:
        first, last = (int(part) for part in years.split("-", maxsplit=1))
        if first > last or last - first > 20:
            raise ValueError
    except ValueError as exc:
        raise typer.BadParameter("Use an ascending year range, e.g. 2023-2025") from exc
    paths = collect_annexes(sources)
    if not paths:
        raise typer.BadParameter("No annex workbooks found")
    generate_from_sources(_workspace(), paths, list(range(first, last + 1)), out)
    typer.echo(str(out))


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
    typer.echo(f"Lucrare: {result.job_id}")
    if result.client_proposal:
        typer.echo(json.dumps(result.client_proposal, ensure_ascii=False))


@invoices_app.command("confirm")
def invoices_confirm(job: str, confirm: bool = typer.Option(False, "--confirm")) -> None:
    ws = _workspace()
    _, proposed = batch_client(ws, job)
    if proposed is None:
        raise EmaError("client_missing", "Clientul lotului nu a fost identificat.", job)
    typer.echo(
        json.dumps(
            {
                "name": proposed.name,
                "tax_id": proposed.tax_id,
                "pods": proposed.pods,
                "pod_fill": proposed.pod_fill,
                "disagreements": proposed.disagreements,
                "candidates": proposed.candidates,
                "memory": proposed.memory,
            },
            ensure_ascii=False,
        )
    )
    if not confirm:
        raise EmaError("confirmation_required", "Confirmaţi clientul cu --confirm.", job)
    decision = confirm_client(ws, job)
    checks = invoice_readiness(ws, job)
    typer.echo(f"Confirmare: {decision.id}; exportabile: {checks.exportable}")


@invoices_app.command("export")
def invoices_export(job: str) -> None:
    ws = _workspace()
    with ws.connect() as db:
        dest = ws.job_path(db, job) / "outputs" / "Facturi.xlsx"
    checks = invoice_readiness(ws, job)
    if checks.omitted:
        typer.echo(f"Omise din Excel ({len(checks.omitted)}): {', '.join(checks.omitted)}")
    typer.echo(str(export_invoices(ws, job, dest)))


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
        raise EmaError("intake_failed", "Prelucrarea fişierului a eşuat.", str(recorded["error"]))
    if recorded["state"] == "cancelled":
        raise EmaError("intake_cancelled", "Prelucrarea fişierului a fost anulată.", collection)
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
def serve(
    port: int = typer.Option(8766, min=0, max=65535),
    dev_origin: str | None = typer.Option(None, "--dev-origin"),
    mock: bool = typer.Option(False, "--mock"),
) -> None:
    if port == 0:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
    with TemporaryDirectory(prefix="ema-mock-") if mock else nullcontext() as temp:
        ws = Workspace(Path(temp)) if temp is not None else _workspace()
        if mock:
            seed_mock(ws)
        code = secrets.token_urlsafe(32)
        origin = dev_origin or f"http://127.0.0.1:{port}"
        typer.echo(f"Open {origin}/app/#code={code}")
        uvicorn.Server(
            uvicorn_config(
                create_app(ws, port, launch_code=code, dev_origin=dev_origin, mock=mock), port
            )
        ).run()


@_app.command("desktop")
def desktop() -> None:
    raise typer.Exit(run_desktop())


@_app.command("check-install")
def check_install() -> None:
    result = run_install_check()
    typer.echo(json.dumps(result, ensure_ascii=False))
    required_ok = all(check["ok"] or not check["required"] for check in result["checks"])
    raise typer.Exit(0 if required_ok else 1)


@_app.command("mcp")
def mcp(
    import_root: list[Path] = typer.Option([], "--import-root"),  # noqa: B008
) -> None:
    """Serve the agent tools over stdio (MCP)."""
    serve_mcp(import_root)


def app() -> None:
    install_keyring()
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                reconfigure(encoding="utf-8")
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
