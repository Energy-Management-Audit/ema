"""The Research stage over synthetic equipment rows: replay, guard, budget and call bound."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from tests.workspace_jobs import create_job

from ema.api.error_status import STATUS
from ema.audit import research_stage
from ema.audit.research_stage import (
    BATCH,
    EXTRACTION_FILE,
    PROMPT,
    PROMPT_VERSION,
    SEARCH_FILE,
    Extraction,
    Sources,
    research_equipment,
)
from ema.audit.stages import start_audit_stage
from ema.cli import app
from ema.core.errors import EmaError
from ema.core.jobs import get_job, status
from ema.core.llm import curated_models
from ema.core.llm.replay import request_hashes
from ema.core.llm.types import Exchange, ToolSpec
from ema.core.review.evidence import get_evidence
from ema.core.review.fields import fields, propose
from ema.core.review.models import Evidence, Manual
from ema.core.workspace import Workspace

MODEL = next(model.id for model in curated_models() if model.provider == "openai")
NAME = "Compresor Exemplu CX-15 seria 4471"
QUERY = "Compresor Exemplu fisa tehnica"
HIT = {
    "title": "Compresor Exemplu CX-15",
    "url": "https://example.org/cx-15",
    "snippet": "Compresor Exemplu CX-15 produce aer comprimat cu motor de 15 kW.",
}
TEXT = f"{HIT['title']}\n{HIT['snippet']}"
QUOTE = "Compresor Exemplu CX-15 produce aer comprimat cu motor de 15 kW"
SPEC = {
    "id": "1",
    "result": 1,
    "model": "Compresor Exemplu CX-15",
    "purpose": "produce aer comprimat",
    "energy_features": "motor de 15 kW",
    "quote": QUOTE,
}


def _job(ws: Workspace, names: list[str]) -> str:
    job = create_job(ws, "audit", "synthetic", 2026)
    for number, name in enumerate(names, 1):
        key = f"audit.equipment_row.{number}.name"
        evidence = Evidence(
            id=f"synthetic:{key}",
            provenance="manual",
            locator=Manual(who="synthetic"),
            method="manual",
            retrieved_at=datetime.now(UTC),
            highlight="exact",
        )
        propose(ws, job, key, name, [evidence], state="supplied")
    return job


def _recorded_run(ws: Workspace, job: str, search: dict[str, Any], responses: list[Any]) -> Path:
    """A finished research run folder holding hand-authored search and extraction recordings."""
    with ws.connect() as db:
        db.execute(
            "INSERT INTO runs (id,job_id,stage,owner,state,started_at) VALUES (?,?,?,?,?,?)",
            ("recorded", job, "research", "test", "ready", "2026-01-01T00:00:00+00:00"),
        )
        folder = ws.job_path(db, job) / "work" / "research" / "recorded"
    folder.mkdir(parents=True)
    (folder / SEARCH_FILE).write_text(
        json.dumps({"source": "hand-authored", "queries": search}), encoding="utf-8"
    )
    rows = [
        {
            "model": MODEL,
            "request_hashes": request_hashes(
                MODEL,
                [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": json.dumps(content, ensure_ascii=False)},
                ],
                (),
                Extraction.model_json_schema(),
                4096,
                PROMPT_VERSION,
            ),
            "choices": [{"message": {"content": json.dumps(answer)}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 120},
        }
        for content, answer in responses
    ]
    (folder / EXTRACTION_FILE).write_text(
        json.dumps(
            {"source": "hand-authored", "format": "openai-chat-completions", "responses": rows}
        ),
        encoding="utf-8",
    )
    return folder


def _content(*items: tuple[str, str, list[dict[str, str]]]) -> dict[str, Any]:
    """The extraction request exactly as the stage sends it."""
    return {
        "items": [
            {
                "id": number,
                "equipment": name,
                "excerpts": [
                    {"n": n, "url": hit["url"], "text": f"{hit['title']}\n{hit['snippet']}"}
                    for n, hit in enumerate(hits, 1)
                ],
            }
            for number, name, hits in items
        ]
    }


def _llm_calls(ws: Workspace, job: str) -> int:
    with ws.connect() as db:
        return int(
            db.execute(
                "SELECT COUNT(*) FROM llm_calls WHERE job_id=? AND section=?",
                (job, "research:ch3.equipment"),
            ).fetchone()[0]
        )


def _log(ws: Workspace, job: str) -> list[dict[str, Any]]:
    with ws.connect() as db:
        text = (ws.job_path(db, job) / "log.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


class FakeSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str) -> list[dict[str, str]]:
        self.queries.append(query)
        return [{**HIT, "url": f"https://example.org/{len(self.queries)}"}]


class FakeProvider:
    """Stands in for the live adapter; answers every batch with no sourced item."""

    name = "openai"

    def __init__(self, answer: dict[str, Any] | None = None) -> None:
        self.calls = 0
        self.answer = answer or {"items": []}

    def respond(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: tuple[ToolSpec, ...],
        schema: dict[str, Any] | None = None,
        max_output_tokens: int = 4096,
        synthetic: bool = False,
        *,
        prompt_version: str = "",
        attachments: Mapping[str, bytes] | None = None,
    ) -> Exchange:
        del model, messages, tools, schema, max_output_tokens, synthetic, attachments
        assert prompt_version == PROMPT_VERSION
        self.calls += 1
        return Exchange(json.dumps(self.answer), (), 1000, 200)


def test_replayed_search_and_extraction_drive_the_stage_from_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ws = Workspace(tmp_path / "ws")
    monkeypatch.setenv("EMA_WORKSPACE", str(ws.root))
    job = _job(ws, [NAME])
    _recorded_run(ws, job, {QUERY: [HIT]}, [(_content(("1", NAME, [HIT])), {"items": [SPEC]})])
    monkeypatch.setattr(sys, "argv", ["ema", "audit", "run", job, "research"])

    with pytest.raises(SystemExit) as exited:
        app()

    assert exited.value.code == 0
    run = json.loads(capsys.readouterr().out)["run_id"]
    assert next(item for item in status(ws, job).runs if item["id"] == run)["state"] == "ready"
    slug = hashlib.sha256(SPEC["model"].casefold().encode()).hexdigest()[:20]
    field = next(item for item in fields(ws, job) if item.key == f"audit.equipment.{slug}")
    assert field.value == "Compresor Exemplu CX-15: produce aer comprimat; motor de 15 kW"
    (evidence_id,) = field.evidence
    evidence = get_evidence(ws, evidence_id)
    assert evidence.provenance == "online"
    assert evidence.quote == QUOTE
    assert evidence.trust_reason == "Search result excerpt from example.org"
    assert evidence.locator.model_dump()["url"] == HIT["url"]
    assert evidence.file_sha == hashlib.sha256(TEXT.encode()).hexdigest()
    assert _llm_calls(ws, job) == 1
    done = next(event for event in _log(ws, job) if event.get("event") == "research_done")
    assert (done["live"], done["rows"], done["calls"], done["sourced"]) == (False, 1, 1, 1)


def test_live_run_records_both_files_and_a_later_run_replays_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = _job(ws, [NAME])
    monkeypatch.setenv("EMA_RESEARCH_LIVE", "1")
    monkeypatch.setenv("EMA_BRAVE_API_KEY", "synthetic-key")
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "true")
    live = FakeProvider({"items": [SPEC]})
    monkeypatch.setattr("ema.audit.search_brave.BraveSearch.search", lambda _, query: [HIT])
    monkeypatch.setattr(research_stage, "live_provider", lambda _: (live, MODEL))

    first = research_equipment(ws, job)

    monkeypatch.setenv("EMA_RESEARCH_LIVE", "0")
    second = research_equipment(ws, job)
    assert (first.live, first.sourced, second.live, second.sourced) == (True, ("1",), False, ("1",))
    assert live.calls == 1
    with ws.connect() as db:
        folder = ws.job_path(db, job) / "work" / "research" / first.run
    recorded = json.loads((folder / SEARCH_FILE).read_text(encoding="utf-8"))
    assert recorded == {"source": "recorded", "queries": {QUERY: [HIT]}}
    assert (folder / EXTRACTION_FILE).is_file()
    assert not (folder.parent / second.run / EXTRACTION_FILE).exists()


def test_without_a_recording_and_live_off_the_stage_refuses_before_starting(
    tmp_path: Path,
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = _job(ws, [NAME])

    with pytest.raises(EmaError) as refused:
        start_audit_stage(ws, job, "research", int(str(get_job(ws, job)["revision"])))

    assert refused.value.code == "research_replay_missing"
    assert STATUS["research_replay_missing"] == 409
    assert status(ws, job).runs == []


def test_guard_refuses_a_private_value_and_counts_it(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    # A one-word name makes the whole private value part of the query.
    job = _job(ws, [NAME, "Uscator"])
    _recorded_run(ws, job, {QUERY: [HIT]}, [(_content(("1", NAME, [HIT])), {"items": [SPEC]})])

    summary = research_equipment(ws, job)

    assert summary.refused == ("2",)
    assert summary.sourced == ("1",)
    assert summary.failed == {}
    verdicts = [
        (event["value"], event["verdict"])
        for event in _log(ws, job)
        if event.get("event") == "research_outbound" and event["kind"] == "query"
    ]
    assert verdicts == [(QUERY, "allowed"), ("[redacted]", "private_value")]


def test_spent_budget_stops_the_stage_before_any_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.5")
    ws = Workspace(tmp_path / "ws")
    job = _job(ws, [f"Pompa{number:02d} Model X{number}" for number in range(1, BATCH + 3)])
    with ws.connect() as db:
        db.execute(
            "INSERT INTO llm_calls(job_id,section,provider,model,prompt_version,input_tokens,"
            "output_tokens,estimated_cost_usd,duration_ms) VALUES(?,?,?,?,?,?,?,?,?)",
            (job, "fill", "openai", MODEL, "audit-fill-v1", 1, 1, 0.75, 1),
        )
    search, provider = FakeSearch(), FakeProvider()
    monkeypatch.setattr(
        research_stage, "research_sources", lambda *_: Sources(search, provider, MODEL, False)
    )

    summary = research_equipment(ws, job)

    assert provider.calls == 0
    assert _llm_calls(ws, job) == 0
    assert set(summary.failed.values()) == {"ai_budget"}
    assert len(summary.failed) == BATCH
    assert summary.stopped == ("11", "12")
    assert len(search.queries) == BATCH  # the stopped batch is not even searched
    run = next(item for item in status(ws, job).runs if item["id"] == summary.run)
    assert run["state"] == "ready"


@pytest.mark.parametrize("models", [10, 21])
def test_one_extraction_call_per_batch_of_ten_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, models: int
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = _job(ws, [f"Motor{number:02d} Model X{number}" for number in range(1, models + 1)])
    search, provider = FakeSearch(), FakeProvider()
    monkeypatch.setattr(
        research_stage, "research_sources", lambda *_: Sources(search, provider, MODEL, False)
    )

    summary = research_equipment(ws, job)

    # A 10-model job: 10 searches (no AI cost) and one extraction call.
    assert summary.calls == provider.calls == _llm_calls(ws, job) == math.ceil(models / BATCH)
    assert len(search.queries) == models
    assert len(summary.not_found) == models
