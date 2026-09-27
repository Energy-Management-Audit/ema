"""Workspace files, slots, and path authority."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import IO, Literal

from ema.core.errors import EmaError
from ema.core.logging import log_exception
from ema.core.workspace.backup_install import install_backup
from ema.core.workspace.cleanup import delete_job_rows
from ema.core.workspace.lock import workspace_lock
from ema.core.workspace.mutations import delete_job as delete_job_impl
from ema.core.workspace.references import evidence_uses_file, referenced_files
from ema.core.workspace.schema import migrate
from ema.core.workspace.settings import write_settings


def _file_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class SlotVersion:
    job_id: str
    slot: str
    version: int
    file_sha: str
    origin: str
    converted_from: str | None


class WorkspaceConnection(sqlite3.Connection):
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Workspace:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "logs").mkdir(exist_ok=True)
        with self.connect() as db:
            migrate(db)
        self.finish_deletes()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.root / "ema.sqlite", timeout=30, factory=WorkspaceConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise EmaError("invalid_path", "Calea fişierului este invalidă.", relative)
        return path

    def job_path(self, db: sqlite3.Connection, job: str) -> Path:
        row = db.execute(
            "SELECT relative_path FROM jobs WHERE id=? AND deleted=0", (job,)
        ).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        return self.path(str(row["relative_path"]))

    def make_job_folders(self, relative: str) -> None:
        root = self.path(relative)
        for part in ("work", "cache", "outputs", "edits"):
            (root / part).mkdir(parents=True, exist_ok=True)
        (root / "log.jsonl").touch(exist_ok=True)

    def job_log(self, db: sqlite3.Connection, job: str) -> IO[str]:
        return (self.job_path(db, job) / "log.jsonl").open("a", encoding="utf-8")

    def settings_file(self) -> Path:
        return self.root / "settings.toml"

    def settings_text(self) -> str | None:
        path = self.settings_file()
        return path.read_text(encoding="utf-8") if path.exists() else None

    def app_log(self) -> IO[str]:
        return (self.root / "logs" / "ema.jsonl").open("a", encoding="utf-8")

    def artifact_dir(self, db: sqlite3.Connection, job: str, stage: str, run: str) -> Path:
        if not stage or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for c in stage
        ):
            raise EmaError("invalid_stage", "Etapa este invalidă.", stage)
        path = self.job_path(db, job) / "work" / stage / run
        path.mkdir(parents=True, exist_ok=True)
        return path

    def add_file(self, client_slug: str, source: Path) -> str:
        if not client_slug or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for c in client_slug
        ):
            raise EmaError(
                "invalid_client", "Identificatorul clientului este invalid.", client_slug
            )
        directory = self.path(f"clients/{client_slug}/files")
        directory.mkdir(parents=True, exist_ok=True)
        temp = directory / f".{uuid.uuid4().hex}.tmp"
        try:
            shutil.copyfile(source, temp)
            sha = _file_sha(temp)
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT relative_path FROM files WHERE sha=? AND client_slug=?",
                    (sha, client_slug),
                ).fetchone()
                if row is not None:
                    existing = self.path(str(row["relative_path"]))
                    if not existing.is_file():
                        os.replace(temp, existing)
                    db.execute(
                        "UPDATE files SET added_at=? WHERE sha=? AND client_slug=?",
                        (time.time(), sha, client_slug),
                    )
                    return sha
                ext = source.suffix.lower()
                if not ext or not ext[1:].isalnum() or len(ext) > 16:
                    ext = ".bin"
                relative = f"clients/{client_slug}/files/{sha}{ext}"
                target = self.path(relative)
                os.replace(temp, target)
                db.execute(
                    "INSERT INTO files VALUES (?, ?, ?, ?, ?)",
                    (sha, client_slug, relative, target.stat().st_size, time.time()),
                )
        finally:
            temp.unlink(missing_ok=True)
        return sha

    def set_slot(
        self,
        job: str,
        slot: str,
        file_sha: str,
        *,
        origin: str = "upload",
        converted_from: str | None = None,
    ) -> SlotVersion:
        parts = slot.split("/")
        if (
            not 1 <= len(parts) <= 16
            or (len(parts) > 2 and parts[0] not in {"dossier", "visit"})
            or (parts[0] == "visit" and len(parts) > 4)
            or (parts[0] == "visit" and any(len(part) > 255 for part in parts[1:]))
            or any(part in ("", ".", "..") for part in parts)
            or any("\\" in part or any(ord(char) < 32 for char in part) for part in parts)
        ):
            raise EmaError("invalid_slot", "Numele fişierului este invalid.", "")
        with self.connect() as db:
            job_row = db.execute(
                "SELECT client_slug FROM jobs WHERE id=? AND deleted=0", (job,)
            ).fetchone()
            if job_row is None:
                raise EmaError("job_missing", "Lucrarea nu există.", job)
            if (
                db.execute(
                    "SELECT 1 FROM files WHERE sha=? AND client_slug=?",
                    (file_sha, job_row["client_slug"]),
                ).fetchone()
                is None
            ):
                raise EmaError("file_missing", "Fişierul nu există.", file_sha)
            db.execute("INSERT OR IGNORE INTO slots (job_id,name) VALUES (?,?)", (job, slot))
            row = db.execute(
                "SELECT next_version FROM slots WHERE job_id=? AND name=?", (job, slot)
            ).fetchone()
            version = int(row["next_version"])
            db.execute(
                "INSERT INTO slot_versions VALUES (?,?,?,?,?,?)",
                (job, slot, version, file_sha, origin, converted_from),
            )
            db.execute(
                "UPDATE slots SET active_version=?,next_version=next_version+1, "
                "revision=revision+1 WHERE job_id=? AND name=?",
                (version, job, slot),
            )
        return SlotVersion(job, slot, version, file_sha, origin, converted_from)

    def list_versions(self, job: str, slot: str) -> list[SlotVersion]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM slot_versions WHERE job_id=? AND slot=? ORDER BY version",
                (job, slot),
            ).fetchall()
        return [
            SlotVersion(
                str(r["job_id"]),
                str(r["slot"]),
                int(r["version"]),
                str(r["file_sha"]),
                str(r["origin"]),
                r["converted_from"],
            )
            for r in rows
        ]

    def list_slots(self, job: str, prefix: str) -> list[str]:
        """List active collection items in stable allocation order."""
        collection = f"{prefix}/" if prefix else ""
        with self.connect() as db:
            rows = db.execute(
                "SELECT name FROM slots WHERE job_id=? AND substr(name,1,?)=? "
                "AND active_version IS NOT NULL ORDER BY name",
                (job, len(collection), collection),
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def file_path(self, client_slug: str, file_sha: str) -> Path:
        with self.connect() as db:
            row = db.execute(
                "SELECT relative_path FROM files WHERE client_slug=? AND sha=?",
                (client_slug, file_sha),
            ).fetchone()
        if row is None:
            raise EmaError("file_missing", "Fişierul nu există.", file_sha)
        return self.path(str(row["relative_path"]))

    def remove_version(
        self, job: str, slot: str, version: int, *, on_revision: int | None = None
    ) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT active_version,revision FROM slots WHERE job_id=? AND name=?", (job, slot)
            ).fetchone()
            if on_revision is not None and (current is None or current["revision"] != on_revision):
                raise EmaError("stale_revision", "Fişierul a fost modificat.", "")
            cursor = db.execute(
                "DELETE FROM slot_versions WHERE job_id=? AND slot=? AND version=?",
                (job, slot, version),
            )
            if cursor.rowcount == 0:
                raise EmaError("version_missing", "Versiunea nu există.", f"{job}/{slot}/{version}")
            row = db.execute(
                "SELECT MAX(version) AS active FROM slot_versions WHERE job_id=? AND slot=?",
                (job, slot),
            ).fetchone()
            if current is not None and current["active_version"] != row["active"]:
                db.execute(
                    "UPDATE slots SET active_version=?,revision=revision+1 "
                    "WHERE job_id=? AND name=?",
                    (row["active"], job, slot),
                )

    def delete_job(self, job: str, *, on_revision: int | None = None) -> None:
        delete_job_impl(self, job, on_revision=on_revision)

    def finish_deletes(self) -> None:
        with workspace_lock(self.root):
            with self.connect() as db:
                rows = db.execute("SELECT id,relative_path FROM jobs WHERE deleted=1").fetchall()
            for row in rows:
                try:
                    shutil.rmtree(self.path(str(row["relative_path"])))
                except FileNotFoundError:
                    pass  # The folder was removed before an interrupted delete.
                except OSError as exc:
                    with self.app_log() as handle:
                        log_exception(handle, exc)
                    continue
                with self.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    delete_job_rows(db, str(row["id"]))

    def gc(self) -> None:
        with workspace_lock(self.root), self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            referenced_outputs = {
                str(row[0]) for row in db.execute("SELECT relative_path FROM outputs")
            }
            running = {
                str(row[0]) for row in db.execute("SELECT id FROM runs WHERE state='running'")
            }
            for row in db.execute("SELECT relative_path FROM jobs"):
                output_dir = self.path(str(row[0])) / "outputs"
                for path in output_dir.glob("*"):
                    if (
                        path.is_file()
                        and path.relative_to(self.root).as_posix() not in referenced_outputs
                        and path.name.split("-", 1)[0] not in running
                        and (
                            not path.name.startswith(".")
                            or path.stat().st_mtime < time.time() - 3600
                        )
                    ):
                        path.unlink()
            rows = db.execute(
                "SELECT sha,client_slug,relative_path FROM files WHERE added_at<?",
                (time.time() - 3600,),
            ).fetchall()
            for row in rows:
                used = db.execute(
                    "SELECT 1 FROM slot_versions sv JOIN jobs j ON j.id=sv.job_id "
                    "WHERE sv.file_sha=? AND j.client_slug=? LIMIT 1",
                    (row["sha"], row["client_slug"]),
                ).fetchone()
                if used is None:
                    used = db.execute(
                        "SELECT 1 FROM run_inputs WHERE file_sha=? AND client_slug=? LIMIT 1",
                        (row["sha"], row["client_slug"]),
                    ).fetchone()
                if used is None and not evidence_uses_file(
                    db, str(row["sha"]), str(row["client_slug"])
                ):
                    self.path(str(row["relative_path"])).unlink(missing_ok=True)
                    db.execute(
                        "DELETE FROM files WHERE sha=? AND client_slug=?",
                        (row["sha"], row["client_slug"]),
                    )

    def referenced_files(self, db: sqlite3.Connection) -> list[tuple[str, str, int]]:
        return referenced_files(db)

    def record_artifacts(self, db: sqlite3.Connection, run: str, directory: Path) -> None:
        for path in directory.rglob("*"):
            if path.is_file():
                relative = path.relative_to(self.root).as_posix()
                db.execute(
                    "INSERT INTO run_files VALUES (?,?,?,?)",
                    (
                        run,
                        relative,
                        _file_sha(path),
                        path.stat().st_size,
                    ),
                )

    def save_output(
        self, db: sqlite3.Connection, job: str, run: str, source: Path, name: str
    ) -> Path:
        if not name or Path(name).name != name or name in {".", ".."}:
            raise EmaError("output_name", "Numele documentului este invalid.", name)
        target = self.job_path(db, job) / "outputs" / f"{run}-{name}"
        if target.exists():
            raise EmaError("output_exists", "Documentul există deja.", str(target))
        temp = target.with_name(f".{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, temp)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return target

    def record_outputs(
        self, db: sqlite3.Connection, job: str, run: str, paths: list[tuple[Path, str]]
    ) -> None:
        for target, kind in paths:
            seq = int(db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM outputs").fetchone()[0])
            db.execute(
                "INSERT INTO outputs (id,job_id,run_id,relative_path,sha,size,kind,seq) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    job,
                    run,
                    target.relative_to(self.root).as_posix(),
                    _file_sha(target),
                    target.stat().st_size,
                    kind,
                    seq,
                ),
            )

    install_backup = staticmethod(install_backup)

    write_settings = write_settings


add_file = Workspace.add_file
set_slot = Workspace.set_slot
list_versions = Workspace.list_versions
remove_version = Workspace.remove_version
