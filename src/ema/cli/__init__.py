"""Command line interface."""

import json
import socket
from pathlib import Path

import typer
import uvicorn

from ema import __version__
from ema.api import create_app
from ema.core.backup import backup, restore
from ema.core.config import workspace_path
from ema.core.errors import EmaError
from ema.core.jobs import list_jobs, recover, status
from ema.core.logging import write_event
from ema.core.workspace import Workspace

_app = typer.Typer(no_args_is_help=True, invoke_without_command=True)
workspace_app = typer.Typer()
job_app = typer.Typer()
_app.add_typer(workspace_app, name="workspace")
_app.add_typer(job_app, name="job")


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
