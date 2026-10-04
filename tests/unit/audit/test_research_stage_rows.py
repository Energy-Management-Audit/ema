"""Research stage review round: whole-number evidence, live gating, replay source, row counts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests.unit.audit.test_research_stage import (
    HIT,
    NAME,
    QUERY,
    SPEC,
    _content,
    _job,
    _log,
    _recorded_run,
)

from ema.audit import research_stage
from ema.audit.research_equipment import in_quote
from ema.audit.research_stage import research_equipment
from ema.core.errors import EmaError
from ema.core.review.fields import fields
from ema.core.workspace import Workspace


@pytest.mark.parametrize(
    ("value", "quote", "found"),
    [
        ("15 kW", "motor de 15 kW.", True),
        ("15 kW", "motor de 115 kW", False),
        ("15 kW", "consum 15 kWh", False),
        ("234,5 kW", "putere 1.234,5 kW", False),
        ("234,5 kW", "putere 1 234,5 kW", False),
        ("1.234,5 kW", "putere 1.234,5 kW", True),
        ("1 234,5 kW", "putere 1 234,5 kW", True),
        ("1.234", "putere 1.234,5 kW", False),
        ("15 kW", "115 kW sau 15 kW", True),
        ("CX-15", "Compresor CX-150", False),
    ],
)
def test_a_value_matches_whole_words_and_numbers_only(value: str, quote: str, found: bool) -> None:
    assert in_quote(value, quote) is found


def test_a_number_inside_a_longer_number_is_not_evidence(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = _job(ws, [NAME])
    hit = {**HIT, "snippet": "Compresor Exemplu CX-15 produce aer comprimat cu motor de 115 kW."}
    quote = "Compresor Exemplu CX-15 produce aer comprimat cu motor de 115 kW"
    spec = {**SPEC, "energy_features": "15 kW", "quote": quote}
    _recorded_run(ws, job, {QUERY: [hit]}, [(_content(("1", NAME, [hit])), {"items": [spec]})])

    summary = research_equipment(ws, job)

    assert (summary.sourced, summary.failed) == ((), {"1": "evidence_quote"})
    assert not [item for item in fields(ws, job) if item.key.startswith("audit.equipment.")]


def test_brave_without_client_live_replays_the_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = _job(ws, [NAME])
    monkeypatch.setenv("EMA_RESEARCH_LIVE", "1")
    monkeypatch.setenv("EMA_BRAVE_API_KEY", "synthetic-key")
    monkeypatch.delenv("EMA_AI_CLIENT_LIVE", raising=False)

    def no_brave(_: object, query: str) -> list[dict[str, str]]:
        raise AssertionError(query)

    monkeypatch.setattr("ema.audit.search_brave.BraveSearch.search", no_brave)
    with pytest.raises(EmaError) as refused:
        research_stage.research_sources(ws, job)
    assert refused.value.code == "research_replay_missing"

    _recorded_run(ws, job, {QUERY: [HIT]}, [(_content(("1", NAME, [HIT])), {"items": [SPEC]})])
    summary = research_equipment(ws, job)

    assert (summary.live, summary.sourced) == (False, ("1",))


def test_a_replay_answers_from_its_recording_not_the_client_search_cache(
    tmp_path: Path,
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = _job(ws, [NAME])
    with ws.connect() as db:
        slug = db.execute("SELECT client_slug FROM jobs WHERE id=?", (job,)).fetchone()[0]
    cache = ws.path(
        f"clients/{slug}/research/search-{hashlib.sha256(QUERY.encode()).hexdigest()}.json"
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    stale = [{**HIT, "snippet": ""}]
    cache.write_text(json.dumps(stale), encoding="utf-8")
    _recorded_run(ws, job, {QUERY: [HIT]}, [(_content(("1", NAME, [HIT])), {"items": [SPEC]})])

    summary = research_equipment(ws, job)

    assert (summary.sourced, summary.not_found) == (("1",), ())
    assert json.loads(cache.read_text(encoding="utf-8")) == stale


def test_rows_that_repeat_a_name_share_one_search_and_each_keep_their_number(
    tmp_path: Path,
) -> None:
    ws = Workspace(tmp_path / "ws")
    # Row 2 is a one-word private name the guard refuses; rows 1 and 3 repeat one model.
    job = _job(ws, [NAME, "Uscator", f"  {NAME.upper()} "])
    _recorded_run(ws, job, {QUERY: [HIT]}, [(_content(("1", NAME, [HIT])), {"items": [SPEC]})])

    summary = research_equipment(ws, job)

    assert (summary.rows, summary.calls) == (3, 1)
    assert (summary.sourced, summary.refused) == (("1", "3"), ("2",))
    log = _log(ws, job)
    queries = [
        event["value"]
        for event in log
        if event.get("event") == "research_outbound" and event["kind"] == "query"
    ]
    assert queries == [QUERY, "[redacted]"]
    done = next(event for event in log if event.get("event") == "research_done")
    assert (done["rows"], done["sourced"], done["refused"]) == (3, 2, 1)
