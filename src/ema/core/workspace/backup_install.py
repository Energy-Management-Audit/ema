"""Install a verified backup into a new workspace directory."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from ema.core.workspace.lock import workspace_lock


def install_backup(archive: zipfile.ZipFile, names: set[str], target: Path) -> None:
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        staging = Path(temp) / "workspace"
        staging.mkdir()
        with workspace_lock(staging):
            for relative in names:
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(relative) as source, path.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
        staging.rename(target)
