"""PIEE draft command backed by the workflow use case."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ema.core.config import workspace_path
from ema.core.errors import EmaError
from ema.core.jobs import status, subscribe
from ema.core.workspace import Workspace
from ema.piee.workflow import GenerateRequest, start_generate

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
    ws = Workspace(workspace_path())
    job, run = start_generate(
        ws, GenerateRequest(client, year, anexa, necesar, prelucrare, previous_piee)
    )
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    if record["state"] != "ready":
        raise EmaError("piee_generation_failed", "Generarea PIEE a eșuat.", str(record["error"]))
    with ws.connect() as db:
        output = db.execute(
            "SELECT relative_path FROM outputs WHERE job_id=? AND run_id=? AND kind='draft'",
            (job, run),
        ).fetchone()
    if output is None:
        raise EmaError("piee_output_missing", "Ciorna PIEE lipsește.", run)
    typer.echo(json.dumps({"job": job, "draft": str(ws.path(str(output["relative_path"])))}))
