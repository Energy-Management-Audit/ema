"""All-caps client names need the same fact-token boundary as title-case names."""

from ema.audit.draft_checks import check_draft
from ema.audit.draft_schema import DraftText, SectionDraft


def test_unreferenced_acronym_client_name_is_rejected() -> None:
    draft = SectionDraft(
        section="ch2.date_generale",
        status="drafted",
        paragraphs=[DraftText(text="ACME operează aici.")],
    )
    assert any(issue.code == "literal_name" for issue in check_draft(draft, {}, "synthetic").fatal)
