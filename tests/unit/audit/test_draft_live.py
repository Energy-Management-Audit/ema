"""Live Draft over a fake provider: a call per chapter group, recordings and the stage's stops."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from tests.audit_replay import audit_job_with_facts

from ema.audit.draft_live import DraftSummary, start_draft
from ema.audit.draft_plan import allowance
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
# A second section in each chapter, each from a fact that is not a passage.
CH2_OTHER, CH3 = "ch2.manager", ("ch3.parc_auto", "ch3.automatizare")


class FakeLive:
    """Stands in for the OpenAI adapter. Per-section modes: ok, omit (left out of every
    answer), quota (the call fails), retry (invalid in the first answer)."""

    name = "openai"

    def __init__(self, modes: dict[str, str] | None = None) -> None:
        self.modes = modes or {}
        self.calls: list[tuple[str, tuple[str, ...], int]] = []
        self.models: list[str] = []
        self.synthetic: list[bool] = []
        self.support_response: str | None = None

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
        request = json.loads(str(messages[1]["content"]))
        if prompt_version.endswith("-support"):
            self.calls.append(("support", (), max_output_tokens))
            verdicts = [
                {"location": item["location"], "sentence_index": item["sentence_index"]}
                | {"supported": True, "reason": ""}
                for item in request
            ]
            return Exchange(self.support_response or json.dumps({"verdicts": verdicts}), (), 1, 1)
        retry = "request" in request
        asked = (request["request"] if retry else request)["sections"]
        names = tuple(item["section"] for item in asked)
        self.calls.append(("retry" if retry else "draft", names, max_output_tokens))
        if any(self.modes.get(name) == "quota" for name in names):
            raise EmaError("ai_quota_day", "Cota zilnică.", model)
        drafts = [
            self._draft(item, invalid=self.modes.get(item["section"]) == "retry" and not retry)
            for item in asked
            if self.modes.get(item["section"]) != "omit"
        ]
        return Exchange(json.dumps({"sections": drafts}), (), 1, 1)

    @staticmethod
    def _draft(item: dict[str, Any], *, invalid: bool) -> dict[str, Any]:
        key = item["facts"][0]["key"]
        text = "Atelier Exemplu." if invalid else f"valoarea este {{{{f:{key}}}}}."
        paragraph = DraftText(text=text, fact_ids=[] if invalid else [key])
        return SectionDraft(
            section=item["section"], status="drafted", paragraphs=[paragraph]
        ).model_dump()

    def logical(self) -> list[str]:
        return [kind for kind, _, _ in self.calls]


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


def _two_chapters(ws: Workspace) -> str:
    job = audit_job_with_facts(ws)
    for section in (CH2_OTHER, *CH3):
        _found(ws, job, section)
    return job


def _run(ws: Workspace, job: str) -> tuple[DraftSummary, str]:
    summaries: list[DraftSummary] = []
    run = start_draft(ws, job, summaries=summaries)
    for _ in subscribe(ws, job):
        pass
    state = next(item for item in status(ws, job).runs if item["id"] == run)
    return summaries[0], str(state["state"])


def _logical_calls(ws: Workspace, job: str) -> int:
    with ws.connect() as db:
        return int(
            db.execute("SELECT COUNT(*) FROM llm_calls WHERE job_id=?", (job,)).fetchone()[0]
        )


def test_live_single_section_takes_the_chapter_path_and_records_one_file(
    tmp_path: Path, live: FakeLive
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = _two_chapters(ws)

    result = draft_section(ws, job, SECTION)

    assert (result.draft_status, result.section_status) == ("drafted", "drafted")
    assert [(kind, names) for kind, names, _ in live.calls] == [
        ("draft", (SECTION,)),
        ("support", ()),
    ]
    assert set(live.models) == {default_model("openai").id}
    assert live.synthetic == [False] * len(live.synthetic)
    recording = result.draft_path.parent.parent / f"chapter-{SECTION}.json"
    recorded = json.loads(recording.read_text(encoding="utf-8"))
    assert recorded["source"] == "recorded" and len(recorded["responses"]) == 2


def test_a_recorded_chapter_replays_offline(
    tmp_path: Path, live: FakeLive, monkeypatch: pytest.MonkeyPatch
) -> None:
    live.modes[SECTION] = "retry"
    ws = Workspace(tmp_path / "ws")
    job = _two_chapters(ws)
    recorded = draft_section(ws, job, SECTION)
    recording = recorded.draft_path.parent.parent / f"chapter-{SECTION}.json"
    assert live.logical() == ["draft", "retry", "support"]

    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "0")
    replayed = draft_section(ws, job, SECTION, recording=recording)

    assert live.logical() == ["draft", "retry", "support"]
    assert replayed.run != recorded.run
    assert replayed.draft_path.read_text(encoding="utf-8") == recorded.draft_path.read_text(
        encoding="utf-8"
    )
    assert (replayed.draft_status, replayed.review) == (recorded.draft_status, recorded.review)
    with pytest.raises(EmaError) as both:
        draft_section(
            ws,
            job,
            SECTION,
            draft_recording=recording,
            support_recording=recording,
            recording=recording,
        )
    assert both.value.code == "replay_invalid"


def test_support_error_keeps_written_and_queued_draft(tmp_path: Path, live: FakeLive) -> None:
    live.support_response = "not json"
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
    assert live.calls == []


def test_one_call_per_chapter_drafts_its_sections_and_records_each_group(
    tmp_path: Path, live: FakeLive
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = _two_chapters(ws)

    summary, state = _run(ws, job)

    assert state == "ready"
    assert summary.drafted == dict.fromkeys((SECTION, CH2_OTHER, *CH3), "drafted")
    assert [(kind, names) for kind, names, _ in live.calls] == [
        ("draft", (SECTION, CH2_OTHER)),
        ("support", ()),
        ("draft", CH3),
        ("support", ()),
    ]
    # No audit base is configured, so each section counts as an unmeasured one.
    assert live.calls[0][2] == allowance([None, None])
    assert set(summary.skipped) | set(summary.drafted) | set(summary.not_applicable) == set(
        SECTION_FACTS
    )
    with ws.connect() as db:
        run = str(db.execute("SELECT id FROM runs WHERE stage='draft'").fetchone()["id"])
        folder = ws.artifact_dir(db, job, "draft", run)
    for group in ("2-1", "3-1"):
        recorded = json.loads((folder / f"chapter-{group}.json").read_text(encoding="utf-8"))
        assert len(recorded["responses"]) == 2
    assert {path.name for path in (folder / "sections").glob("*.json")} == {
        name
        for section in summary.drafted
        for name in (f"{section}.json", f"{section}.draft-review.json")
    }


def test_a_two_chapter_job_takes_at_most_six_logical_calls(tmp_path: Path, live: FakeLive) -> None:
    live.modes.update({SECTION: "retry", CH3[0]: "retry"})
    ws = Workspace(tmp_path / "ws")
    job = _two_chapters(ws)

    summary, _ = _run(ws, job)

    assert summary.failed == {}
    assert live.logical() == ["draft", "retry", "support"] * 2
    assert _logical_calls(ws, job) == 6
    # The retry carries only the failing section.
    assert [names for kind, names, _ in live.calls if kind == "retry"] == [(SECTION,), (CH3[0],)]


def test_an_omitted_section_is_retried_then_fails_alone(tmp_path: Path, live: FakeLive) -> None:
    live.modes[CH2_OTHER] = "omit"
    ws = Workspace(tmp_path / "ws")
    job = _two_chapters(ws)

    summary, state = _run(ws, job)

    assert state == "ready"
    assert summary.failed == {CH2_OTHER: "draft_incomplete"}
    assert set(summary.drafted) == {SECTION, *CH3}
    assert ("retry", (CH2_OTHER,)) in [(kind, names) for kind, names, _ in live.calls]


def test_day_quota_stops_the_remaining_groups(tmp_path: Path, live: FakeLive) -> None:
    live.modes[SECTION] = "quota"
    ws = Workspace(tmp_path / "ws")
    job = _two_chapters(ws)

    summary, _ = _run(ws, job)

    assert summary.failed == {SECTION: "ai_quota_day", CH2_OTHER: "ai_quota_day"}
    assert summary.stopped == CH3
    assert summary.drafted == {}
    assert live.logical() == ["draft"]


def test_the_budget_stops_the_next_group_before_its_call(
    tmp_path: Path, live: FakeLive, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FixedCost:
        def cost(self, *_args: Any) -> float:
            return 0.2

    monkeypatch.setattr("ema.core.llm.structured.selected_model", lambda *_a: FixedCost())
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.5")
    ws = Workspace(tmp_path / "ws")
    job = _two_chapters(ws)

    summary, _ = _run(ws, job)

    assert set(summary.drafted) == {SECTION, CH2_OTHER}
    assert summary.failed == dict.fromkeys(CH3, "ai_budget")
    assert live.logical() == ["draft", "support"]
    assert job_spend(ws, job) == pytest.approx(0.4)


def test_checker_retry_is_budgeted(
    tmp_path: Path, live: FakeLive, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FixedCost:
        def cost(self, *_args: Any) -> float:
            return 0.2

    monkeypatch.setattr("ema.core.llm.structured.selected_model", lambda *_a: FixedCost())
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.7")
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    live.modes[SECTION] = "retry"
    summary, _ = _run(ws, job)
    assert summary.drafted == {SECTION: "drafted"}
    assert live.logical() == ["draft", "retry", "support"]
    assert job_spend(ws, job) == pytest.approx(0.6)


def test_job_budget_spent_earlier_stops_the_stage_before_any_call(
    tmp_path: Path, live: FakeLive, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.5")
    ws = Workspace(tmp_path / "ws")
    job = _two_chapters(ws)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO llm_calls(job_id,section,provider,model,prompt_version,input_tokens,"
            "output_tokens,estimated_cost_usd,duration_ms) VALUES(?,?,?,?,?,?,?,?,?)",
            (job, SECTION, "openai", "earlier", "audit-fill-v1", 1, 1, 0.75, 1),
        )

    summary, _ = _run(ws, job)

    assert set(summary.failed.values()) == {"ai_budget"}
    assert summary.stopped == CH3
    assert live.calls == []
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
    assert live.calls[0][:2] == ("draft", (SECTION,))
