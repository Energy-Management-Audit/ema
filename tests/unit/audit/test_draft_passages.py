"""Draft over passage facts: one paragraph per passage, every sentence cites, no filler."""

from datetime import UTC, datetime
from pathlib import Path

from tests.audit_replay import draft_recording, support_recording
from tests.unit.audit.test_draft_structured import DraftProvider, SupportProvider
from tests.workspace_jobs import create_job

from ema.audit.draft_agent import draft_section_replay, draft_section_run, recorded_facts
from ema.audit.draft_prompt import PROMPT_VERSION, instructions, rule_text
from ema.audit.draft_render import draft_blocks
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.core.llm.models import default_model
from ema.core.office.blocks import Paragraph
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, Manual
from ema.core.workspace import Workspace

# Passages from no flow scheme or Fişa block are the overview, which ch3.flux describes (D3).
SECTION = "ch3.flux"
PASSAGES = {
    "audit.process_sections": "Piesele sunt degresate într-o baie alcalină şi clătite.",
    "audit.process_sections.2": "Piesele uscate trec în cabina de vopsire electrostatică.",
    "audit.process_sections.3": "Vopseaua se polimerizează în cuptorul încălzit cu gaz.",
}


def paragraph(text: str, *keys: str) -> DraftText:
    return DraftText(text=text, fact_ids=list(keys))


DRAFT = SectionDraft(
    section=SECTION,
    status="drafted",
    paragraphs=[
        paragraph("{{f:audit.process_sections}}", "audit.process_sections"),
        paragraph("Etapa următoare: {{f:audit.process_sections.2}}", "audit.process_sections.2"),
        paragraph("{{f:audit.process_sections.3}}", "audit.process_sections.3"),
    ],
)


def passage_job(ws: Workspace) -> str:
    job = create_job(ws, "audit", "synthetic", 2026)
    for key, value in PASSAGES.items():
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


def run(ws: Workspace, job: str, drafts: list[SectionDraft]) -> tuple[DraftProvider, SectionDraft]:
    provider = DraftProvider(drafts)
    _, accepted, check, _ = draft_section_run(
        ws,
        job,
        SECTION,
        provider,
        SupportProvider(),
        model_id=default_model("openai").id,
        synthetic=True,
    )
    assert check.fatal == () and check.cited_sentences == check.total_sentences
    return provider, accepted


def test_the_prompt_asks_for_cited_sentences_her_register_and_length_by_target() -> None:
    prompt = instructions()
    assert "Nu scrie introduceri, generalități sau concluzii fără fapt" in rule_text(
        "uncited_sentence"
    )
    assert "câte un pasaj pe paragraf, în ordinea numerelor" in rule_text("passage_order")
    assert "diacritice corecte (ă, â, î, ș, ț)" in prompt
    assert 'kind "bullet"' in prompt and "niciun tabel" in prompt
    assert "ținta de cuvinte a secțiunii" in prompt
    assert "Transformatoarele (audit.transformer.*)" in prompt
    assert "nu alegi și nu împaci valorile" in prompt
    assert "Nu repeți o cantitate pe care o arată un tabel al capitolului" in prompt


def test_the_prompt_version_keys_recordings_of_this_task() -> None:
    # Recordings are keyed by version: one made for an earlier prompt is never replayed.
    assert PROMPT_VERSION == "audit-draft-v4"


def test_a_multi_paragraph_draft_over_numbered_passages_is_accepted(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = passage_job(ws)
    provider, accepted = run(ws, job, [DRAFT])

    assert accepted == DRAFT
    (request,) = provider.requests
    (asked,) = request["sections"]
    assert {item["key"]: item["text"] for item in asked["facts"]} == PASSAGES
    blocks = draft_blocks(accepted, recorded_facts(ws, job, SECTION), ())
    assert [block.segments for block in blocks if isinstance(block, Paragraph)] == [
        [PASSAGES["audit.process_sections"]],
        ["Etapa următoare: " + PASSAGES["audit.process_sections.2"]],
        [PASSAGES["audit.process_sections.3"]],
    ]


def test_filler_goes_back_once_with_the_sentence_rule(tmp_path: Path) -> None:
    padded = DRAFT.model_copy(
        update={
            "paragraphs": [
                paragraph(
                    "{{f:audit.process_sections}} Procesul este modern şi eficient.",
                    "audit.process_sections",
                ),
                *DRAFT.paragraphs[1:],
            ]
        }
    )

    ws = Workspace(tmp_path / "ws")
    provider, accepted = run(ws, passage_job(ws), [padded, DRAFT])

    assert accepted == DRAFT
    assert [
        (error["rule"], error["rule_text"], error["location"], error["detail"])
        for error in provider.requests[1]["errors"]
    ] == [
        (
            "uncited_sentence",
            rule_text("uncited_sentence"),
            "paragraph:0",
            "Procesul este modern şi eficient.",
        )
    ]


def test_replay_reproduces_the_passage_draft_offline(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = passage_job(ws)
    drafts = draft_recording(ws, job, DRAFT, tmp_path / "draft.json")
    support = support_recording(ws, job, DRAFT, tmp_path / "support.json", None)

    _, accepted, check, flags = draft_section_replay(ws, job, SECTION, drafts, support)

    assert accepted == DRAFT
    assert (check.fatal, flags) == ((), ())
    # One passage a paragraph, and each ends its sentence.
    assert check.total_sentences == 3
