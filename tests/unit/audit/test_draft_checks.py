"""Draft trust boundary: references, missing facts and names (rendering: test_section_body)."""

import pytest

from ema.audit.draft_checks import check_draft
from ema.audit.draft_schema import DraftFigure, DraftTable, DraftText, SectionDraft
from ema.core.review.models import Field


def unrendered_items(draft: SectionDraft) -> tuple[str, ...]:
    return tuple(
        [
            f"table:{index}: not rendered yet; S8 table slots required"
            for index in range(len(draft.tables))
        ]
        + [
            f"figure:{index}: not rendered yet; S8 figure slots required"
            for index in range(len(draft.figures))
        ]
    )


def _fact(key: str, value: str | int, kind: str = "text") -> Field:
    return Field(
        id=key,
        job_id="synthetic",
        key=key,
        label=key,
        value_type=kind,
        value=value,
        state="supplied",
        presence="found",
        evidence=["synthetic-evidence"],
    )


def _draft(text: str, ids: list[str], section: str = "ch2.date_generale") -> SectionDraft:
    return SectionDraft(
        section=section,
        status="drafted",
        paragraphs=[DraftText(text=text, fact_ids=ids)],
    )


def test_rejects_literal_number_name_ai_and_unknown_fact() -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    for text, ids, code in (
        (
            "Societatea {{f:audit.company_name}} are 500 angajați.",
            ["audit.company_name"],
            "literal_number",
        ),
        ("Societatea Inventata are sediul aici.", [], "literal_name"),
        (
            "Societatea {{f:audit.company_name}} folosește un algoritm AI.",
            ["audit.company_name"],
            "ai_mention",
        ),
        ("Societatea {{f:audit.cui}} este aici.", ["audit.cui"], "fact_missing"),
    ):
        assert code in {
            issue.code for issue in check_draft(_draft(text, ids), facts, "synthetic").fatal
        }


def test_sentence_start_after_a_sentence_fact_is_not_a_name() -> None:
    facts = {
        "audit.company_name": _fact("audit.company_name", "Atelier Exemplu"),
        "audit.business_activity": _fact("audit.business_activity", "Produce piese turnate."),
    }
    names = {
        issue.detail
        for issue in check_draft(
            _draft(
                "Dotările sunt noi. {{f:audit.business_activity}} Aceste etape sunt continue. "
                "Societatea {{f:audit.company_name}} Inventata are sediul aici.",
                ["audit.business_activity", "audit.company_name"],
            ),
            facts,
            "synthetic",
        ).fatal
        if issue.code == "literal_name"
    }
    assert names == {"Inventata"}


@pytest.mark.parametrize(
    ("value", "text", "names"),
    [
        ("„Produce piese.”  ", "{{f:audit.business_activity}} Aceste etape continuă.", set()),
        ("Produce piese.", "{{f:audit.business_activity}}Aceste etape continuă.", set()),
        ("Produce piese.", "{{f:audit.business_activity}}  Aceste etape continuă.", set()),
        ("Produce piese.", "{{f:audit.business_activity}} ACME are sediul aici.", {"ACME"}),
        (
            "piese turnate",
            "Societatea produce {{f:audit.business_activity}} Inventata.",
            {"Inventata"},
        ),
        (
            "piese",
            "Producţia include {{f:audit.business_activity}} şi Aceştia Inventati.",
            {"Aceştia Inventati"},
        ),
        ("Produce piese.", "{{f:audit.business_activity}} ANRE avizează. CUI și CAEN apar.", set()),
    ],
)
def test_name_rule_at_fact_boundaries(value: str, text: str, names: set[str]) -> None:
    facts = {"audit.business_activity": _fact("audit.business_activity", value)}
    found = {
        (issue.code, issue.detail)
        for issue in check_draft(
            _draft(text, ["audit.business_activity"], "ch2.activitate"), facts, "synthetic"
        ).fatal
        if issue.code == "literal_name"
    }
    assert found == {("literal_name", name) for name in names}


def test_an_uncited_body_sentence_is_fatal_filler() -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    draft = _draft(
        "Societatea {{f:audit.company_name}} produce bunuri. Este modernă.", ["audit.company_name"]
    )
    checked = check_draft(draft, facts, "synthetic")
    assert checked.coverage == 0.5
    assert [(issue.code, issue.location, issue.detail) for issue in checked.fatal] == [
        ("uncited_sentence", "paragraph:0", "Este modernă.")
    ]
    assert checked.review == ()


@pytest.mark.parametrize(
    "text",
    [
        "Sediul este pe str. {{f:audit.company_name}}.",
        "Clădirea de la nr. {{f:audit.company_name}} este în jud. {{f:audit.company_name}}.",
    ],
)
def test_an_abbreviation_does_not_end_a_sentence(text: str) -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    checked = check_draft(_draft(text, ["audit.company_name"]), facts, "synthetic")
    assert (checked.cited_sentences, checked.total_sentences, checked.fatal) == (1, 1, ())


def test_an_uncited_cell_is_reviewed_not_fatal() -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    cited = DraftText(text="{{f:audit.company_name}}", fact_ids=["audit.company_name"])
    table = DraftTable(caption=cited, rows=[[DraftText(text="Denumire"), cited]])
    draft = SectionDraft(section="ch2.date_generale", status="drafted", tables=[table])
    checked = check_draft(draft, facts, "synthetic")
    assert checked.fatal == ()
    assert [(issue.code, issue.location) for issue in checked.review] == [
        ("uncited_sentence", "table:0:0:0")
    ]


def test_a_numbered_passage_is_a_fact_of_its_section() -> None:
    passage = "Etapa de vopsire începe cu degresarea pieselor."
    facts = {
        key: _fact(key, passage)
        for key in ("audit.process_sections", "audit.process_sections.2", "audit.history.2")
    }
    ok = SectionDraft(
        section="ch3.process",
        status="drafted",
        paragraphs=[
            DraftText(text=f"{{{{f:{key}}}}}", fact_ids=[key])
            for key in ("audit.process_sections", "audit.process_sections.2")
        ],
    )
    assert check_draft(ok, facts, "synthetic").fatal == ()
    foreign = _draft("{{f:audit.history.2}}", ["audit.history.2"], "ch3.process")
    assert [issue.code for issue in check_draft(foreign, facts, "synthetic").fatal] == [
        "fact_missing"
    ]


def test_nonrenderable_items_are_reviewed() -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    rich = SectionDraft(
        section="ch2.date_generale",
        status="drafted",
        tables=[
            DraftTable(
                caption=DraftText(
                    text="Date despre {{f:audit.company_name}}.", fact_ids=["audit.company_name"]
                ),
                rows=[
                    [DraftText(text="{{f:audit.company_name}}", fact_ids=["audit.company_name"])]
                ],
            )
        ],
        figures=[
            DraftFigure(
                fact_id="audit.company_name",
                caption=DraftText(text="{{f:audit.company_name}}", fact_ids=["audit.company_name"]),
            )
        ],
    )
    assert not check_draft(rich, facts, "synthetic").fatal
    assert {item.code for item in check_draft(rich, facts, "synthetic").review} == {
        "unrendered_figure",
    }
    assert len(unrendered_items(rich)) == 2
