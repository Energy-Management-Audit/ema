"""Draft trust boundary: references, missing facts and names (rendering: test_section_body)."""

from ema.audit.draft_checks import check_draft
from ema.audit.draft_render import unrendered_items
from ema.audit.draft_schema import DraftFigure, DraftTable, DraftText, SectionDraft
from ema.core.review.models import Field


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


def _draft(text: str, ids: list[str]) -> SectionDraft:
    return SectionDraft(
        section="ch2.date_generale",
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


def test_uncited_and_nonrenderable_items_are_reviewed() -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    draft = _draft(
        "Societatea {{f:audit.company_name}} produce bunuri. Este modernă.", ["audit.company_name"]
    )
    checked = check_draft(draft, facts, "synthetic")
    assert checked.coverage == 0.5
    assert [issue.code for issue in checked.review] == ["uncited_sentence"]
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
