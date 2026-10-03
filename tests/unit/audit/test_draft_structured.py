"""Synthetic Draft v2 request, checker retry, and runtime style redaction."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from tests.audit_replay import CH2_DRAFT, audit_job_with_facts

from ema.audit.draft_agent import draft_section_run
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.draft_style import style_example
from ema.core.errors import EmaError
from ema.core.llm import Limits
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

    def respond(self, *args: Any, **kwargs: Any) -> Exchange:
        return Exchange('{"flags": []}', (), 1, 1)


def _run(tmp_path: Path, drafts: list[SectionDraft]) -> tuple[DraftProvider, SectionDraft]:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    provider = DraftProvider(drafts)
    _, accepted, _, _ = draft_section_run(
        ws,
        job,
        SECTION,
        provider,
        SupportProvider(),
        Limits(8),
        model_id=default_model("openai").id,
        synthetic=True,
    )
    return provider, accepted


def test_accepted_draft_uses_one_structured_call(tmp_path: Path) -> None:
    provider, accepted = _run(tmp_path, [CH2_DRAFT])
    assert accepted == CH2_DRAFT
    assert len(provider.requests) == 1
    assert provider.requests[0]["task"].startswith(f"Redactează secţiunea {SECTION}")


def test_literal_name_retry_carries_rule(tmp_path: Path) -> None:
    invalid = SectionDraft(
        section=SECTION,
        status="drafted",
        paragraphs=[DraftText(text="Atelier Exemplu are activitate.")],
    )
    provider, accepted = _run(tmp_path, [invalid, CH2_DRAFT])
    assert accepted == CH2_DRAFT
    assert len(provider.requests) == 2
    assert any(error["rule"] == "literal_name" for error in provider.requests[1]["errors"])


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
    provider, _ = _run(tmp_path, [CH2_DRAFT])
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
            Limits(8),
            model_id=default_model("openai").id,
            synthetic=True,
        )
    assert error.value.code == "ai_budget"
    assert provider.requests == []
