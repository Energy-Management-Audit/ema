"""Ch. 4 variable factors (#162 D4): one checked call at the end of Draft, from the job's facts,
stored for review with the inputs it was written from."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tests.workspace_jobs import create_job

from ema.audit import draft_live, render_writers
from ema.audit.chapter_four_blocks import chapter_four_blocks
from ema.audit.chapter_four_comments import FACTOR_LEAD
from ema.audit.chapter_four_factors import FORMULA, PROMPT_VERSION, factor_issues
from ema.audit.draft_live import DraftSummary, start_draft
from ema.audit.read import read_dossier
from ema.core.errors import EmaError
from ema.core.jobs import status, subscribe
from ema.core.llm.types import Exchange, ToolSpec
from ema.core.office.blocks import BulletList, Missing, Paragraph
from ema.core.office.missing_text import MISSING_TEXT
from ema.core.review import decide, fields, propose
from ema.core.review.evidence import get_evidence
from ema.core.review.models import Derivation, Evidence, Field, Manual
from ema.core.workspace import Workspace
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.necesar import parse_necesar_info, to_dataset

FIXTURE = Path(__file__).parents[2] / "fixtures/audit/synthetic_necesar.xlsx"
KEY = "narrative.ch4.factors.electricitate"
GOOD = (
    "regimul de lucru și numărul de schimburi: consumul atinge valori maxime în timpul "
    "schimburilor de producție active și scade în afara lor"
)
SEASON = "climatizarea: răcirea spațiilor crește consumul în sezonul cald;"
FACTS = {
    "audit.business_activity": "Producția de piese prin injecție de mase plastice.",
    "audit.work_regime": "Trei schimburi, cinci zile pe săptămână.",
    "audit.process_sections": "Granulele sunt uscate, injectate și răcite în matriță.",
    "audit.equipment": "Mașini de injecție, uscătoare de granule și răcitoare de apă.",
    "audit.electricity_supply": "Alimentarea se face dintr-un post de transformare propriu.",
}
CLIENT_RULE = (
    "Orice afirmație specifică acestui client (schimburile și programul de lucru, "
    "echipamentele, procesele, produsele, sezonalitatea propriei activități) o faci numai pe "
    "baza faptelor din cerere. Ce nu apare în fapte nu atribui clientului: formulezi factorul "
    "la modul general."
)


class FakeFactors:
    """Stands in for the OpenAI adapter: `factors` for every requested resource, or a failure."""

    name = "openai"

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.instructions: list[str] = []
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
        self.instructions.append(str(messages[0]["content"]))
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
    """The synthetic Necesar has electricity only: ch4.electricitate applies, the rest do not.
    It holds none of the facts the factors are written from."""
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    read_dossier(ws, job, FIXTURE)
    return ws, job


def _fact(ws: Workspace, job: str, key: str, value: str) -> None:
    evidence = Evidence(
        id=f"synthetic:{key}:{value}",
        provenance="manual",
        locator=Manual(who="synthetic"),
        method="manual",
        retrieved_at=datetime.now(UTC),
        highlight="exact",
    )
    propose(ws, job, key, value, [evidence], state="supplied")


def _with_facts(tmp_path: Path) -> tuple[Workspace, str]:
    ws, job = _job(tmp_path)
    for key, value in FACTS.items():
        _fact(ws, job, key, value)
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
        if field.key.startswith("narrative.ch4.factors.") and field.value is not None
    }


def _field(ws: Workspace, job: str) -> Field:
    return next(field for field in fields(ws, job) if field.key == KEY)


def _inputs(ws: Workspace, job: str) -> list[str]:
    by_key = {field.key: field for field in fields(ws, job)}
    return sorted(f"{key}@{by_key[key].revision}" for key in FACTS)


def test_draft_sends_the_jobs_facts_and_records_them_with_the_list(
    tmp_path: Path, live: FakeFactors
) -> None:
    ws, job = _with_facts(tmp_path)
    _, run = _draft(ws, job)

    assert run["state"] == "ready"
    assert live.versions == [PROMPT_VERSION] == ["audit-ch4-factors-v2"]
    assert live.requests[0] == {
        "resources": [{"id": "ch4.electricitate", "resource": "energie electrică"}],
        "activity": [FACTS["audit.business_activity"]],
        "work_regime": [FACTS["audit.work_regime"]],
        "processes": [FACTS["audit.process_sections"]],
        "equipment": [FACTS["audit.equipment"]],
        "supply": {"ch4.electricitate": [FACTS["audit.electricity_supply"]]},
    }
    assert CLIENT_RULE in live.instructions[0]
    assert _lists(ws, job) == {KEY: GOOD + "\n" + SEASON.rstrip(";")}
    field = _field(ws, job)
    assert (field.state, field.chapter, field.value_type) == ("enriched", "ch4", "text")
    evidence = get_evidence(ws, field.evidence[0])
    assert evidence.locator.who == "agent"  # type: ignore[union-attr]
    assert evidence.derivation == Derivation(
        formula_id=FORMULA, inputs=_inputs(ws, job), factor_version=PROMPT_VERSION
    )

    _draft(ws, job)
    assert len(live.requests) == 1


def test_without_facts_the_request_goes_out_and_the_prompt_keeps_it_general(
    tmp_path: Path, live: FakeFactors
) -> None:
    ws, job = _job(tmp_path)
    _draft(ws, job)
    assert live.requests == [
        {"resources": [{"id": "ch4.electricitate", "resource": "energie electrică"}]}
    ]
    assert CLIENT_RULE in live.instructions[0]
    evidence = get_evidence(ws, _field(ws, job).evidence[0])
    assert evidence.derivation is not None and evidence.derivation.inputs == []


def _render(
    ws: Workspace, job: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Mapping[str, str]:
    """The texts write_four hands the chapter, with the document engine left out."""
    dataset = to_dataset(parse_necesar_info(FIXTURE))
    seen: list[Mapping[str, str]] = []

    def render(*_args: object, texts: Mapping[str, str], **_kwargs: object) -> tuple[None, list]:
        seen.append(texts)
        return None, []

    monkeypatch.setattr(render_writers, "select_checklist", lambda _: SimpleNamespace(file_sha="x"))
    monkeypatch.setattr(render_writers, "parse_necesar_info", lambda _: None)
    monkeypatch.setattr(render_writers, "to_dataset", lambda _: dataset)
    monkeypatch.setattr(render_writers, "render_chapter_four", render)
    monkeypatch.setattr(render_writers, "write_sentence_record", lambda *_: None)
    monkeypatch.setattr(ws, "file_path", lambda *_: FIXTURE)
    render_writers.write_four(
        tmp_path / "in.docx",
        tmp_path / "out.docx",
        ws=ws,
        client="synthetic",
        dossier=[],
        job_fields=fields(ws, job),
        identity=("Forbidden Base SRL",),
        chart_source=tmp_path / "base.docx",
        client_name="Synthetic SRL",
        charts_skipped=[],
    )
    return seen[-1]


def _printed(texts: Mapping[str, str]) -> object:
    """What follows the electricity factor lead-in in the chapter built from these texts."""
    blocks = chapter_four_blocks(to_dataset(parse_necesar_info(FIXTURE)), FACTORS_2026, texts=texts)
    lead = blocks.index(Paragraph("body", [FACTOR_LEAD["ch4.electricitate"]]))
    return blocks[lead + 1]


def test_a_source_fact_edit_makes_the_list_stale_until_draft_writes_it_again(
    tmp_path: Path, live: FakeFactors, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = _with_facts(tmp_path)
    _draft(ws, job)
    field = _field(ws, job)
    decide(ws, job, field.id, "accept", field.revision, "user")
    assert isinstance(_printed(_render(ws, job, tmp_path, monkeypatch)), BulletList)

    _fact(ws, job, "audit.work_regime", "Două schimburi, cinci zile pe săptămână.")
    texts = _render(ws, job, tmp_path, monkeypatch)
    assert "ch4.factors.electricitate" not in texts
    assert _printed(texts) == Missing("body", MISSING_TEXT)

    # The same words again: the list is proposed anew, with its current inputs, for review.
    _draft(ws, job)
    assert len(live.requests) == 2
    assert live.requests[1]["work_regime"] == ["Două schimburi, cinci zile pe săptămână."]
    refreshed = _field(ws, job)
    assert (refreshed.value, refreshed.review) == (field.value, "pending")
    evidence = get_evidence(ws, refreshed.evidence[0])
    assert evidence.derivation is not None
    assert evidence.derivation.inputs == _inputs(ws, job)
    assert isinstance(_printed(_render(ws, job, tmp_path, monkeypatch)), BulletList)
    _draft(ws, job)
    assert len(live.requests) == 2


def test_a_rejected_list_is_drafted_again(tmp_path: Path, live: FakeFactors) -> None:
    ws, job = _with_facts(tmp_path)
    _draft(ws, job)
    field = _field(ws, job)
    decide(ws, job, field.id, "reject", field.revision, "user")
    live.factors = [SEASON]
    _draft(ws, job)
    assert len(live.requests) == 2
    again = _field(ws, job)
    assert (again.value, again.review) == (SEASON.rstrip(";"), "pending")


def test_a_rejected_list_drafted_in_the_same_words_is_proposed_again(
    tmp_path: Path, live: FakeFactors
) -> None:
    ws, job = _with_facts(tmp_path)
    _draft(ws, job)
    field = _field(ws, job)
    decide(ws, job, field.id, "reject", field.revision, "user")
    _draft(ws, job)
    again = _field(ws, job)
    assert (again.value, again.review) == (field.value, "pending")


def test_accepted_and_corrected_lists_are_kept(tmp_path: Path, live: FakeFactors) -> None:
    ws, job = _with_facts(tmp_path)
    _draft(ws, job)
    field = _field(ws, job)
    decide(ws, job, field.id, "accept", field.revision, "user")
    _draft(ws, job)
    assert len(live.requests) == 1
    field = _field(ws, job)
    decide(ws, job, field.id, "correct", field.revision, "user", value="lista ei")
    _fact(ws, job, "audit.work_regime", "Un schimb.")
    _draft(ws, job)
    assert len(live.requests) == 1
    assert _lists(ws, job) == {KEY: "lista ei"}


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


def test_render_reads_a_current_list_and_skips_a_rejected_one(
    tmp_path: Path, live: FakeFactors, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = _job(tmp_path)
    _draft(ws, job)
    field = _field(ws, job)
    assert _render(ws, job, tmp_path, monkeypatch)["ch4.factors.electricitate"] == field.value
    decide(ws, job, field.id, "reject", field.revision, "user")
    assert "ch4.factors.electricitate" not in _render(ws, job, tmp_path, monkeypatch)
