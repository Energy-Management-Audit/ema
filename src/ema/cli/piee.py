"""PIEE draft command backed by the workflow use case."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ema.core.config import workspace_path
from ema.core.workspace import Workspace
from ema.piee.workflow import GenerateRequest
from ema.workflows_registry import generate_draft

piee_app = typer.Typer()


@piee_app.command("generate")
def generate(
    client: str = typer.Option(..., "--client"),
    year: int = typer.Option(..., "--year"),
    anexa: Path = typer.Option(..., "--anexa"),  # noqa: B008
    necesar: Path | None = typer.Option(None, "--necesar"),  # noqa: B008
    prelucrare: Path | None = typer.Option(None, "--prelucrare"),  # noqa: B008
    previous_piee: Path | None = typer.Option(None, "--previous-piee"),  # noqa: B008
) -> None:
    """Create a reviewed job and a draft; final export remains a separate decision."""
    result = generate_draft(
        Workspace(workspace_path()),
        GenerateRequest(client, year, anexa, necesar, prelucrare, previous_piee),
    )
    typer.echo(
        json.dumps(
            {
                "job": result.job,
                "run": result.run,
                "draft": str(result.draft),
                "workbook": str(result.workbook),
            }
        )
    )
