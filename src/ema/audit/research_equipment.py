"""Sourced equipment research cached per client and model."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ema.audit.research_web import OutboundGuard, Snapshot, fetch, load_snapshot, store_snapshot
from ema.core.errors import EmaError
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, FieldSpec, Url
from ema.core.workspace import Workspace


@dataclass(frozen=True)
class EquipmentEntry:
    model: str
    purpose: str
    energy_features: str
    source_url: str
    snapshot_sha: str
    quote: str
    trust_reason: str
    retrieved_at: str
    image_status: str
    image_url: str | None
    image_attribution: str | None
    source_job: str = ""


def _cache_path(ws: Workspace, job: str, model: str) -> tuple[str, Path]:
    slug = hashlib.sha256(model.casefold().encode()).hexdigest()[:20]
    with ws.connect() as db:
        row = db.execute("SELECT client_slug FROM jobs WHERE id=?", (job,)).fetchone()
    if row is None:
        raise EmaError("job_missing", "Lucrarea nu există.", job)
    return slug, ws.path(f"clients/{row['client_slug']}/research/equipment-{slug}.json")


_SPACE, _THOUSANDS = "[ \u00a0\u202f]", r"\d{3}(?!\d)"  # 1 234,5 groups its thousands


def _extends(before: str, value: str, after: str) -> bool:
    """Whether the text around the value makes it part of a longer word or number: 115 kW
    holds "15 kW", 15 kWh holds "15 kW", 1.234,5 and 1 234,5 hold "234,5"."""
    first, last = value[0], value[-1]
    return bool(
        (first.isalnum() and before[-1:].isalnum())
        or (last.isalnum() and after[:1].isalnum())
        or (first.isdigit() and re.search(r"\d[.,]$", before))
        or (first.isdigit() and re.search(rf"\d{_SPACE}$", before) and re.match(_THOUSANDS, value))
        or (last.isdigit() and re.match(r"[.,]\d", after))
        or (last.isdigit() and re.match(_SPACE + _THOUSANDS, after))
    )


def in_quote(value: str, quote: str) -> bool:
    """Whether the value appears in the quote as whole words and numbers, never inside one."""
    start = quote.find(value) if value else -1
    while start >= 0:
        if not _extends(quote[:start], value, quote[start + len(value) :]):
            return True
        start = quote.find(value, start + 1)
    return False


def _propose_entry(ws: Workspace, job: str, slug: str, entry: EquipmentEntry) -> None:
    evidence = Evidence(
        id=hashlib.sha256(f"{job}:{entry.snapshot_sha}:{entry.quote}".encode()).hexdigest(),
        provenance="online",
        file_sha=entry.snapshot_sha,
        locator=Url(url=entry.source_url, snapshot_sha=entry.snapshot_sha),
        method="online",
        retrieved_at=datetime.fromisoformat(entry.retrieved_at),
        quote=entry.quote,
        trust_reason=entry.trust_reason,
        highlight="exact",
    )
    propose(
        ws,
        job,
        FieldSpec(
            key=f"audit.equipment.{slug}",
            label=entry.model,
            value_type="text",
            chapter="ch3.equipment",
        ),
        f"{entry.model}: {entry.purpose}; {entry.energy_features}",
        [evidence],
        state="enriched",
    )


def cached_equipment(ws: Workspace, job: str, model: str) -> EquipmentEntry | None:
    model = model.strip()
    if not model or len(model) > 120:
        raise EmaError("equipment_invalid", "Modelul echipamentului este invalid.", "")
    slug, target = _cache_path(ws, job, model)
    if not target.exists():
        return None
    entry = EquipmentEntry(**json.loads(target.read_text(encoding="utf-8")))
    if entry.source_job and entry.source_job != job:
        with ws.connect() as db:
            source = db.execute(
                "SELECT client_slug FROM jobs WHERE id=?", (entry.source_job,)
            ).fetchone()
            current = db.execute("SELECT client_slug FROM jobs WHERE id=?", (job,)).fetchone()
        if source is None or current is None or source["client_slug"] != current["client_slug"]:
            raise EmaError("snapshot_missing", "Sursa online lipseşte.", "")
        snapshot = load_snapshot(ws, entry.source_job, entry.snapshot_sha)
        if snapshot.url != entry.source_url or entry.quote not in snapshot.text:
            raise EmaError("snapshot_changed", "Sursa online s-a modificat.", "")
        store_snapshot(ws, job, snapshot)
    else:
        load_snapshot(ws, job, entry.snapshot_sha)
    _propose_entry(ws, job, slug, entry)
    return entry


def record_equipment(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    guard: OutboundGuard,
    snapshot: Snapshot,
    *,
    model: str,
    purpose: str,
    energy_features: str,
    quote: str,
    trust_reason: str,
    image_url: str = "",
    image_attribution: str = "",
) -> EquipmentEntry:
    model = model.strip()
    if not purpose or not energy_features:
        raise EmaError("equipment_invalid", "Datele echipamentului sunt incomplete.", "")
    existing = cached_equipment(ws, job, model)
    if existing is not None:
        return existing
    if (
        not quote
        or quote not in snapshot.text
        or not all(in_quote(value, quote) for value in (model, purpose, energy_features))
    ):
        raise EmaError("evidence_quote", "Fragmentul nu susţine descrierea echipamentului.", model)
    if not trust_reason.strip() or "\n" in trust_reason or len(trust_reason) > 240:
        raise EmaError("trust_reason", "Motivul sursei este invalid.", model)
    image_status = "later: visit photo"
    actual_image_url: str | None = None
    if image_url and image_attribution:
        image = fetch(ws, job, guard, image_url)
        if image.content_type not in {"image/png", "image/jpeg"}:
            raise EmaError("image_type", "Imaginea echipamentului este invalidă.", image_url)
        image_status, actual_image_url = "sourced", image.url
    snapshot = store_snapshot(ws, job, snapshot)
    entry = EquipmentEntry(
        model,
        purpose,
        energy_features,
        snapshot.url,
        snapshot.sha,
        quote,
        trust_reason.strip(),
        snapshot.retrieved_at.isoformat(),
        image_status,
        actual_image_url,
        image_attribution or None,
        job,
    )
    slug, target = _cache_path(ws, job, model)
    _propose_entry(ws, job, slug, entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entry.__dict__, ensure_ascii=False), encoding="utf-8")
    return entry
