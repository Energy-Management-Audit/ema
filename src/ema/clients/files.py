"""Bounded client upload intake and immutable file metadata."""

from __future__ import annotations

import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from ema.clients.registry import get_client, validate_id
from ema.core.errors import EmaError
from ema.core.office.sniff import FileKind, sniff
from ema.core.workspace import Workspace

LIMIT = 104857600
_EXTENSIONS = {
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".pdf",
    ".html",
    ".htm",
    ".jpeg",
    ".jpg",
    ".png",
    ".gif",
    ".tif",
    ".tiff",
    ".bmp",
    ".zip",
    ".txt",
}


def store_upload(
    ws: Workspace, client_id: str, stream: BinaryIO, name: str, limit: int = LIMIT
) -> dict[str, Any]:
    validate_id(client_id)
    get_client(ws, client_id)
    basename = name.replace("\\", "/").rsplit("/", 1)[-1]
    basename = re.sub(r"[^\w.() -]", "_", basename).strip(". ")
    extension = Path(basename).suffix.lower()
    if not basename or extension not in _EXTENSIONS:
        raise EmaError("file_type", "Tipul fişierului nu este acceptat.", "")
    temporary_dir = ws.path("temp")
    temporary_dir.mkdir(exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=temporary_dir, suffix=extension, delete=False
        ) as handle:
            temporary = Path(handle.name)
            size = 0
            while chunk := stream.read(65536):
                size += len(chunk)
                if size > limit:
                    raise EmaError("file_too_large", "Fişierul este prea mare.", "")
                handle.write(chunk)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    assert temporary is not None
    try:
        identified = sniff(temporary)
        if size == 0 or identified.kind == FileKind.UNKNOWN or identified.mismatch:
            raise EmaError("file_type", "Tipul fişierului nu este acceptat.", "")
        sha = ws.add_file(client_id, temporary)
        with ws.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO client_uploads"
                "(client_id,sha,original_name,kind,size_bytes,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    client_id,
                    sha,
                    basename,
                    identified.kind.value,
                    size,
                    datetime.now(UTC).isoformat(),
                ),
            )
            row = db.execute(
                "SELECT original_name,size_bytes,kind FROM client_uploads "
                "WHERE client_id=? AND sha=?",
                (client_id, sha),
            ).fetchone()
        assert row is not None
        return {
            "sha": sha,
            "name": str(row["original_name"]),
            "size_bytes": int(row["size_bytes"]),
            "kind": str(row["kind"]),
            "intake": "stored",
        }
    finally:
        temporary.unlink(missing_ok=True)


def file_versions(ws: Workspace, client_id: str, sha: str) -> list[dict[str, Any]]:
    validate_id(client_id)
    get_client(ws, client_id)
    with ws.connect() as db:
        row = db.execute(
            "SELECT original_name,size_bytes FROM client_uploads WHERE client_id=? AND sha=?",
            (client_id, sha),
        ).fetchone()
    if row is None:
        raise EmaError("file_missing", "Fişierul nu există.", "")
    return [
        {"version": 1, "sha": sha, "name": row["original_name"], "size_bytes": row["size_bytes"]}
    ]
