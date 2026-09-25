"""Guarded public web access and immutable job-local source snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import unquote

from ema.core.errors import EmaError
from ema.core.logging import write_event
from ema.core.review.fields import fields
from ema.core.web import fetch_bytes
from ema.core.web import request as _request
from ema.core.workspace import Workspace

MAX_QUERY = 180
MAX_URL = 2048
MAX_BODY = 2_000_000
_ALLOWED_TYPES = ("text/html", "text/plain", "application/json", "image/png", "image/jpeg")
_CONTACT = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:\+?\d[\d .()-]{8,}\d)")
_ACCOUNT = re.compile(
    r"\bRO\d{2}[A-Z0-9]{8,30}\b|\b(?:contract|iban|cont)\s*"
    r"(?:nr\.?\s*:?|:)\s*([A-Z0-9/-]{5,40})",
    re.I,
)


def _compact(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


@dataclass(frozen=True)
class Snapshot:
    url: str
    sha: str
    retrieved_at: datetime
    content_type: str
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def store_snapshot(ws: Workspace, job: str, snapshot: Snapshot) -> Snapshot:
    if hashlib.sha256(snapshot.body).hexdigest() != snapshot.sha:
        raise EmaError("snapshot_changed", "Sursa online s-a modificat.", "")
    with ws.connect() as db:
        root = ws.job_path(db, job) / "cache" / "online"
        row = db.execute("SELECT client_slug FROM jobs WHERE id=?", (job,)).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        client_slug = str(row["client_slug"])
    root.mkdir(parents=True, exist_ok=True)
    target, metadata = root / snapshot.sha, root / f"{snapshot.sha}.json"
    if metadata.exists():
        previous = load_snapshot(ws, job, snapshot.sha)
        if previous.url != snapshot.url:
            raise EmaError("snapshot_source", "Aceeași sursă are altă adresă.", snapshot.url)
        return previous
    target.write_bytes(snapshot.body)
    ws.add_file(client_slug, target)
    metadata.write_text(
        json.dumps(
            {
                "url": snapshot.url,
                "retrieved_at": snapshot.retrieved_at.isoformat(),
                "content_type": snapshot.content_type,
            }
        ),
        encoding="utf-8",
    )
    return snapshot


def load_snapshot(ws: Workspace, job: str, sha: str) -> Snapshot:
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise EmaError("snapshot_missing", "Sursa online lipsește.", "")
    with ws.connect() as db:
        root = ws.job_path(db, job) / "cache" / "online"
    body_file, metadata_file = root / sha, root / f"{sha}.json"
    if not body_file.is_file() or not metadata_file.is_file():
        raise EmaError("snapshot_missing", "Sursa online lipsește.", "")
    body = body_file.read_bytes()
    if hashlib.sha256(body).hexdigest() != sha:
        raise EmaError("snapshot_changed", "Sursa online s-a modificat.", "")
    meta = json.loads(metadata_file.read_text(encoding="utf-8"))
    return Snapshot(
        meta["url"], sha, datetime.fromisoformat(meta["retrieved_at"]), meta["content_type"], body
    )


class OutboundGuard:
    def __init__(self, ws: Workspace, job: str, document_texts: tuple[str, ...] = ()) -> None:
        self.ws, self.job = ws, job
        values: set[str] = set()
        for field in fields(ws, job):
            if field.value is None:
                continue
            key = field.key.casefold()
            if any(part in key for part in ("cui", "company_name", "address", "website", "caen")):
                continue
            if isinstance(field.value, str | int | float | Decimal):
                values.add(str(field.value).strip())
        for document in document_texts:
            values.update(match.group().strip() for match in _CONTACT.finditer(document))
            values.update(match.group(1) or match.group(0) for match in _ACCOUNT.finditer(document))
        self.private = tuple(value.casefold() for value in values if len(value) >= 4)
        self.private_compact = tuple(
            compact for value in values if len(compact := _compact(value)) >= 4
        )
        self.private_digits = tuple(
            digits
            for value in values
            if (digits := re.sub(r"\D", "", value))
            and _compact(value) == digits
            and len(digits) >= 4
        )

    def check(self, kind: str, value: str) -> None:
        reason = "allowed"
        if kind == "query" and (not value.strip() or len(value) > MAX_QUERY):
            reason = "query_length"
        elif kind == "url" and len(value) > MAX_URL:
            reason = "url_length"
        decoded = value
        for _ in range(3):
            later = unquote(decoded)
            if later == decoded:
                break
            decoded = later
        digits = re.sub(r"\D", "", decoded)
        compact = _compact(decoded)
        if (
            any(secret in decoded.casefold() for secret in self.private)
            or any(secret in digits for secret in self.private_digits)
            or any(secret in compact for secret in self.private_compact)
        ):
            reason = "private_value"
        with self.ws.connect() as db, self.ws.job_log(db, self.job) as handle:
            write_event(
                handle,
                "research_outbound",
                kind=kind,
                value=value if reason == "allowed" else "[redacted]",
                digest=hashlib.sha256(value.encode()).hexdigest(),
                verdict=reason,
            )
        if reason != "allowed":
            raise EmaError("outbound_refused", "Cererea online a fost refuzată.", reason)


def fetch(
    ws: Workspace,
    job: str,
    guard: OutboundGuard,
    url: str,
    *,
    method: str = "GET",
    payload: bytes | None = None,
) -> Snapshot:
    current, content_type, body = fetch_bytes(
        url,
        method=method,
        payload=payload,
        check_url=lambda value: guard.check("url", value),
        request=_request,
    )
    sha = hashlib.sha256(body).hexdigest()
    retrieved = datetime.now(UTC)
    return store_snapshot(ws, job, Snapshot(current, sha, retrieved, content_type, body))
