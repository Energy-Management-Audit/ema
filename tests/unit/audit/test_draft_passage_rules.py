"""Draft checks over passages: sentence ends, uncited text, support and sentence rendering."""

import json
from pathlib import Path
from typing import Any, Literal

import pytest
from tests.audit_replay import audit_job_with_facts
from tests.unit.audit.test_draft_checks import _draft, _fact
from tests.unit.audit.test_draft_passages import PASSAGES
from tests.unit.audit.test_draft_structured import DraftProvider

from ema.audit.draft_agent import draft_section_run
from ema.audit.draft_checks import DraftReview, check_draft
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
    checked = check_draft(draft, facts, "synthetic")
    assert (checked.fatal, checked.cited_sentences, checked.total_sentences) == ((), 1, 2)


@pytest.mark.parametrize("kind", ["body", "bullet"])
def test_an_uncited_paragraph_of_either_kind_passes(kind: Kind) -> None:
    # #143 D2: uncited_sentence is gone; the support pass judges general text instead.
    draft = section(
        text(
            "Piesele sunt degresate şi clătite {{c:audit.process_sections}}.",
            "audit.process_sections",
        ),
        text("Etapele procesului", kind=kind),
    )
    checked = check_draft(draft, FACTS, "synthetic")
    assert (checked.fatal, checked.review) == ((), ())


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


CH2 = "ch2.date_generale"


def test_a_value_only_paragraph_is_not_checked_or_flagged(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    lead_in = "Societatea {{f:audit.company_name}} produce ambalaje."
    draft = SectionDraft(
        section=CH2,
        status="drafted",
        paragraphs=[
            text("{{f:audit.company_name}}", "audit.company_name"),
            text(lead_in, "audit.company_name"),
        ],
    )
    verdicts = [
        {
            "location": f"{CH2}:paragraph:{index}",
            "sentence_index": 0,
            "kind": "client",
            "supported": False,
        }
        for index in (0, 1)
    ]
    support = Support(json.dumps({"verdicts": verdicts}))
    _, _, _, flags = draft_section_run(
        ws,
        job,
        CH2,
        DraftProvider([draft]),
        support,
        model_id=default_model("openai").id,
        synthetic=True,
    )
    assert [item["location"] for item in support.requests[0]] == [f"{CH2}:paragraph:1"]
    assert [(flag.location, flag.sentence) for flag in flags] == [("paragraph:1", lead_in)]


def test_a_section_of_values_only_needs_no_support_call(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    draft = SectionDraft(
        section=CH2,
        status="drafted",
        paragraphs=[text("{{f:audit.company_name}}", "audit.company_name")],
    )
    support = Support('{"verdicts": []}')
    _, _, _, flags = draft_section_run(
        ws,
        job,
        CH2,
        DraftProvider([draft]),
        support,
        model_id=default_model("openai").id,
        synthetic=True,
    )
    assert (support.requests, flags) == ([], ())


@pytest.mark.parametrize(
    "flag",
    [
        "Uscarea urmează în cuptor {{c:audit.equipment}}",
        "{{f:audit.company_name}} Uscarea urmează în cuptor {{c:audit.equipment}}",
    ],
)
def test_a_flag_on_the_next_sentence_keeps_the_value_and_leaves_no_marker(flag: str) -> None:
    facts = FACTS | {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu.")}
    draft = section(
        text(
            "{{f:audit.company_name}} Uscarea urmează în cuptor {{c:audit.equipment}}.",
            "audit.company_name",
            "audit.equipment",
        )
    )
    issues = (DraftReview("unsupported", "paragraph:0", "claim", flag),)
    (block,) = draft_blocks(draft, facts, issues)
    assert isinstance(block, Paragraph)
    assert block.segments == ["Atelier Exemplu."]
