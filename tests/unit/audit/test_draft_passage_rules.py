"""Draft checks over passages: sentence ends, labels, layout, support and sentence rendering."""

import json
from pathlib import Path
from typing import Any, Literal

import pytest
from tests.unit.audit.test_draft_checks import _draft, _fact
from tests.unit.audit.test_draft_passages import PASSAGES, passage_job
from tests.unit.audit.test_draft_structured import DraftProvider

from ema.audit.base_anchor import MARKER
from ema.audit.draft_agent import draft_section_run
from ema.audit.draft_checks import DraftReview, check_draft
from ema.audit.draft_prompt import rule_text
from ema.audit.draft_render import draft_blocks
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.core.llm.models import default_model
from ema.core.llm.types import Exchange
from ema.core.office.blocks import Paragraph
from ema.core.workspace import Workspace

# Passages from no flow scheme or Fişa block are the overview, which ch3.flux describes (D3).
SECTION = "ch3.flux"
FACTS = {key: _fact(key, value) for key, value in PASSAGES.items()} | {
    "audit.equipment": _fact("audit.equipment", "cuptor de polimerizare")
}


Kind = Literal["body", "bullet"]


def text(value: str, *keys: str, kind: Kind = "body") -> DraftText:
    return DraftText(text=value, fact_ids=list(keys), kind=kind)


def section(*paragraphs: DraftText) -> SectionDraft:
    return SectionDraft(section=SECTION, status="drafted", paragraphs=list(paragraphs))


@pytest.mark.parametrize("name", ["Firma Exemplu S.R.L.", "Exemplu S.A.", "Hala de la nr."])
def test_a_value_ending_on_an_abbreviation_does_not_end_the_sentence(name: str) -> None:
    facts = {"audit.company_name": _fact("audit.company_name", name)}
    draft = _draft("Societatea {{f:audit.company_name}} produce piese.", ["audit.company_name"])
    checked = check_draft(draft, facts, "synthetic")
    assert (checked.fatal, checked.cited_sentences, checked.total_sentences) == ((), 1, 1)


def test_a_value_ending_a_sentence_still_ends_one() -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu.")}
    draft = _draft("{{f:audit.company_name}} Produce piese.", ["audit.company_name"])
    fatal = check_draft(draft, facts, "synthetic").fatal
    assert [(issue.code, issue.detail) for issue in fatal] == [
        ("uncited_sentence", "Produce piese.")
    ]


@pytest.mark.parametrize(("kind", "fatal"), [("body", True), ("bullet", False)])
def test_only_an_uncited_body_paragraph_is_fatal(kind: Kind, fatal: bool) -> None:
    draft = section(
        text("{{f:audit.process_sections}}", "audit.process_sections"),
        text("Etapele procesului", kind=kind),
    )
    checked = check_draft(draft, FACTS, "synthetic")
    issues = checked.fatal if fatal else checked.review
    assert [(issue.code, issue.location) for issue in issues] == [
        ("uncited_sentence", "paragraph:1")
    ]
    assert (checked.review if fatal else checked.fatal) == ()


def test_two_passages_in_one_body_paragraph_are_fatal() -> None:
    draft = section(
        text(
            "{{f:audit.process_sections}} {{f:audit.process_sections.2}}",
            "audit.process_sections",
            "audit.process_sections.2",
        )
    )
    fatal = check_draft(draft, FACTS, "synthetic").fatal
    assert [(issue.code, issue.location, issue.detail) for issue in fatal] == [
        ("passage_paragraph", "paragraph:0", "audit.process_sections, audit.process_sections.2")
    ]


def test_passages_out_of_source_order_are_fatal() -> None:
    draft = section(
        text("{{f:audit.process_sections.2}}", "audit.process_sections.2"),
        text("{{f:audit.process_sections}}", "audit.process_sections"),
        text("{{f:audit.process_sections.3}}", "audit.process_sections.3"),
    )
    fatal = check_draft(draft, FACTS, "synthetic").fatal
    assert [(issue.code, issue.location, issue.detail) for issue in fatal] == [
        ("passage_order", "paragraph:1", "audit.process_sections")
    ]


