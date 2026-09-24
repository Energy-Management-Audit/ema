"""S14 synthetic request-bound replay and structure comparison with auditor audits."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.oxml.ns import qn
from tests.golden.s14_structure import auditor_structure
from tests.golden.test_s10b_audit_base import _identity, _references

from ema.audit.base import build_base
from ema.audit.base_units import UnitPlan
from ema.audit.draft_agent import (
    INSTRUCTIONS,
    PROMPT_VERSION,
    DraftTools,
    draft_section_replay,
    recorded_facts,
)
from ema.audit.draft_checks import SUPPORT_PROMPT, SupportResult
from ema.audit.draft_render import render_draft_section, render_section
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.sections import get_status, refresh_staleness
from ema.core.jobs import create_job
from ema.core.llm import Limits
from ema.core.llm.replay import request_hashes
from ema.core.office.anchors import find, stamp
from ema.core.review.fields import propose
from ema.core.review.models import Evidence, Field, Manual
from ema.core.workspace import Workspace

pytestmark = pytest.mark.golden
MODEL = "gemini-3.6-flash"


def _recording(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text(
        json.dumps(
            {"source": "hand-authored", "format": "openai-chat-completions", "responses": rows},
            ensure_ascii=False,
        )
    )
    return path


def _draft_replay(ws: Workspace, job: str, draft: SectionDraft, path: Path) -> Path:
    tools = DraftTools(ws, job, draft.section)
    specs = tuple(tool.spec for tool in tools.tools().values())
    messages: list[dict[str, Any]] = [{"role": "system", "content": INSTRUCTIONS}]
    rows: list[dict[str, Any]] = []
    calls = [
        ("read_facts", {}),
        ("read_style_guide", {}),
        ("write_section_draft", draft.model_dump()),
    ]
    for index, (name, args) in enumerate(calls):
        rows.append(
            {
                "request_hashes": request_hashes(
                    MODEL, messages, specs, None, 4096, PROMPT_VERSION
                ),
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": str(index),
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(args, ensure_ascii=False),
                                    },
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        )
        result = tools.tools()[name].execute(args)
        messages.append(
            {
                "role": "assistant",
                "tool_calls": [{"id": str(index), "name": name, "arguments": args}],
            }
        )
        messages.append(
            {"role": "tool", "name": name, "tool_call_id": str(index), "content": result}
        )
    assert tools.draft is not None
    rows.append(
        {
            "request_hashes": request_hashes(MODEL, messages, specs, None, 4096, PROMPT_VERSION),
            "choices": [{"message": {"content": "Draft complete"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )
    return _recording(path, rows)


def _support_replay(
    ws: Workspace, job: str, draft: SectionDraft, path: Path, flagged: int | None
) -> Path:
    facts = recorded_facts(ws, job, draft.section)
    request = [
        {
            "location": f"paragraph:{index}",
            "text": paragraph.text,
            "facts": {key: str(facts[key].value) for key in paragraph.fact_ids},
        }
        for index, paragraph in enumerate(draft.paragraphs)
    ]
    content = json.dumps(request, ensure_ascii=False)
    messages = [
        {"role": "system", "content": SUPPORT_PROMPT},
        {"role": "user", "content": content},
    ]
    flags = (
        []
        if flagged is None
        else [
            {
                "location": f"paragraph:{flagged}",
                "sentence": draft.paragraphs[flagged].text,
                "reason": "The cited fact does not support a claim about efficiency.",
            }
        ]
    )
    row = {
        "request_hashes": request_hashes(
            MODEL,
            messages,
            (),
            SupportResult.model_json_schema(),
            4096,
            PROMPT_VERSION + "-support",
        ),
        "choices": [{"message": {"content": json.dumps({"flags": flags})}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    return _recording(path, [row])


def _base(tmp_path: Path) -> tuple[Path, Path]:
    base, anchors = tmp_path / "base.docx", tmp_path / "base.anchors.json"
    document = Document()
    slots = (
        ("ch2.date_generale", "company", "[de completat]"),
        ("ch2.date_generale", "claim", "[de completat]"),
        ("ch3.flux", "process", "[de completat]"),
    )
    records = []
    for index, (section, slot, text) in enumerate(slots, 1):
        paragraph = document.add_paragraph(text)
        stamp(paragraph._p, slot, index)
        records.append(
            {
                "slot": slot,
                "section": section,
                "classification": "variable",
                "part": "word/document.xml",
            }
        )
    document.save(str(base))
    anchors.write_text(json.dumps({"version": 1, "anchors": records}))
    return base, anchors


def test_synthetic_chapters_replay_render_and_compare(tmp_path: Path) -> None:
    reference = os.environ.get("EMA_REFERENCE")
    assert reference and Path(reference).is_dir(), "EMA_REFERENCE is required for this golden"
    structure = auditor_structure(Path(reference))
    assert len(structure) == 5
    assert all(item["sections"] for item in structure.values())
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    for key, value in (
        ("audit.company_name", "Atelier Exemplu"),
        ("audit.employees", 85),
        ("audit.process_sections", "asamblare"),
    ):
        evidence = Evidence(
            id="synthetic:" + key,
            provenance="manual",
            locator=Manual(who="synthetic"),
            method="manual",
            retrieved_at=datetime.now(UTC),
            highlight="exact",
        )
        propose(ws, job, key, value, [evidence], state="supplied")
    drafts = [
        SectionDraft(
            section="ch2.date_generale",
            status="drafted",
            paragraphs=[
                DraftText(
                    text="Societatea {{f:audit.company_name}} are {{f:audit.employees}} angajați.",
                    fact_ids=["audit.company_name", "audit.employees"],
                ),
                DraftText(
                    text=(
                        "Societatea {{f:audit.company_name}} utilizează "
                        "echipamente moderne, eficiente."
                    ),
                    fact_ids=["audit.company_name"],
                ),
            ],
        ),
        SectionDraft(
            section="ch3.flux",
            status="drafted",
            paragraphs=[
                DraftText(
                    text="Fluxul {{f:audit.process_sections}} este descris.",
                    fact_ids=["audit.process_sections"],
                )
            ],
        ),
    ]
    rejected = DraftTools(ws, job, "ch2.date_generale").write_section_draft(
        SectionDraft(
            section="ch2.date_generale",
            status="drafted",
            paragraphs=[
                DraftText(
                    text="Societatea {{f:audit.company_name}} are 99 angajați.",
                    fact_ids=["audit.company_name"],
                )
            ],
        ).model_dump()
    )
    assert rejected == {"accepted": False, "errors": ["literal_number"]}
    base, anchors = _base(tmp_path)
    rendered = base
    coverage = []
    for index, draft in enumerate(drafts):
        state, replayed, checked, flags = draft_section_replay(
            ws,
            job,
            draft.section,
            _draft_replay(ws, job, draft, tmp_path / f"draft-{index}.json"),
            _support_replay(
                ws, job, draft, tmp_path / f"support-{index}.json", 1 if index == 0 else None
            ),
            Limits(8),
        )
        assert state.status == "done" and not checked.fatal
        assert len(flags) == (1 if index == 0 else 0)
        coverage.append(checked.coverage)
        output = tmp_path / f"rendered-{index}.docx"
        render_draft_section(
            ws,
            job,
            rendered,
            anchors,
            output,
            draft=replayed,
            facts=recorded_facts(ws, job, draft.section),
            flags=flags,
        )
        review = json.loads(output.with_suffix(".draft-review.json").read_text())
        assert review["coverage"] == 1.0
        assert len(review["review"]) == (1 if index == 0 else 0)
        rendered = output
    texts = [p.text for p in Document(str(rendered)).paragraphs]
    assert "Atelier Exemplu" in texts[0] and "85" in texts[0]
    assert texts[1] == "[de completat]"  # unsupported prose withheld
    assert "asamblare" in texts[2]
    assert coverage == [1.0, 1.0]
    synthetic_structure = {
        draft.section: {"paragraphs": len(draft.paragraphs), "tables": len(draft.tables)}
        for draft in drafts
    }
    propose(
        ws,
        job,
        "audit.process_sections",
        "asamblare și ambalare",
        [
            Evidence(
                id="synthetic:process-update",
                provenance="manual",
                locator=Manual(who="synthetic"),
                method="manual",
                retrieved_at=datetime.now(UTC),
                highlight="exact",
            )
        ],
        state="supplied",
    )
    refresh_staleness(ws, job)
    assert get_status(ws, job, "ch3.flux").stale
    assert not get_status(ws, job, "ch2.date_generale").stale
    print(
        f"S14 synthetic: coverage={coverage}; support_flags=1; "
        f"comparator_audits={len(structure)}; evidence=level 1; "
        f"structure={json.dumps({'synthetic': synthetic_structure, 'auditor': structure})}"
    )


def test_synthetic_paragraph_in_auditor_base(tmp_path: Path) -> None:
    reference = os.environ.get("EMA_REFERENCE")
    assert reference and Path(reference).is_dir(), "EMA_REFERENCE is required for this golden"
    source, prototype = _references(Path(reference))
    base, output = tmp_path / "base.docx", tmp_path / "rendered.docx"
    build_base(
        UnitPlan("Atelier Exemplu", 1, frozenset({"electricity", "gas"}), 0, False, 0, 0),
        base_document=source,
        measurement_prototype=prototype,
        output=base,
        base_identity=_identity(source),
    )
    anchors = base.with_suffix(".anchors.json")
    mapping = json.loads(anchors.read_text())
    other_slot = next(
        item["slot"]
        for item in mapping["anchors"]
        if item["section"] == "ch3.flux" and item["classification"] == "variable"
    )
    before = find([Document(str(base)).element], other_slot)
    before_text = "".join(node.text or "" for node in before.iter(qn("w:t")))
    fact = {
        "audit.company_name": Field(
            id="synthetic",
            job_id="synthetic",
            key="audit.company_name",
            label="Company",
            value_type="text",
            value="Atelier Exemplu",
            state="supplied",
            presence="found",
            evidence=["synthetic-evidence"],
        )
    }
    draft = SectionDraft(
        section="ch2.date_generale",
        status="drafted",
        paragraphs=[
            DraftText(text="Societatea {{f:audit.company_name}}.", fact_ids=["audit.company_name"])
        ],
    )
    render_section(base, anchors, output, draft, fact, (), job="synthetic")
    after_document = Document(str(output))
    after = find([after_document.element], other_slot)
    assert "".join(node.text or "" for node in after.iter(qn("w:t"))) == before_text
    assert any(
        "Societatea Atelier Exemplu." in paragraph.text for paragraph in after_document.paragraphs
    )
