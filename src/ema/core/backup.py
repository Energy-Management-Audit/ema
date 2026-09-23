"""Consistent workspace snapshots and verified restoration."""

import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from ema.core.errors import EmaError
from ema.core.workspace import Workspace
from ema.core.workspace.lock import workspace_lock


def _checksum(stream: IO[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while block := stream.read(1024 * 1024):
        digest.update(block)
        size += len(block)
    return digest.hexdigest(), size


def backup(workspace: Workspace, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    target = dest_dir / f"ema-backup-{stamp}.zip"
    partial = dest_dir / f".ema-backup-{stamp}.zip.partial"
    try:
        with workspace_lock(workspace.root), tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "ema.sqlite"
            with workspace.connect() as source, sqlite3.connect(snapshot) as dest:
                source.backup(dest)
            with sqlite3.connect(snapshot) as db:
                refs = workspace.referenced_files(db)
            manifest: list[dict[str, object]] = []
            settings = [("settings.toml", "", -1)] if workspace.settings_file().exists() else []
            with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for relative, expected_sha, expected_size in [
                    ("ema.sqlite", "", -1),
                    *settings,
                    *refs,
                ]:
                    path = snapshot if relative == "ema.sqlite" else workspace.path(relative)
                    with path.open("rb") as stream:
                        sha, size = _checksum(stream)
                    if expected_sha and (sha != expected_sha or size != expected_size):
                        raise EmaError(
                            "backup_changed", "Fișierul s-a modificat în timpul copiei.", relative
                        )
                    archive.write(path, relative)
                    manifest.append({"path": relative, "sha256": sha, "size": size})
                archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
            with zipfile.ZipFile(partial) as archive:
                _verify_archive(archive, partial)
            os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def restore(archive_path: Path, new_workspace: Path) -> Path:
    if new_workspace.exists():
        raise EmaError("restore_exists", "Destinația există deja.", str(new_workspace))
    with zipfile.ZipFile(archive_path) as archive:
        expected = _verify_archive(archive, archive_path)
        Workspace.install_backup(archive, expected, new_workspace)
    Workspace(new_workspace)
    return new_workspace


def _verify_archive(archive: zipfile.ZipFile, path: Path) -> set[str]:
    try:
        manifest = json.loads(archive.read("manifest.json"))
    except (KeyError, ValueError) as exc:
        raise EmaError("backup_manifest", "Copia nu are un manifest valid.", str(exc)) from exc
    names = set(archive.namelist())
    expected = {str(entry["path"]) for entry in manifest}
    if names != expected | {"manifest.json"} or "ema.sqlite" not in expected:
        raise EmaError("backup_manifest", "Lista fișierelor din copie este invalidă.", str(path))
    for entry in manifest:
        relative = str(entry["path"])
        entry_path = Path(relative)
        if entry_path.is_absolute() or ".." in entry_path.parts or relative.startswith("."):
            raise EmaError("backup_path", "Copia conține o cale invalidă.", relative)
        with archive.open(relative) as stream:
            sha, size = _checksum(stream)
        if sha != entry["sha256"] or size != entry["size"]:
            raise EmaError("backup_checksum", "Suma de control nu corespunde.", relative)
    return expected
