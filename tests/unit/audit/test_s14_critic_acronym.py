"""All-caps client names need the same fact-token boundary as title-case names."""

from tests.unit.audit.test_draft_checks import _fact

from ema.audit.draft_checks import check_draft
from ema.audit.draft_schema import DraftText, SectionDraft

FACTS = {
    "audit.company_name": _fact("audit.company_name", "ACME"),
    "audit.employees": _fact("audit.employees", 85, "number"),
}


def _names(text: str, ids: list[str]) -> list[str]:
    draft = SectionDraft(
        section="ch2.date_generale",
        status="drafted",
        paragraphs=[DraftText(text=text, fact_ids=ids)],
    )
    return [
        issue.detail
        for issue in check_draft(draft, FACTS, "synthetic").fatal
        if issue.code == "literal_name"
    ]


def test_an_acronym_client_name_outside_its_token_is_rejected() -> None:
    assert _names("ACME operează aici.", []) == ["ACME"]
    assert _names(
        "Firma ACME are personal propriu {{c:audit.employees}}.", ["audit.employees"]
    ) == ["ACME"]


def test_an_acronym_no_fact_holds_is_left_to_the_support_pass() -> None:
    # #143 D2: an uncited sentence fails only on a name the section's facts hold.
    assert _names("ELNOR livrează energie.", []) == []
    assert _names("Firma ELNOR are personal {{c:audit.employees}}.", ["audit.employees"]) == [
        "ELNOR"
    ]
