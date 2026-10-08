"""Ch. 4 variable factors (#162 D4): one checked call at the end of Draft, stored for review."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tests.workspace_jobs import create_job

from ema.audit import draft_live, render_writers
from ema.audit.chapter_four_factors import PROMPT_VERSION, factor_issues
from ema.audit.draft_live import DraftSummary, start_draft
from ema.audit.read import read_dossier
from ema.core.errors import EmaError
from ema.core.jobs import status, subscribe
from ema.core.llm.types import Exchange, ToolSpec
from ema.core.review import decide, fields
from ema.core.review.evidence import get_evidence
from ema.core.review.models import Field
from ema.core.workspace import Workspace
from ema.energy_data.necesar import parse_necesar_info, to_dataset

FIXTURE = Path(__file__).parents[2] / "fixtures/audit/synthetic_necesar.xlsx"
KEY = "narrative.ch4.factors.electricitate"
GOOD = (
    "regimul de lucru și numărul de schimburi: consumul atinge valori maxime în timpul "
    "schimburilor de producție active și scade noaptea"
)
SEASON = "climatizarea: răcirea spațiilor crește consumul în sezonul cald;"


class FakeFactors:
    """Stands in for the OpenAI adapter: `factors` for every requested resource, or a failure."""

    name = "openai"

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.versions: list[str] = []
        self.factors = [GOOD, SEASON]
        self.extra: list[dict[str, Any]] = []
        self.fail = False

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
        thinking_tokens: int | None = None,
    ) -> Exchange:
        request = json.loads(str(messages[1]["content"]))
        self.requests.append(request)
        self.versions.append(prompt_version)
        if self.fail:
            raise EmaError("ai_provider", "Furnizorul AI a eșuat.", model)
        lists = [{"id": item["id"], "factors": self.factors} for item in request["resources"]]
        return Exchange(json.dumps({"lists": [*lists, *self.extra]}), (), 1, 1)


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> FakeFactors:
    fake = FakeFactors()
    monkeypatch.setenv("EMA_PROVIDER", "openai")
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    monkeypatch.setenv("EMA_LLM_LIVE", "1")
    monkeypatch.setenv("EMA_OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr("ema.audit.fill_stage.OpenAIProvider", lambda *_a, **_k: fake)
    # Chapters 2-3 are drafted by their own calls; these tests look at the ch. 4 one alone.
    monkeypatch.setattr(draft_live, "draftable", lambda ws, job: ([], [], []))
    return fake


def _job(tmp_path: Path) -> tuple[Workspace, str]:
    """The synthetic Necesar has electricity only: ch4.electricitate applies, the rest do not."""
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    read_dossier(ws, job, FIXTURE)
    return ws, job


def _draft(ws: Workspace, job: str) -> tuple[DraftSummary, dict[str, Any]]:
    summaries: list[DraftSummary] = []
    run = start_draft(ws, job, summaries=summaries)
    for _ in subscribe(ws, job):
        pass
    return summaries[0], next(item for item in status(ws, job).runs if item["id"] == run)


def _lists(ws: Workspace, job: str) -> dict[str, str]:
    return {
        field.key: str(field.value)
        for field in fields(ws, job)
        if field.key.startswith("narrative.ch4.factors.")
    }


def test_draft_asks_once_for_each_analysed_resource_and_proposes_its_list(
    tmp_path: Path, live: FakeFactors
) -> None:
    ws, job = _job(tmp_path)
    _, run = _draft(ws, job)

    assert run["state"] == "ready"
    assert live.versions == [PROMPT_VERSION] == ["audit-ch4-factors-v1"]
    assert live.requests[0]["resources"] == [
        {"id": "ch4.electricitate", "resource": "energie electrică"}
    ]
    assert _lists(ws, job) == {KEY: GOOD + "\n" + SEASON.rstrip(";")}
    field = next(field for field in fields(ws, job) if field.key == KEY)
    assert (field.state, field.chapter, field.value_type) == ("enriched", "ch4", "text")
    evidence = get_evidence(ws, field.evidence[0])
    assert evidence.locator.who == "agent"  # type: ignore[union-attr]
    assert PROMPT_VERSION in str(evidence.locator.note)  # type: ignore[union-attr]

    _draft(ws, job)
    assert len(live.requests) == 1


def test_factors_with_numbers_names_or_ai_wording_are_dropped(
    tmp_path: Path, live: FakeFactors
) -> None:
    ws, job = _job(tmp_path)
    live.factors = [
        "volumul producției: consumul crește cu 20 % în lunile de vârf",
        "volumul producției: în trei schimburi consumul crește",
        "liniile Siemens: motoarele mari pornesc odată cu producția",
        "consumul a fost estimat de inteligența artificială",
        GOOD,
    ]
    live.extra = [{"id": "ch4.gaz", "factors": [GOOD]}]
    _draft(ws, job)
    assert _lists(ws, job) == {KEY: GOOD}


def test_a_list_with_no_passing_factor_leaves_the_marker(tmp_path: Path, live: FakeFactors) -> None:
    ws, job = _job(tmp_path)
    live.factors = ["consumul crește cu 20 %"]
    _draft(ws, job)
    assert _lists(ws, job) == {}


def test_a_failed_call_is_a_stage_warning_and_no_list(tmp_path: Path, live: FakeFactors) -> None:
    ws, job = _job(tmp_path)
    live.fail = True
    _, run = _draft(ws, job)
    assert run["state"] == "ready"
    assert _lists(ws, job) == {}
    with ws.connect() as db:
        log = (ws.job_path(db, job) / "log.jsonl").read_text(encoding="utf-8")
    failed = [json.loads(line) for line in log.splitlines() if "ch4_factors_failed" in line]
    assert [event["code"] for event in failed] == ["ai_provider"]


def test_factor_checks() -> None:
    sources = ["Producția de vopsele în hala Exemplu."]
    assert factor_issues(GOOD, sources) == []
    assert factor_issues("hala Exemplu: ventilarea halei", sources) == []
    assert factor_issues("consum de 5 ori mai mare", sources) == ["literal_number"]
    assert factor_issues("două schimburi", sources) == ["literal_number"]
    # A common technical acronym passes; a brand the request does not show does not.
    assert factor_issues("echipamentele HVAC: răcirea", sources) == []
    assert factor_issues("motoarele ABB: pornirea", sources) == ["literal_name"]
    assert factor_issues("liniile Atlas Copco: aerul comprimat", sources) == ["literal_name"]
    assert factor_issues(" ".join(["cuvânt"] * 61), sources) == ["length"]


def test_render_reads_each_reviewed_list_and_skips_a_rejected_one(
    tmp_path: Path, live: FakeFactors, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = _job(tmp_path)
    live.extra = []
    _draft(ws, job)
    field = next(field for field in fields(ws, job) if field.key == KEY)
    dataset = to_dataset(parse_necesar_info(FIXTURE))
    seen: list[Mapping[str, str]] = []

    def render(
        *_args: object, texts: Mapping[str, str], **_kwargs: object
    ) -> tuple[None, list[str]]:
        seen.append(texts)
        return None, []

    monkeypatch.setattr(render_writers, "select_checklist", lambda _: SimpleNamespace(file_sha="x"))
    monkeypatch.setattr(render_writers, "parse_necesar_info", lambda _: None)
    monkeypatch.setattr(render_writers, "to_dataset", lambda _: dataset)
    monkeypatch.setattr(render_writers, "render_chapter_four", render)
    monkeypatch.setattr(render_writers, "write_sentence_record", lambda *_: None)

    def write(job_fields: list[Field]) -> Mapping[str, str]:
        render_writers.write_four(
            tmp_path / "in.docx",
            tmp_path / "out.docx",
            ws=SimpleNamespace(file_path=lambda *_: FIXTURE),  # type: ignore[arg-type]
            client="synthetic",
            dossier=[],
            job_fields=job_fields,
            identity=("Forbidden Base SRL",),
            chart_source=tmp_path / "base.docx",
            client_name="Synthetic SRL",
            charts_skipped=[],
        )
        return seen[-1]

    assert write(fields(ws, job))["ch4.factors.electricitate"] == str(field.value)
    decide(ws, job, field.id, "reject", field.revision, "user")
    assert "ch4.factors.electricitate" not in write(fields(ws, job))
