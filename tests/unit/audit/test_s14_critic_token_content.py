"""Fact substitution must not bypass deliverable language checks."""

from ema.audit.draft_checks import check_draft
from ema.audit.draft_render import _resolved
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.core.review.models import Field


def test_ai_disclaimer_from_fact_token_is_rejected() -> None:
    fact = Field(
        id="synthetic",
        job_id="synthetic",
        key="audit.company_name",
        label="Company",
        value_type="text",
        value="Atelier Exemplu (generat automat de AI)",
        state="supplied",
        presence="found",
        evidence=["synthetic-evidence"],
    )
    draft = SectionDraft(
        section="ch2.date_generale",
        status="drafted",
        paragraphs=[
            DraftText(
                text="Societatea {{f:audit.company_name}}.",
                fact_ids=["audit.company_name"],
            )
        ],
    )
    facts = {fact.key: fact}
    assert "AI" in _resolved(draft.paragraphs[0].text, facts)
    assert any(issue.code == "ai_mention" for issue in check_draft(draft, facts, "synthetic").fatal)
