"""Regression target: reused equipment evidence remains inspectable in the new job."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from tests.workspace_jobs import create_job

from ema.audit.research_equipment import cached_equipment, record_equipment
from ema.audit.research_web import OutboundGuard, Snapshot, load_snapshot
from ema.core.workspace import Workspace


def test_reused_equipment_snapshot_is_available_in_next_job(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    first_job = create_job(ws, "audit", "synthetic", 2026)
    body = b"Example Motor X pumps water with variable speed."
    sha = hashlib.sha256(body).hexdigest()
    with ws.connect() as db:
        root = ws.job_path(db, first_job) / "cache" / "online"
    root.mkdir(parents=True)
    (root / sha).write_bytes(body)
    (root / f"{sha}.json").write_text(
        '{"url":"https://example.org/motor","retrieved_at":"2026-01-01T00:00:00+00:00",'
        '"content_type":"text/plain"}',
        encoding="utf-8",
    )
    snapshot = Snapshot("https://example.org/motor", sha, datetime.now(UTC), "text/plain", body)
    record_equipment(
        ws,
        first_job,
        OutboundGuard(ws, first_job),
        snapshot,
        model="Example Motor X",
        purpose="pumps water",
        energy_features="variable speed",
        quote=body.decode(),
        trust_reason="Synthetic manufacturer page",
    )

    next_job = create_job(ws, "audit", "synthetic", 2027)
    reused = cached_equipment(ws, next_job, "Example Motor X")
    assert reused is not None
    copied = load_snapshot(ws, next_job, reused.snapshot_sha)
    assert copied.body == body
    assert copied.url == reused.source_url
    assert copied.retrieved_at.isoformat() == reused.retrieved_at
    assert reused.quote in copied.text
