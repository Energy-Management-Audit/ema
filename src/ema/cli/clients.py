"""Client registry commands."""

import json

import typer

from ema.clients.registry import create_client, list_clients
from ema.core.config import workspace_path
from ema.core.workspace import Workspace

clients_app = typer.Typer()


@clients_app.command("add")
def add(
    name: str = typer.Option(..., "--name"), cui: str | None = typer.Option(None, "--cui")
) -> None:
    """Register a client in the workspace."""
    typer.echo(
        json.dumps(create_client(Workspace(workspace_path()), name, cui), ensure_ascii=False)
    )


@clients_app.command("list")
def list_command() -> None:
    """List registered clients."""
    typer.echo(json.dumps(list_clients(Workspace(workspace_path())), ensure_ascii=False))
