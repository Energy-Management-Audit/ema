"""Audit section drafting over recorded AI responses."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer

from ema.audit.draft_stage import draft_section
from ema.core.config import workspace_path
from ema.core.jobs import recover
from ema.core.workspace import Workspace

audit_app = typer.Typer()


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
