"""Frozen entry: Ema.exe without arguments opens the desktop window (docs/decisions/0001)."""

import sys
from pathlib import Path

from ema.cli import app

if len(sys.argv) == 1 and Path(sys.executable).stem == "Ema":
    sys.argv.append("desktop")
app()
