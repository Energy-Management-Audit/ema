"""Synthetic Draft v2 request, checker retry, and runtime style redaction."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from tests.audit_replay import CH2_DRAFT, audit_job_with_facts

from ema.audit.draft_agent import FACT_RULE, SENTENCE_RULE, draft_section_run
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.draft_style import style_example
from ema.core.errors import EmaError
from ema.core.llm.models import default_model
from ema.core.llm.types import Exchange
from ema.core.workspace import Workspace

SECTION = "ch2.date_generale"


class DraftProvider:
    name = "openai"

    def __init__(self, drafts: list[SectionDraft]) -> None:
        self.drafts = drafts
        self.requests: list[dict[str, Any]] = []

    def respond(self, *args: Any, **kwargs: Any) -> Exchange:
        messages = args[1]
        self.requests.append(json.loads(messages[1]["content"]))
        return Exchange(self.drafts.pop(0).model_dump_json(), (), 1, 1)


class SupportProvider:
    name = "openai"

    def __init__(self, response: str = '{"flags": []}') -> None:
        self.response = response
        self.calls = 0

    def respond(self, *args: Any, **kwargs: Any) -> Exchange:
        self.calls += 1
        return Exchange(self.response, (), 1, 1)


def _run(
    tmp_path: Path, drafts: list[SectionDraft]
) -> tuple[DraftProvider, SupportProvider, SectionDraft]:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    provider = DraftProvider(drafts)
    support = SupportProvider()
    _, accepted, _, _ = draft_section_run(
        ws,
        job,
        SECTION,
        provider,
        support,
        model_id=default_model("openai").id,
        synthetic=True,
    )
    return provider, support, accepted


def test_accepted_draft_uses_one_structured_call(tmp_path: Path) -> None:
    provider, support, accepted = _run(tmp_path, [CH2_DRAFT])
    assert accepted == CH2_DRAFT
    assert len(provider.requests) == 1
    assert support.calls == 1
    assert FACT_RULE in provider.requests[0]["task"]
    assert provider.requests[0]["task"].startswith(f"Redactează secţiunea {SECTION}")


def test_literal_name_retry_carries_rule(tmp_path: Path) -> None:
    invalid = SectionDraft(
        section=SECTION,
        status="drafted",
        paragraphs=[DraftText(text="Atelier Exemplu are activitate.")],
    )
    provider, support, accepted = _run(tmp_path, [invalid, CH2_DRAFT])
    assert accepted == CH2_DRAFT
    assert len(provider.requests) == 2
    assert support.calls == 1
    rules = {(error["rule"], error["rule_text"]) for error in provider.requests[1]["errors"]}
    assert rules == {("literal_name", FACT_RULE), ("uncited_sentence", SENTENCE_RULE)}
    assert FACT_RULE in json.loads(provider.requests[1]["request"])["task"]


def test_second_fatal_draft_stops_after_two_calls(tmp_path: Path) -> None:
    invalid = SectionDraft(
        section=SECTION, status="drafted", paragraphs=[DraftText(text="Atelier Exemplu.")]
    )
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    provider, support = DraftProvider([invalid, invalid]), SupportProvider()
    with pytest.raises(EmaError) as error:
        draft_section_run(
            ws, job, SECTION, provider, support, model_id=default_model("openai").id, synthetic=True
        )
    assert error.value.code == "draft_incomplete"
    assert len(provider.requests) == 2
    assert support.calls == 0


def test_bad_support_keeps_accepted_draft(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    provider = DraftProvider([CH2_DRAFT])
    support = SupportProvider(
        '{"flags": [{"location": "elsewhere", "sentence": "x", "reason": "x"}]}'
    )
    _, accepted, _, flags = draft_section_run(
        ws, job, SECTION, provider, support, model_id=default_model("openai").id, synthetic=True
    )
    assert accepted == CH2_DRAFT
    assert [(flag.code, flag.location, flag.detail) for flag in flags] == [
        ("support_unavailable", "section", "support_invalid")
    ]
    assert len(provider.requests) == support.calls == 1


@pytest.mark.parametrize(
    "sentence",
    [
        "{{f:audit.company_name}} are",
        "Societatea {{f:audit.company_name}} are {{f:audit.employees}} angajați",
        "Societatea  {{f:audit.company_name}} are {{f:audit.employees}} angajați.",
    ],
)
def test_support_accepts_paragraph_fragments(tmp_path: Path, sentence: str) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    support = SupportProvider(
        json.dumps(
            {"flags": [{"location": "paragraph:0", "sentence": sentence, "reason": "claim"}]}
        )
    )
    _, _, _, flags = draft_section_run(
        ws,
        job,
        SECTION,
        DraftProvider([CH2_DRAFT]),
        support,
        model_id=default_model("openai").id,
        synthetic=True,
    )
    assert [(flag.code, flag.sentence) for flag in flags] == [("unsupported", sentence)]


def test_support_accepts_two_sentences(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    draft = SectionDraft(
        section=SECTION,
        status="drafted",
        paragraphs=[
            DraftText(
                text=(
                    "Societatea {{f:audit.company_name}} există. "
                    "Are {{f:audit.employees}} angajați."
                ),
                fact_ids=["audit.company_name", "audit.employees"],
            )
        ],
    )
    sentence = "Societatea {{f:audit.company_name}} există. Are {{f:audit.employees}} angajați"
    support = SupportProvider(
        json.dumps(
            {"flags": [{"location": "paragraph:0", "sentence": sentence, "reason": "claim"}]}
        )
    )
    _, _, _, flags = draft_section_run(
        ws,
        job,
        SECTION,
        DraftProvider([draft]),
        support,
        model_id=default_model("openai").id,
        synthetic=True,
    )
    assert [(flag.code, flag.sentence) for flag in flags] == [("unsupported", sentence)]


def test_invalid_json_has_no_hidden_retry(tmp_path: Path) -> None:
    class InvalidProvider(DraftProvider):
        def respond(self, *args: Any, **kwargs: Any) -> Exchange:
            self.requests.append({})
            return Exchange("not json", (), 1, 1)

    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    provider, support = InvalidProvider([]), SupportProvider()
    with pytest.raises(EmaError) as error:
        draft_section_run(
            ws, job, SECTION, provider, support, model_id=default_model("openai").id, synthetic=True
        )
    assert error.value.code == "ai_schema"
    assert len(provider.requests) == 1
    assert support.calls == 0


def test_style_example_masks_identity_and_every_number(tmp_path: Path) -> None:
    base = tmp_path / "synthetic.docx"
    doc = Document()
    doc.add_paragraph("DESCRIEREA ȘI ISTORICUL SOCIETĂȚII", style="Heading 1")
    doc.add_paragraph("Date generale", style="Heading 2")
    doc.add_paragraph("Atelier Exemplu are 1.234 angajați în 2026.")
    doc.add_paragraph("Istoria companiei", style="Heading 2")
    doc.save(base)
    example = style_example(base, ("Atelier Exemplu",), SECTION)
    assert "Atelier Exemplu" not in example
    assert not re.search(r"\d", example)
    assert example.count("{{…}}") == 3


def test_style_example_masks_unlisted_names_variants_and_acronyms(tmp_path: Path) -> None:
    base = tmp_path / "synthetic.docx"
    doc = Document()
    doc.add_paragraph("DESCRIEREA ȘI ISTORICUL SOCIETĂȚII", style="Heading 1")
    doc.add_paragraph("Date generale", style="Heading 2")
    doc.add_paragraph(
        "Clientul Ştefan\nIonescu lucrează cu Ana Popescu în Brașov la ACME. "
        "În 2026-02-03 avea 12,5%."
    )
    doc.add_paragraph("Istoria companiei", style="Heading 2")
    doc.save(base)
    example = style_example(base, ("Ștefan Ionescu",), SECTION)
    for leaked in ("Ştefan", "Ionescu", "Ana", "Popescu", "Brașov", "ACME", "2026", "12,5"):
        assert leaked not in example
    assert example.count("{{…}}") >= 7


def test_provider_receives_only_redacted_base_example(tmp_path: Path, monkeypatch: Any) -> None:
    base = tmp_path / "synthetic.docx"
    doc = Document()
    doc.add_paragraph("DESCRIEREA ȘI ISTORICUL SOCIETĂȚII", style="Heading 1")
    doc.add_paragraph("Date generale", style="Heading 2")
    doc.add_paragraph("Atelier Exemplu avea 12 angajați în 2025.")
    doc.add_paragraph("Istoria companiei", style="Heading 2")
    doc.save(base)
    identity = tmp_path / "identity.json"
    identity.write_text(json.dumps(["Atelier Exemplu"]), encoding="utf-8")
    monkeypatch.setenv("EMA_AUDIT_BASE_DOCUMENT", str(base))
    monkeypatch.setenv("EMA_AUDIT_BASE_IDENTITY", str(identity))
    provider, _, _ = _run(tmp_path, [CH2_DRAFT])
    example = provider.requests[0]["style_example"]
    assert example
    assert "Atelier Exemplu" not in example
    assert not re.search(r"\d", example)


def test_preflight_refuses_before_draft_call(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.000001")
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    provider = DraftProvider([CH2_DRAFT])
    with pytest.raises(EmaError) as error:
        draft_section_run(
            ws,
            job,
            SECTION,
            provider,
            SupportProvider(),
            model_id=default_model("openai").id,
            synthetic=True,
        )
    assert error.value.code == "ai_budget"
    assert provider.requests == []
