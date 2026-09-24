"""A cited fact must belong to the job being drafted."""

from ema.audit.draft_checks import check_draft
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.core.review.models import Field


def test_foreign_job_fact_is_rejected() -> None:
    fact = Field(
        id="foreign",
        job_id="another-job",
        key="audit.company_name",
        label="Company",
        value_type="text",
        value="Atelier Exemplu",
        state="supplied",
        presence="found",
        evidence=["synthetic-evidence"],
    )
    draft = SectionDraft(
        section="ch2.date_generale",
        status="drafted",
        paragraphs=[
            DraftText(text="Societatea {{f:audit.company_name}}.", fact_ids=["audit.company_name"])
        ],
    )
    assert check_draft(draft, {fact.key: fact}, "synthetic").fatal
