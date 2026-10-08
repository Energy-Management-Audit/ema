"""Draft over passage facts (prompt v5): each passage rewritten and cited, general sentences
between them, never a passage printed as the source has it."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from tests.audit_replay import draft_recording, support_recording
from tests.unit.audit.test_draft_structured import DraftProvider, SupportProvider
from tests.workspace_jobs import create_job

from ema.audit.draft_agent import draft_section_replay, draft_section_run, recorded_facts
from ema.audit.draft_prompt import PROMPT_VERSION, instructions, rule_text
from ema.audit.draft_render import draft_blocks
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.draft_support import SUPPORT_PROMPT
from ema.core.llm.models import default_model
from ema.core.office.blocks import Paragraph
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, Manual
from ema.core.workspace import Workspace

# Passages from no flow scheme or Fişa block pool in the first 3.1.x unit (#155 D1).
SECTION = "ch3.process"
PASSAGES = {
    "audit.process_sections": "Piesele sunt degresate într-o baie alcalină şi clătite.",
    "audit.process_sections.2": "Piesele uscate trec în cabina de vopsire electrostatică.",
    "audit.process_sections.3": "Vopseaua se polimerizează în cuptorul încălzit cu gaz.",
}


def paragraph(text: str, *keys: str, kind: Literal["body", "bullet"] = "body") -> DraftText:
    return DraftText(text=text, fact_ids=list(keys), kind=kind, unit=1)


INTRO = "Vopsirea în câmp electrostatic asigură o acoperire uniformă a pieselor metalice."
STAGES = (
    "degresarea pieselor într-o baie alcalină, urmată de clătire",
    "vopsirea electrostatică a pieselor uscate",
    "polimerizarea vopselei în cuptorul încălzit cu gaz",
)
DRAFT = SectionDraft(
    section=SECTION,
    status="drafted",
    paragraphs=[
        paragraph(INTRO + " Fluxul tehnologic cuprinde următoarele etape:"),
        *(
            paragraph(f"{stage} {{{{c:{key}}}}};", key, kind="bullet")
            for stage, key in zip(STAGES, PASSAGES, strict=True)
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
    assert check.fatal == ()
    return provider, accepted


@pytest.mark.parametrize(
    ("code", "phrase"),
    [
        # (a) numbers and client data from facts; D3 the one exception.
        ("literal_name", "orice nume propriu al clientului"),
        ("literal_name", "mărcile și modelele echipamentelor, autorizațiile și numerele lor"),
        ("literal_number", "Singura excepție sunt referințele normative"),
        ("literal_number", "Legea nr. 121/2014, SR EN ISO 50001, SR EN 16247"),
        # (d) passages rewritten, never printed whole.
        ("passage_verbatim", "Un pasaj se rescrie întotdeauna în registrul auditorului"),
        ("passage_verbatim", "Un pasaj nu se redă niciodată cu {{f:}}"),
        ("passage_verbatim", "devine elemente de listă"),
        ("passage_reused", "nu se mai folosește în altă secțiune a capitolului"),
    ],
)
def test_each_checked_rule_holds_its_key_phrase(code: str, phrase: str) -> None:
    assert phrase in rule_text(code)


@pytest.mark.parametrize(
    "phrase",
    [
        # (b) a description of the client cites its fact.
        "Când descrii clientul pe baza unui fapt, fără să-i reproduci valoarea, citezi",
        # (c) general sentences, and what they may never do.
        "Propozițiile generale sunt permise și așteptate și nu au citare",
        "ce face o etapă de proces, un tip de echipament sau o utilitate",
        "nu afirmă și nu lasă să se înțeleagă ca fapt nimic despre acest client",
        # (e) length by target, explanation where facts are thin, no repetition.
        "scrii până la ținta de cuvinte a secțiunii",
        "dezvolți cu explicații generale",
        "Nu umpli niciodată prin repetare",
        # (f) general text alone does not make a section.
        "textul general singur nu face o secțiune",
        # v4's register and rules 11-15 stay.
        "diacritice corecte (ă, â, î, ș, ț)",
        "Nu repeți o cantitate pe care o arată un tabel al capitolului",
        "nu alegi și nu împaci valorile",
        "Transformatoarele (audit.transformer.*)",
        "Secțiunea ch3.process descrie unitățile 3.1.x",
        'Status "missing", cu missing_fact_ids',
    ],
)
def test_the_prompt_holds_the_v5_rules(phrase: str) -> None:
    assert phrase in instructions()


def test_v4_strict_prose_rules_are_gone() -> None:
    prompt = instructions()
    assert "Nu scrie introduceri, generalități sau concluzii fără fapt" not in prompt
    assert "Un pasaj se redă întreg" not in prompt
    assert "Când faptele nu ajung, scrii mai scurt" not in prompt


def test_the_support_prompt_judges_client_and_general_sentences() -> None:
    assert '"client"' in SUPPORT_PROMPT and '"general"' in SUPPORT_PROMPT
    assert "states or implies a fact about this client" in SUPPORT_PROMPT


def test_the_prompt_version_keys_recordings_of_this_task() -> None:
    # Recordings are keyed by version: one made for an earlier prompt is never replayed.
    assert PROMPT_VERSION == "audit-draft-v6"


def test_a_multi_paragraph_draft_over_numbered_passages_is_accepted(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = passage_job(ws)
    provider, accepted = run(ws, job, [DRAFT])

    assert accepted == DRAFT
    (request,) = provider.requests
    (asked,) = request["sections"]
    assert {item["key"]: item["text"] for item in asked["facts"]} == PASSAGES
    blocks = draft_blocks(accepted, recorded_facts(ws, job, SECTION), ())
    assert [(block.proto, block.segments) for block in blocks if isinstance(block, Paragraph)] == [
        ("body", [INTRO + " Fluxul tehnologic cuprinde următoarele etape:"]),
        *(("bullet", [stage + ";"]) for stage in STAGES),
    ]


def test_a_verbatim_passage_goes_back_once_with_the_passage_rule(tmp_path: Path) -> None:
    verbatim = DRAFT.model_copy(
        update={
            "paragraphs": [
                *DRAFT.paragraphs[:1],
                paragraph("{{f:audit.process_sections}}", "audit.process_sections", kind="bullet"),
                *DRAFT.paragraphs[2:],
            ]
        }
    )

    ws = Workspace(tmp_path / "ws")
    provider, accepted = run(ws, passage_job(ws), [verbatim, DRAFT])

    assert accepted == DRAFT
    assert [
        (error["rule"], error["rule_text"], error["location"], error["detail"])
        for error in provider.requests[1]["errors"]
    ] == [
        (
            "passage_verbatim",
            rule_text("passage_verbatim"),
            "paragraph:1",
            "audit.process_sections",
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
    # The general lead-in's two sentences, then a cited bullet for each passage.
    assert (check.cited_sentences, check.total_sentences) == (3, 5)
