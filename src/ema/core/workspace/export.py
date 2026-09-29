"""Copy a checked, immutable output to a user-selected path."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from ema.core.errors import EmaError
from ema.core.workspace import Workspace


def copy_output(ws: Workspace, relative: str, sha: str, dest: Path) -> Path:
    source = ws.path(relative)
    if hashlib.sha256(source.read_bytes()).hexdigest() != sha:
        raise EmaError("output_changed", "Documentul sursă a fost modificat.", relative)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as temp:
        temporary = Path(temp.name)
    try:
        shutil.copyfile(source, temporary)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != sha:
            raise EmaError("output_changed", "Documentul sursă a fost modificat.", relative)
        os.replace(temporary, dest)
    finally:
        temporary.unlink(missing_ok=True)
    return dest