def test_a_misplaced_passage_goes_back_with_the_passage_rule(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = passage_job(ws)
    ordered = section(
        text("{{f:audit.process_sections}}", "audit.process_sections"),
        text("{{f:audit.process_sections.2}}", "audit.process_sections.2"),
    )
    reversed_ = section(*reversed(ordered.paragraphs))
    provider = DraftProvider([reversed_, ordered])
    _, accepted, _, _ = draft_section_run(
        ws,
        job,
        SECTION,
        provider,
        Support("{}"),
        model_id=default_model("openai").id,
        synthetic=True,
    )
    assert accepted == ordered
    assert [(error["rule"], error["rule_text"]) for error in provider.requests[1]["errors"]] == [
        ("passage_order", rule_text("passage_order"))
    ]
    assert "în ordinea numerelor" in rule_text("passage_order")


@pytest.mark.parametrize(
    ("key", "valid"), [("audit.process_sections.2", True), ("audit.history.2", False)]
)
def test_a_numbered_key_may_be_listed_missing(key: str, valid: bool) -> None:
    draft = SectionDraft(section=SECTION, status="missing", missing_fact_ids=[key])
    fatal = check_draft(draft, {}, "synthetic").fatal
    assert [issue.code for issue in fatal] == ([] if valid else ["missing_status_invalid"])


class Support:
    name = "openai"

    def __init__(self, flags: str) -> None:
        self.flags = flags
        self.requests: list[Any] = []

    def respond(self, *args: Any, **kwargs: Any) -> Exchange:
        self.requests.append(json.loads(args[1][1]["content"]))
        return Exchange(self.flags, (), 1, 1)


def test_a_passage_only_paragraph_is_not_checked_or_flagged(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = passage_job(ws)
    draft = section(
        text("{{f:audit.process_sections}}", "audit.process_sections"),
        text("Etapa următoare: {{f:audit.process_sections.2}}", "audit.process_sections.2"),
    )
    lead_in = "Etapa următoare: {{f:audit.process_sections.2}}"
    verdicts = [
        {"location": f"{SECTION}:paragraph:0", "sentence_index": 0, "supported": False},
        {"location": f"{SECTION}:paragraph:1", "sentence_index": 0, "supported": False},
    ]
    support = Support(json.dumps({"verdicts": verdicts}))
    _, _, _, flags = draft_section_run(
        ws,
        job,
        SECTION,
        DraftProvider([draft]),
        support,
        model_id=default_model("openai").id,
        synthetic=True,
    )
    assert [item["location"] for item in support.requests[0]] == [f"{SECTION}:paragraph:1"]
    assert [(flag.location, flag.sentence) for flag in flags] == [("paragraph:1", lead_in)]


def test_a_section_of_passages_only_needs_no_support_call(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = passage_job(ws)
    draft = section(text("{{f:audit.process_sections}}", "audit.process_sections"))
    support = Support('{"verdicts": []}')
    _, _, _, flags = draft_section_run(
        ws,
        job,
        SECTION,
        DraftProvider([draft]),
        support,
        model_id=default_model("openai").id,
        synthetic=True,
    )
    assert (support.requests, flags) == ([], ())


@pytest.mark.parametrize(
    "flag",
    [
        "Uscarea urmează în {{f:audit.equipment}}",
        "{{f:audit.process_sections}} Uscarea urmează în {{f:audit.equipment}}",
    ],
)
def test_a_flag_on_the_next_sentence_keeps_the_passage(flag: str) -> None:
    draft = section(
        text(
            "{{f:audit.process_sections}} Uscarea urmează în {{f:audit.equipment}}.",
            "audit.process_sections",
            "audit.equipment",
        )
    )
    issues = (DraftReview("unsupported", "paragraph:0", "claim", flag),)
    (block,) = draft_blocks(draft, FACTS, issues)
    assert isinstance(block, Paragraph)
    assert block.segments == [f"{PASSAGES['audit.process_sections']} {MARKER}"]
