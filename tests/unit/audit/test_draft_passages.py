"""Draft v2 over passage facts: one paragraph per passage, every sentence cites, no filler."""

from datetime import UTC, datetime
from pathlib import Path

from tests.audit_replay import draft_recording, support_recording
from tests.unit.audit.test_draft_structured import DraftProvider, SupportProvider
from tests.workspace_jobs import create_job

from ema.audit.draft_agent import (
    INSTRUCTIONS,
    LENGTH_RULE,
    SENTENCE_RULE,
    draft_section_replay,
    draft_section_run,
    recorded_facts,
)
from ema.audit.draft_render import draft_blocks
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.core.llm.models import default_model
from ema.core.office.blocks import Paragraph
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, Manual
from ema.core.workspace import Workspace

SECTION = "ch3.process"
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
        paragraph(
            "Etapa următoare: {{f:audit.process_sections.2}} {{f:audit.process_sections.3}}",
            "audit.process_sections.2",
            "audit.process_sections.3",
        ),
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


def test_the_task_asks_for_cited_sentences_and_length_by_facts() -> None:
    assert SENTENCE_RULE in INSTRUCTIONS and LENGTH_RULE in INSTRUCTIONS
    assert "3–6" not in INSTRUCTIONS
    assert "nu scrie propoziţii fără fapt" in SENTENCE_RULE
    assert "un paragraf pentru fiecare subiect" in LENGTH_RULE


def test_a_multi_paragraph_draft_over_numbered_passages_is_accepted(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = passage_job(ws)
    provider, accepted = run(ws, job, [DRAFT])

    assert accepted == DRAFT
    (request,) = provider.requests
    assert SENTENCE_RULE in request["task"] and LENGTH_RULE in request["task"]
    assert {item["key"]: item["value"] for item in request["facts"]} == PASSAGES
    blocks = draft_blocks(accepted, recorded_facts(ws, job, SECTION), ())
    assert [block.segments for block in blocks if isinstance(block, Paragraph)] == [
        [PASSAGES["audit.process_sections"]],
        [
            "Etapa următoare: "
            + PASSAGES["audit.process_sections.2"]
            + " "
            + PASSAGES["audit.process_sections.3"]
        ],
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
    ] == [("uncited_sentence", SENTENCE_RULE, "paragraph:0", "Procesul este modern şi eficient.")]


def test_replay_reproduces_the_passage_draft_offline(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = passage_job(ws)
    drafts = draft_recording(ws, job, DRAFT, tmp_path / "draft.json")
    support = support_recording(ws, job, DRAFT, tmp_path / "support.json", None)

    _, accepted, check, flags = draft_section_replay(ws, job, SECTION, drafts, support)

    assert accepted == DRAFT
    assert (check.fatal, flags) == ((), ())
    # Each passage ends a sentence: one in the first paragraph, two in the second.
    assert check.total_sentences == 3
