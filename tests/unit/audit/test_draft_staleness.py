"""A filtered chapter fact still has its actual revision in a Draft run."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from tests.unit.audit.test_draft_live import FakeLive
from tests.workspace_jobs import create_job

from ema.audit import draft_live, render_writers
from ema.audit.draft_live import start_draft
from ema.audit.draft_plan import Group
from ema.audit.draft_schema import DraftText
from ema.core.jobs import status, subscribe
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, Manual
from ema.core.workspace import Workspace


def test_two_groups_with_a_filtered_shared_fact_publish_current_and_render_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = FakeLive()
    monkeypatch.setenv("EMA_PROVIDER", "openai")
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    monkeypatch.setenv("EMA_LLM_LIVE", "1")
    monkeypatch.setenv("EMA_OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr("ema.audit.fill_stage.OpenAIProvider", lambda *_a, **_k: live)
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    for key in ("audit.equipment", "audit.process_sections"):
        evidence = Evidence(
            id="synthetic:" + key,
            provenance="manual",
            locator=Manual(who="synthetic"),
            method="manual",
            retrieved_at=datetime.now(UTC),
            highlight="exact",
        )
        propose(ws, job, key, "Exemplu", [evidence], state="supplied")
    sections = ("ch3.flux", "ch3.process")
    monkeypatch.setattr(draft_live, "draftable", lambda _ws, _job: (list(sections), [], []))
    original_groups = draft_live.chapter_groups

    def two_groups(ws: Workspace, job: str, selected: list[str], facts=None):
        groups, units = original_groups(ws, job, selected, facts)
        (group,) = groups
        assert "audit.process_sections" in group.sections[0].facts
        assert "audit.process_sections" not in group.sections[1].facts
        flux, process = group.sections
        return [
            Group("3-1", 3, (flux,)),
            Group("3-2", 3, (replace(process, units=((1, ()),)),)),
        ], units

    monkeypatch.setattr(draft_live, "chapter_groups", two_groups)
    original_draft = FakeLive._draft

    def draft(item: dict[str, Any], *, invalid: bool) -> dict[str, Any]:
        result = original_draft(item, invalid=invalid)
        if item["section"] == "ch3.flux":
            result["paragraphs"] = [
                DraftText(
                    text="Valoarea este descrisă {{c:audit.process_sections}}.",
                    fact_ids=["audit.process_sections"],
                ).model_dump()
            ]
        elif item["section"] == "ch3.process":
            result["paragraphs"][0]["unit"] = 1
        return result

    monkeypatch.setattr(live, "_draft", draft)

    run = start_draft(ws, job)
    for _ in subscribe(ws, job):
        pass

    record = next(item for item in status(ws, job).runs if item["id"] == run)
    assert (record["state"], record["publication"]) == ("ready", "current")
    assert [names for kind, names, _ in live.calls if kind == "draft"] == [
        ("ch3.flux",),
        ("ch3.process",),
    ]
    with ws.connect() as db:
        reads = db.execute(
            "SELECT revision FROM run_reads WHERE run_id=? AND table_name='fields.key' "
            "AND row_id=?",
            (run, f"{job}:audit.process_sections"),
        ).fetchall()
    assert [row["revision"] for row in reads] == [1]
    assert render_writers.ready_runs(ws, job, "draft")
