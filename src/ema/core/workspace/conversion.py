"""Atomic publication of a converted file while its source remains active."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import uuid
from pathlib import Path

from ema.core.workspace import SlotVersion, Workspace


def active_version(ws: Workspace, job: str, slot: str) -> SlotVersion | None:
    with ws.connect() as db:
        row = db.execute(
            "SELECT v.* FROM slots s JOIN slot_versions v ON v.job_id=s.job_id "
            "AND v.slot=s.name AND v.version=s.active_version "
            "WHERE s.job_id=? AND s.name=?",
            (job, slot),
        ).fetchone()
    if row is None:
        return None
    return SlotVersion(
        str(row["job_id"]),
        str(row["slot"]),
        int(row["version"]),
        str(row["file_sha"]),
        str(row["origin"]),
        row["converted_from"],
    )


def publish_conversion(
    ws: Workspace, job: str, slot: str, original: SlotVersion, source: Path
) -> SlotVersion | None:
    """Store a conversion only while its source remains the active slot version."""
    with source.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    created: Path | None = None
    try:
        with ws.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT j.client_slug,s.active_version,s.next_version,v.file_sha "
                "FROM jobs j JOIN slots s ON s.job_id=j.id "
                "LEFT JOIN slot_versions v ON v.job_id=s.job_id AND v.slot=s.name "
                "AND v.version=s.active_version "
                "WHERE j.id=? AND j.deleted=0 AND s.name=?",
                (job, slot),
            ).fetchone()
            if (
                row is None
                or original.job_id != job
                or original.slot != slot
                or row["active_version"] != original.version
                or row["file_sha"] != original.file_sha
            ):
                return None
            client = str(row["client_slug"])
            file_row = db.execute(
                "SELECT relative_path FROM files WHERE sha=? AND client_slug=?",
                (sha, client),
            ).fetchone()
            if file_row is None:
                directory = ws.path(f"clients/{client}/files")
                directory.mkdir(parents=True, exist_ok=True)
                target = directory / f"{sha}.docx"
                temporary = directory / f".{uuid.uuid4().hex}.tmp"
                try:
                    shutil.copyfile(source, temporary)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
                created = target
                db.execute(
                    "INSERT INTO files VALUES (?,?,?,?,?)",
                    (
                        sha,
                        client,
                        str(target.relative_to(ws.root)),
                        target.stat().st_size,
                        time.time(),
                    ),
                )
            version = int(row["next_version"])
            db.execute(
                "INSERT INTO slot_versions VALUES (?,?,?,?,?,?)",
                (job, slot, version, sha, "converted", original.file_sha),
            )
            db.execute(
                "UPDATE slots SET active_version=?,next_version=next_version+1, "
                "revision=revision+1 WHERE job_id=? AND name=? AND active_version=?",
                (version, job, slot, original.version),
            )
        return SlotVersion(job, slot, version, sha, "converted", original.file_sha)
    except Exception:
        if created is not None:
            created.unlink(missing_ok=True)
        raise
