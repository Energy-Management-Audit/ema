"""A chapter call (D2): several sections in one answer, one retry, passages used once, units (D3)
and length targets (D8)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.unit.audit.test_draft_checks import _fact
from tests.unit.audit.test_draft_structured import DraftProvider, SupportProvider
from tests.workspace_jobs import create_job

from ema.audit import draft_chapter
from ema.audit.draft_agent import chapter_groups
from ema.audit.draft_chapter import Passes, run_group, unit_issues
from ema.audit.draft_plan import (
    MAX_OUTPUT_TOKENS,
    THINKING_TOKENS,
    Group,
    SectionPlan,
    allowance,
    offered,
    plan_section,
    split,
)
from ema.audit.draft_prompt import Used
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.draft_style import Example
from ema.core.llm.models import default_model
from ema.core.llm.types import Exchange
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, Manual
from ema.core.workspace import Workspace

EQUIPMENT = "Linia are un cuptor de polimerizare şi o cabină de vopsire."
FLUX, CONSUMERS = "ch3.flux", "ch3.consumatori"


def _job(ws: Workspace, facts: dict[str, str]) -> str:
    job = create_job(ws, "audit", "synthetic", 2026)
    for key, value in facts.items():
        evidence = Evidence(
            id="synthetic:" + key,
            provenance="manual",
            locator=Manual(who="synthetic"),
            method="manual",
            retrieved_at=datetime.now(UTC),
            highlight="exact",
        )
        propose(ws, job, key, value, [evidence], state="supplied")
    return job


def _draft(section: str, text: str, *keys: str) -> SectionDraft:
    return SectionDraft(
        section=section, status="drafted", paragraphs=[DraftText(text=text, fact_ids=list(keys))]
    )


def _run(
    tmp_path: Path,
    sections: list[str],
    answers: list[object],
    provider: DraftProvider | None = None,
) -> tuple[DraftProvider, SupportProvider, Used, object, Workspace, str]:
    ws = Workspace(tmp_path / "ws")
    job = _job(ws, {"audit.equipment": EQUIPMENT, "audit.process_sections": "Piesele se spală."})
    (group,), units = chapter_groups(ws, job, sections)
    provider, support, used = provider or DraftProvider(answers), SupportProvider(), Used()  # type: ignore[arg-type]
    passes = Passes(provider, support, default_model("openai").id, synthetic=True)
    result = run_group(ws, job, group, passes, used, units)
    return provider, support, used, result, ws, job


QUOTED = _draft(FLUX, "{{f:audit.equipment}}", "audit.equipment")
FLOW = _draft(FLUX, "{{f:audit.process_sections}}", "audit.process_sections")
PARAPHRASED = _draft(
    CONSUMERS,
    "Consumatorii principali sunt utilajele liniei {{c:audit.equipment}}.",
    "audit.equipment",
)


def test_one_call_drafts_two_sections(tmp_path: Path) -> None:
    provider, support, used, result, _, _ = _run(tmp_path, [FLUX, CONSUMERS], [[FLOW, PARAPHRASED]])
    assert [item["section"] for item in provider.requests[0]["sections"]] == [FLUX, CONSUMERS]
    assert set(result.drafted) == {FLUX, CONSUMERS}  # type: ignore[attr-defined]
    assert (len(provider.requests), support.calls) == (1, 1)
    # A paraphrased passage is used as much as a quoted one.
    assert used.passages == {"audit.process_sections", "audit.equipment"}


class TruncatedDraft(DraftProvider):
    def __init__(self) -> None:
        super().__init__([[FLOW, PARAPHRASED]])
        self.thinking: list[int | None] = []

    def respond(self, *args: object, **kwargs: object) -> Exchange:
        self.thinking.append(kwargs.get("thinking_tokens"))  # type: ignore[arg-type]
        if not self.requests:
            self.requests.append(json.loads(args[1][1]["content"]))  # type: ignore[index]
            self.limits.append(args[4])  # type: ignore[arg-type]
            return Exchange('{"sections": [', (), 1, 1, finish_reason="MAX_TOKENS")
        return super().respond(*args, **kwargs)


def test_truncated_chapter_retries_once_with_twice_the_allowance(tmp_path: Path) -> None:
    provider = TruncatedDraft()
    _, _, _, result, _, _ = _run(tmp_path, [FLUX, CONSUMERS], [], provider)
    assert set(result.drafted) == {FLUX, CONSUMERS}  # type: ignore[attr-defined]
    assert 2 * provider.limits[0] < MAX_OUTPUT_TOKENS == 65_536
    assert provider.limits[1] == min(65_536, 2 * provider.limits[0])
    assert provider.thinking == [THINKING_TOKENS, THINKING_TOKENS]
    assert len(provider.requests) == 2


def test_the_truncation_retry_never_asks_past_the_output_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(draft_chapter, "MAX_OUTPUT_TOKENS", 20_000)
    provider = TruncatedDraft()
    _run(tmp_path, [FLUX, CONSUMERS], [], provider)
    assert 2 * provider.limits[0] > 20_000
    assert provider.limits[1] == 20_000


def test_a_passage_used_by_an_earlier_section_goes_back_with_what_is_used(tmp_path: Path) -> None:
    provider, _, _, result, _, _ = _run(
        tmp_path, [FLUX, CONSUMERS], [[QUOTED, PARAPHRASED], PARAPHRASED]
    )
    retry = provider.requests[1]
    assert [item["section"] for item in retry["request"]["sections"]] == [CONSUMERS]
    assert [(error["section"], error["rule"]) for error in retry["errors"]] == [
        (CONSUMERS, "passage_reused")
    ]
    assert retry["request"]["used_passages"] == ["audit.equipment"]
    assert retry["request"]["opening_sentences"] == {FLUX: "{{f:audit.equipment}}"}
    assert result.failed[CONSUMERS].code == "draft_incomplete"  # type: ignore[attr-defined]


def test_two_sections_may_not_paraphrase_one_passage(tmp_path: Path) -> None:
    described = _draft(FLUX, "Linia are utilaje {{c:audit.equipment}}.", "audit.equipment")
    provider, _, used, result, _, _ = _run(
        tmp_path, [FLUX, CONSUMERS], [[described, PARAPHRASED], PARAPHRASED]
    )
    assert [(error["section"], error["rule"]) for error in provider.requests[1]["errors"]] == [
        (CONSUMERS, "passage_reused")
    ]
    assert set(result.drafted) == {FLUX}  # type: ignore[attr-defined]
    assert used.passages == {"audit.equipment"}


def test_unknown_and_duplicate_sections_are_dropped_and_logged(tmp_path: Path) -> None:
    unknown = _draft("ch3.apa", "Apa vine din reţea {{c:audit.equipment}}.", "audit.equipment")
    second = _draft(FLUX, "Fluxul are utilaje {{c:audit.equipment}}.", "audit.equipment")
    answer = json.dumps(
        {
            "sections": [
                FLOW.model_dump(),
                second.model_dump(),
                unknown.model_dump(),
                {"section": CONSUMERS, "status": "drafted"},
            ]
        }
    )
    provider, _, _, result, ws, job = _run(tmp_path, [FLUX, CONSUMERS], [answer, PARAPHRASED])
    assert result.drafted[FLUX].draft == FLOW  # type: ignore[attr-defined]
    assert result.drafted[CONSUMERS].draft == PARAPHRASED  # type: ignore[attr-defined]
    assert [error["rule"] for error in provider.requests[1]["errors"]] == ["omitted"]
    with ws.connect() as db:
        log = (ws.job_path(db, job) / "log.jsonl").read_text(encoding="utf-8")
    (event,) = [json.loads(line) for line in log.splitlines() if "draft_section_dropped" in line]
    assert event["sections"] == [
        {"section": CONSUMERS, "reason": "malformed"},
        {"section": FLUX, "reason": "duplicate"},
        {"section": "ch3.apa", "reason": "unknown"},
    ]


def test_a_section_still_failing_after_the_retry_fails_alone(tmp_path: Path) -> None:
    filler = _draft(CONSUMERS, "Consumatorii sunt diverşi.")
    provider, support, _, result, _, _ = _run(
        tmp_path, [FLUX, CONSUMERS], [[QUOTED, filler], filler]
    )
    assert set(result.drafted) == {FLUX}  # type: ignore[attr-defined]
    assert result.failed[CONSUMERS].code == "draft_incomplete"  # type: ignore[attr-defined]
    # The accepted section only quotes its passage, which claims nothing to support.
    assert (len(provider.requests), support.calls) == (2, 0)


UNITS = {
    "audit.process_sections": None,
    "audit.process_sections.2": 1,
    "audit.process_sections.3": 2,
}
PASSAGES = {key: _fact(key, "etapa") for key in UNITS} | {
    "audit.equipment": _fact("audit.equipment", "x")
}


def test_the_overview_goes_to_the_flux_and_unit_passages_to_the_process() -> None:
    assert set(offered(FLUX, PASSAGES, UNITS)) == {"audit.process_sections", "audit.equipment"}
    process = plan_section("ch3.process", PASSAGES, Example("", 100), UNITS, 3)
    assert set(process.facts) == {
        "audit.process_sections.2",
        "audit.process_sections.3",
        "audit.equipment",
    }
    assert process.units == (
        (1, ("audit.process_sections.2",)),
        (2, ("audit.process_sections.3",)),
        (3, ()),
    )
    # The base's unit text, once for each unit that has passages.
    assert process.target == 200


def test_a_process_paragraph_cites_only_its_own_unit() -> None:
    plan = plan_section("ch3.process", PASSAGES, None, UNITS, 2)
    draft = SectionDraft(
        section="ch3.process",
        status="drafted",
        paragraphs=[
            DraftText(
                text="{{f:audit.process_sections.2}}", fact_ids=["audit.process_sections.2"], unit=1
            ),
            DraftText(
                text="{{f:audit.process_sections.3}}", fact_ids=["audit.process_sections.3"], unit=1
            ),
            DraftText(text="Utilaje {{c:audit.equipment}}.", fact_ids=["audit.equipment"]),
        ],
    )
    assert [(issue.code, issue.location) for issue in unit_issues(draft, plan, UNITS)] == [
        ("unit_passage", "paragraph:1"),
        ("unit_missing", "paragraph:2"),
    ]
    other = _draft(FLUX, "{{f:audit.process_sections}}", "audit.process_sections")
    other.paragraphs[0].unit = 1
    flux = plan_section(FLUX, PASSAGES, None, UNITS)
    assert [issue.code for issue in unit_issues(other, flux, UNITS)] == ["unit_outside"]


def test_the_target_scales_her_own_words_by_the_facts_found() -> None:
    facts = {"audit.water_supply": _fact("audit.water_supply", "reţea")}
    utilities = plan_section("ch3.utilitati", facts, Example("exemplu", 400), {})
    water = plan_section("ch3.apa", facts, Example("exemplu", 120), {})
    assert (utilities.target, water.target) == (100, 120)
    assert plan_section("ch3.apa", facts, None, {}).target is None
    rejected = {
        "audit.water_supply": facts["audit.water_supply"].model_copy(update={"review": "rejected"})
    }
    assert plan_section("ch3.apa", rejected, Example("exemplu", 120), {}).target is None


def test_the_allowance_and_the_split_follow_the_targets() -> None:
    assert allowance([1000]) == 16_000 + int(2.5 * 1000 * 1.3)
    assert allowance([20_000]) == MAX_OUTPUT_TOKENS
    plans = [
        SectionPlan(f"ch3.{name}", {}, words, "")
        for name, words in zip("abcd", (9000, 5000, 6000, 100), strict=True)
    ]
    groups = split(3, plans)
    assert [[plan.section for plan in group.sections] for group in groups] == [
        ["ch3.a", "ch3.b"],
        ["ch3.c", "ch3.d"],
    ]
    assert [group.id for group in groups] == ["3-1", "3-2"]
    assert all(group.allowance < MAX_OUTPUT_TOKENS for group in groups)
    assert [len(group.sections) for group in split(3, [SectionPlan("ch3.a", {}, 30_000, "")])] == [
        1
    ]


def test_her_longest_chapter_plans_as_one_group() -> None:
    # Her longest chapter holds about 10,800 words of targets. One group per chapter keeps a
    # two-chapter job at six logical calls at most: a draft, a retry and a support pass each.
    plans = [SectionPlan(f"ch3.{index}", {}, 1350, "") for index in range(8)]
    assert sum(plan.target or 0 for plan in plans) == 10_800
    (group,) = split(3, plans)
    assert len(group.sections) == 8
    assert group.allowance < MAX_OUTPUT_TOKENS


def test_later_groups_receive_the_passages_earlier_groups_used(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = _job(ws, {"audit.equipment": EQUIPMENT})
    groups, units = chapter_groups(ws, job, [FLUX, CONSUMERS])
    first, second = (Group(f"3-{n}", 3, (plan,)) for n, plan in enumerate(groups[0].sections, 1))
    used = Used()
    described = _draft(FLUX, "Linia are utilaje {{c:audit.equipment}}.", "audit.equipment")
    for group, answer in ((first, described), (second, PARAPHRASED)):
        provider = DraftProvider([answer, answer])
        passes = Passes(provider, SupportProvider(), default_model("openai").id, synthetic=True)
        run_group(ws, job, group, passes, used, units)
    # The earlier group only paraphrased the passage; the later one still receives its key.
    assert provider.requests[0]["used_passages"] == ["audit.equipment"]
    assert provider.requests[0]["opening_sentences"] == {
        FLUX: "Linia are utilaje {{c:audit.equipment}}."
    }
