"""Hidden entry point for one Windows Word operation."""

import sys
from pathlib import Path

import typer

if sys.platform == "win32":
    from ema.windows.word_com import run


def office_worker(request: Path) -> None:
    if sys.platform == "win32":
        raise typer.Exit(run(request))
    raise typer.Exit(3)
