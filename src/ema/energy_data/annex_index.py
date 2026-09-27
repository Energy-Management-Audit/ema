"""Index imported Anexa 2–3 workbooks by their in-document CUI."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException

from ema.clients.files import LIMIT
from ema.core.errors import EmaError
from ema.core.office.errors import OfficeError
from ema.core.office.sniff import FileKind, sniff
from ema.core.workspace import Workspace
from ema.energy_data.anexa import parse_anexa
from ema.energy_data.source import Located


@dataclass(frozen=True)
class ImportedAnnex:
    file_name: str
    client_id: str
    client_name: str | None
    created: bool
    year: int
    sha: str


@dataclass(frozen=True)
class IgnoredFile:
    file_name: str
    code: str
    reason: str


@dataclass(frozen=True)
class AnnexImport:
    imported: tuple[ImportedAnnex, ...]
    ignored: tuple[IgnoredFile, ...]


@dataclass(frozen=True)
class IndexedAnnex:
    client_id: str
    sha: str
    year: int
    data: dict[str, Any]
    read_at: str


_REASONS = {
    "not_spreadsheet": "Nu este un registru Excel.",
    "file_too_large": "Fişierul este prea mare.",
    "unreadable": "Nu poate fi citit ca Anexa 2–3.",
    "cui_missing": "CUI-ul lipseşte din anexă.",
    "year_missing": "Anul anexei lipseşte.",
    "cui_ambiguous": "CUI-uri pentru clienţi diferiţi",
}


def _text(value: Located | None) -> str | None:
    return str(value.value).strip() if value is not None else None


def _ref(value: Located | None) -> str | None:
    return value.ref.a1 if value is not None else None


def _persist_annex(
    ws: Workspace, temporary: Path, name: str, ids: list[str], year: int, data: dict[str, Any]
) -> ImportedAnnex | IgnoredFile:
    kind = sniff(temporary)
    if kind.mismatch or kind.kind not in {FileKind.XLS, FileKind.XLSX}:
        return IgnoredFile(name, "unreadable", "Extensia nu corespunde conţinutului fişierului.")
    with temporary.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    basename = re.sub(r"[^\w.() -]", "_", name).strip(". ")
    pending: Path | None = None
    created_file: Path | None = None
    try:
        with ws.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            clients = db.execute("SELECT id,name,cui FROM clients WHERE cui IS NOT NULL").fetchall()
            matches = [row for row in clients if re.sub(r"\D", "", str(row["cui"])) in ids]
            if len({str(row["id"]) for row in matches}) > 1:
                return IgnoredFile(name, "cui_ambiguous", _REASONS["cui_ambiguous"])
            created = not matches
            client_id = uuid.uuid4().hex if created else str(matches[0]["id"])
            client_name = data["name"] if created else matches[0]["name"]
            if created:
                db.execute(
                    "INSERT INTO clients(id,name,cui) VALUES (?,?,?)",
                    (client_id, client_name, ids[0]),
                )
            file_row = db.execute(
                "SELECT relative_path FROM files WHERE sha=? AND client_slug=?",
                (sha, client_id),
            ).fetchone()
            relative = (
                str(file_row["relative_path"])
                if file_row is not None
                else f"clients/{client_id}/files/{sha}{temporary.suffix.lower()}"
            )
            target = ws.path(relative)
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                pending = target.with_name(f".{uuid.uuid4().hex}.tmp")
                shutil.copyfile(temporary, pending)
                os.replace(pending, target)
                pending = None
                created_file = target
            if file_row is None:
                db.execute(
                    "INSERT INTO files(sha,client_slug,relative_path,size,added_at) "
                    "VALUES (?,?,?,?,?)",
                    (sha, client_id, relative, temporary.stat().st_size, time.time()),
                )
            else:
                db.execute(
                    "UPDATE files SET added_at=? WHERE sha=? AND client_slug=?",
                    (time.time(), sha, client_id),
                )
            db.execute(
                "INSERT OR IGNORE INTO client_uploads"
                "(client_id,sha,original_name,kind,size_bytes,created_at) VALUES (?,?,?,?,?,?)",
                (
                    client_id,
                    sha,
                    basename,
                    kind.kind.value,
                    temporary.stat().st_size,
                    datetime.now(UTC).isoformat(),
                ),
            )
            db.execute(
                "INSERT INTO client_annexes(client_id,sha,year,data,read_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(client_id,sha) DO UPDATE SET year=excluded.year,"
                "data=excluded.data,read_at=excluded.read_at",
                (
                    client_id,
                    sha,
                    year,
                    json.dumps(data, ensure_ascii=False),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return ImportedAnnex(name, client_id, client_name, created, year, sha)
    except BaseException:
        if created_file is not None:
            created_file.unlink(missing_ok=True)
        raise
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def _import_one(ws: Workspace, name: str, stream: BinaryIO) -> ImportedAnnex | IgnoredFile:  # noqa: PLR0911
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    extension = Path(name).suffix.lower()
    if extension not in {".xls", ".xlsx"}:
        return IgnoredFile(name, "not_spreadsheet", _REASONS["not_spreadsheet"])
    temp_dir = ws.path("temp")
    temp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=extension, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        try:
            with temporary.open("wb") as handle:
                size = 0
                while chunk := stream.read(65536):
                    size += len(chunk)
                    if size > LIMIT:
                        return IgnoredFile(name, "file_too_large", _REASONS["file_too_large"])
                    handle.write(chunk)
        except OSError:
            return IgnoredFile(name, "unreadable", _REASONS["unreadable"])
        try:
            annex = parse_anexa(temporary)
        except InvalidFileException:
            return IgnoredFile(
                name, "unreadable", "Extensia nu corespunde conţinutului fişierului."
            )
        except (OSError, ValueError, RuntimeError, OfficeError, BadZipFile):
            return IgnoredFile(name, "unreadable", _REASONS["unreadable"])
        raw_cui = _text(annex.identity.get("cui")) or ""
        ids = re.findall(r"(?<!\d)\d{2,10}(?!\d)", raw_cui)
        if not ids:
            return IgnoredFile(name, "cui_missing", _REASONS["cui_missing"])
        year = annex.year.value if annex.year is not None else None
        if not isinstance(year, int) or isinstance(year, bool):
            return IgnoredFile(name, "year_missing", _REASONS["year_missing"])
        total = annex.monthly_total_tep or annex.annual.get("total_tep")
        data = {
            key: _text(annex.identity.get(key))
            for key in (
                "name",
                "cui",
                "registrul_comertului",
                "address",
                "caen_code",
                "caen_description",
                "contact_person",
            )
        }
        data["total_tep"] = _text(total)
        data["total_tep_ref"] = _ref(total)
        data["file_name"] = name
        return _persist_annex(ws, temporary, name, ids, year, data)
    finally:
        temporary.unlink(missing_ok=True)


def import_annexes(ws: Workspace, files: list[tuple[str, BinaryIO]]) -> AnnexImport:
    imported: list[ImportedAnnex] = []
    ignored: list[IgnoredFile] = []
    for name, stream in files:
        try:
            result = _import_one(ws, name, stream)
        except EmaError as exc:
            code = "file_too_large" if exc.code == "file_too_large" else "unreadable"
            result = IgnoredFile(name, code, f"{_REASONS[code]} ({exc.code})")
        except Exception as exc:
            result = IgnoredFile(
                name, "unreadable", f"{_REASONS['unreadable']} ({type(exc).__name__})"
            )
        if isinstance(result, ImportedAnnex):
            imported.append(result)
        else:
            ignored.append(result)
    return AnnexImport(tuple(imported), tuple(ignored))


def indexed(ws: Workspace) -> dict[str, list[IndexedAnnex]]:
    with ws.connect() as db:
        rows = db.execute(
            "SELECT client_id,sha,year,data,read_at FROM client_annexes "
            "ORDER BY year DESC,read_at DESC,sha DESC"
        ).fetchall()
    result: dict[str, list[IndexedAnnex]] = {}
    for row in rows:
        result.setdefault(str(row["client_id"]), []).append(
            IndexedAnnex(
                str(row["client_id"]),
                str(row["sha"]),
                int(row["year"]),
                json.loads(str(row["data"])),
                str(row["read_at"]),
            )
        )
    return result
