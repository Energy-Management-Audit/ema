"""Live Draft over a fake provider: the task turn, recordings, and the stage's section choice."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from tests.audit_replay import audit_job_with_facts

from ema.audit.catalogue import CATALOGUE
from ema.audit.draft_agent import (
    FACT_RULE,
    LENGTH_RULE,
    PASSAGE_RULE,
    REFERENCE_RULE,
    SENTENCE_RULE,
    WORDING_RULE,
    draft_task,
)
from ema.audit.draft_live import DraftSummary, start_draft
from ema.audit.draft_schema import SECTION_FACTS, DraftText, SectionDraft
from ema.audit.draft_stage import draft_section
from ema.audit.stages import start_audit_stage
from ema.cli import app
from ema.core.errors import EmaError
from ema.core.jobs import get_job, status, subscribe
from ema.core.llm.agent import job_spend
from ema.core.llm.models import default_model
from ema.core.llm.types import Exchange, ToolSpec
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, Manual
from ema.core.workspace import Workspace

SECTION = "ch2.date_generale"
TASK = (
    "Redactează secţiunea ch2.date_generale „Date generale”. "
    "Câmpul section este exact „ch2.date_generale”. "
    f"{FACT_RULE} {SENTENCE_RULE} {LENGTH_RULE} {PASSAGE_RULE} {REFERENCE_RULE} {WORDING_RULE}"
)
TITLES = {section.id: section.title for section in CATALOGUE}


class FakeLive:
    """Stands in for the OpenAI adapter; per-section modes: ok, empty (no draft), quota."""

    name = "openai"

    def __init__(self, modes: dict[str, str] | None = None) -> None:
        self.modes = modes or {}
        self.tasks: list[str] = []
        self.models: list[str] = []
        self.synthetic: list[bool] = []
        self.support_response = '{"flags": []}'

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
        self.models.append(model)
        self.synthetic.append(synthetic)
        if prompt_version.endswith("-support"):
            return Exchange(self.support_response, (), 1, 1)
        request = json.loads(str(messages[1]["content"]))
        if "request" in request:
            request = json.loads(request["request"])
        task = request["task"]
        self.tasks.append(task)
        section = re.findall("„([^”]+)”", task)[-1]
        mode = self.modes.get(section, "ok")
        if mode == "quota":
            raise EmaError("ai_quota_day", "Cota zilnică.", model)
        if mode == "empty":
            return Exchange(json.dumps({"flags": []}), (), 1, 1)
        if mode == "retry" and self.tasks.count(task) == 1:
            invalid = SectionDraft(
                section=section, status="drafted", paragraphs=[DraftText(text="Atelier Exemplu.")]
            )
            return Exchange(invalid.model_dump_json(), (), 1, 1)
        key = next(item["key"] for item in request["facts"] if item["presence"] == "found")
        draft = SectionDraft(
            section=section,
            status="drafted",
            paragraphs=[DraftText(text=f"valoarea este {{{{f:{key}}}}}.", fact_ids=[key])],
        )
        return Exchange(draft.model_dump_json(), (), 1, 1)


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> FakeLive:
    fake = FakeLive()
    monkeypatch.setenv("EMA_PROVIDER", "openai")
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    monkeypatch.setenv("EMA_LLM_LIVE", "1")
    monkeypatch.setenv("EMA_OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr("ema.audit.fill_stage.OpenAIProvider", lambda *_a, **_k: fake)
    return fake


def _found(ws: Workspace, job: str, section: str) -> None:
    key = sorted(SECTION_FACTS[section])[0]
    evidence = Evidence(
        id="synthetic:" + key,
        provenance="manual",
        locator=Manual(who="synthetic"),
        method="manual",
        retrieved_at=datetime.now(UTC),
        highlight="exact",
    )
    propose(ws, job, key, "Exemplu", [evidence], state="supplied")


def test_task_sentence_names_the_section_id_and_title_exactly() -> None:
    assert TITLES[SECTION] == "Date generale"
    assert draft_task(SECTION) == TASK


def test_live_draft_section_runs_on_settings_and_records_both_passes(
    tmp_path: Path, live: FakeLive
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)

    result = draft_section(ws, job, SECTION)

    assert (result.draft_status, result.section_status) == ("drafted", "drafted")
    assert live.tasks and set(live.tasks) == {TASK}
    assert set(live.models) == {default_model("openai").id}
    assert live.synthetic == [False] * len(live.synthetic)
    folder = result.draft_path.parent.parent / "draft"
    for name in (f"{SECTION}.draft.json", f"{SECTION}.support.json"):
        recorded = json.loads((folder / name).read_text(encoding="utf-8"))
        assert recorded["source"] == "recorded" and recorded["responses"]
    assert json.loads((folder / f"{SECTION}.draft.json").read_text("utf-8"))["responses"][0][
        "choices"
    ][0]["message"]["content"]


def test_support_error_keeps_written_and_queued_draft(tmp_path: Path, live: FakeLive) -> None:
    live.support_response = '{"flags": [{"location": "bad", "sentence": "x", "reason": "x"}]}'
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    result = draft_section(ws, job, SECTION)
    assert result.draft_status == "drafted"
    assert result.draft_path.is_file()
    assert any(flag.code == "support_unavailable" for flag in result.review)
    assert result.section_status == "drafted"


def test_live_switch_off_sends_nothing(
    tmp_path: Path, live: FakeLive, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "0")
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    with pytest.raises(EmaError) as refused:
        draft_section(ws, job, SECTION, draft_recording=None, support_recording=None)
    assert refused.value.code == "ai_client_disabled"
    with pytest.raises(EmaError) as stage:
        start_audit_stage(ws, job, "draft", int(str(get_job(ws, job)["revision"])))
    assert stage.value.code == "ai_client_disabled"
    assert live.tasks == []


def _run(ws: Workspace, job: str) -> tuple[DraftSummary, str]:
    summaries: list[DraftSummary] = []
    run = start_draft(ws, job, summaries=summaries)
    for _ in subscribe(ws, job):
        pass
    state = next(item for item in status(ws, job).runs if item["id"] == run)
    return summaries[0], str(state["state"])


def test_stage_drafts_only_sections_with_a_found_fact(tmp_path: Path, live: FakeLive) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)

    started = start_audit_stage(ws, job, "draft", int(str(get_job(ws, job)["revision"])))
    for _ in subscribe(ws, job):
        pass

    assert next(item for item in status(ws, job).runs if item["id"] == started)["state"] == "ready"
    assert {re.findall("„([^”]+)”", task)[-1] for task in live.tasks} == {SECTION}
    summary, _ = _run(ws, job)
    assert summary.drafted == {SECTION: "drafted"}
    assert SECTION not in summary.skipped
    assert set(summary.skipped) | {SECTION} | set(summary.not_applicable) == set(SECTION_FACTS)


def test_one_failed_section_does_not_fail_the_others(tmp_path: Path, live: FakeLive) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    other = next(item for item in SECTION_FACTS if item != SECTION)
    _found(ws, job, other)
    live.modes[other] = "empty"

    summary, state = _run(ws, job)

    assert summary.drafted == {SECTION: "drafted"}
    assert summary.failed == {other: "ai_schema"}
    assert state == "ready"


def test_day_quota_stops_the_remaining_sections(tmp_path: Path, live: FakeLive) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    order = [item for item in SECTION_FACTS if item != SECTION][:2]
    for section in order:
        _found(ws, job, section)
    first, second = sorted([SECTION, *order], key=list(SECTION_FACTS).index)[:2]
    live.modes[first] = "quota"

    summary, _ = _run(ws, job)

    assert summary.failed == {first: "ai_quota_day"}
    assert second in summary.drafted
    assert len(live.tasks) == 3


def test_quota_stops_sections_after_first_batch(tmp_path: Path, live: FakeLive) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    order = list(SECTION_FACTS)[:5]
    for section in order:
        if section != SECTION:
            _found(ws, job, section)
    live.modes[order[0]] = "quota"
    summary, _ = _run(ws, job)
    assert summary.failed[order[0]] == "ai_quota_day"
    assert summary.stopped == (order[4],)
    assert order[4] not in summary.drafted
    assert len(live.tasks) == 4


def test_parallel_budget_keeps_order_and_caps_calls(
    tmp_path: Path, live: FakeLive, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FixedCost:
        def cost(self, *_args: Any) -> float:
            return 0.2

    monkeypatch.setattr("ema.core.llm.structured.selected_model", lambda *_a: FixedCost())
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.5")
    order = list(SECTION_FACTS)[:4]
    for index in range(3):
        ws = Workspace(tmp_path / f"ws-{index}")
        job = audit_job_with_facts(ws)
        for section in order:
            if section != SECTION:
                _found(ws, job, section)
        summary, _ = _run(ws, job)
        assert len(summary.drafted) == 1
        assert list(summary.drafted) == [section for section in order if section in summary.drafted]
        assert list(summary.failed) == [section for section in order if section in summary.failed]
        assert set(summary.failed.values()) == {"ai_budget"}
        assert job_spend(ws, job) == pytest.approx(0.4)
        assert len(live.tasks) == index + 1


def test_checker_retry_is_budgeted(
    tmp_path: Path, live: FakeLive, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FixedCost:
        def cost(self, *_args: Any) -> float:
            return 0.2

    monkeypatch.setattr("ema.core.llm.structured.selected_model", lambda *_a: FixedCost())
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.5")
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    live.modes[SECTION] = "retry"
    summary, _ = _run(ws, job)
    assert summary.drafted == {SECTION: "drafted"}
    assert summary.failed == {}
    assert len(live.tasks) == 2
    assert job_spend(ws, job) == pytest.approx(0.4)


def test_job_budget_spent_earlier_stops_the_stage_before_any_call(
    tmp_path: Path, live: FakeLive, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.5")
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    for section in [item for item in SECTION_FACTS if item != SECTION][:2]:
        _found(ws, job, section)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO llm_calls(job_id,section,provider,model,prompt_version,input_tokens,"
            "output_tokens,estimated_cost_usd,duration_ms) VALUES(?,?,?,?,?,?,?,?,?)",
            (job, SECTION, "openai", "earlier", "audit-fill-v1", 1, 1, 0.75, 1),
        )

    summary, _ = _run(ws, job)

    assert set(summary.failed.values()) == {"ai_budget"}
    assert live.tasks == []
    with ws.connect() as db:
        log = (ws.job_path(db, job) / "log.jsonl").read_text(encoding="utf-8")
    spend = [json.loads(line) for line in log.splitlines() if '"ai_spend"' in line]
    assert [(item["stage"], item["usd"], item["job_usd"]) for item in spend] == [
        ("draft", 0.0, 0.75)
    ]


def test_cli_run_draft_takes_the_stage_path(
    tmp_path: Path,
    live: FakeLive,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ws = Workspace(tmp_path / "ws")
    monkeypatch.setenv("EMA_WORKSPACE", str(ws.root))
    job = audit_job_with_facts(ws)
    monkeypatch.setattr(sys, "argv", ["ema", "audit", "run", job, "draft"])

    with pytest.raises(SystemExit) as exited:
        app()

    run = json.loads(capsys.readouterr().out)["run_id"]
    assert exited.value.code == 0
    assert next(item for item in status(ws, job).runs if item["id"] == run)["state"] == "ready"
    assert {re.findall("„([^”]+)”", task)[-1] for task in live.tasks} == {SECTION}
